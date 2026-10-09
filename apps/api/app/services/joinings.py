"""rec-023 (DEC-SCOPE-158, spec §1-§3): joining management + placement closure -- the §17 joining on an Accepted offer, its moves (Joined /
Did Not Join), their side effects on the application (rec-017), the company (rec-005) and the requirement's vacancies (rec-007), the proof
file and the joinings list.

The joining lives on its offer (JN1), so every read and write resolves through services/offers.py's scoped loaders (rec-007's requirement
scope: out of scope = the same 404 as missing). Lock order: the application, the offer, the job, the company. Functions only; nothing here
commits -- the route owns the transaction. Logs and audit carry ids, statuses and field names, never a name, the reason or a file name."""

from datetime import UTC, date, datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Candidate, Company, Job, JobApplication, JobOffer, User
from app.schemas import RecJoiningUpdate
from app.services import applications, company_pipeline, offers
from app.services import recruiter_requirements as requirements
from app.services.interviews import field_error

NOT_ACCEPTED = "Joining is recorded once the offer is Accepted"
FINAL = "This joining is already final"
NOT_SELECTED = "The candidate must be Selected to join"
USE_JOINING = "Record the joining on the candidate's offer (Joined needs the actual joining date)"
NO_PROOF = "No joining proof has been uploaded"
PROOF_CLOSED = "A Did Not Join joining takes no proof"
VACANCIES_FILLED = "All vacancies filled"
FIELDS = {  # the PUT body key -> the job_offers column (JN1: the expected date is the offer's joining date)
    "expected_joining_date": "joining_date",
    "actual_joining_date": "actual_joining_date",
    "joining_location": "joining_location",
    "reporting_manager": "reporting_manager",
    "confirmed_by": "joining_confirmed_by",
    "confirmed_on": "joining_confirmed_on",
    "reason": "not_joined_reason",
}
VIEWS = {  # the list views: (status, order)
    "due": ("pending", (JobOffer.joining_date.asc().nulls_last(), JobOffer.id)),
    "joined": ("joined", (JobOffer.actual_joining_date.desc().nulls_last(), JobOffer.updated_at.desc(), JobOffer.id)),
    "did_not_join": ("did_not_join", (JobOffer.updated_at.desc(), JobOffer.id)),
}


async def has_offer(db: AsyncSession, application_id) -> bool:
    return bool(await db.scalar(select(JobOffer.id).where(JobOffer.application_id == application_id)))


def _check(offer: JobOffer, target: str, values: dict, today: date) -> None:
    """JN4-JN6: the dates first, then what the target status needs (one 422, on its field)."""
    expected, actual, confirmed_on = values["expected_joining_date"], values["actual_joining_date"], values["confirmed_on"]
    if expected is not None and expected < offer.offered_on:
        raise field_error("expected_joining_date", "The expected joining date cannot be before the offer date", expected.isoformat())
    if actual is not None and actual > today:
        raise field_error("actual_joining_date", "The actual joining date cannot be in the future", actual.isoformat())
    if actual is not None and actual < offer.offered_on:
        raise field_error("actual_joining_date", "The actual joining date cannot be before the offer date", actual.isoformat())
    if confirmed_on is not None and confirmed_on > today:
        raise field_error("confirmed_on", "The confirmation date cannot be in the future", confirmed_on.isoformat())
    if target == "joined":
        if actual is None:
            raise field_error("actual_joining_date", "Enter the actual joining date to mark Joined")
        if values["confirmed_by"] is None and offer.proof_key is None:
            raise field_error("confirmed_by", "Enter who confirmed the joining, or upload the joining proof first")
    if target == "did_not_join" and len(values["reason"] or "") < 2:
        raise field_error("reason", "Enter why the candidate did not join (at least 2 characters)", values["reason"])


async def update(db: AsyncSession, user: User, offer: JobOffer, application: JobApplication, job: Job, payload: RecJoiningUpdate, today: date) -> dict:
    """PUT: the whole §17 joining, and optionally its move. Returns {fields, from, to} ({} when nothing changed: no history, no audit)."""
    current = offer.joining_status
    if offer.status != "accepted" or current is None:
        raise HTTPException(409, NOT_ACCEPTED)
    if current != "pending":
        raise HTTPException(409, FINAL)
    target = payload.joining_status or current
    values = payload.model_dump(include=set(FIELDS))
    if target != "did_not_join":
        values["reason"] = None  # the reason belongs to Did Not Join only
    _check(offer, target, values, today)
    if target == "joined" and application.status != "selected":
        raise HTTPException(409, NOT_SELECTED)
    changed = sorted(key for key, column in FIELDS.items() if getattr(offer, column) != values[key])
    if not changed and target == current:
        return {}
    for key in changed:
        setattr(offer, FIELDS[key], values[key])
    if changed:
        offers.record_event(db, offer, user, "joining", fields=changed)
    if target != current:
        offer.joining_status = target
        offers.record_event(db, offer, user, target, note=values["reason"])
        await _side_effects(db, user, application, job, target)
    audit(db, user, "update", offer, {"fields": changed, "status": target, **({"from": current} if target != current else {})})
    return {"fields": changed, "from": current, "to": target}


