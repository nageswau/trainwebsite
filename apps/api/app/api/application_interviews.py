"""nehn-037 part 4 (DEC-SCOPE-296) -- admission interviews on an overseas application: list, schedule, change, record the result.

CC4: the counselor records them on their applications, direct and agency; the Overseas Admin on any. The student and the agency read.
Writes use the offers' entry (`_writable`, moves no stage): role, `_assigned_application` scope, the row lock, the swapped-counselor
re-check, then the closed and archived-agency refusals (I6). The row lock serialises writes on one application; the last one wins and
every one is audited. Spec: docs/superpowers/specs/2026-10-27-nehn-037-admission-interviews-design.md.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.application_offers import READERS, _tell_student, _writable
from app.api.deps import get_current_user
from app.api.workflows import _assigned_application, _audit, _require
from app.core.database import get_db
from app.models import ApplicationInterview, OverseasApplication, University, User
from app.schemas import ApplicationInterviewCreate, ApplicationInterviewUpdate
from app.services import agent_notifications as agency_notices

logger = logging.getLogger("app.application_interviews")

router = APIRouter(prefix="/workflows/overseas/applications", tags=["application-interviews"])
student_router = APIRouter(prefix="/workflows/overseas/student", tags=["application-interviews"])

MODE_LABELS = {"online": "Online", "in_person": "In person", "phone": "Phone"}
OUTCOME_LABELS = {None: "Awaiting result", "passed": "Passed", "not_successful": "Not successful", "cancelled": "Cancelled"}
DECIDED = {"passed", "not_successful"}
FIELDS = ("scheduled_at", "mode", "location", "student_note", "outcome")
MAX_PER_APPLICATION = 20  # I4
NOT_FOUND = "Interview not found"
TOO_EARLY = "A result can be recorded only after the interview date -- or mark it cancelled"
FULL = f"An application can hold at most {MAX_PER_APPLICATION} interviews"


def problem(values: dict) -> str | None:
    """I3: passed / not successful only once the interview time has passed; cancelled any time."""
    if values["outcome"] in DECIDED and values["scheduled_at"] > datetime.now(UTC):
        return TOO_EARLY
    return None


def view(row: ApplicationInterview, recorded_by: str | None = None, *, staff: bool) -> dict:
    data = {
        "id": row.id,
        "application_id": row.application_id,
        "scheduled_at": row.scheduled_at,
        "mode": row.mode,
        "mode_label": MODE_LABELS[row.mode],
        "location": row.location,
        "student_note": row.student_note,
        "outcome": row.outcome,
        "outcome_label": OUTCOME_LABELS[row.outcome],
        "updated_at": row.updated_at,
    }
    return data | {"recorded_by": recorded_by} if staff else data


async def _views(db: AsyncSession, application_id: UUID, *, staff: bool, interview_id: UUID | None = None) -> list[dict]:
    stmt = (
        select(ApplicationInterview, User.full_name)
        .outerjoin(User, User.id == ApplicationInterview.created_by_id)
        .where(ApplicationInterview.application_id == application_id)
        .order_by(ApplicationInterview.scheduled_at.desc(), ApplicationInterview.id)
    )
    if interview_id is not None:
        stmt = stmt.where(ApplicationInterview.id == interview_id)
    return [view(row, name, staff=staff) for row, name in (await db.execute(stmt.execution_options(populate_existing=True))).all()]


async def _university(db: AsyncSession, item: OverseasApplication) -> str:
    return await db.scalar(select(University.name).where(University.id == item.university_id)) or "Your university"


@router.get("/{application_id}/interviews")
async def list_interviews(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every interview of the application, latest first. Who recorded it goes to staff only."""
    _require(user, READERS, "overseas")
    item = await _assigned_application(db, user, application_id)
    return {"interviews": await _views(db, item.id, staff=user.role in {"counselor", "overseas_admin", "super_admin"})}


