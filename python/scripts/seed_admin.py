"""种子脚本: 创建初始管理员账号。

用法:
    cd python
    python -m scripts.seed_admin --email admin@example.com --password MySecret123

环境变量(优先级高于命令行):
    ADMIN_EMAIL
    ADMIN_PASSWORD
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auth.password import hash_password  # noqa: E402
from db.base import AsyncSessionLocal, init_db  # noqa: E402
from db.models import UserORM, UserRole  # noqa: E402
from repositories import UserRepository  # noqa: E402
from sqlalchemy import select  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def seed_admin(email: str, password: str) -> None:
    await init_db()

    async with AsyncSessionLocal() as session:
        repo = UserRepository(session)
        existing = await repo.get_by_email(email)
        if existing is not None:
            if existing.role == UserRole.ADMIN:
                logger.info("Admin already exists: %s (id=%d)", email, existing.id)
                return
            logger.error("Email %s already exists with non-admin role", email)
            sys.exit(1)

        password_hash = hash_password(password)
        user = UserORM(
            email=email,
            password_hash=password_hash,
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
        )
        session.add(user)
        await session.commit()
        logger.info("Admin created: id=%d email=%s", user.id, email)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed initial admin user")
    parser.add_argument("--email", default=os.environ.get("ADMIN_EMAIL"))
    parser.add_argument("--password", default=os.environ.get("ADMIN_PASSWORD"))
    args = parser.parse_args()

    if not args.email or not args.password:
        parser.error("Email and password are required (via args or ADMIN_EMAIL/ADMIN_PASSWORD env)")

    if len(args.password) < 8:
        parser.error("Password must be at least 8 characters")

    asyncio.run(seed_admin(args.email, args.password))


if __name__ == "__main__":
    main()
