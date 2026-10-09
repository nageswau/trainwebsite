"""rec-018 (DEC-SCOPE-149, spec §2): an application's screening -- the §13 checklist and its result (SC1-SC8).

Functions only; nothing here commits -- the route owns the transaction and has already locked the application (rec-017's
`load_scoped(lock=True)`), so concurrent saves serialise. The status moves only through `applications.change_status` (SC3). Logs and the
audit row carry ids, field names and the result, never a value: salary and remarks are internal."""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SCREENING_RESULTS, ApplicationScreening, JobApplication, User
from app.services import applications

AUDIT = "recruiter_application.screening"
LABELS = {"shortlisted": "Shortlisted", "hold": "Hold", "rejected": "Rejected", "need_more_info": "Need More Information"}
FIELDS = (
    "qualification_verified",
    "experience_verified",
    "skills_verified",
    "expected_salary",
    "notice_days",
    "location_preference",
    "communication_rating",
    "technical_rating",
    "availability",
    "willing_to_relocate",
    "remarks",
    "result",
)
MOVES = {"shortlisted": ("shortlisted", ("sourced", "screened")), "rejected": ("rejected", applications.OPEN)}  # SC3: target, from
NOT_OPEN = "Only an open application can be screened. Reopen it first."


def result_out(result: str | None) -> dict | None:
    return {"key": result, "label": LABELS[result]} if result else None


def can_edit(user: User, application: JobApplication) -> bool:
    return applications.can_write(user) and application.status in applications.OPEN  # SC4


async def current(db: AsyncSession, application_id) -> ApplicationScreening | None:
    stmt = select(ApplicationScreening).where(ApplicationScreening.application_id == application_id).execution_options(populate_existing=True)
    return await db.scalar(stmt)


async def screening_out(db: AsyncSession, row: ApplicationScreening | None) -> dict | None:
    if row is None:
        return None
    by = await db.get(User, row.screened_by_user_id)
    values = {f: getattr(row, f) for f in FIELDS}
    if values["expected_salary"] is not None:
        values["expected_salary"] = float(values["expected_salary"])
    return {**values, "result_label": LABELS[row.result], "screened_by": {"id": by.id, "full_name": by.full_name}, "updated_at": row.updated_at}


async def read(db: AsyncSession, user: User, application: JobApplication) -> dict:
    return {
        "screening": await screening_out(db, await current(db, application.id)),
        "results": [{"key": r, "label": LABELS[r]} for r in SCREENING_RESULTS],
        "can_edit": can_edit(user, application),
    }


async def save(db: AsyncSession, user: User, application: JobApplication, sent: dict) -> str | None:
    """SC4: 409 unless open. SC5: replace the one current row, auditing the changed names; an unchanged form writes nothing. SC3: move
    the status. Returns the previous status when it moved, else None."""
    if application.status not in applications.OPEN:
        raise HTTPException(409, NOT_OPEN)
    row = await current(db, application.id)
    changed = [f for f in FIELDS if row is None or getattr(row, f) != sent[f]]
    if changed:
        if row is None:
            row = ApplicationScreening(application_id=application.id, screened_by_user_id=user.id)
            db.add(row)
        for field in FIELDS:
            setattr(row, field, sent[field])
        row.screened_by_user_id, row.updated_at = user.id, await db.scalar(select(func.now()))
        applications.audit(db, user, "screening", application, {"fields": sorted(changed), "result": sent["result"]})
    target, origins = MOVES.get(sent["result"], (None, ()))
    if target is None or application.status not in origins:
        return None
    return await applications.change_status(db, user, application, target, f"Screening: {LABELS[sent['result']]}")
