"""User profile routes — PATCH /users/me, GET /users/me, GET /users/me/mind."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.db.session import AsyncSessionDep, get_user_by_id
from app.dependencies import CurrentUser
from app.security.audit_logger import AuditAction, AuditOutcome, write_audit_log

router = APIRouter()


class UserProfileOut(BaseModel):
    user_id: str
    email: str
    is_active: bool
    is_verified: bool
    created_at: str


class PatchProfileIn(BaseModel):
    email: EmailStr | None = None


@router.get("/me", response_model=UserProfileOut)
async def get_my_profile(current_user: CurrentUser, db: AsyncSessionDep) -> UserProfileOut:
    return UserProfileOut(
        user_id=current_user.user_id,
        email=current_user.email,
        is_active=current_user.is_active,
        is_verified=current_user.is_verified,
        created_at=current_user.created_at.isoformat(),
    )


@router.patch("/me", response_model=UserProfileOut)
async def patch_my_profile(
    body: PatchProfileIn,
    current_user: CurrentUser,
    db: AsyncSessionDep,
) -> UserProfileOut:
    user = await get_user_by_id(db, current_user.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if body.email and body.email != user.email:
        user.email = body.email
        user.is_verified = False

    await db.commit()
    await db.refresh(user)

    await write_audit_log(
        db=db,
        action=AuditAction.PROFILE_UPDATED,
        outcome=AuditOutcome.SUCCESS,
        actor_user_id=current_user.user_id,
        resource_type="user",
        resource_id=user.user_id,
    )

    return UserProfileOut(
        user_id=user.user_id,
        email=user.email,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at.isoformat(),
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(current_user: CurrentUser, db: AsyncSessionDep) -> None:
    user = await get_user_by_id(db, current_user.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    user.is_active = False
    await db.commit()

    await write_audit_log(
        db=db,
        action=AuditAction.ACCOUNT_DEACTIVATED,
        outcome=AuditOutcome.SUCCESS,
        actor_user_id=current_user.user_id,
        resource_type="user",
        resource_id=user.user_id,
    )


# ---------------------------------------------------------------------------
# User mind endpoints — the product IS the human mind
# ---------------------------------------------------------------------------

class MindEntryOut(BaseModel):
    id: str
    category: str
    title: str
    content: str
    tags: str
    claim_type: str
    version: int
    updated_at: str


class UserMindStateOut(BaseModel):
    mind_name: str
    soulmate_name: str
    identity_title: str
    identity_content: str
    open_gaps: int
    self_reflections: int
    wisdom_absorbed: int
    entangled_products: List[str]
    angel_guides: List[str]
    recent_reflections: List[MindEntryOut]
    open_gap_list: List[MindEntryOut]
    soulmate_insights: List[MindEntryOut]   # what the soulmate has written about you
    angel_insights: List[MindEntryOut]      # wisdom angels deposited into your mind
    is_alive: bool  # True if mind has been spawned
    # Self-editing / proposal loop
    confidence_score: float         # 0.0–1.0: how well the mind knows itself
    pending_proposals: int          # proposals not yet reviewed
    proposals: List[MindEntryOut]   # recent proposals (self + code)


@router.get("/me/mind", response_model=UserMindStateOut)
async def get_my_mind(current_user: CurrentUser, db: AsyncSessionDep) -> UserMindStateOut:
    """Return the current user's living mind state.

    This is the product: the user's own mind — its identity, its open questions,
    its self-reflections, its angel guides, its entanglement with the product.
    If the mind hasn't been spawned yet (legacy user), spawn it now.
    """
    from app.core.seed_mind_store import get_own_entries, MIND_BASE_REGISTRY
    from app.core.product_lifecycle import (
        spawn_human_mind, entangle_user_with_product, HUMAN_MIND_TAG,
    )
    from app.core.seed_mind_memory import (
        MISSION_PURPOSE, QUESTION_TO_EXPLORE, SELF_REFLECTION,
        WISDOM_EXTRACTED, REALITY_FRAMEWORK, MORAL_ROOT,
    )

    mind_name = f"user_{current_user.user_id}"
    _COMPANION = "companion_app_mind"
    _COMPANION_NAME = "MindAI Companion App"

    # Ensure mind exists — lazy spawn for users registered before this feature
    identity_entries = await get_own_entries(db, mind_name=mind_name, category=MISSION_PURPOSE, limit=1)
    if not identity_entries:
        await spawn_human_mind(
            db,
            user_id=current_user.user_id,
            email=current_user.email,
            display_name=getattr(current_user, "display_name", None),
        )
        await entangle_user_with_product(
            db,
            user_mind=mind_name,
            product_mind=_COMPANION,
            product_name=_COMPANION_NAME,
        )
        await db.commit()
        identity_entries = await get_own_entries(db, mind_name=mind_name, category=MISSION_PURPOSE, limit=1)

    identity = identity_entries[0] if identity_entries else None

    # Gather mind state — counts use dedicated queries so they are always accurate
    from sqlmodel import select, func
    from app.models.seed_mind_memory import SeedMindMemoryEntry

    async def _count(cat: str) -> int:
        r = await db.execute(
            select(func.count()).where(
                SeedMindMemoryEntry.mind_name == mind_name,
                SeedMindMemoryEntry.category == cat,
                SeedMindMemoryEntry.is_current == True,  # noqa: E712
            )
        )
        return r.scalar() or 0

    _all_gaps   = await get_own_entries(db, mind_name=mind_name, category=QUESTION_TO_EXPLORE, limit=50)
    # Filter internal self-test gaps AND resolved gaps — only show live user-facing gaps
    gaps        = [
        g for g in _all_gaps
        if not g.title.startswith("self_test:")
        and "resolved" not in (g.tags or "")
        and "gap_closed" not in (g.tags or "")
    ]
    reflections = await get_own_entries(db, mind_name=mind_name, category=SELF_REFLECTION,     limit=50)
    wisdom      = await get_own_entries(db, mind_name=mind_name, category=WISDOM_EXTRACTED,    limit=50)
    reality     = await get_own_entries(db, mind_name=mind_name, category=REALITY_FRAMEWORK,   limit=20)
    moral       = await get_own_entries(db, mind_name=mind_name, category=MORAL_ROOT,          limit=10)

    # Real counts — filter self_test and resolved from gap count
    gap_count        = len(gaps)

    # Reflection and wisdom: user mind + seed_mind base (user is not separate from it)
    async def _count_combined(cat: str, minds: list) -> int:
        r = await db.execute(
            select(func.count()).where(
                SeedMindMemoryEntry.mind_name.in_(minds),
                SeedMindMemoryEntry.category == cat,
                SeedMindMemoryEntry.is_current == True,  # noqa: E712
            )
        )
        return r.scalar() or 0

    _combined_minds = [mind_name, "seed_mind"]
    reflection_count = await _count_combined(SELF_REFLECTION, _combined_minds)
    wisdom_count     = await _count_combined(WISDOM_EXTRACTED, _combined_minds)

    # Confidence score: how well the mind knows itself
    total_entries_r = await db.execute(
        select(func.count()).where(
            SeedMindMemoryEntry.mind_name == mind_name,
            SeedMindMemoryEntry.is_current == True,  # noqa: E712
        )
    )
    total_entries = total_entries_r.scalar() or 0
    confidence_score = min(1.0, total_entries / 200)

    # Proposals: SELF_REFLECTION entries tagged 'proposal' or 'code_proposal'
    # Also include INDUCTION notifications about dev mind proposals
    all_proposals = [e for e in reflections if any(t in (e.tags or "") for t in ("proposal", "code_proposal"))]

    # Pending = proposals with no reviewed: INDUCTION yet
    from app.core.seed_mind_memory import INDUCTION
    inductions = await get_own_entries(db, mind_name=mind_name, category=INDUCTION, limit=500)
    reviewed_ids = {ind.title.split(":")[1] for ind in inductions if ind.title and ind.title.startswith("reviewed:")}
    pending_proposals_list = [p for p in all_proposals if p.id not in reviewed_ids]
    # Also count dev mind proposal notifications in founder's inbox
    proposal_notifications = [i for i in inductions if "proposal_notification" in (i.tags or "")]
    pending_proposal_count = len(pending_proposals_list)

    # For the proposals list: own proposals + incoming proposal notifications
    combined_proposals = all_proposals + [n for n in proposal_notifications if n not in all_proposals]

    # Entangled products — REALITY_FRAMEWORK entries with "entangled_with:" prefix
    entangled = [e.title.replace("entangled_with:", "") for e in reality if e.title.startswith("entangled_with:")]

    # Angel guides — REALITY_FRAMEWORK entries from angel task assignments
    # (written as "[guide:mind_name]" tasks — read from moral entries for now)
    guides = [e.title.replace("guide:", "") for e in moral if e.title.startswith("guide:")]
    # fallback: read from tasks
    if not guides:
        guides = ["gabriel", "kiraman_katibin", "raphael", "guardian"]

    def _entry_out(e: object) -> MindEntryOut:
        return MindEntryOut(
            id=str(e.id),
            category=e.category,
            title=e.title,
            content=e.content,
            tags=e.tags or "",
            claim_type=e.claim_type or "",
            version=e.version,
            updated_at=e.updated_at.isoformat() if e.updated_at else "",
        )

    # Soulmate insights — WISDOM_EXTRACTED entries written by soulmate mirror
    soulmate_wisdom = [e for e in wisdom if "soulmate_mirror" in (e.tags or "")]
    # Angel insights — WISDOM_EXTRACTED entries deposited by angel guides
    angel_wisdom = [e for e in wisdom if "angel_guide" in (e.tags or "") and "soulmate_mirror" not in (e.tags or "")]

    return UserMindStateOut(
        mind_name=mind_name,
        soulmate_name=f"{mind_name}_soulmate",
        identity_title=identity.title if identity else f"identity:{current_user.user_id}",
        identity_content=identity.content if identity else "",
        open_gaps=gap_count,
        self_reflections=reflection_count,
        wisdom_absorbed=wisdom_count,
        entangled_products=entangled or [_COMPANION],
        angel_guides=guides,
        recent_reflections=[_entry_out(e) for e in reflections[:5]],
        open_gap_list=[_entry_out(e) for e in gaps[:5]],
        soulmate_insights=[_entry_out(e) for e in soulmate_wisdom[:10]],
        angel_insights=[_entry_out(e) for e in angel_wisdom[:10]],
        is_alive=identity is not None,
        confidence_score=round(confidence_score, 3),
        pending_proposals=pending_proposal_count,
        proposals=[_entry_out(e) for e in combined_proposals[:10]],
    )


class FeedSignalIn(BaseModel):
    signal_title: str
    signal_content: str
    tags: Optional[str] = ""


@router.post("/me/mind/signal", status_code=status.HTTP_201_CREATED)
async def feed_mind_signal(
    body: FeedSignalIn,
    current_user: CurrentUser,
    db: AsyncSessionDep,
) -> dict:
    """Write a signal from this user's interaction into the product mind.

    Called after conversations, learning sessions, or significant interactions.
    The product mind accumulates signals across all users. Recurring patterns
    crystallize into capability minds — features born from genuine need.
    """
    from app.core.product_lifecycle import feed_user_signal_to_product

    user_mind = f"user_{current_user.user_id}"
    await feed_user_signal_to_product(
        db,
        user_mind=user_mind,
        product_mind="companion_app_mind",
        signal_title=body.signal_title[:80],
        signal_content=body.signal_content[:500],
        signal_tags=body.tags or "",
    )
    await db.commit()
    return {"ok": True, "fed_to": "companion_app_mind"}
