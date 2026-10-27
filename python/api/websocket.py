"""WebSocket 实时通信端点(带 JWT 鉴权 + 心跳 + 单连接 + 优雅关闭)。

连接方式:
    ws://host/ws/{learner_public_id}?token=JWT_ACCESS_TOKEN

设计:
- 客户端在 query string 中传 token
- 服务端校验 token 后接受连接
- 拒绝非本人连接(学生只能连自己的 WebSocket)
- 心跳: 服务端 60s 无消息则发 ping,客户端 10s 内必须回 pong,否则关闭(4001)
- 单用户单连接: 同 learner_public_id 新连接会踢掉旧连接(4002)
- 优雅关闭: 服务端 shutdown 时向所有连接发 1001 going_away

消息规范:
- 入站: {"action": "submit|question|message|pong", ...}
- 出站: {"type": "event|error|ping|ack", ...}
"""

import asyncio
import json
import logging
import time

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from auth.jwt import decode_access_token
from db.models import UserORM, UserRole

ws_router = APIRouter()
logger = logging.getLogger(__name__)

# 心跳相关常量(秒)
RECEIVE_TIMEOUT = 60  # 60s 无消息则发 ping
PONG_TIMEOUT = 10  # ping 后 10s 无响应则断开

# WebSocket 关闭码(应用自定义 4xxx)
CODE_HEARTBEAT_TIMEOUT = 4001
CODE_DUPLICATE_CONNECTION = 4002
CODE_SERVER_SHUTDOWN = 1001


class ConnectionManager:
    """WebSocket 连接管理器(单实例)。

    每个 learner_public_id 同时只能有一个活跃连接。
    新连接会踢掉旧连接(发 4002 关闭帧)。
    """

    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, learner_public_id: str, websocket: WebSocket) -> bool:
        """接受新连接。若该 learner 已有连接,先踢掉旧的。

        Returns:
            True 表示连接成功(旧的已被踢)。
        """
        old = self.active_connections.get(learner_public_id)
        if old is not None:
            try:
                await old.send_json(
                    {
                        "type": "error",
                        "code": "duplicate_connection",
                        "message": "Another connection took over",
                    }
                )
                await old.close(code=CODE_DUPLICATE_CONNECTION)
            except Exception:
                logger.warning(
                    "failed_to_kick_old_ws: learner=%s", learner_public_id
                )
            self.active_connections.pop(learner_public_id, None)
            _update_ws_gauge()

        await websocket.accept()
        self.active_connections[learner_public_id] = websocket
        _update_ws_gauge()
        logger.info("WebSocket connected: %s", learner_public_id)
        return True

    def disconnect(self, learner_public_id: str) -> None:
        removed = self.active_connections.pop(learner_public_id, None)
        if removed is not None:
            _update_ws_gauge()
            logger.info("WebSocket disconnected: %s", learner_public_id)

    async def send_to_learner(self, learner_public_id: str, data: dict) -> bool:
        """向指定 learner 发消息。返回是否成功投递(在线)。"""
        ws = self.active_connections.get(learner_public_id)
        if ws is None:
            return False
        try:
            await ws.send_json(data)
            return True
        except Exception:
            logger.warning(
                "ws_send_failed: learner=%s, removing stale connection",
                learner_public_id,
            )
            self.disconnect(learner_public_id)
            return False

    async def disconnect_all(
        self, code: int = CODE_SERVER_SHUTDOWN, reason: str = "server_shutdown"
    ) -> None:
        """服务端关闭时,向所有连接发关闭帧。"""
        conns = list(self.active_connections.items())
        self.active_connections.clear()
        _update_ws_gauge()
        for learner_public_id, ws in conns:
            try:
                await ws.close(code=code, reason=reason)
            except Exception:
                logger.warning(
                    "failed_to_close_ws_on_shutdown: learner=%s", learner_public_id
                )
        logger.info("ws_disconnect_all: count=%d", len(conns))


def _update_ws_gauge() -> None:
    """同步 WebSocket 连接数到 Prometheus(若可用)。"""
    try:
        from observability.metrics import ACTIVE_WS_CONNECTIONS

        ACTIVE_WS_CONNECTIONS.set(len(manager.active_connections))
    except ImportError:
        pass


