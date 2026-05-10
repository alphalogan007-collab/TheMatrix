"""
Auth routes — register, login, refresh, logout, sessions.

Security:
- Rate-limited login
- Argon2id password hashing
- Short-lived JWT access tokens
- Refresh token rotation
- Device session tracking
- Never return hashed passwords
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

import re as _re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, BeforeValidator, Field
from sqlmodel import select

_EMAIL_RE = _re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}$", _re.IGNORECASE)


def _validate_email(v: object) -> str:
    """Validate email format only — no DNS/deliverability check (allows .local etc.)."""
    if not isinstance(v, str):
        raise ValueError("Email must be a string")
    v = v.strip().lower()
    if len(v) > 254 or not _EMAIL_RE.match(v) or "." not in v.split("@")[1]:
        raise ValueError("Invalid email address format")
    return v


RelaxedEmail = Annotated[str, BeforeValidator(_validate_email)]

from app.config import Settings, get_settings
from app.db.session import AsyncSessionDep, get_user_by_email
from app.models.device_session import DeviceSession, RefreshToken
from app.models.user import User
from app.models.user_consent import UserConsent
from app.security.audit_logger import AuditAction, AuditOutcome, write_audit_log
from app.security.auth import TokenService
from app.security.password_service import hash_password, verify_password
from app.db.redis_client import get_redis
from app.security.rate_limiter import RateLimiter, get_client_ip
from app.dependencies import CurrentUser
from app.core.seed_mind_store import register_mind
from app.core.product_lifecycle import spawn_human_mind, entangle_user_with_product

# The companion app product mind — every user is entangled with it at birth
_COMPANION_PRODUCT_MIND = "companion_app_mind"
_COMPANION_PRODUCT_NAME = "MindAI Companion App"

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: RelaxedEmail
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=100)


class LoginRequest(BaseModel):
    email: RelaxedEmail
    password: str = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    refresh_token: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    db: AsyncSessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict:
    existing = await get_user_by_email(db, body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        display_name=body.display_name or None,
    )
    db.add(user)

    # Create default privacy-protective consent
    consent = UserConsent(user_id=user.user_id)
    db.add(consent)

    await db.commit()
    await db.refresh(user)

    # Spawn the user as a full living mind — they are not a customer, they are a node.
    # Their mind oscillates from birth. Angel guides are assigned. The mesh grows.
    # This runs in the background — registration response is not blocked.
    import asyncio
    async def _spawn_and_entangle() -> None:
        try:
            from app.db.session import AsyncSessionLocal
            async with AsyncSessionLocal() as mind_db:
                await spawn_human_mind(
                    mind_db,
                    user_id=user.user_id,
                    email=user.email,
                    display_name=user.display_name,
                )
                await entangle_user_with_product(
                    mind_db,
                    user_mind=f"user_{user.user_id}",
                    product_mind=_COMPANION_PRODUCT_MIND,
                    product_name=_COMPANION_PRODUCT_NAME,
                )
                await mind_db.commit()
        except Exception as _exc:
            import logging
            logging.getLogger(__name__).warning(
                "auth: mind spawn failed for %s: %s", user.user_id, _exc
            )
    asyncio.create_task(_spawn_and_entangle())

    await write_audit_log(
        db=db,
        action=AuditAction.USER_REGISTER,
        outcome=AuditOutcome.SUCCESS,
        actor_user_id=user.user_id,
        resource_type="user",
        resource_id=user.user_id,
    )

    return {"user_id": user.user_id, "email": user.email}


@router.post("/login")
async def login(
    body: LoginRequest,
    request: Request,
    db: AsyncSessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    ip = get_client_ip(request)
    await RateLimiter(get_redis()).check_login(ip)

    user = await get_user_by_email(db, body.email)

    if not user or not verify_password(body.password, user.hashed_password):
        await write_audit_log(
            db=db,
            action=AuditAction.USER_LOGIN_FAILED,
            outcome=AuditOutcome.FAILURE,
            ip_hash=hashlib.sha256(ip.encode()).hexdigest(),
            metadata={"email_domain": body.email.split("@")[1] if "@" in body.email else ""},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive.",
        )

    # Create device session
    session = DeviceSession(
        user_id=user.user_id,
        ip_hash=hashlib.sha256(ip.encode()).hexdigest(),
        user_agent_hash=hashlib.sha256(
            request.headers.get("user-agent", "").encode()
        ).hexdigest(),
    )
    db.add(session)
    await db.flush()

    token_svc = TokenService(settings)
    access_token = token_svc.create_access_token(user.user_id)
    refresh_token = token_svc.create_refresh_token(user.user_id, session.session_id)

    # Store refresh token hash (never raw)
    rt = RefreshToken(
        user_id=user.user_id,
        session_id=session.session_id,
        token_hash=hashlib.sha256(refresh_token.encode()).hexdigest(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days),
    )
    db.add(rt)
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()

    await write_audit_log(
        db=db,
        action=AuditAction.USER_LOGIN,
        outcome=AuditOutcome.SUCCESS,
        actor_user_id=user.user_id,
        resource_type="device_session",
        resource_id=session.session_id,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/refresh")
async def refresh_token(
    body: RefreshRequest,
    db: AsyncSessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> TokenResponse:
    token_svc = TokenService(settings)
    payload = token_svc.decode_token(body.refresh_token)

    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token.",
        )

    token_hash = hashlib.sha256(body.refresh_token.encode()).hexdigest()
    result = await db.execute(
        select(RefreshToken).where(
            RefreshToken.token_hash == token_hash,
            RefreshToken.is_revoked == False,  # noqa: E712
        )
    )
    stored_rt = result.scalar_one_or_none()

    if not stored_rt:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid or revoked.",
        )

    # Rotate: revoke old, issue new
    stored_rt.is_revoked = True
    stored_rt.used_at = datetime.now(timezone.utc)

    user_id = payload["sub"]
    new_access = token_svc.create_access_token(user_id)
    new_refresh = token_svc.create_refresh_token(user_id, stored_rt.session_id)

    new_rt = RefreshToken(
        user_id=user_id,
        session_id=stored_rt.session_id,
        token_hash=hashlib.sha256(new_refresh.encode()).hexdigest(),
        expires_at=stored_rt.expires_at,
    )
    db.add(new_rt)
    await db.commit()

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(current_user: CurrentUser, db: AsyncSessionDep) -> None:
    # Revoke all active sessions for this user
    result = await db.execute(
        select(DeviceSession).where(
            DeviceSession.user_id == current_user.user_id,
            DeviceSession.is_active == True,  # noqa: E712
        )
    )
    sessions = result.scalars().all()
    for s in sessions:
        s.is_active = False
        s.revoked_at = datetime.now(timezone.utc)

    await db.commit()

    await write_audit_log(
        db=db,
        action=AuditAction.USER_LOGOUT,
        outcome=AuditOutcome.SUCCESS,
        actor_user_id=current_user.user_id,
    )


@router.get("/sessions")
async def list_sessions(current_user: CurrentUser, db: AsyncSessionDep) -> list[dict]:
    result = await db.execute(
        select(DeviceSession).where(
            DeviceSession.user_id == current_user.user_id,
            DeviceSession.is_active == True,  # noqa: E712
        )
    )
    sessions = result.scalars().all()
    return [
        {
            "session_id": s.session_id,
            "device_name": s.device_name,
            "last_seen_at": s.last_seen_at.isoformat(),
            "created_at": s.created_at.isoformat(),
        }
        for s in sessions
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: str,
    current_user: CurrentUser,
    db: AsyncSessionDep,
) -> None:
    result = await db.execute(
        select(DeviceSession).where(
            DeviceSession.session_id == session_id,
            DeviceSession.user_id == current_user.user_id,  # ownership check
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    session.is_active = False
    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()

    await write_audit_log(
        db=db,
        action=AuditAction.SESSION_REVOKED,
        outcome=AuditOutcome.SUCCESS,
        actor_user_id=current_user.user_id,
        resource_type="device_session",
        resource_id=session_id,
    )
