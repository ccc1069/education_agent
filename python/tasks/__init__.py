"""具体定时任务: P2#17。

每个任务都是 async callable,可被 SchedulerService 调度或手动触发。

任务列表:
- execute_pending_deletions: 扫描 scheduled_at<=now 的删除请求并执行
- send_review_reminders: 扫描 review_schedules.next_review<=now 的复习计划
- cleanup_expired_tokens: 删除过期 refresh_tokens
- generate_daily_stats: 每日学习统计(示例)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models import (
    AuditLogORM,
    PrivacyDeletionRequestORM,
    RefreshTokenORM,
    ReviewScheduleORM,
    SubmissionORM,
    UserORM,
)
from services import PrivacyService

logger = logging.getLogger(__name__)


async def execute_pending_deletions(
    session_factory: async_sessionmaker[AsyncSession],
    batch_size: int = 50,
) -> dict[str, Any]:
    """执行到期的账户删除请求。

    扫描 status=pending 且 scheduled_at<=now 的请求,逐个执行软删 + PII 物理删除。
    返回执行统计。
    """
    now = datetime.utcnow()
    executed: list[int] = []
    failed: list[dict[str, Any]] = []

    async with session_factory() as session:
        result = await session.execute(
            select(PrivacyDeletionRequestORM)
            .where(
                PrivacyDeletionRequestORM.status == "pending",
                PrivacyDeletionRequestORM.scheduled_at.is_not(None),
                PrivacyDeletionRequestORM.scheduled_at <= now,
            )
            .limit(batch_size)
        )
        due = list(result.scalars().all())

    logger.info("deletion_task: due_count=%d", len(due))

    for req in due:
        try:
            async with session_factory() as session:
                service = PrivacyService(session)
                result = await service.execute_deletion(req.user_id)
                executed.append(result["id"])
        except Exception as e:
            failed.append(
                {"request_id": req.id, "user_id": req.user_id, "error": str(e)}
            )
            logger.exception(
                "deletion_execute_failed: req=%d user=%d", req.id, req.user_id
            )

    return {
        "executed": executed,
        "failed": failed,
        "total_due": len(due),
    }


async def send_review_reminders(
    session_factory: async_sessionmaker[AsyncSession],
    batch_size: int = 200,
) -> dict[str, Any]:
    """扫描到期的复习计划,通过 NotificationService 推送提醒。

    流程:
    1. 查询到期的 ReviewSchedule + 对应 User(学生)
    2. 对每条调用 NotificationService.send(priority=1, channel=ws)
       - 频控: 同 user 1 小时内 5 条 -> 后续被 failed
       - 偏好: 受勿扰时段约束(priority=1<2,落入勿扰则 failed)
    3. 返回统计(delivered/failed/total)
    """
    from services import NotificationService

    now = datetime.utcnow()
    async with session_factory() as session:
        result = await session.execute(
            select(ReviewScheduleORM, UserORM)
            .join(UserORM, UserORM.learner_id == ReviewScheduleORM.learner_id)
            .where(
                ReviewScheduleORM.next_review <= now,
                UserORM.is_active.is_(True),
            )
            .limit(batch_size)
        )
        rows = result.all()

    logger.info("review_reminder_task: due_count=%d", len(rows))

    delivered = 0
    failed = 0
    reminders_meta: list[dict[str, Any]] = []
    for review, user in rows:
        overdue_hours = int((now - review.next_review).total_seconds() / 3600)
        try:
            async with session_factory() as session:
                service = NotificationService(session)
                notif = await service.send(
                    user_id=user.id,
                    type_="review_reminder",
                    title=f"复习提醒: {review.knowledge_id}",
                    body=f"已逾期 {overdue_hours} 小时,建议立即复习",
                    payload={
                        "knowledge_id": review.knowledge_id,
                        "next_review": review.next_review.isoformat(),
                        "overdue_hours": overdue_hours,
                    },
                    priority=1,
                    preferred_channel="ws",
                )
            if notif.status == "delivered":
                delivered += 1
            else:
                failed += 1
            reminders_meta.append(
                {
                    "user_id": user.id,
                    "knowledge_id": review.knowledge_id,
                    "notification_id": notif.id,
                    "status": notif.status,
                }
            )
        except Exception as e:
            failed += 1
            logger.exception(
                "review_reminder_dispatch_failed: user=%d knowledge=%s err=%s",
                user.id,
                review.knowledge_id,
                e,
            )

    return {
        "reminders_count": len(rows),
        "delivered_count": delivered,
        "failed_count": failed,
        "reminders": reminders_meta[:10],
    }


async def cleanup_expired_tokens(
    session_factory: async_sessionmaker[AsyncSession],
    days_old: int = 30,
) -> dict[str, Any]:
    """清理过期 refresh_tokens(已过期 N 天且已撤销)。

    保留近期 30 天用于审计,更老的物理删除。
    """
    cutoff = datetime.utcnow() - timedelta(days=days_old)
    async with session_factory() as session:
        result = await session.execute(
            delete(RefreshTokenORM)
            .where(
                RefreshTokenORM.expires_at < cutoff,
                RefreshTokenORM.revoked.is_(True),
            )
            .execution_options(synchronize_session=False)
        )
        deleted_count = result.rowcount or 0
        await session.commit()

    logger.info("token_cleanup_task: deleted=%d", deleted_count)
    return {"deleted_tokens": deleted_count, "cutoff": cutoff.isoformat()}


async def generate_daily_stats(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[str, Any]:
    """生成每日学习统计(用于运营看板)。

    统计:
    - 今日活跃学生数(有 submission)
    - 今日答题总数
    - 今日正确率
    - 累计审计日志数
    """
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    async with session_factory() as session:
        # 今日答题
        sub_result = await session.execute(
            select(
                SubmissionORM.learner_id,
                SubmissionORM.is_correct,
            ).where(
                SubmissionORM.created_at >= today_start,
                SubmissionORM.created_at < today_end,
            )
        )
        rows = sub_result.all()
        active_learners = {r[0] for r in rows}
        total_submissions = len(rows)
        correct = sum(1 for r in rows if r[1])
        accuracy = correct / total_submissions if total_submissions else 0.0

        # 累计审计日志
        from sqlalchemy import func

        audit_count_result = await session.execute(
            select(func.count(AuditLogORM.id))
        )
        total_audit_logs = audit_count_result.scalar_one()

    stats = {
        "date": today_start.date().isoformat(),
        "active_learners": len(active_learners),
        "total_submissions": total_submissions,
        "accuracy": round(accuracy, 4),
        "total_audit_logs": total_audit_logs,
        "generated_at": datetime.utcnow().isoformat(),
    }
    logger.info("daily_stats: %s", stats)
    return stats


# 任务注册表(供 API 路由查找)
TASK_REGISTRY: dict[str, dict[str, Any]] = {
    "execute_pending_deletions": {
        "func": execute_pending_deletions,
        "description": "执行到期的账户删除请求(扫描 scheduled_at<=now)",
        "category": "privacy",
    },
    "send_review_reminders": {
        "func": send_review_reminders,
        "description": "扫描到期的复习计划并生成提醒",
        "category": "engagement",
    },
    "cleanup_expired_tokens": {
        "func": cleanup_expired_tokens,
        "description": "清理过期且已撤销的 refresh_tokens",
        "category": "maintenance",
    },
    "generate_daily_stats": {
        "func": generate_daily_stats,
        "description": "生成每日学习统计",
        "category": "analytics",
    },
}


def get_task_names() -> list[str]:
    return list(TASK_REGISTRY.keys())


def get_task_func(name: str):
    entry = TASK_REGISTRY.get(name)
    if entry is None:
        return None
    return entry["func"]
