"""
Database session management.
Uses async SQLAlchemy + SQLModel with PostgreSQL.
"""

from __future__ import annotations

from typing import Annotated, AsyncGenerator, Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from app.config import get_settings

settings = get_settings()

# Engine is None when DATABASE_URL is not configured (Redis-only / Prophet mode)
engine = (
    create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
    )
    if settings.database_url
    else None
)

AsyncSessionLocal = (
    sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    if engine
    else None
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    if AsyncSessionLocal is None:
        raise RuntimeError("Database not configured (DATABASE_URL not set)")
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


AsyncSessionDep = Annotated[AsyncSession, Depends(get_db)]


async def create_all_tables() -> None:
    """Create all tables (use Alembic in production instead)."""
    if engine is None:
        return  # No DB configured — Redis-only / Prophet mode
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


# ---------------------------------------------------------------------------
# Query helpers — used by auth and authorization layers
# ---------------------------------------------------------------------------
async def get_user_by_id(db: AsyncSession, user_id: str) -> Optional[object]:
    from app.models.user import User
    result = await db.execute(select(User).where(User.user_id == user_id))
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[object]:
    from app.models.user import User
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_identity_instance_by_id(db: AsyncSession, instance_id: str) -> Optional[object]:
    from app.models.identity_instance import IdentityMindInstance
    result = await db.execute(
        select(IdentityMindInstance).where(
            IdentityMindInstance.instance_id == instance_id
        )
    )
    return result.scalar_one_or_none()


async def get_identity_instance_by_user(db: AsyncSession, user_id: str) -> Optional[object]:
    from app.models.identity_instance import IdentityMindInstance
    result = await db.execute(
        select(IdentityMindInstance).where(IdentityMindInstance.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_interaction_frame_by_id(db: AsyncSession, frame_id: str) -> Optional[object]:
    from app.models.interaction_frame import InteractionFrame
    result = await db.execute(
        select(InteractionFrame).where(InteractionFrame.frame_id == frame_id)
    )
    return result.scalar_one_or_none()


async def get_screen_frame_by_id(db: AsyncSession, frame_id: str) -> Optional[object]:
    from app.models.screen import ScreenFrame
    result = await db.execute(
        select(ScreenFrame).where(ScreenFrame.frame_id == frame_id)
    )
    return result.scalar_one_or_none()


async def get_active_blueprint(db: AsyncSession) -> Optional[object]:
    from app.models.blueprint import CoreMindBlueprintRecord
    result = await db.execute(
        select(CoreMindBlueprintRecord).where(CoreMindBlueprintRecord.is_active == True)  # noqa: E712
    )
    return result.scalar_one_or_none()
