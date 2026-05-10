"""
FastAPI shared dependencies — injected via Depends()
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import Settings, get_settings
from app.db.session import AsyncSessionDep
from app.security.auth import TokenService
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=True)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: AsyncSessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    """
    Resolve the authenticated user from the JWT access token.
    NEVER accept user_id from request body — always derive from token.
    """
    token_service = TokenService(settings)
    user = await token_service.get_user_from_access_token(credentials.credentials, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive.",
        )
    return user


async def get_current_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require admin role. Raises 403 if user is not admin."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAdmin = Annotated[User, Depends(get_current_admin)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
