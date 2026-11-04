"""hrc-014 (DEC-SCOPE-377 D4-D10): merge a duplicate candidate (the victim) into the candidate that stays (the survivor) -- the itc-007
lead-merge shape.

Both are found inside the pool (anything else is a 404), locked FOR UPDATE in id order so two merges of a crossing pair serialise, and every
rule is checked again on the locked rows. The victim's applications (with their profile-share items), calls, messages, consents, hrc-015's
documents and document requests, the skills the survivor lacks and every resume move to the survivor (one UPDATE per table); the chosen and the empty survivor fields take the victim's
values; the victim is archived with `merged_into_id`. An application on a requirement both are on cannot move ((candidate, job) is unique):
an open one blocks the merge (409), a closed one stays on the archived victim (D6). Contact and compensation never move (D4). One
`candidate.merge` audit row on the survivor, one `candidate.merged_into` on the victim. Functions only; nothing here commits. Logs carry
ids and counts, never names, contact data or the reason text."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Candidate,
    CandidateConsent,
    CandidateDocument,
    CandidateDocumentRequest,
    CandidateResume,
    CandidateSkill,
    Job,
    JobApplication,
    ProfileShareItem,
    RecruiterCall,
    RecruiterMessage,
    User,
)
from app.services import candidate_duplicates, recruitment_history
from app.services import candidates as svc

logger = logging.getLogger("app.candidates")

# The fields the merge form compares and may take from the victim (D4); contact and compensation are shown, never moved.
FIELDS = ("name", "location", "qualification", "college", "passing_year", "experience_months", "current_company", "notice_days", "preferred_role", "linkedin")
CLOSED = ("rejected", "withdrawn")  # an application in one of these may stay behind on the victim (D6)
# Moved wholesale by `candidate_id`; applications, skills and resumes have their own rules below.
MOVED = {
    "calls": RecruiterCall, "messages": RecruiterMessage, "consents": CandidateConsent,
    # hrc-015: documents and document requests (a second pending request of a type is cancelled first, see `_cancel_clashing_requests`)
    "documents": CandidateDocument, "document_requests": CandidateDocumentRequest,
}  # fmt: skip

MERGE_SELF = "A candidate cannot be merged into itself"
SURVIVOR_ARCHIVED = "Restore {code} before merging into it"
VICTIM_ARCHIVED = "{code} is archived. Restore it first"
VICTIM_MERGED = "{code} was already merged into another candidate"
VICTIM_LINKED = "{code} is linked to a student login. Merge the other candidate into it instead"
BOTH_LINKED = "Both candidates are linked to student logins, so they cannot be merged"
OPEN_ON_SAME_JOB = "Both candidates are on {jobs}. Reject or withdraw {code}'s application there first"
RACE = "Something changed while merging. Reload and try again"


def _empty(value) -> bool:
    return value is None or value == ""


async def _victim(db: AsyncSession, code: str) -> Candidate:
    victim = await db.scalar(select(Candidate).where(func.upper(Candidate.candidate_code) == code.strip().upper(), *svc.pool_filter()))
    if victim is None:
        raise HTTPException(404, svc.NOT_FOUND)
    return victim


def check(survivor: Candidate, victim: Candidate) -> None:
    if victim.id == survivor.id:
        raise HTTPException(422, MERGE_SELF)
    if survivor.archived_at is not None:
        raise HTTPException(409, SURVIVOR_ARCHIVED.format(code=survivor.candidate_code))
    if victim.merged_into_id is not None:
        raise HTTPException(409, VICTIM_MERGED.format(code=victim.candidate_code))
    if victim.archived_at is not None:
        raise HTTPException(409, VICTIM_ARCHIVED.format(code=victim.candidate_code))
    if victim.user_id is not None:  # D5: one login is one candidate; its consent history is the student's own
        raise HTTPException(409, BOTH_LINKED if survivor.user_id is not None else VICTIM_LINKED.format(code=victim.candidate_code))


async def _conflicts(db: AsyncSession, survivor: Candidate, victim: Candidate) -> list[dict]:
    """The victim's applications on a requirement the survivor is on too; an open one blocks."""
    theirs = select(JobApplication.job_id).where(JobApplication.candidate_id == survivor.id)
    rows = (await db.execute(
        select(JobApplication, Job.title).join(Job, Job.id == JobApplication.job_id).where(JobApplication.candidate_id == victim.id, JobApplication.job_id.in_(theirs))
        .order_by(Job.title)
    )).all()  # fmt: skip
    return [{"application_id": a.id, "job_id": a.job_id, "job_title": title, "status": a.status, "blocking": a.status not in CLOSED} for a, title in rows]


