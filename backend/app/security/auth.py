"""
Authentication — JWT access tokens + refresh token rotation.

Security principles:
- Access tokens: short-lived (15 min default)
- Refresh tokens: rotated on every use
- Device sessions tracked
- Never accept user_id from client — derive from verified token
- Rate limit login endpoint
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.models.user import User


class TokenService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def create_access_token(self, user_id: str) -> str:
        """Create a short-lived JWT access token."""
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=self.settings.jwt_access_token_expire_minutes)
        payload = {
            "sub": user_id,
            "iat": now,
            "exp": expire,
            "type": "access",
            "jti": uuid.uuid4().hex,
        }
        return jwt.encode(
            payload,
            self.settings.secret_key,
            algorithm=self.settings.jwt_algorithm,
        )

    def create_refresh_token(self, user_id: str, device_session_id: str) -> str:
        """Create a refresh token bound to a device session."""
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=self.settings.jwt_refresh_token_expire_days)
        payload = {
            "sub": user_id,
            "iat": now,
            "exp": expire,
            "type": "refresh",
            "jti": uuid.uuid4().hex,
            "sid": device_session_id,
        }
        return jwt.encode(
            payload,
            self.settings.secret_key,
            algorithm=self.settings.jwt_algorithm,
        )

    def decode_token(self, token: str) -> Optional[dict]:
        """Decode and validate a JWT. Returns None on any error."""
        try:
            return jwt.decode(
                token,
                self.settings.secret_key,
                algorithms=[self.settings.jwt_algorithm],
            )
        except JWTError:
            return None

    async def get_user_from_access_token(
        self, token: str, db: AsyncSession
    ) -> Optional[User]:
        """Resolve the User from a validated access token."""
        from app.db.session import get_user_by_id

        payload = self.decode_token(token)
        if payload is None:
            return None
        if payload.get("type") != "access":
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        return await get_user_by_id(db, user_id)
