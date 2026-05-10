"""Database seeder — creates baseline admin user and active blueprint."""

from __future__ import annotations

import asyncio
import os

import structlog
from sqlmodel import select

from app.config import get_settings
from app.db.session import AsyncSessionLocal as async_session_factory
from app.models.blueprint import BlueprintStatus, CoreMindBlueprintRecord
from app.models.user import User
from app.models.user_consent import UserConsent
from app.security.password_service import hash_password

logger = structlog.get_logger(__name__)
settings = get_settings()


async def seed() -> None:
    async with async_session_factory() as db:
        # 1. Seed admin user
        admin_email = os.environ.get("SEED_ADMIN_EMAIL", "admin@mindai.local")
        admin_password = os.environ.get("SEED_ADMIN_PASSWORD", "ChangeMe_Seed_2024!")

        result = await db.execute(select(User).where(User.email == admin_email))
        existing = result.scalar_one_or_none()
        if not existing:
            admin_user = User(
                email=admin_email,
                hashed_password=hash_password(admin_password),
                is_active=True,
                is_admin=True,
                is_verified=True,
            )
            db.add(admin_user)
            await db.flush()

            consent = UserConsent(user_id=admin_user.user_id)
            db.add(consent)
            logger.info("seed.admin_user_created", email=admin_email)
        else:
            logger.info("seed.admin_user_already_exists", email=admin_email)
            admin_user = existing

        # 2. Seed active blueprint v1.0.0
        bp_result = await db.execute(
            select(CoreMindBlueprintRecord).where(CoreMindBlueprintRecord.version == "1.0.0")
        )
        existing_bp = bp_result.scalar_one_or_none()
        if not existing_bp:
            blueprint = CoreMindBlueprintRecord(
                version="1.0.0",
                description="MindAI v1 identity guidance blueprint — baseline release.",
                checksum="0000000000000000000000000000000000000000000000000000000000000000",
                signature="seed-placeholder",
                moral_kernel_version="1.0.0",
                fact_kernel_version="1.0.0",
                guidance_kernel_version="1.0.0",
                safety_kernel_version="1.0.0",
                status=BlueprintStatus.RELEASED.value,
                is_active=True,
            )
            db.add(blueprint)
            logger.info("seed.blueprint_created", version="1.0.0")
        else:
            logger.info("seed.blueprint_already_exists", version="1.0.0")

        await db.commit()
    logger.info("seed.complete")


if __name__ == "__main__":
    asyncio.run(seed())
