"""Consent management routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlmodel import select

from app.db.session import AsyncSessionDep
from app.dependencies import CurrentUser
from app.models.user_consent import UserConsent
from app.security.audit_logger import AuditAction, AuditOutcome, write_audit_log

router = APIRouter()


class ConsentOut(BaseModel):
    data_processing: bool
    screen_guardian: bool
    local_memory: bool
    analytics: bool
    research: bool
    updated_at: str | None


class ConsentIn(BaseModel):
    data_processing: bool | None = None
    screen_guardian: bool | None = None
    local_memory: bool | None = None
    analytics: bool | None = None
    research: bool | None = None


@router.get("/consent", response_model=ConsentOut)
async def get_consent(current_user: CurrentUser, db: AsyncSessionDep) -> ConsentOut:
    result = await db.execute(select(UserConsent).where(UserConsent.user_id == current_user.user_id))
    consent = result.scalar_one_or_none()
    if not consent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consent record not found.")
    return ConsentOut(
        data_processing=consent.data_processing,
        screen_guardian=consent.screen_guardian,
        local_memory=consent.local_memory,
        analytics=consent.analytics,
        research=consent.research,
        updated_at=consent.updated_at.isoformat() if consent.updated_at else None,
    )


@router.patch("/consent", response_model=ConsentOut)
async def update_consent(body: ConsentIn, current_user: CurrentUser, db: AsyncSessionDep) -> ConsentOut:
    result = await db.execute(select(UserConsent).where(UserConsent.user_id == current_user.user_id))
    consent = result.scalar_one_or_none()
    if not consent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Consent record not found.")

    if body.data_processing is not None:
        consent.data_processing = body.data_processing
    if body.screen_guardian is not None:
        consent.screen_guardian = body.screen_guardian
    if body.local_memory is not None:
        consent.local_memory = body.local_memory
    if body.analytics is not None:
        consent.analytics = body.analytics
    if body.research is not None:
        consent.research = body.research

    await db.commit()
    await db.refresh(consent)

    await write_audit_log(
        db=db,
        action=AuditAction.CONSENT_UPDATED,
        outcome=AuditOutcome.SUCCESS,
        actor_user_id=current_user.user_id,
        resource_type="user_consent",
        resource_id=consent.consent_id,
        metadata={
            "data_processing": consent.data_processing,
            "screen_guardian": consent.screen_guardian,
            "local_memory": consent.local_memory,
        },
    )

    return ConsentOut(
        data_processing=consent.data_processing,
        screen_guardian=consent.screen_guardian,
        local_memory=consent.local_memory,
        analytics=consent.analytics,
        research=consent.research,
        updated_at=consent.updated_at.isoformat() if consent.updated_at else None,
    )
