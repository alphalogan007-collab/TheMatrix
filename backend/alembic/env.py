"""Alembic env.py — async SQLModel migrations."""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool
from sqlmodel import SQLModel

# Import all models so their metadata is registered
from app.models.user import User  # noqa: F401
from app.models.device_session import DeviceSession, RefreshToken  # noqa: F401
from app.models.blueprint import CoreMindBlueprintRecord  # noqa: F401
from app.models.identity_instance import IdentityMindInstance, UserState  # noqa: F401
from app.models.interaction_frame import InteractionFrame, AdvisorResponse  # noqa: F401
from app.models.user_consent import UserConsent  # noqa: F401
from app.models.screen import ScreenFrame, ScreenGuardianVerdict  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.knowledge_pattern import KnowledgePattern  # noqa: F401
from app.models.feedback import Feedback  # noqa: F401
from app.models.admin import AdminGrant  # noqa: F401
from app.models.blueprint_content import BlueprintContentEntry  # noqa: F401
from app.models.pattern_candidate import PatternCandidate  # noqa: F401

import os

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url from environment variable if set
database_url = os.environ.get("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
