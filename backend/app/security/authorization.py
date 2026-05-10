"""
Object-Level Authorization — Every request verifies ownership.

NEVER trust user_id from request body.
ALWAYS derive user_id from verified access token.
Every object access checks: authenticated user owns the resource.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.user import User


async def assert_owns_identity_instance(
    db: AsyncSession, current_user: User, instance_id: str
) -> None:
    """Raise 403 if the identity instance does not belong to the current user."""
    from app.db.session import get_identity_instance_by_id

    instance = await get_identity_instance_by_id(db, instance_id)
    if instance is None or instance.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this identity instance.",
        )


async def assert_owns_interaction_frame(
    db: AsyncSession, current_user: User, frame_id: str
) -> None:
    """Raise 403 if the interaction frame does not belong to the current user."""
    from app.db.session import get_interaction_frame_by_id

    frame = await get_interaction_frame_by_id(db, frame_id)
    if frame is None or frame.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this interaction frame.",
        )


async def assert_owns_screen_frame(
    db: AsyncSession, current_user: User, frame_id: str
) -> None:
    """Raise 403 if the screen frame does not belong to the current user."""
    from app.db.session import get_screen_frame_by_id

    frame = await get_screen_frame_by_id(db, frame_id)
    if frame is None or frame.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this screen frame.",
        )
