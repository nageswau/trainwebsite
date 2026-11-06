"""hrc-022 (DEC-SCOPE-386): the external candidate's own routes. Registration, verification and resend are public and answer the same
whatever the email (C2/C5); every `/candidate/me*` route is the signed-in candidate's own record only (C10) -- no id is ever taken from
the caller. The allow-list setting sits with the other recruiter candidate settings (C7). Each write is one transaction committed here;
verification emails go out after it as a background task."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import CHANGE_PASSWORD_FAILED, _change_password_wait_seconds
from app.api.deps import get_current_user
from app.core.client_ip import client_ip
from app.core.database import get_db
from app.core.security import verify_password
from app.models import AuditLog, User
from app.notifications.phone import normalise_phone
from app.schemas import CandidatePortalConsent, CandidatePortalEmailChange, CandidatePortalRegistration, CandidatePortalResend, CandidatePortalToken
from app.services import applications as job_applications
from app.services import candidate_jobs, interview_results, website_intake
from app.services import candidate_ownership as ownership
from app.services import candidate_portal as portal
from app.services import candidate_privacy as privacy
from app.services import candidates as svc
from app.services import portal as sections

router = APIRouter(prefix="/candidate", tags=["candidate-portal"])
settings_router = APIRouter(prefix="/recruiter/candidate-self-service-settings", tags=["recruiter-candidates"])
ACCEPTED = {"accepted": True}
WRONG_CONSENT = "Please accept the current consent wording"


def _candidate(user: User = Depends(get_current_user)) -> User:
    if user.role != portal.ROLE:
        raise HTTPException(403, "Only candidates can use the candidate portal")
    return user


def _send(background: BackgroundTasks, delivery: portal.Delivery | None) -> dict:
    if delivery:
        background.add_task(portal.deliver, delivery)
    return {**ACCEPTED, **portal.dev_token(delivery)}


@router.post("/register", status_code=202)
async def register(payload: CandidatePortalRegistration, request: Request, background: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    if payload.consent_version != portal.CONSENT_VERSION:
        raise HTTPException(422, WRONG_CONSENT)
    if payload.phone and normalise_phone(payload.phone) is None:
        raise HTTPException(422, "Enter a valid mobile number")
    delivery = await portal.register(db, full_name=payload.full_name, email=payload.email, phone=payload.phone, password=payload.password, ip=client_ip(request),
                                    utm=website_intake.clean_utm(payload.utm))  # hrc-023 W2
    await db.commit()
    return _send(background, delivery)


@router.post("/resend-verification", status_code=202)
async def resend_verification(payload: CandidatePortalResend, background: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    delivery = await portal.resend(db, payload.email)
    await db.commit()
    return _send(background, delivery)


@router.post("/verify-email")
async def verify_email(payload: CandidatePortalToken, request: Request, db: AsyncSession = Depends(get_db)):
    purpose = await portal.verify(db, payload.token, client_ip(request))
    await db.commit()
    return {"ok": True, "purpose": purpose}


@router.get("/me")
async def my_profile(user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    return await portal.profile_out(db, user, await portal.own(db, user))


@router.patch("/me")
async def update_my_profile(payload: dict = Body(...), user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    candidate = await portal.update_profile(db, user, payload)
    await db.commit()
    return await portal.profile_out(db, user, candidate)


@router.post("/me/email", status_code=202)
async def change_my_email(payload: CandidatePortalEmailChange, background: BackgroundTasks, user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    """C9: the throttles first (before bcrypt), then the current password -- a wrong one counts towards change-password's lockout."""
    await db.refresh(user, attribute_names=["password_hash"], with_for_update=True)
    if wait := await portal.email_change_wait_seconds(db, user) or await _change_password_wait_seconds(db, user.id):
        raise HTTPException(429, f"Too many attempts; try again in {wait} seconds", headers={"Retry-After": str(wait)})
    if not verify_password(payload.current_password, user.password_hash):
        db.add(AuditLog(user_id=user.id, action=CHANGE_PASSWORD_FAILED, entity_type="user", entity_id=str(user.id), outcome="denied",
                        metadata_json={"reason": "incorrect_current_password", "via": "candidate_email_change"}))  # fmt: skip
        await db.commit()
        raise HTTPException(400, "Incorrect current password")
    delivery = await portal.request_email_change(db, user, payload.new_email)
    await db.commit()
    return _send(background, delivery)