manager = ConnectionManager()


async def _authenticate_ws(
    token: str, learner_public_id: str
) -> tuple[int, UserRole] | None:
    """校验 token 并确认用户对该 learner 有访问权。返回 (user_id, role)。"""
    token_data = decode_access_token(token)
    if token_data is None:
        return None

    # 延迟导入: 让测试 fixture 替换 db.base.AsyncSessionLocal 后能取到最新引用
    from db.base import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        from repositories import LearnerRepository

        result = await session.execute(select(UserORM).where(UserORM.id == token_data.user_id))
        user = result.scalar_one_or_none()
        if user is None or not user.is_active:
            return None

        if user.role == UserRole.STUDENT:
            # 学生只能连自己的 WS
            if user.learner_id is None:
                return None
            learner_repo = LearnerRepository(session)
            learner = await learner_repo.get_by_id(user.learner_id)
            if learner is None or learner.public_id != learner_public_id:
                return None
        # 教师/管理员可连任意(后续 P2 加班级权限校验)
        return user.id, user.role


async def _handle_action(
    orch, learner_public_id: str, data: dict
) -> list[dict] | None:
    """处理客户端 action,返回待回推的事件列表。"""
    action = data.get("action", "")

    if action == "pong":
        return []  # 心跳响应,无业务事件

    if action == "submit":
        events = await orch.submit_answer(
            learner_public_id,
            data.get("knowledge_id", ""),
            data.get("is_correct", False),
            data.get("time_spent_seconds", 0),
        )
    elif action == "question":
        events = await orch.ask_question(
            learner_public_id,
            data.get("knowledge_id", ""),
            data.get("question", ""),
            debate_mode=bool(data.get("debate_mode", False)),
        )
    elif action == "message":
        events = await orch.send_message(
            learner_public_id,
            data.get("message", ""),
            data.get("knowledge_id", "general"),
        )
    else:
        return None  # 未知 action

    return [
        {
            "event_type": e.type.value,
            "source": e.source,
            "data": e.data,
            "timestamp": e.timestamp.isoformat(),
        }
        for e in events[-10:]
    ]


@ws_router.websocket("/ws/{learner_public_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    learner_public_id: str,
    token: str = Query(default=""),
):
    """WebSocket 端点。token 通过 query 传递。"""
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    auth_result = await _authenticate_ws(token, learner_public_id)
    if auth_result is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(learner_public_id, websocket)

    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=RECEIVE_TIMEOUT
                )
            except asyncio.TimeoutError:
                # 60s 无消息,发 ping;再等 10s 无 pong 则断开
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
                try:
                    raw = await asyncio.wait_for(
                        websocket.receive_text(), timeout=PONG_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    await websocket.close(
                        code=CODE_HEARTBEAT_TIMEOUT, reason="heartbeat_timeout"
                    )
                    break
                # 收到任何消息都算存活,继续业务处理
                data = json.loads(raw)
                events = await _handle_action(
                    websocket.app.state.orchestrator, learner_public_id, data
                )
                if events is None:
                    await manager.send_to_learner(
                        learner_public_id,
                        {
                            "type": "error",
                            "code": "unknown_action",
                            "message": f"Unknown action: {data.get('action', '')}",
                        },
                    )
                else:
                    for event in events:
                        await manager.send_to_learner(
                            learner_public_id, {"type": "event", **event}
                        )
                continue

            # 正常收到消息
            data = json.loads(raw)
            events = await _handle_action(
                websocket.app.state.orchestrator, learner_public_id, data
            )
            if events is None:
                await manager.send_to_learner(
                    learner_public_id,
                    {
                        "type": "error",
                        "code": "unknown_action",
                        "message": f"Unknown action: {data.get('action', '')}",
                    },
                )
                continue
            for event in events:
                await manager.send_to_learner(
                    learner_public_id, {"type": "event", **event}
                )

    except WebSocketDisconnect:
        manager.disconnect(learner_public_id)
    except Exception:
        logger.exception("WebSocket error for learner %s", learner_public_id)
        manager.disconnect(learner_public_id)
