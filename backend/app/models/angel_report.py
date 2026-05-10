"""AngelReport — DB model for Angel Mind observation reports.

Each Angel Mind writes structured reports here as it runs its intelligence loop.
Reports are admin-only (founder access only via /angels/ endpoints).

Table: angel_reports
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class AngelReport(SQLModel, table=True):
    __tablename__ = "angel_reports"

    id: str = Field(
        default_factory=lambda: f"ar_{uuid.uuid4().hex}",
        primary_key=True,
    )

    # Which angel generated this report
    angel_name: str = Field(index=True)           # "michael", "gabriel", …

    # Report classification
    report_type: str = Field(index=True)          # "SECURITY_SCAN", "MISSION_STATUS", …
    severity: str = Field(default="INFO")          # "INFO", "WARNING", "CRITICAL"

    # Content
    title: str = Field(default="")
    summary: str = Field(
        default="",
        sa_column=sa.Column(sa.Text, nullable=False, server_default=""),
    )

    # Structured data (JSON text — keeps DB simple, no JSONB dependency needed)
    findings: str = Field(
        default="{}",
        sa_column=sa.Column(sa.Text, nullable=False, server_default="{}"),
    )
    recommendations: str = Field(
        default="[]",
        sa_column=sa.Column(sa.Text, nullable=False, server_default="[]"),
    )

    # Founder workflow
    is_reviewed: bool = Field(default=False)       # founder has read this report
    reviewed_at: str = Field(default="")           # ISO timestamp of review

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
