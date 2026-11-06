"""pob-020 (DEC-SCOPE-412): the question bank, templates, a requirement's screening form, sessions and comparison.

A requirement or application id resolves through rec-007's scope (out of scope = 404); every write is one transaction -- role, row lock,
change, audit, one commit here. Included by app/api/recruiter_applications.py."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import SCREENING_CATEGORIES, User
from app.schemas import (
    RecScreeningFormCreate,
    RecScreeningFormVersion,
    RecScreeningKnockoutApproval,
    RecScreeningQuestionIn,
    RecScreeningQuestionPatch,
    RecScreeningSessionIn,
    RecScreeningTemplateIn,
    RecScreeningTemplatePatch,
)
from app.services import applications
from app.services import recruiter_requirements as requirements
from app.services import screening_forms as svc

router = APIRouter(tags=["recruiter-screening"])  # the parent router adds /recruiter


# --- the bank ---------------------------------------------------------------------------------------------------------------------------
@router.get("/screening/questions")
async def list_screening_questions(
    q: str | None = Query(default=None, max_length=200),
    category: Literal[SCREENING_CATEGORIES] | None = None,
    include_archived: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc.require_manager(user)
    return await svc.list_questions(db, q, category, include_archived, limit, offset)


@router.post("/screening/questions", status_code=201)
async def create_screening_question(payload: RecScreeningQuestionIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_manager(user)
    row = await svc.create_question(db, user, payload.model_dump())
    await db.commit()
    return {"question": svc.question_out(row)}


@router.patch("/screening/questions/{question_id}")
async def update_screening_question(question_id: UUID, payload: RecScreeningQuestionPatch, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_manager(user)
    row = await svc.update_question(db, user, question_id, payload.model_dump(exclude_unset=True))
    await db.commit()
    return {"question": svc.question_out(row)}


# --- templates --------------------------------------------------------------------------------------------------------------------------
@router.get("/screening/templates")
async def list_screening_templates(
    include_archived: bool = False,
    limit: int = Query(default=100, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc.require_manager(user)
    return await svc.list_templates(db, include_archived, limit)


@router.post("/screening/templates", status_code=201)
async def create_screening_template(payload: RecScreeningTemplateIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_manager(user)
    template = await svc.create_template(db, user, payload.name, payload.model_dump()["questions"])
    await db.commit()
    return {"template": template}


@router.patch("/screening/templates/{template_id}")
async def update_screening_template(template_id: UUID, payload: RecScreeningTemplatePatch, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_manager(user)
    template = await svc.update_template(db, user, template_id, payload.model_dump())  # None = not sent; each question needs its defaults
    await db.commit()
    return {"template": template}


# --- a requirement's form ---------------------------------------------------------------------------------------------------------------
@router.get("/requirements/{requirement_id}/screening-form")
async def read_screening_form(requirement_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await requirements.load_scoped(db, user, requirement_id)
    return await svc.read_form(db, user, job)


@router.post("/requirements/{requirement_id}/screening-form", status_code=201)
async def create_screening_form(requirement_id: UUID, payload: RecScreeningFormCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await requirements.load_scoped(db, user, requirement_id, lock=True)
    form = await svc.create_form(db, user, job, payload.template_id)
    await db.commit()
    return {"form": await svc.form_out(db, form)}


@router.put("/requirements/{requirement_id}/screening-form")
async def save_screening_form(requirement_id: UUID, payload: RecScreeningFormVersion, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await requirements.load_scoped(db, user, requirement_id, lock=True)
    form = await svc.save_form(db, user, job, payload.model_dump()["questions"])
    await db.commit()
    return {"form": await svc.form_out(db, form)}


@router.post("/requirements/{requirement_id}/screening-form/approve-knockouts")
async def approve_screening_knockouts(requirement_id: UUID, payload: RecScreeningKnockoutApproval, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await requirements.load_scoped(db, user, requirement_id, lock=True)
    form = await svc.approve_knockouts(db, user, job, payload.version)
    await db.commit()
    return {"form": await svc.form_out(db, form)}


@router.get("/requirements/{requirement_id}/screening-comparison")
async def screening_comparison(requirement_id: UUID, version: int | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    job = await requirements.load_scoped(db, user, requirement_id)
    return await svc.comparison(db, user, job, version)


# --- sessions ---------------------------------------------------------------------------------------------------------------------------
@router.get("/applications/{application_id}/screening-sessions")
async def list_screening_sessions(application_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    application, job = await applications.load_scoped(db, user, application_id)
    return await svc.read_sessions(db, user, application, job)


@router.post("/applications/{application_id}/screening-sessions", status_code=201)
async def record_screening_session(application_id: UUID, payload: RecScreeningSessionIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    application, job = await applications.load_scoped(db, user, application_id, lock=True)
    applications.require_writer(user, application.id, "record_screening_session")
    session = await svc.record(db, user, application, job, payload.model_dump())
    await db.commit()
    applications.log("recruiter_application_screening_session", user, application, recommendation=session.recommendation, knockout_triggered=session.knockout_triggered)
    return {"session": (await svc.sessions_out(db, user, application.id, session.id))[0]}
