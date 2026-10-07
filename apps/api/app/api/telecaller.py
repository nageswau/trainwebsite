"""tel-001 (DEC-SCOPE-073, spec §5.7): telecaller and manager reads, the telecaller's phone self-edit (TL3), the admin telecaller
list and the reporting-manager picker.

Scope always comes from the session -- no /telecaller route takes a user id -- so there is no IDOR surface; the admin list is
narrowed by team in SQL (T21). Lists reuse bdm-001's paging helpers: {items, total, limit, offset}, ordered by name then id."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.admin import ensure_admin
from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching, _paged
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import LEAD_PRIORITIES, AuditLog, Enquiry, TelecallerProfile, User
from app.schemas import (
    LeadEnquiryCreate,
    LeadQualificationIn,
    LeadStageHistoryPage,
    LeadStageMove,
    LeadStageOut,
    LeadTimelinePage,
    TelecallerAdminPage,
    TelecallerLeadCreate,
    TelecallerLeadUpdate,
    TelecallerManagerPage,
    TelecallerMeOut,
    TelecallerTeamPage,
)
from app.services import lead_follow_ups, lead_intake, lead_pipeline, lead_qualification, telecaller_leads
from app.services.bdm_appointments import db_now
from app.services.telecaller import admin_team_filter, parse_self_update, person_ref, profile_out, require_manager, team_filter, telecaller_context
from app.worker import sync_enquiry_to_crm_task

router = APIRouter(prefix="/telecaller", tags=["telecaller"])
admin_router = APIRouter(prefix="/admin", tags=["telecaller-admin"])
Manager = aliased(User)


def _team_row(profile: TelecallerProfile, user: User) -> dict:
    return {
        "id": user.id, "full_name": user.full_name, "email": user.email, "phone": user.phone, "active": user.active,
        "team": profile.team, "employee_id": profile.employee_id,
    }


def _admin_row(profile: TelecallerProfile, user: User, manager: User) -> dict:
    return {**_team_row(profile, user), "reporting_manager": person_ref(manager), "manager_active": manager.active}


def _profiles(filters: list):
    """One query: profile + its user + its manager (no N+1)."""
    return (
        select(TelecallerProfile, User, Manager)
        .join(User, User.id == TelecallerProfile.user_id)
        .join(Manager, Manager.id == TelecallerProfile.reporting_manager_user_id)
        .where(*filters)
    )


def _me(user: User, profile: TelecallerProfile, manager: User) -> dict:
    return {
        "id": user.id, "full_name": user.full_name, "email": user.email, "phone": user.phone, "active": user.active,
        "division": user.division, "telecaller_profile": profile_out(profile, manager),
    }


@router.get("/me", response_model=TelecallerMeOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile = await telecaller_context(db, user)
    return _me(user, profile, await db.get(User, profile.reporting_manager_user_id))


@router.patch("/profile", response_model=TelecallerMeOut)
async def update_own_profile(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """TL3: the phone only; every other key is a 422 (TelecallerSelfUpdate forbids extras). The audit row names the field, not the
    value (no phone numbers in the log)."""
    profile = await telecaller_context(db, user)
    user.phone = parse_self_update(payload).phone
    db.add(AuditLog(user_id=user.id, action="telecaller.profile_update", entity_type="user", entity_id=str(user.id), metadata_json={"fields": ["phone"]}))
    out = _me(user, profile, await db.get(User, profile.reporting_manager_user_id))
    await db.commit()
    return out


@router.get("/manager/team", response_model=TelecallerTeamPage)
async def team(q: str | None = SEARCH, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """T23 / AC4: a manager's direct reports (inactive included, with their status); super_admin sees all. `q` only narrows."""
    require_manager(user)
    filters = team_filter(user) + _matching(like_pattern(q), User.full_name, User.email, TelecallerProfile.employee_id)
    return await _paged(db, _profiles(filters), limit, offset, lambda profile, member, _manager: _team_row(profile, member))


