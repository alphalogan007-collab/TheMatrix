"""
Password Service — Secure password hashing with Argon2id.
Rate limiting and login attempt tracking is handled at the route level.
"""

from __future__ import annotations

from passlib.context import CryptContext

# Argon2id: memory-hard, resistant to GPU cracking
_ctx = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(plain: str) -> str:
    """Hash a password using Argon2id."""
    return _ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain password against its Argon2id hash."""
    return _ctx.verify(plain, hashed)
