"""PCE (Proficiency-Based Curriculum Engine) models.

Three tables:
  learner_profiles      — one row per user, static context (age, background…)
  learner_area_levels   — one row per (user, area), tracks current proficiency level
  learner_sessions      — append-only log of every lesson delivered
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

# ---------------------------------------------------------------------------
# Enums (stored as plain strings for portability)
# ---------------------------------------------------------------------------

RELIGION_BACKGROUNDS = [
    "islam", "christian", "jewish", "hindu", "buddhist", "secular", "unknown",
]

LEARNING_STYLES = ["story", "analysis", "visual", "mixed"]

LEARNING_AREAS = [
    "faith", "history", "science", "mind", "character", "language", "practical_life",
]

LESSON_SOURCES = ["chatgpt", "youtube", "both"]

# Levels 0–8
MIN_LEVEL = 0
MAX_LEVEL = 8


# ---------------------------------------------------------------------------
# LearnerProfile
# ---------------------------------------------------------------------------

class LearnerProfile(SQLModel, table=True):
    __tablename__ = "learner_profiles"

    id: str = Field(
        default_factory=lambda: f"lp_{uuid.uuid4().hex}",
        primary_key=True,
    )

    # Link to auth user (nullable so anonymous flows work)
    user_id: str = Field(index=True, unique=True)

    # Age drives depth limit gate
    age: int = Field(default=0)

    # Faith/worldview background — used to choose opening language
    religion_background: str = Field(default="unknown")

    # 0 = distressed, 5 = thriving
    emotional_condition: int = Field(default=3)

    # How the learner prefers to receive information
    learning_style: str = Field(default="mixed")

    # True if a parent / mentor is co-supervising
    parent_involved: bool = Field(default=False)

    # Free-text notes the system collects at Level 0 orientation
    orientation_notes: str = Field(
        default="",
        sa_column=sa.Column(sa.Text, nullable=False, server_default=""),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )


# ---------------------------------------------------------------------------
# LearnerAreaLevel
# ---------------------------------------------------------------------------

class LearnerAreaLevel(SQLModel, table=True):
    __tablename__ = "learner_area_levels"

    id: str = Field(
        default_factory=lambda: f"lal_{uuid.uuid4().hex}",
        primary_key=True,
    )

    user_id: str = Field(index=True)
    area: str = Field(index=True)          # one of LEARNING_AREAS

    # 0 (orientation) … 8 (teacher/guide)
    current_level: int = Field(default=0)

    # Total sessions completed at ANY level for this area
    session_count: int = Field(default=0)

    # Sessions completed at the CURRENT level (reset on level-up)
    sessions_at_level: int = Field(default=0)

    # Running average engagement score at current level (0.0–1.0)
    avg_engagement: float = Field(default=0.0)

    last_session_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    unlocked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )

    __table_args__ = (
        sa.UniqueConstraint("user_id", "area", name="uq_learner_area"),
    )


# ---------------------------------------------------------------------------
# LearnerSession
# ---------------------------------------------------------------------------

class LearnerSession(SQLModel, table=True):
    __tablename__ = "learner_sessions"

    id: str = Field(
        default_factory=lambda: f"ls_{uuid.uuid4().hex}",
        primary_key=True,
    )

    user_id: str = Field(index=True)
    area: str = Field(index=True)
    level: int = Field(default=0)
    source: str = Field(default="both")           # chatgpt / youtube / both

    # The prompt sent to ChatGPT (stored for audit/replay)
    prompt_used: str = Field(
        default="",
        sa_column=sa.Column(sa.Text, nullable=False, server_default=""),
    )

    # Short summary of what was delivered (first 500 chars of content)
    content_summary: str = Field(
        default="",
        sa_column=sa.Column(sa.Text, nullable=False, server_default=""),
    )

    # 0.0 = disengaged, 1.0 = highly engaged (set by thumbs feedback)
    engagement_score: float = Field(default=0.5)

    # True if this session pushed the learner to the next level
    level_up_triggered: bool = Field(default=False)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