def _require_no_blocking(victim: Candidate, conflicts: list[dict]) -> None:
    blocking = [c["job_title"] for c in conflicts if c["blocking"]]
    if blocking:
        raise HTTPException(409, OPEN_ON_SAME_JOB.format(jobs=", ".join(blocking), code=victim.candidate_code))


async def _counts(db: AsyncSession, survivor: Candidate, victim: Candidate, kept: list[UUID]) -> dict:
    async def count(model, *where) -> int:
        return await db.scalar(select(func.count()).select_from(model).where(*where)) or 0

    survivor_skills = select(CandidateSkill.skill_id).where(CandidateSkill.candidate_id == survivor.id)
    return {
        "applications": await count(JobApplication, JobApplication.candidate_id == victim.id, JobApplication.id.not_in(kept)),
        "share_items": await count(ProfileShareItem, ProfileShareItem.candidate_id == victim.id, ProfileShareItem.application_id.not_in(kept)),
        **{key: await count(model, model.candidate_id == victim.id) for key, model in MOVED.items()},
        "skills": await count(CandidateSkill, CandidateSkill.candidate_id == victim.id, CandidateSkill.skill_id.not_in(survivor_skills)),
        "resumes": await count(CandidateResume, CandidateResume.candidate_id == victim.id),
    }


def _side(candidate: Candidate, sees_compensation: bool) -> dict:
    out = {"id": candidate.id, "candidate_code": candidate.candidate_code, "status": candidate.status, "created_at": candidate.created_at,
           "mobile": candidate.mobile, "email": candidate.email, **{field: getattr(candidate, field) for field in FIELDS}}  # fmt: skip
    if sees_compensation:
        out |= {field: getattr(candidate, field) for field in ("current_salary", "expected_salary")}
    return out


async def preview(db: AsyncSession, user: User, survivor_id: UUID, code: str) -> dict:
    """The merge form: both sides, what would move and the same-requirement conflicts (a blocking one disables Merge). Read only."""
    survivor = await svc.load(db, survivor_id)
    victim = await _victim(db, code)
    check(survivor, victim)
    conflicts = await _conflicts(db, survivor, victim)
    kept = [c["application_id"] for c in conflicts]
    sees = await svc.sees_compensation(db, user)
    return {"survivor": _side(survivor, sees), "victim": _side(victim, sees), "fields": list(FIELDS), "conflicts": conflicts,
            "moved": await _counts(db, survivor, victim, kept)}  # fmt: skip


async def _lock(db: AsyncSession, survivor_id: UUID, victim_id: UUID) -> tuple[Candidate, Candidate]:
    stmt = select(Candidate).where(Candidate.id.in_([survivor_id, victim_id]), *svc.pool_filter()).order_by(Candidate.id).with_for_update()
    rows = {row.id: row for row in (await db.scalars(stmt.execution_options(populate_existing=True))).all()}
    if len(rows) != 2:
        raise HTTPException(404, svc.NOT_FOUND)
    survivor, victim = rows[survivor_id], rows[victim_id]
    check(survivor, victim)
    return survivor, victim


async def _move_resumes(db: AsyncSession, survivor: Candidate, victim: Candidate) -> int:
    """D7: one numbering by upload time across both, so the newest upload is current; negative first, as (candidate, version) is unique."""
    resumes = (await db.scalars(select(CandidateResume).where(CandidateResume.candidate_id.in_([survivor.id, victim.id])))).all()
    moved = sum(1 for r in resumes if r.candidate_id == victim.id)
    ordered = sorted(resumes, key=lambda r: (r.created_at, r.candidate_id != survivor.id, r.version))
    for position, resume in enumerate(ordered, start=1):
        resume.candidate_id, resume.version = survivor.id, -position
    await db.flush()
    for position, resume in enumerate(ordered, start=1):
        resume.version = position
    await db.flush()
    return moved


