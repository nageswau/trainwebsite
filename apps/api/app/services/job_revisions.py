"""pob-002 (DEC-SCOPE-407 R1-R5, R8): a job requirement's revisions -- one append-only snapshot of its material fields per save that changed
any of them.

Functions only; nothing here commits -- the writing route owns the transaction and has locked the job row (`load_scoped(lock=True)`), so
`max(revision) + 1` cannot race; `uq_job_revisions_revision` is the backstop. A snapshot keeps references by display name (hrc-004's
`audited_values`), so a revision reads as the requirement stood, even after a category or contact is renamed. Commercial values are
stored, and dropped on read for a caller without `commercials.client.view` (R8)."""

import logging
from decimal import Decimal

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, JobRevision, User
from app.schemas import REC_REQUIREMENT_FIELDS
from app.services import recruiter_requirements as requirements

logger = logging.getLogger("app.recruiter")

NOT_FOUND = "Revision not found"
BASELINE_REASON = "Recorded before revisions were kept"
# The snapshot's keys in screen order, with their labels (references by name: `job_category`, not `job_category_id`).
LABELS = {
    "title": "Job title",
    "requisition_reference": "Requisition reference",
    "lead_source": "Lead source",
    "department": "Department",
    "job_category": "Job category",
    "vacancies": "Number of vacancies",
    "qualification": "Qualification",
    "experience_min_months": "Experience from (months)",
    "experience_max_months": "Experience to (months)",
    "certifications": "Certifications",
    "country": "Country",
    "state": "State",
    "city": "City",
    "location": "Job location",
    "work_mode": "Work mode",
    "relocation_required": "Relocation required",
    "travel_requirement": "Travel",
    "salary_min": "Salary from",
    "salary_max": "Salary to",
    "salary_currency": "Salary currency",
    "salary_period": "Pay period",
    "shift": "Shift",
    "employment_type": "Employment type",
    "benefits": "Benefits",
    "hiring_manager": "Hiring manager",
    "joining_requirement": "Joining requirement",
    "expected_joining_date": "Expected joining date",
    "closes_on": "Application deadline",
    "requirement_date": "Requirement date",
    "priority": "Priority",
    "required_skills": "Required skills",
    "preferred_skills": "Preferred skills",
    "description": "Job description",
    "interview_rounds": "Interview rounds",
    "screening_steps": "Screening steps",
    "decision_maker_contact": "Decision-maker",
    "expected_tat_days": "Expected turnaround (days)",
    "backup_owner": "Backup owner",
    "fee_basis": "Fee basis",
    "fee_value": "Fee",
    "payment_trigger": "Payment trigger",
    "payment_days": "Payment due (days after joining)",
    "payment_terms": "Payment terms",
    "replacement_terms": "Replacement terms",
}
COMMERCIAL_KEYS = frozenset({"fee_basis", "fee_value", "payment_trigger", "payment_days", "payment_terms", "replacement_terms"})
_COLUMNS = (*REC_REQUIREMENT_FIELDS, "fee_basis", "fee_value")  # R4: every column a create or edit writes, and the rec-031 fee


async def snapshot(db: AsyncSession, job: Job) -> dict:
    """Every material field of the job as it stands in this session (JSON-safe)."""
    return jsonable_encoder(await requirements.audited_values(db, job, _COLUMNS, skills=True), custom_encoder={Decimal: str})  # money stays exact


def _changed(before: dict, after: dict) -> list[str]:
    return [k for k in LABELS if before.get(k) != after.get(k) and not (before.get(k) in (None, "") and after.get(k) in (None, ""))]


async def _last(db: AsyncSession, job_id) -> int | None:
    return await db.scalar(select(func.max(JobRevision.revision)).where(JobRevision.job_id == job_id))


def _add(db: AsyncSession, job: Job, number: int, values: dict, changed: list[str], reason: str | None, author: User | None) -> None:
    db.add(JobRevision(job_id=job.id, revision=number, snapshot=values, changed_fields=changed, reason=reason, author_user_id=author.id if author else None,
                       created_at=func.clock_timestamp()))  # fmt: skip  # a baseline and its edit keep their order


async def record_created(db: AsyncSession, user: User, job: Job) -> None:
    """R2: revision 1 of a new requirement (after its skills are set)."""
    _add(db, job, 1, await snapshot(db, job), [], None, user)


async def record(db: AsyncSession, user: User, job: Job, before: dict, reason: str | None) -> int | None:
    """R2/R3: one revision when a material field changed since `before` (the caller's snapshot before the edit, taken under the row
    lock); a job without revisions first gets its baseline. Call after the edit is flushed. Returns the new revision number or None."""
    after = await snapshot(db, job)
    changed = _changed(before, after)
    if not changed:
        return None
    last = await _last(db, job.id)
    if last is None:
        _add(db, job, 1, before, [], BASELINE_REASON, None)
        last = 1
    _add(db, job, last + 1, after, changed, reason, user)
    logger.info("recruiter_requirement_revised", extra={"extra_fields": {"actor_id": str(user.id), "job_id": str(job.id), "revision": last + 1, "fields": len(changed)}})
    return last + 1


def _visible(keys, view: bool) -> list[str]:
    return [k for k in keys if view or k not in COMMERCIAL_KEYS]


def _author(user: User | None) -> dict | None:
    return {"id": user.id, "full_name": user.full_name} if user else None


async def list_page(db: AsyncSession, job: Job, *, view: bool, limit: int, offset: int) -> dict:
    """R5: newest first; `changed_fields` without the commercial names for a caller who cannot see them."""
    where = JobRevision.job_id == job.id
    total = await db.scalar(select(func.count()).select_from(JobRevision).where(where)) or 0
    stmt = (select(JobRevision, User).outerjoin(User, User.id == JobRevision.author_user_id).where(where)
            .order_by(JobRevision.revision.desc()).limit(limit).offset(offset))  # fmt: skip
    items = [
        {"revision": r.revision, "author": _author(author), "reason": r.reason, "created_at": r.created_at,
         "changed_fields": [{"field": k, "label": LABELS[k]} for k in _visible(r.changed_fields or [], view) if k in LABELS]}
        for r, author in (await db.execute(stmt)).all()
    ]  # fmt: skip
    return {"items": items, "total": total, "limit": limit, "offset": offset}


async def _get(db: AsyncSession, job: Job, number: int) -> tuple[JobRevision, User | None]:
    row = (await db.execute(select(JobRevision, User).outerjoin(User, User.id == JobRevision.author_user_id)
                            .where(JobRevision.job_id == job.id, JobRevision.revision == number))).first()  # fmt: skip
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return row[0], row[1]


async def read(db: AsyncSession, job: Job, number: int, compare_to: int | None, *, view: bool) -> dict:
    """R5: revision `number`'s values, and its changes against `compare_to` (default: the revision before it; none for revision 1)."""
    revision, author = await _get(db, job, number)
    other = compare_to if compare_to is not None else (number - 1 if number > 1 else None)
    base = (await _get(db, job, other))[0].snapshot if other is not None else None
    keys = _visible(LABELS, view)
    values = revision.snapshot or {}
    return {
        "revision": revision.revision,
        "author": _author(author),
        "reason": revision.reason,
        "created_at": revision.created_at,
        "compared_to": other,
        "values": [{"field": k, "label": LABELS[k], "value": values.get(k)} for k in keys],
        "changes": None if base is None else [{"field": k, "label": LABELS[k], "before": base.get(k), "after": values.get(k)} for k in _changed(base, values) if k in keys],
    }
