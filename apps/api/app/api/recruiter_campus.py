"""pob-015 (DEC-SCOPE-426, API §12LS): vacancies shared with a college, its students' outcomes, the campus calendar (and its ICS) and the
TPO widget.

Every `{org_id}` resolves through pob-013's `college_placement.load` / `editable` (out of scope 404, role 403, archived 409). Every write
is one transaction -- scope, the organization row lock, role, state, validation, change, audit, one commit -- and returns the college's
vacancies view. Mounted on recruiter_drives.router (prefix /recruiter)."""

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import SEARCH
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import BdmOrganization, InstitutionVacancyShare, User
from app.schemas import VacancyResponseIn, VacancyShareIn
from app.services import campus_placement as svc
from app.services import college_placement as placement
from app.services import recruiter_messages as messages
from app.services.bdm_appointments import today_ist

router = APIRouter(tags=["recruiter-campus"])
FROM = Query(None, alias="from")
TO = Query(None, alias="to")
DUPLICATE = "This vacancy was already recorded as shared on that day by that channel"


async def _respond(db: AsyncSession, user: User, org: BdmOrganization) -> dict:
    return {"vacancies": await svc.view(db, user, org)}


@router.get("/colleges/{org_id}/vacancies")
async def college_vacancies(org_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _respond(db, user, await placement.load(db, user, org_id))


@router.get("/colleges/{org_id}/vacancy-options")
async def vacancy_options(org_id: UUID, q: str | None = SEARCH, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The share form's picker: the college's writers only (V2)."""
    org = await placement.load(db, user, org_id)
    if not placement.can_edit(user, org):
        raise HTTPException(403, placement.EDIT_REFUSAL)
    return await svc.options(db, user, like_pattern(q))


@router.post("/colleges/{org_id}/vacancy-shares", status_code=201)
async def share_vacancy(org_id: UUID, payload: VacancyShareIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """V1-V5. Records the share (the message itself goes through the pob-023 composer). Not idempotent by key; a same-day, same-channel
    repeat of the same requirement is 409."""
    org = await placement.editable(db, user, org_id, "vacancy_share")
    job = await svc.shareable_job(db, user, payload.requirement_id)
    now = datetime.now(UTC)
    today = today_ist(now)
    shared_on: date = payload.shared_on or today
    if shared_on > today:
        raise HTTPException(422, "A share can't be in the future")
    if payload.template_id is not None:
        template = await messages.usable_template(db, user, payload.template_id)
        if template.category != "college_tpo":
            raise HTTPException(422, svc.TEMPLATE_CATEGORY)
        await messages.mark_used(db, template.id, now)
    share = InstitutionVacancyShare(organization_id=org.id, job_id=job.id, shared_on=shared_on, channel=payload.channel, template_id=payload.template_id,
                                    notes=payload.notes, shared_by_user_id=user.id)  # fmt: skip
    db.add(share)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, DUPLICATE) from None
    metadata = {"share_id": str(share.id), "job_id": str(job.id), "channel": share.channel}
    placement.audit(db, user, "vacancy_share", org.id, metadata)
    await db.commit()
    placement.log("placement_vacancy_share", user, org.id, **metadata)
    return await _respond(db, user, org)


@router.patch("/colleges/{org_id}/vacancy-shares/{share_id}")
async def answer_share(org_id: UUID, share_id: UUID, payload: VacancyResponseIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """V6: the college's answer. A share of another college is 404. The same answer is no change (no audit)."""
    org = await placement.editable(db, user, org_id, "vacancy_response")
    share = await placement.owned(db, InstitutionVacancyShare, org.id, share_id, svc.SHARE_NOT_FOUND)
    if (share.response, share.response_note) != (payload.response, payload.response_note):
        svc.record_answer(share, user, payload.response, payload.response_note, datetime.now(UTC))
        metadata = {"share_id": str(share.id), "response": payload.response}
        placement.audit(db, user, "vacancy_response", org.id, metadata)
        await db.commit()
        placement.log("placement_vacancy_response", user, org.id, **metadata)
    else:
        await db.commit()  # releases the row lock
    return await _respond(db, user, org)


@router.get("/campus-calendar")
async def campus_calendar(start: date | None = FROM, end: date | None = TO, college_id: UUID | None = None, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):  # fmt: skip
    """V8: at most 92 days (default: this month, IST)."""
    first, last = svc.window(start, end, today_ist(datetime.now(UTC)))
    return await svc.calendar(db, user, first, last, college_id)


@router.get("/campus-calendar.ics")
async def campus_calendar_ics(start: date | None = FROM, end: date | None = TO, college_id: UUID | None = None, user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):  # fmt: skip
    """V9: the same entries as all-day events."""
    first, last = svc.window(start, end, today_ist(datetime.now(UTC)))
    body = svc.ics(await svc.calendar(db, user, first, last, college_id))
    headers = {"Content-Disposition": f'attachment; filename="campus-calendar-{first}.ics"', "Cache-Control": "no-store"}
    return Response(body, media_type="text/calendar; charset=utf-8", headers=headers)


@router.get("/campus-summary")
async def campus_summary(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """V10: the TPO partnerships widget over the caller's colleges."""
    return await svc.summary(db, user, today_ist(datetime.now(UTC)))