async def _privacy(db: AsyncSession, user: User, candidate) -> dict:
    """hrc-035 (DEC-SCOPE-396 K6): the consent view plus the latest deletion request (null = none)."""
    return {**await portal.privacy_out(db, candidate), "erasure": privacy.request_out(await privacy.own_request(db, user))}


@router.get("/me/privacy")
async def my_privacy(user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    return await _privacy(db, user, await portal.own(db, user))


@router.put("/me/privacy")
async def save_my_privacy(payload: CandidatePortalConsent, request: Request, user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    if payload.consent_version != portal.CONSENT_VERSION:
        raise HTTPException(422, WRONG_CONSENT)
    candidate = await portal.set_consent(db, user, payload.opted_in, client_ip(request))
    await db.commit()
    return await _privacy(db, user, candidate)


@router.post("/me/erasure-request")
async def request_my_erasure(response: Response, user: User = Depends(_candidate), db: AsyncSession = Depends(get_db)):
    """hrc-035 K6: the candidate's own "delete my data" request for the HR Manager -- 201 new, 200 the open one again (no id is taken)."""
    candidate = await portal.own(db, user)
    _, created = await privacy.request_erasure(db, user)
    await db.commit()
    response.status_code = 201 if created else 200
    return await _privacy(db, user, candidate)


# --- hrc-027 (DEC-SCOPE-398 J1): the open jobs a candidate or an IT student may see, and applying to one ----------------------------
def _job_seeker(user: User = Depends(get_current_user)) -> User:
    if (user.role, user.division) not in {(portal.ROLE, "it"), ("it_student", "it")}:
        raise HTTPException(403, "Only candidates and IT students can use the job recommendations")
    return user


@router.get("/jobs")
async def my_jobs(
    view: Literal["recommended", "matching", "all"] = "recommended",
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(_job_seeker),
    db: AsyncSession = Depends(get_db),
):
    return await candidate_jobs.listing(db, user, view=view, q=q, limit=limit, offset=offset)


@router.post("/jobs/{job_id}/apply", status_code=201)
async def apply_to_job(job_id: UUID, user: User = Depends(_job_seeker), db: AsyncSession = Depends(get_db)):
    item = await candidate_jobs.apply(db, user, job_id)
    await db.commit()
    return {"id": item.id, "code": item.application_code, "status_label": job_applications.candidate_label(item.candidate_status)}


@router.get("/results")
async def my_results(user: User = Depends(_job_seeker), db: AsyncSession = Depends(get_db)):
    """hrc-030 (DEC-SCOPE-409 R9): the caller's own published interview results only; nothing unpublished."""
    return {"items": await interview_results.mine(db, user)}


# --- hrc-031 (DEC-SCOPE-412 P1): the caller's own applications and interviews; the same payloads as the student portal's sections ------
@router.get("/applications")
async def my_applications(user: User = Depends(_job_seeker), db: AsyncSession = Depends(get_db)):
    return await sections.my_applications(db, user)


@router.get("/interviews")
async def my_interviews(user: User = Depends(_job_seeker), db: AsyncSession = Depends(get_db)):
    return await sections.my_interviews(db, user)


@settings_router.get("")
async def self_service_settings(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """C7: every candidate reader sees the allow-list; placement managers and super_admin (the hrc-012 setting editors) change it."""
    svc.require_reader(user)
    return {"fields": await portal.allow_list(db), "available": list(portal.UNIVERSE), "can_edit": user.role in ownership.SETTING_EDITORS}


@settings_router.put("")
async def save_self_service_settings(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in ownership.SETTING_EDITORS:
        raise HTTPException(403, "Only a placement manager can change candidate self-service fields")
    fields = await portal.save_allow_list(db, user, payload.get("fields"))
    await db.commit()
    return {"fields": fields, "available": list(portal.UNIVERSE), "can_edit": True}
