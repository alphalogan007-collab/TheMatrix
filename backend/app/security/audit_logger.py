"""
Audit Logger — Append-only audit log for all sensitive system events.

Security properties:
- Append-only (no updates, no deletes via normal API)
- Every entry includes actor, action, resource, outcome, timestamp
- Sensitive values are never logged raw (tokens, passwords, screenshots)
- Request/trace IDs for correlation
- Production: route to WORM storage or append-only external log service

Events logged:
- login, logout, token refresh
- blueprint updates, approvals, releases
- identity instance creation
- advice generation
- screen guardian activation
- screenshot checks
- permission changes
- failed authorization
- suspicious requests
- provider errors
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import structlog

log = structlog.get_logger()


class AuditAction(str, Enum):
    # Auth
    USER_REGISTER = "user.register"
    USER_LOGIN = "user.login"
    USER_LOGIN_FAILED = "user.login_failed"
    USER_LOGOUT = "user.logout"
    TOKEN_REFRESH = "token.refresh"
    TOKEN_REVOKED = "token.revoked"
    SESSION_CREATED = "session.created"
    SESSION_REVOKED = "session.revoked"

    # Identity
    IDENTITY_INSTANCE_CREATED = "identity.instance.created"
    IDENTITY_INSTANCE_ACCESSED = "identity.instance.accessed"

    # Advice
    ADVICE_GENERATED = "advice.generated"
    ADVICE_BLOCKED = "advice.blocked"

    # Screen Guardian
    SCREEN_CHECK_TEXT = "screen.check.text"
    SCREEN_CHECK_SCREENSHOT = "screen.check.screenshot"
    SCREEN_GUARDIAN_ACTIVATED = "screen.guardian.activated"

    # Blueprint
    BLUEPRINT_DRAFT_CREATED = "blueprint.draft.created"
    BLUEPRINT_VALIDATED = "blueprint.validated"
    BLUEPRINT_APPROVED = "blueprint.approved"
    BLUEPRINT_RELEASED = "blueprint.released"
    BLUEPRINT_FROZEN = "blueprint.frozen"
    BLUEPRINT_CHECKSUM_FAILED = "blueprint.checksum_failed"

    # Security
    AUTH_FAILED = "auth.failed"
    AUTHZ_FAILED = "authz.failed"
    INJECTION_DETECTED = "security.injection_detected"
    RATE_LIMIT_HIT = "security.rate_limit"
    SUSPICIOUS_REQUEST = "security.suspicious_request"

    # Admin
    ADMIN_ACTION = "admin.action"
    CONSENT_UPDATED = "consent.updated"


class AuditOutcome(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    BLOCKED = "BLOCKED"
    WARNING = "WARNING"


async def write_audit_log(
    db: Any,
    action: AuditAction,
    outcome: AuditOutcome,
    actor_user_id: Optional[str] = None,
    actor_type: str = "user",
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    request_id: Optional[str] = None,
    ip_hash: Optional[str] = None,
    user_agent_hash: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """
    Write an immutable audit log entry.

    metadata must be pre-redacted — never include tokens, passwords,
    raw screenshots, or private message content.
    """
    from app.models.audit_log import AuditLog

    # Sanitize metadata — never log secrets
    safe_metadata = _sanitize_metadata(metadata or {})

    entry = AuditLog(
        audit_id=f"aud_{uuid.uuid4().hex}",
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        action=action.value,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        ip_hash=ip_hash,
        user_agent_hash=user_agent_hash,
        outcome=outcome.value,
        metadata_redacted=safe_metadata,
        created_at=datetime.now(timezone.utc),
    )

    db.add(entry)
    await db.commit()

    # Also log to structured log for SIEM forwarding
    log.info(
        "audit_event",
        audit_id=entry.audit_id,
        action=action.value,
        outcome=outcome.value,
        actor_user_id=actor_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
    )


_SENSITIVE_KEYS = {
    "password", "token", "secret", "key", "authorization",
    "screenshot", "raw_image", "transcript", "private",
}


def _sanitize_metadata(metadata: dict) -> dict:
    """Remove or redact sensitive keys from metadata before logging."""
    return {
        k: "[REDACTED]" if any(s in k.lower() for s in _SENSITIVE_KEYS) else v
        for k, v in metadata.items()
    }