@student_router.get("/interviews")
async def my_interviews(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The signed-in student's interviews across their own applications, latest first (AC3)."""
    _require(user, {"overseas_student"}, "overseas")
    rows = (
        await db.execute(
            select(ApplicationInterview, OverseasApplication.application_code, University.name)
            .join(OverseasApplication, OverseasApplication.id == ApplicationInterview.application_id)
            .join(University, University.id == OverseasApplication.university_id)
            .where(OverseasApplication.student_id == user.id)
            .order_by(ApplicationInterview.scheduled_at.desc(), ApplicationInterview.id)
            .limit(200)
        )
    ).all()
    return {"items": [view(row, staff=False) | {"application_code": code, "university": university} for row, code, university in rows]}


async def _saved(db: AsyncSession, user: User, item: OverseasApplication, row: ApplicationInterview, before: dict | None) -> dict:
    """Tell the student (I7: added, moved or a new result -- not a note-only change) and the agency, audit the field names, commit."""
    changed = [name for name in FIELDS if before is None or before[name] != getattr(row, name)]
    university = await _university(db, item)
    if before is None:
        await _tell_student(db, item, "Interview scheduled", f"{university}: an admission interview is scheduled -- see your applications page.")
    elif "outcome" in changed:
        title = "Interview cancelled" if row.outcome == "cancelled" else "Interview result"
        await _tell_student(db, item, title, f"{university}: admission interview -- {OUTCOME_LABELS[row.outcome].lower()}.")
    elif "scheduled_at" in changed:
        await _tell_student(db, item, "Interview rescheduled", f"{university}: your admission interview has a new time -- see your applications page.")
    elif {"mode", "location"} & set(changed):
        await _tell_student(db, item, "Interview updated", f"{university}: the details of your admission interview changed -- see your applications page.")
    await agency_notices.details_changed(db, item, user)  # CC5
    action = "added" if before is None else "updated"
    await _audit(db, user, "overseas.application.interview", "overseas_application", item.id, {"interview_id": str(row.id), "action": action, "fields": changed, "outcome": row.outcome})
    await db.commit()
    logger.info("application_interview_saved", extra={"extra_fields": {"application_id": str(item.id), "interview_id": str(row.id), "action": action, "actor_id": str(user.id)}})
    [saved] = await _views(db, item.id, staff=True, interview_id=row.id)
    return {"interview": saved, "changed": True}


@router.post("/{application_id}/interviews", status_code=201)
async def add_interview(application_id: UUID, payload: ApplicationInterviewCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Schedule (or record a past) admission interview. Moves no stage, so it is allowed on hold."""
    item = await _writable(db, user, application_id, moves_stage=False)
    values = payload.model_dump()
    if message := problem(values):
        raise HTTPException(422, message)
    count = await db.scalar(select(func.count()).select_from(ApplicationInterview).where(ApplicationInterview.application_id == item.id)) or 0
    if count >= MAX_PER_APPLICATION:
        raise HTTPException(422, FULL)
    row = ApplicationInterview(application_id=item.id, created_by_id=user.id, updated_by_id=user.id, **values)
    db.add(row)
    await db.flush()
    return await _saved(db, user, item, row, None)


@router.patch("/{application_id}/interviews/{interview_id}")
async def update_interview(application_id: UUID, interview_id: UUID, payload: ApplicationInterviewUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Change only the keys sent; the result is checked as a whole (I3). Nothing different: 200, unchanged, nothing written."""
    item = await _writable(db, user, application_id, moves_stage=False)
    row = await db.get(ApplicationInterview, interview_id)
    if row is None or row.application_id != item.id:
        raise HTTPException(404, NOT_FOUND)
    before = {name: getattr(row, name) for name in FIELDS}
    values = before | payload.model_dump(exclude_unset=True)
    if values == before:
        [current] = await _views(db, item.id, staff=True, interview_id=row.id)
        return {"interview": current, "changed": False}
    if message := problem(values):
        raise HTTPException(422, message)
    for name, value in values.items():
        setattr(row, name, value)
    row.updated_by_id = user.id
    await db.flush()
    return await _saved(db, user, item, row, before)