async def _side_effects(db: AsyncSession, user: User, application: JobApplication, job: Job, target: str) -> None:
    """JN7 / JN8: Joined -> the application Joined, rec-005 `candidate_joined`, and the requirement Closed once its vacancies are filled;
    Did Not Join -> the application Withdrawn (when that move is allowed)."""
    if target == "did_not_join":
        applications.follow(db, user, application, "withdrawn", "Did not join")
        return
    await applications.change_status(db, user, application, "joined", "Joined")
    job = await db.scalar(select(Job).where(Job.id == job.id).with_for_update().execution_options(populate_existing=True))
    company = await db.scalar(select(Company).where(Company.id == job.company_id).with_for_update().execution_options(populate_existing=True))
    await company_pipeline.apply_event(db, company, "candidate_joined", user)
    await db.flush()  # this application's Joined is in the count below
    if job.vacancies is not None and job.status not in requirements.ENDED and await requirements.joined_count(db, job.id) >= job.vacancies:
        await requirements.change_status(db, user, job, "closed", VACANCIES_FILLED)


# --- the proof (JN4) ----------------------------------------------------------------------------------------------------------------
def check_proof_open(offer: JobOffer) -> None:
    if offer.joining_status is None:
        raise HTTPException(409, NOT_ACCEPTED)
    if offer.joining_status == "did_not_join":
        raise HTTPException(409, PROOF_CLOSED)


def attach_proof(db: AsyncSession, user: User, offer: JobOffer, key: str, content_type: str, name: str | None, size: int) -> None:
    """The replaced object is kept; its key goes on the history row, never into a response."""
    old_key = offer.proof_key
    offer.proof_key, offer.proof_content_type, offer.proof_name, offer.proof_uploaded_at = key, content_type, name, datetime.now(UTC)
    offers.record_event(db, offer, user, "proof", letter_key=old_key)
    audit(db, user, "proof", offer, {"content_type": content_type, "replaced": old_key is not None, "bytes": size})


# --- the list -----------------------------------------------------------------------------------------------------------------------
def _rows():
    return (
        select(JobOffer, JobApplication, Candidate, Job, Company)
        .join(JobApplication, JobApplication.id == JobOffer.application_id)
        .join(Candidate, Candidate.id == JobApplication.candidate_id)
        .join(Job, Job.id == JobApplication.job_id)
        .join(Company, Company.id == Job.company_id)
    )


async def list_page(db: AsyncSession, user: User, view: str, today: date, limit: int, offset: int) -> dict:
    """The caller's joinings (rec-007's requirement scope) in one view; the counts are the three views' totals."""
    scope = await requirements.caller_scope(db, user)
    status, order = VIEWS[view]
    base = select(func.count()).select_from(JobOffer).join(JobApplication, JobApplication.id == JobOffer.application_id).join(Job, Job.id == JobApplication.job_id)
    total = await db.scalar(base.where(*scope, JobOffer.joining_status == status))
    rows = (await db.execute(_rows().where(*scope, JobOffer.joining_status == status).order_by(*order).limit(limit).offset(offset))).all()
    counts = (await db.execute(base.with_only_columns(*(func.count().filter(JobOffer.joining_status == s) for s, _ in VIEWS.values())).where(*scope))).one()
    items = [
        {
            "id": o.id,
            "position": o.position,
            "offered_on": o.offered_on,
            "application": {"id": a.id, "status": a.status, "status_label": applications.label(a.status)},
            "candidate": {"id": c.id, "code": c.candidate_code, "name": c.name},
            "requirement": {"id": j.id, "code": j.requirement_code, "title": j.title},
            "company": {"id": co.id, "name": co.name},
            "joining": offers.joining_out(user, o, today),
        }
        for o, a, c, j, co in rows
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset, "counts": {v: n or 0 for v, n in zip(VIEWS, counts, strict=True)}}


def audit(db: AsyncSession, user: User, action: str, offer: JobOffer, metadata: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id, action=f"recruiter_joining.{action}", entity_type="job_offer", entity_id=str(offer.id), metadata_json=metadata or {}))
