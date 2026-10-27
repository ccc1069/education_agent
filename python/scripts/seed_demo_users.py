"""种子脚本: 写入与前端演示账号一致的用户。

用法:
    cd python
    python -m scripts.seed_demo_users

账号(密码均为 demo123456):
    student@demo.com  学生
    teacher@demo.com  教师(同时绑定 learner，可体验学习主链路)
    admin@demo.com    管理员(同时绑定 learner，可体验学习主链路)
"""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth.password import hash_password  # noqa: E402
from db.base import AsyncSessionLocal, init_db  # noqa: E402
from db.models import LearnerORM, UserORM, UserRole  # noqa: E402
from repositories import UserRepository  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEMO_PASSWORD = "demo123456"
DEMO_USERS = (
    ("student@demo.com", UserRole.STUDENT, "李同学"),
    ("teacher@demo.com", UserRole.TEACHER, "王老师"),
    ("admin@demo.com", UserRole.ADMIN, "管理员"),
)


async def _ensure_learner(session, user: UserORM, name: str) -> str:
    """教职工也绑一个 learner，便于演示学习页。"""
    if user.learner_id is not None:
        result = await session.get(LearnerORM, user.learner_id)
        if result is not None:
            return result.public_id
    learner = LearnerORM(public_id=str(uuid.uuid4()), name=name)
    session.add(learner)
    await session.flush()
    user.learner_id = learner.id
    await session.flush()
    return learner.public_id


async def seed_demo_users() -> None:
    await init_db()
    password_hash = hash_password(DEMO_PASSWORD)

    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        for email, role, name in DEMO_USERS:
            existing = await repo.get_by_email(email)
            if existing is not None:
                if existing.learner_id is None:
                    public_id = await _ensure_learner(session, existing, name)
                    logger.info(
                        "已补绑 learner: %s (id=%d public_id=%s)",
                        email,
                        existing.id,
                        public_id,
                    )
                else:
                    logger.info(
                        "已存在,跳过: %s (id=%d role=%s)",
                        email,
                        existing.id,
                        existing.role.value,
                    )
                continue
            if role == UserRole.STUDENT:
                user, learner = await repo.create_student(email, password_hash, name)
                user.is_verified = True
                logger.info(
                    "已创建学生: id=%d email=%s learner=%s",
                    user.id,
                    email,
                    learner.public_id,
                )
            else:
                user = await repo.create_staff(email, password_hash, role, name)
                user.is_verified = True
                public_id = await _ensure_learner(session, user, name)
                logger.info(
                    "已创建职员: id=%d email=%s role=%s learner=%s",
                    user.id,
                    email,
                    role.value,
                    public_id,
                )
        await session.commit()
    logger.info("演示账号就绪,统一密码: %s", DEMO_PASSWORD)


def main() -> None:
    asyncio.run(seed_demo_users())


if __name__ == "__main__":
    main()
