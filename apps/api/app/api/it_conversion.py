"""itc-011: the one-step IT conversion and the onboarding checklist (docs/superpowers/specs/2026-11-03-itc-011-it-one-step-conversion-
design.md; API_CONTRACT.md and RBAC_MATRIX.md blocks naming itc-011).

- GET/POST /counselor/leads/{id}/convert-it: the lead's owner IT counselor (another lead 404; any other role 403).
- GET/POST /admin/leads/{id}/convert-it: the IT Admin (another division's lead 403, as the admin lead routes).
- GET /it/enrollments/{id}/onboarding: the student (own), their IT counselor, the IT Admin; PATCH .../{item_id}: the counselor or the
  IT Admin.

POST needs an `Idempotency-Key` header: a retry with the same key on that lead answers 200 with the stored result and creates nothing.
The set-password link is mailed after the commit and its token is never returned."""

from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Enquiry, ItConversion, User
from app.schemas import ItConversionIn, ItOnboardingTick
from app.services import bdm_leads, counselor_students, it_conversion, it_student_counselors, lead_handover, lead_pipeline

counselor_router = APIRouter(prefix="/counselor/leads", tags=["it-conversion"])
admin_router = APIRouter(prefix="/admin/leads", tags=["it-conversion"])
router = APIRouter(prefix="/it/enrollments", tags=["it-conversion"])

COUNSELOR_ONLY = "Only an IT counselor can convert a lead to an IT student"
ADMIN_ONLY = "Only the IT Admin can convert a lead here"


async def _counselor_lead(db: AsyncSession, user: User, lead_id: UUID) -> Enquiry:
    filters = lead_handover.counselor_scope(user)
    it_student_counselors.require_it_counselor(user, COUNSELOR_ONLY)
    return await lead_pipeline.locked_lead(db, lead_id, *filters)


async def _admin_lead(db: AsyncSession, user: User, lead_id: UUID) -> Enquiry:
    if user.role != "it_admin" or user.division != "it":
        raise HTTPException(403, ADMIN_ONLY)
    return await bdm_leads.locked_for_admin(db, user, lead_id)


async def _convert(db: AsyncSession, user: User, lead: Enquiry, payload: ItConversionIn, key: str | None, response: Response,
                   read_lead: Callable[[UUID], Awaitable[dict]]) -> dict:  # fmt: skip
    key = it_conversion.require_key(key)
    lead_id = lead.id
    row = await it_conversion.replay(db, lead, key)
    issued, replayed = None, row is not None
    if replayed:
        response.status_code = 200
    else:
        row, issued = await it_conversion.convert(db, user, lead, payload, key)
        row_id = row.id
        await lead_handover.commit_link(db, user, lead_id)
        row = await db.get(ItConversion, row_id)
    out = {**await it_conversion.out(db, row), "lead": await read_lead(lead_id), "replayed": replayed}
    if issued is not None:
        out |= await counselor_students.deliver_link(await db.get(User, row.student_user_id), issued, user)
    return out


@counselor_router.get("/{lead_id}/convert-it")
async def counselor_options(lead_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    lead = await _counselor_lead(db, user, lead_id)
    return await it_conversion.options(db, lead)


@counselor_router.post("/{lead_id}/convert-it", status_code=201)
async def counselor_convert(lead_id: UUID, payload: ItConversionIn, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                            user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):  # fmt: skip
    lead = await _counselor_lead(db, user, lead_id)
    filters = lead_handover.counselor_scope(user)
    return await _convert(db, user, lead, payload, idempotency_key, response, lambda lid: lead_handover.detail(db, lid, filters))


@admin_router.get("/{lead_id}/convert-it")
async def admin_options(lead_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    lead = await _admin_lead(db, user, lead_id)
    return await it_conversion.options(db, lead)


@admin_router.post("/{lead_id}/convert-it", status_code=201)
async def admin_convert(lead_id: UUID, payload: ItConversionIn, response: Response, idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
                        user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):  # fmt: skip
    lead = await _admin_lead(db, user, lead_id)
    return await _convert(db, user, lead, payload, idempotency_key, response, lambda lid: bdm_leads.admin_one(db, lid))


@router.get("/{enrollment_id}/onboarding")
async def onboarding(enrollment_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    enrollment = await it_conversion.reachable(db, user, enrollment_id, write=False)
    return {"enrollment_id": enrollment.id, "items": await it_conversion.checklist(db, enrollment.id)}


@router.patch("/{enrollment_id}/onboarding/{item_id}")
async def tick(enrollment_id: UUID, item_id: UUID, payload: ItOnboardingTick, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    enrollment = await it_conversion.reachable(db, user, enrollment_id, write=True)
    await it_conversion.tick(db, user, enrollment, item_id, payload.done)
    await db.commit()
    return {"enrollment_id": enrollment_id, "items": await it_conversion.checklist(db, enrollment_id)}
