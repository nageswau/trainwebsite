"""pob-019 (DEC-SCOPE-437 T1-T3, spec docs/superpowers/specs/2026-11-08-pob-019-candidate-tags-bulk-actions-design.md): a candidate's free
tags (from the rec-002 "Candidate tags" list) and the system tags derived on read.

Functions only; nothing here commits -- the route owns the transaction. The audit row carries tag ids only."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Candidate, CandidateTagLink, RecCandidateTag, User

INACTIVE = "Choose active candidate tags"
EXPERIENCE = (("Fresher", 0, 0), ("0–1 year", 1, 11), ("1–3 years", 12, 35), ("3–5 years", 36, 59), ("5+ years", 60, None))  # T3: F1 + Fresher


async def read(db: AsyncSession, candidate_ids: list[UUID]) -> dict[UUID, list[dict]]:
    """One query: each candidate's tags in list order (a deactivated tag on a candidate still shows, marked inactive)."""
    out: dict[UUID, list[dict]] = {i: [] for i in candidate_ids}
    if not candidate_ids:
        return out
    rows = await db.execute(
        select(CandidateTagLink.candidate_id, RecCandidateTag).join(RecCandidateTag, RecCandidateTag.id == CandidateTagLink.tag_id)
        .where(CandidateTagLink.candidate_id.in_(candidate_ids)).order_by(RecCandidateTag.sort_order, RecCandidateTag.name)
    )  # fmt: skip
    for candidate_id, t in rows.all():
        out[candidate_id].append({"id": t.id, "name": t.name, "active": t.active})
    return out


async def replace(db: AsyncSession, user: User, candidate: Candidate, tag_ids: list[UUID]) -> None:
    """T2: the whole set. A tag already on the candidate may stay though inactive; a newly added one must be an active tag (FOR SHARE, so a
    concurrent deactivation waits for this commit). Unknown and inactive are one 422."""
    current = set(await db.scalars(select(CandidateTagLink.tag_id).where(CandidateTagLink.candidate_id == candidate.id)))
    wanted = set(tag_ids)
    added, removed = [i for i in tag_ids if i not in current], sorted(current - wanted, key=str)
    if added:
        found = set(await db.scalars(
            select(RecCandidateTag.id).where(RecCandidateTag.id.in_(added), RecCandidateTag.active.is_(True)).with_for_update(read=True)
        ))  # fmt: skip
        if found != set(added):
            raise HTTPException(422, INACTIVE)
    if removed:
        await db.execute(delete(CandidateTagLink).where(CandidateTagLink.candidate_id == candidate.id, CandidateTagLink.tag_id.in_(removed)))
    db.add_all(CandidateTagLink(candidate_id=candidate.id, tag_id=i, added_by_user_id=user.id) for i in added)
    if added or removed:
        db.add(AuditLog(user_id=user.id, action="candidate.tags", entity_type="candidate", entity_id=str(candidate.id),
                        metadata_json={"added": [str(i) for i in added], "removed": [str(i) for i in removed]}))  # fmt: skip
    await db.flush()


def system_tags(experience_months: int | None, categories: list[str]) -> list[dict]:
    """T3: derived on read, never stored -- the experience band, then the categories of the skills held (name order)."""
    out = [{"kind": "experience", "label": label} for label, low, high in EXPERIENCE
           if experience_months is not None and experience_months >= low and (high is None or experience_months <= high)]  # fmt: skip
    return out + [{"kind": "skill_category", "label": name} for name in sorted(set(categories), key=str.lower)]