async def _cancel_clashing_requests(db: AsyncSession, actor: User, survivor: Candidate, victim: Candidate) -> None:
    """hrc-015 allows one pending document request per type per candidate: where both are waiting for the same type, the victim's is
    cancelled (kept as history) so the move keeps the survivor's."""
    survivor_pending = select(CandidateDocumentRequest.document_type).where(CandidateDocumentRequest.candidate_id == survivor.id,
                                                                           CandidateDocumentRequest.status == "pending")  # fmt: skip
    await db.execute(
        update(CandidateDocumentRequest)
        .where(CandidateDocumentRequest.candidate_id == victim.id, CandidateDocumentRequest.status == "pending", CandidateDocumentRequest.document_type.in_(survivor_pending))
        .values(status="cancelled", cancelled_at=datetime.now(UTC), cancelled_by_user_id=actor.id)
        .execution_options(synchronize_session=False)
    )


async def merge(db: AsyncSession, actor: User, survivor_id: UUID, code: str, use_victim: list[str], reason: str | None) -> dict:
    """Find, lock, check, move. The route commits. Returns the route's body."""
    found = await _victim(db, code)
    check(await svc.load(db, survivor_id), found)  # 404 / 422 / 409 before anything is locked (and again once locked)
    survivor, victim = await _lock(db, survivor_id, found.id)
    conflicts = await _conflicts(db, survivor, victim)
    _require_no_blocking(victim, conflicts)
    kept = [c["application_id"] for c in conflicts]

    before = await svc.audited_values(db, survivor, FIELDS)
    chosen = []
    for field in FIELDS:
        value = getattr(victim, field)
        if not _empty(value) and (field in use_victim or _empty(getattr(survivor, field))) and value != getattr(survivor, field):
            setattr(survivor, field, value)
            chosen.append(field)

    survivor_skills = select(CandidateSkill.skill_id).where(CandidateSkill.candidate_id == survivor.id).scalar_subquery()
    moving = select(JobApplication.id).where(JobApplication.candidate_id == victim.id, JobApplication.id.not_in(kept)).scalar_subquery()
    moved = {
        # share items first: they are found through the applications that are still the victim's
        "share_items": (await db.execute(update(ProfileShareItem).where(ProfileShareItem.candidate_id == victim.id, ProfileShareItem.application_id.in_(moving))
                                         .values(candidate_id=survivor.id).execution_options(synchronize_session=False))).rowcount,  # fmt: skip
        "applications": (await db.execute(update(JobApplication).where(JobApplication.candidate_id == victim.id, JobApplication.id.not_in(kept))
                                           .values(candidate_id=survivor.id, student_id=survivor.user_id).execution_options(synchronize_session=False))).rowcount,  # fmt: skip
    }
    await _cancel_clashing_requests(db, actor, survivor, victim)
    for key, model in MOVED.items():
        result = await db.execute(update(model).where(model.candidate_id == victim.id).values(candidate_id=survivor.id).execution_options(synchronize_session=False))
        moved[key] = result.rowcount
    moved["skills"] = (await db.execute(update(CandidateSkill).where(CandidateSkill.candidate_id == victim.id, CandidateSkill.skill_id.not_in(survivor_skills))
                                        .values(candidate_id=survivor.id).execution_options(synchronize_session=False))).rowcount  # fmt: skip
    moved["resumes"] = await _move_resumes(db, survivor, victim)

    now = datetime.now(UTC)
    victim.archived_at, victim.archived_by_user_id, victim.updated_by_user_id = now, actor.id, actor.id
    victim.merged_into_id, victim.merged_at, victim.merged_by_user_id = survivor.id, now, actor.id
    survivor.updated_by_user_id = actor.id
    await db.flush()
    await candidate_duplicates.close_for_merge(db, actor, victim.id)

    metadata = {"victim_id": str(victim.id), "victim_code": victim.candidate_code, "moved": moved, "kept_applications": [str(k) for k in kept],
                "use_victim": sorted(use_victim), "fields": sorted(chosen)}  # fmt: skip
    if changed := recruitment_history.diff(before, await svc.audited_values(db, survivor, FIELDS)):
        metadata["changes"] = changed
    svc.audit(db, actor, "merge", survivor, metadata)
    svc.audit(db, actor, "merged_into", victim, {"survivor_id": str(survivor.id), "survivor_code": survivor.candidate_code, "reason": reason})
    await db.flush()
    await candidate_duplicates.detect(db, survivor.id)  # D9: a third duplicate shows up again against the survivor
    logger.info("candidate_merged", extra={"extra_fields": {"survivor_id": str(survivor.id), "victim_id": str(victim.id), "actor_id": str(actor.id), **moved}})
    return {"id": survivor.id, "victim_id": victim.id, "victim_code": victim.candidate_code, "moved": moved, "kept_applications": kept}
