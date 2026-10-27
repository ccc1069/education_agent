"""PrivacyService: 数据导出 + 账户删除 + 同意管理。

设计:
- 数据导出: 异步任务,收集 users/learners/submissions/knowledge_states/events 等数据
- 账户删除: 30 天宽限期(pending -> scheduled -> executing -> completed)
  - 期间可撤销 -> cancelled
  - 执行时: 软删用户(is_active=False) + 物理删除 PII(email/name) + 保留学习数据用于合规
- 同意管理: 追加写,每次同意/撤回都新增一行
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    DataExportJobORM,
    EventORM,
    KnowledgeStateORM,
    LearnerORM,
    PrivacyConsentORM,
    PrivacyDeletionRequestORM,
    SubmissionORM,
    UserORM,
)
from repositories import (
    DataExportJobRepository,
    PrivacyConsentRepository,
    PrivacyDeletionRepository,
)

logger = logging.getLogger(__name__)

DELETION_GRACE_DAYS = 30

CONSENT_TYPES = {
    "analytics",  # 学习行为分析
    "llm_training",  # 数据用于训练 LLM
    "marketing",  # 营销推送
    "third_party_share",  # 第三方数据共享
}


class PrivacyService:
    """隐私数据管理: 导出 + 删除 + 同意。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.consent_repo = PrivacyConsentRepository(session)
        self.deletion_repo = PrivacyDeletionRepository(session)
        self.export_repo = DataExportJobRepository(session)

    # ---------- 同意管理 ----------

    async def set_consent(
        self,
        user_id: int,
        consent_type: str,
        granted: bool,
        ip: str = "",
        user_agent: str = "",
        consent_version: str = "1.0",
    ) -> dict[str, Any]:
        """设置某项同意(追加写)。"""
        if consent_type not in CONSENT_TYPES:
            raise ValueError(
                f"unknown consent_type={consent_type}, allowed={CONSENT_TYPES}"
            )
        record = PrivacyConsentORM(
            user_id=user_id,
            consent_type=consent_type,
            granted=granted,
            consent_version=consent_version,
            ip=ip,
            user_agent=user_agent,
        )
        self.session.add(record)
        await self.session.commit()
        logger.info(
            "consent_set: user=%d type=%s granted=%s", user_id, consent_type, granted
        )
        return self._consent_to_dict(record)

    async def get_consents(self, user_id: int) -> list[dict[str, Any]]:
        """获取用户所有同意的当前状态(每种取最新)。"""
        records = await self.consent_repo.list_user_consents(user_id)
        return [self._consent_to_dict(r) for r in records]

    async def get_consent_status(self, user_id: int) -> dict[str, bool]:
        """获取所有同意类型的当前状态(默认 False)。"""
        records = await self.consent_repo.list_user_consents(user_id)
        status = {t: False for t in CONSENT_TYPES}
        for r in records:
            status[r.consent_type] = r.granted
        return status

    # ---------- 数据导出 ----------

    async def request_export(self, user_id: int) -> dict[str, Any]:
        """创建数据导出任务(pending -> 立即同步执行 completed)。

        生产环境应改为异步(Celery),这里为简化直接同步生成 JSON。
        """
        job = DataExportJobORM(
            user_id=user_id,
            status="pending",
        )
        self.session.add(job)
        await self.session.flush()

        # 同步生成导出数据(生产应改为异步任务)
        try:
            data = await self._collect_user_data(user_id)
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            job.download_url = f"/api/v1/privacy/export/{job.id}/download"
            # 估算大小: 数据字典序列化后的字节数(粗略)
            import json

            job.file_size_bytes = len(json.dumps(data, default=str).encode("utf-8"))
            job.metadata_ = {"data_keys": list(data.keys())}
            await self.session.commit()
            logger.info("export_completed: user=%d job=%d bytes=%d", user_id, job.id, job.file_size_bytes)
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)[:500]
            await self.session.commit()
            logger.error("export_failed: user=%d job=%d err=%s", user_id, job.id, e)
            raise

        return self._export_to_dict(job)

    async def get_export_job(self, job_id: int, user_id: int) -> dict[str, Any] | None:
        """获取导出任务详情(校验用户归属)。"""
        job = await self.export_repo.get_by_id(job_id)
        if job is None or job.user_id != user_id:
            return None
        return self._export_to_dict(job)

    async def get_export_data(self, job_id: int, user_id: int) -> dict[str, Any] | None:
        """获取导出的实际数据(用户可下载)。"""
        job = await self.export_repo.get_by_id(job_id)
        if job is None or job.user_id != user_id:
            return None
        if job.status != "completed":
            return None
        return await self._collect_user_data(user_id)

    async def list_export_jobs(self, user_id: int) -> list[dict[str, Any]]:
        jobs = await self.export_repo.list_by_user(user_id)
        return [self._export_to_dict(j) for j in jobs]

    async def _collect_user_data(self, user_id: int) -> dict[str, Any]:
        """收集用户全部数据(GDPR/PIPL 数据可携带权)。"""
        # 用户基础信息
        user_result = await self.session.execute(
            select(UserORM).where(UserORM.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if user is None:
            raise ValueError(f"User {user_id} not found")

        user_data = {
            "id": user.id,
            "email": user.email,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }

        # learner 信息
        learner_data: dict[str, Any] = {}
        if user.learner_id:
            learner_result = await self.session.execute(
                select(LearnerORM).where(LearnerORM.id == user.learner_id)
            )
            learner = learner_result.scalar_one_or_none()
            if learner:
                learner_data = {
                    "public_id": learner.public_id,
                    "name": learner.name,
                    "profile": learner.profile or {},
                    "created_at": learner.created_at.isoformat() if learner.created_at else None,
                }

        # 知识掌握状态
        ks_data: list[dict[str, Any]] = []
        if user.learner_id:
            ks_result = await self.session.execute(
                select(KnowledgeStateORM).where(
                    KnowledgeStateORM.learner_id == user.learner_id
                )
            )
            for ks in ks_result.scalars().all():
                ks_data.append(
                    {
                        "knowledge_id": ks.knowledge_id,
                        "mastery": ks.mastery,
                        "attempts": ks.attempts,
                        "correct_count": ks.correct_count,
                        "streak": ks.streak,
                        "last_attempt": ks.last_attempt.isoformat() if ks.last_attempt else None,
                    }
                )

        # 答题记录
        sub_data: list[dict[str, Any]] = []
        if user.learner_id:
            sub_result = await self.session.execute(
                select(SubmissionORM).where(SubmissionORM.learner_id == user.learner_id)
            )
            for s in sub_result.scalars().all():
                sub_data.append(
                    {
                        "knowledge_id": s.knowledge_id,
                        "is_correct": s.is_correct,
                        "time_spent_seconds": s.time_spent_seconds,
                        "created_at": s.created_at.isoformat() if s.created_at else None,
                    }
                )

        # 同意历史
        consents = await self.consent_repo.list_user_consents(user_id)
        consent_data = [self._consent_to_dict(c) for c in consents]

        # 删除请求历史
        del_result = await self.session.execute(
            select(PrivacyDeletionRequestORM).where(
                PrivacyDeletionRequestORM.user_id == user_id
            )
        )
        deletion_data = [
            self._deletion_to_dict(d) for d in del_result.scalars().all()
        ]

        return {
            "user": user_data,
            "learner": learner_data,
            "knowledge_states": ks_data,
            "submissions": sub_data,
            "consents": consent_data,
            "deletion_requests": deletion_data,
            "exported_at": datetime.utcnow().isoformat(),
        }

    # ---------- 账户删除 ----------

    async def request_deletion(
        self, user_id: int, reason: str = ""
    ) -> dict[str, Any]:
        """提交账户删除请求(30 天宽限期)。

        - 若已有 pending/scheduled 请求,返回已存在
        - scheduled_at = now + 30 天
        """
        existing = await self.deletion_repo.get_active_by_user(user_id)
        if existing is not None:
            return self._deletion_to_dict(existing)

        now = datetime.utcnow()
        req = PrivacyDeletionRequestORM(
            user_id=user_id,
            status="pending",
            requested_at=now,
            scheduled_at=now + timedelta(days=DELETION_GRACE_DAYS),
            reason=reason,
        )
        self.session.add(req)
        await self.session.commit()
        logger.info("deletion_requested: user=%d scheduled_at=%s", user_id, req.scheduled_at)
        return self._deletion_to_dict(req)

    async def cancel_deletion(self, user_id: int) -> dict[str, Any] | None:
        """撤销删除请求(宽限期内)。"""
        req = await self.deletion_repo.get_active_by_user(user_id)
        if req is None:
            return None
        if req.status not in ("pending", "scheduled"):
            raise ValueError(
                f"cannot cancel deletion in status={req.status}"
            )
        req.status = "cancelled"
        req.cancelled_at = datetime.utcnow()
        await self.session.commit()
        logger.info("deletion_cancelled: user=%d req=%d", user_id, req.id)
        return self._deletion_to_dict(req)

    async def get_deletion_request(self, user_id: int) -> dict[str, Any] | None:
        req = await self.deletion_repo.get_active_by_user(user_id)
        return self._deletion_to_dict(req) if req else None

    async def execute_deletion(self, user_id: int) -> dict[str, Any]:
        """执行账户删除(软删 + PII 物理删除)。

        生产环境应由定时任务调用(扫描 scheduled_at <= now 的 pending 请求)。
        这里同步执行,用于测试与手动触发。

        删除范围:
        - users: is_active=False, email="[deleted]@removed", password_hash="x"
        - learners: name="[deleted]", profile={}
        - 保留: submissions/knowledge_states/events(用于合规审计)
        """
        req = await self.deletion_repo.get_active_by_user(user_id)
        if req is None:
            raise ValueError(f"no active deletion request for user={user_id}")

        # 1. 软删用户
        await self.session.execute(
            update(UserORM)
            .where(UserORM.id == user_id)
            .values(
                is_active=False,
                email=f"[deleted:{user_id}]@removed",
                password_hash="x",
                failed_login_count=0,
            )
        )

        # 2. 软删 learner PII
        user_result = await self.session.execute(
            select(UserORM).where(UserORM.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if user and user.learner_id:
            await self.session.execute(
                update(LearnerORM)
                .where(LearnerORM.id == user.learner_id)
                .values(name="[deleted]", profile={})
            )

        # 3. 更新请求状态
        req.status = "completed"
        req.completed_at = datetime.utcnow()
        await self.session.commit()
        logger.warning("user_deleted: user=%d req=%d", user_id, req.id)
        return self._deletion_to_dict(req)

    # ---------- 内部转换 ----------

    def _consent_to_dict(self, c: PrivacyConsentORM) -> dict[str, Any]:
        return {
            "id": c.id,
            "user_id": c.user_id,
            "consent_type": c.consent_type,
            "granted": c.granted,
            "consent_version": c.consent_version,
            "ip": c.ip,
            "user_agent": c.user_agent,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }

    def _deletion_to_dict(self, d: PrivacyDeletionRequestORM) -> dict[str, Any]:
        return {
            "id": d.id,
            "user_id": d.user_id,
            "status": d.status,
            "requested_at": d.requested_at.isoformat() if d.requested_at else None,
            "scheduled_at": d.scheduled_at.isoformat() if d.scheduled_at else None,
            "completed_at": d.completed_at.isoformat() if d.completed_at else None,
            "cancelled_at": d.cancelled_at.isoformat() if d.cancelled_at else None,
            "reason": d.reason,
        }

    def _export_to_dict(self, j: DataExportJobORM) -> dict[str, Any]:
        return {
            "id": j.id,
            "user_id": j.user_id,
            "status": j.status,
            "requested_at": j.requested_at.isoformat() if j.requested_at else None,
            "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            "download_url": j.download_url,
            "file_size_bytes": j.file_size_bytes,
            "error_message": j.error_message,
            "metadata": j.metadata_ or {},
        }
