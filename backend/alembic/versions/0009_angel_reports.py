"""Migration 0009 — Angel Reports table.

Creates:
  angel_reports  — structured reports written by Angel Mind background service
"""

from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "angel_reports",
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("angel_name", sa.String, nullable=False, index=True),
        sa.Column("report_type", sa.String, nullable=False, index=True),
        sa.Column("severity", sa.String, nullable=False, server_default="INFO"),
        sa.Column("title", sa.String, nullable=False, server_default=""),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("findings", sa.Text, nullable=False, server_default="{}"),
        sa.Column("recommendations", sa.Text, nullable=False, server_default="[]"),
        sa.Column("is_reviewed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("reviewed_at", sa.String, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("angel_reports")