@router.get("/leads")
async def my_leads(
    status: str | None = None,
    priority: Literal[LEAD_PRIORITIES] | None = None,
    product_id: UUID | None = None,
    campaign_id: UUID | None = None,
    follow_up: Literal["today", "overdue"] | None = None,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """tel-008 (spec §2, AC1/AC6): My Leads -- the caller's scope (tel-004 T23), newest first. Every filter is ANDed with the scope, so
    it can only narrow; `q` is a literal substring of the Lead ID, name, email, phone or WhatsApp number. tel-011 F9: `follow_up`."""
    _, filters = lead_pipeline.scope(user)
    for column, value in ((Enquiry.status, status), (Enquiry.priority, priority), (Enquiry.product_id, product_id), (Enquiry.campaign_id, campaign_id)):
        if value:
            filters.append(column == value)
    if follow_up:
        filters.append(lead_follow_ups.due_filter(follow_up, await db_now(db)))
    filters += _matching(like_pattern(q), *telecaller_leads.SEARCHED)
    return await telecaller_leads.page(db, user, filters, limit, offset)


@router.get("/leads/duplicate-check")
async def duplicate_check(phone: str | None = None, email: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """tel-005 (T12, R2): the §18 panel for a mobile and/or email, before a lead is created -- across every lead, closed ones too."""
    lead_pipeline.scope(user)
    phone_key, email_key = lead_intake.identity(phone, email)
    if phone and not phone_key:
        raise HTTPException(422, "Enter a valid mobile number")
    if not phone_key and not email_key:
        raise HTTPException(422, "Enter a mobile number or an email")
    matches = await lead_intake.matching_leads(db, phone_key, email_key)
    return {"matches": await lead_intake.panel(db, user, matches, phone_key, email_key)}


@router.post("/leads", status_code=201)
async def create_lead(payload: TelecallerLeadCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """tel-005 (I1, I2): a telecaller or manager enters a lead; a known person is 409 with the duplicate panel. Like every other lead,
    it is queued for the CRM only after the commit (R10)."""
    _, filters = lead_pipeline.scope(user)
    lead = await lead_intake.create_lead(db, user, payload)
    await db.commit()
    sync_enquiry_to_crm_task.delay(str(lead.id))
    # QA-06: tel-007 may give a manager's lead to a telecaller outside the manager's reports; `in_scope` tells the form not to open it
    in_scope = await db.scalar(select(Enquiry.id).where(Enquiry.id == lead.id, *filters)) is not None
    return {**await telecaller_leads.detail(db, user, lead.id, []), "in_scope": in_scope}


@router.post("/leads/{lead_id}/enquiries", status_code=201)
async def add_enquiry(lead_id: UUID, payload: LeadEnquiryCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """tel-005 (I5): "Add enquiry to this lead" from the duplicate panel -- any lead, append-only, no read access granted."""
    lead_pipeline.scope(user)
    out = await lead_intake.add_enquiry(db, user, lead_id, payload)
    await db.commit()
    return out


@router.get("/leads/{lead_id}")
async def lead_detail(lead_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC2: a lead in scope with its enquiry message and the caller's `read_only` (D1); anything else is 404."""
    _, filters = lead_pipeline.scope(user)
    return await telecaller_leads.detail(db, user, lead_id, filters)


@router.patch("/leads/{lead_id}")
async def update_lead(lead_id: UUID, payload: TelecallerLeadUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """D2: contact fields, product and priority (AC3). The row is locked within the scope, so a lead reassigned while the page was open
    is 404 (spec edge case); a telecaller on a handed-over lead is 403 (AC4)."""
    _, filters = lead_pipeline.scope(user)
    lead = await lead_pipeline.locked_lead(db, lead_id, *filters)
    telecaller_leads.require_writable(user, lead)
    await telecaller_leads.apply_update(db, user, lead, payload.model_dump(exclude_unset=True))
    await db.commit()
    return await telecaller_leads.detail(db, user, lead_id, filters)


@router.get("/leads/{lead_id}/timeline", response_model=LeadTimelinePage)
async def lead_timeline(lead_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """W1: stage and priority changes of a lead in scope, newest first (tel-015 adds the other sources)."""
    _, filters = lead_pipeline.scope(user)
    if await db.scalar(select(Enquiry.id).where(Enquiry.id == lead_id, *filters)) is None:
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)
    return await telecaller_leads.timeline_page(db, lead_id, limit, offset)


@router.get("/leads/{lead_id}/qualification")
async def qualification(lead_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """tel-009 (spec §3): the qualification of a lead in scope -- every stored value (the hidden group's too, AC3) and the product group
    that decides the sections; `read_only` as the detail's (D1)."""
    _, filters = lead_pipeline.scope(user)
    lead = await db.scalar(select(Enquiry).where(Enquiry.id == lead_id, *filters))
    if lead is None:
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)
    return await lead_qualification.read(db, user, lead)


@router.put("/leads/{lead_id}/qualification")
async def save_qualification(lead_id: UUID, payload: LeadQualificationIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """tel-009 (QD2-QD4): replace the fields that apply to the lead's product. The lead is locked within scope (a lead reassigned while
    the form was open is 404); a telecaller on a handed-over lead is 403; the stage never moves."""
    _, filters = lead_pipeline.scope(user)
    lead = await lead_pipeline.locked_lead(db, lead_id, *filters)
    telecaller_leads.require_writable(user, lead)
    await lead_qualification.replace(db, user, lead, payload.model_dump(exclude_unset=True))
    await db.commit()
    lead = await db.scalar(select(Enquiry).where(Enquiry.id == lead_id).execution_options(populate_existing=True))
    return await lead_qualification.read(db, user, lead)


@router.post("/leads/{lead_id}/stage", response_model=LeadStageOut)
async def change_stage(lead_id: UUID, payload: LeadStageMove, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """tel-004 (spec §5): a telecaller's or manager's stage move on a lead in scope (T23; anything else is 404). The lead row is
    locked, so two moves of one lead serialise (each is checked against the stage the other left). tel-008 D1: not on a lead handed
    over to a counselor, for a telecaller (403)."""
    kind, filters = lead_pipeline.scope(user)
    lead = await lead_pipeline.locked_lead(db, lead_id, *filters)
    telecaller_leads.require_writable(user, lead)
    await lead_pipeline.person_move(db, lead, user, kind, payload.to_stage, payload.reason)
    out = lead_pipeline.stage_out(lead)
    await db.commit()
    return out


@router.get("/leads/{lead_id}/stage-history", response_model=LeadStageHistoryPage)
async def stage_history(lead_id: UUID, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC5: every stage change of a lead in scope, oldest first."""
    _, filters = lead_pipeline.scope(user)
    if await db.scalar(select(Enquiry.id).where(Enquiry.id == lead_id, *filters)) is None:
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)
    return await lead_pipeline.history_page(db, lead_id, limit, offset)


@admin_router.get("/telecallers", response_model=TelecallerAdminPage)
async def admin_telecallers(
    team: Literal["it", "overseas"] | None = None,
    active: bool | None = None,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(ensure_admin),
    db: AsyncSession = Depends(get_db),
):
    """`q` matches name, email or Employee ID; it is ANDed with the caller's team scope, so it can never widen it."""
    filters = admin_team_filter(user, team)
    if active is not None:
        filters.append(User.active.is_(active))
    filters += _matching(like_pattern(q), User.full_name, User.email, TelecallerProfile.employee_id)
    return await _paged(db, _profiles(filters), limit, offset, _admin_row)


@admin_router.get("/telecaller-managers", response_model=TelecallerManagerPage)
async def telecaller_managers(q: str | None = SEARCH, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """The reporting-manager picker: active telecaller managers only, searchable by name or email; email tells same-name managers apart.
    tel-025: `telecaller_count` (every report, active or not) for the Telecaller managers card; a correlated count, one query."""
    count = select(func.count()).where(TelecallerProfile.reporting_manager_user_id == User.id).scalar_subquery()
    stmt = select(User.id, User.full_name, User.email, count).where(
        User.role == "telecaller_manager", User.active.is_(True), *_matching(like_pattern(q), User.full_name, User.email)
    )
    return await _paged(db, stmt, limit, offset, lambda id_, full_name, email, n: {"id": id_, "full_name": full_name, "email": email, "telecaller_count": n})
