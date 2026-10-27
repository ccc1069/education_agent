"""FastAPI 应用入口。

启动方式:
    cd python/
    python -m api.main
    或
    uvicorn api.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.auth_routes import router as auth_router
from api.notification_routes import router as notification_router
from api.orchestrator import AgentOrchestrator
from api.privacy_routes import audit_router as audit_router
from api.privacy_routes import router as privacy_router
from api.question_routes import router as question_router
from api.rag_routes import router as rag_router
from api.routes import router
from api.task_routes import router as task_router
from api.teacher_routes import router as teacher_router
from api.tenant_routes import router as tenant_router
from api.vision_routes import router as vision_router
from api.websocket import manager as ws_manager, ws_router
from config.settings import settings
from core.rate_limiter import RateLimitMiddleware, reset_rate_limiter_for_test
from core.tenant_context import TenantMiddleware
from core.tenant_filter import install_tenant_filter
from db.base import close_db
from observability import (
    CorrelationIdMiddleware,
    MetricsMiddleware,
    configure_logging,
    configure_tracing,
    get_logger,
    health_check,
    instrument_app,
    liveness_check,
    metrics_handler,
    readiness_check,
)

# 必须在创建任何 logger 之前配置
configure_logging()
configure_tracing()

logger = get_logger(__name__)

orchestrator: AgentOrchestrator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global orchestrator
    orchestrator = AgentOrchestrator()
    await orchestrator.initialize()
    app.state.orchestrator = orchestrator
    logger.info("agent_orchestrator_started", agents=7)

    # 安装多租户行级隔离过滤(SQLAlchemy event listener)
    install_tenant_filter()
    logger.info("tenant_filter_installed")

    # 启动任务队列 + 调度器
    from core.scheduler import get_scheduler, set_scheduler_session_factory
    from core.task_queue import get_task_queue

    from db.base import AsyncSessionLocal

    set_scheduler_session_factory(AsyncSessionLocal)
    queue = get_task_queue()
    await queue.start()

    # 注册定时任务(cron 表达式,Asia/Shanghai)
    scheduler = get_scheduler()
    from tasks import (
        cleanup_expired_tokens,
        execute_pending_deletions,
        generate_daily_stats,
        send_review_reminders,
    )

    # 每小时扫描到期删除请求
    scheduler.register_interval(
        "execute_pending_deletions",
        execute_pending_deletions,
        seconds=3600,
    )
    # 每天 8 点(北京时间)发送复习提醒
    scheduler.register_cron(
        "send_review_reminders",
        send_review_reminders,
        cron_expr="0 8 * * *",
    )
    # 每天凌晨清理过期 token
    scheduler.register_cron(
        "cleanup_expired_tokens",
        cleanup_expired_tokens,
        cron_expr="0 3 * * *",
    )
    # 每天凌晨生成昨日统计
    scheduler.register_cron(
        "generate_daily_stats",
        generate_daily_stats,
        cron_expr="30 0 * * *",
    )
    scheduler.start()
    app.state.scheduler = scheduler
    app.state.task_queue = queue
    logger.info("task_scheduler_started", tasks=4)

    yield

    logger.info("agent_orchestrator_stopping")
    # 优雅停止: WebSocket 连接 -> 调度器 -> 队列 -> DB
    await ws_manager.disconnect_all()
    await scheduler.stop()
    await queue.stop()
    await close_db()
    logger.info("agent_orchestrator_stopped")


app = FastAPI(
    title="多Agent智能教育系统",
    description=(
        "Mesh+事件驱动个性化学习系统（Python 参考实现）。\n\n"
        "**核心 Agent：** Assessment / Tutor / Curriculum / Hint / Engagement\n"
        "**旁路 Agent：** Critic（LLM-as-judge）、Debate（debate_mode）\n\n"
        "**认证**: 业务接口需 Bearer JWT。注册/登录走 `/api/v1/auth/*`。\n"
        "**约定**: REST 以 GET/POST 为主（删除多为 POST `.../delete`）。\n\n"
        "**可观测性**: `/metrics` Prometheus, `/health` `/ready` `/live`。"
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# 中间件顺序: 后添加的先执行(洋葱模型)
# 1. CORS (最外层)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# 2. Correlation ID (在内层,所有日志都能拿到)
app.add_middleware(CorrelationIdMiddleware)
# 3. Tenant Context (在 Rate Limit 之前,便于按租户限流)
app.add_middleware(TenantMiddleware)
# 4. Rate Limit (在 Metrics 之前,被拒请求不进入业务统计)
app.add_middleware(RateLimitMiddleware)
# 5. Metrics (最内层,只统计业务请求)
app.add_middleware(MetricsMiddleware)

# OpenTelemetry instrumentation (tracing)
if settings.enable_tracing:
    instrument_app(app)

# ---------- 健康检查 + 指标端点(不走 /api/v1 前缀,便于 LB 直接探测) ----------


@app.get("/health", tags=["observability"])
async def health() -> dict:
    """综合健康检查: 包含所有子组件状态。"""
    return await health_check()


@app.get("/ready", tags=["observability"])
async def ready() -> JSONResponse:
    """就绪检查: 数据库 + LLM。失败时返回 503。"""
    result = await readiness_check()
    status_code = 200 if result["status"] == "up" else 503
    return JSONResponse(content=result, status_code=status_code)


@app.get("/live", tags=["observability"])
async def live() -> dict:
    """存活检查: 进程能响应即 up。"""
    return await liveness_check()


@app.get("/metrics", tags=["observability"])
async def metrics():
    """Prometheus 指标暴露端点。"""
    return metrics_handler()


# ---------- 业务路由 ----------

# 认证路由(公开: register/login/refresh)
app.include_router(auth_router, prefix="/api/v1")
# 业务路由(需认证)
app.include_router(router, prefix="/api/v1")
# RAG 知识库路由(需认证)
app.include_router(rag_router, prefix="/api/v1")
# 题目库路由(需认证)
app.include_router(question_router, prefix="/api/v1")
# 教师后台路由(班级 + 作业 + 看板)
app.include_router(teacher_router, prefix="/api/v1")
# 隐私合规路由(同意 + 导出 + 删除)
app.include_router(privacy_router, prefix="/api/v1")
# 审计日志路由(仅管理员)
app.include_router(audit_router, prefix="/api/v1")
# 任务调度管理路由(仅管理员)
app.include_router(task_router, prefix="/api/v1")
# 通知路由(本人)
app.include_router(notification_router, prefix="/api/v1")
# 租户管理路由(仅平台 ADMIN)
app.include_router(tenant_router, prefix="/api/v1")
# 视觉教学路由(P2#16c 多模态)
app.include_router(vision_router, prefix="/api/v1")
# WebSocket
app.include_router(ws_router)


if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=settings.api_port,
        reload=settings.is_dev,
    )
