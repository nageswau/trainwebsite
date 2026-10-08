"""rec-002 (DEC-SCOPE-117, spec §4): the recruiter managed lists and campaigns. Placement managers and super_admin write; recruiters read
active values (C3). The lists are global, so there is no row scope -- only the role checks below, made before anything is read.

Bodies are untyped dicts parsed by services/telecaller._parse, so a 422 is one sentence naming the field (the tel-002 idiom). The
campaign routes are declared first so `campaigns` never reaches the generic `{kind}` routes."""

from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.api.telecaller_catalogue import NOT_AN_OBJECT, _locked, _page
from app.core.database import get_db
from app.models import RecCampaign, RecLeadSource, User
from app.schemas import (
    REC_CATALOGUE_FIELD_LABELS,
    RecCampaignCreate,
    RecCampaignOut,
    RecCampaignPage,
    RecCampaignUpdate,
    RecValueCreate,
    RecValueOut,
    RecValuePage,
    RecValueUpdate,
)
from app.services.recruiter import require_manager
from app.services.recruiter_catalogue import (
    CAMPAIGN_NAME_INDEX,
    active_filters,
    campaign_out,
    catalogue_model,
    locked_active_lead_source,
    require_reader,
    value_out,
)
from app.services.telecaller import _parse
from app.services.telecaller_catalogue import apply_changes, audit, flush_unique

router = APIRouter(prefix="/recruiter/catalogue", tags=["recruiter-catalogue"])
CREATED = "recruiter.catalogue_create"
UPDATED = "recruiter.catalogue_update"


def _body(model, payload):
    return _parse(model, payload, NOT_AN_OBJECT, REC_CATALOGUE_FIELD_LABELS)


def _check_dates(start, end) -> None:
    if end is not None and end < start:
        raise HTTPException(422, "End date cannot be before the start date")


# --- campaigns ------------------------------------------------------------------------------------------------------------------
@router.get("/campaigns", response_model=RecCampaignPage)
async def campaigns(
    lead_source_id: UUID | None = None,
    active: bool | None = None,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Active first, then the newest start, then name."""
    require_reader(user)
    filters = active_filters(user, RecCampaign.active, active) + _matching(like_pattern(q), RecCampaign.name)
    if lead_source_id:
        filters.append(RecCampaign.lead_source_id == lead_source_id)
    stmt = select(RecCampaign, RecLeadSource).join(RecLeadSource, RecLeadSource.id == RecCampaign.lead_source_id).where(*filters)
    order = (RecCampaign.active.desc(), RecCampaign.start_date.desc(), func.lower(RecCampaign.name), RecCampaign.id)
    return await _page(db, stmt, order, limit, offset, campaign_out)


@router.post("/campaigns", response_model=RecCampaignOut, status_code=201)
async def create_campaign(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_manager(user)
    data = _body(RecCampaignCreate, payload)
    _check_dates(data.start_date, data.end_date)
    source = await locked_active_lead_source(db, data.lead_source_id)
    campaign = RecCampaign(**data.model_dump(), active=True)
    db.add(campaign)
    await flush_unique(db, CAMPAIGN_NAME_INDEX, f"A campaign named “{data.name}” already exists")
    audit(db, user, CREATED, RecCampaign.__tablename__, campaign.id, ["name", "lead_source_id", "start_date", "end_date"])
    out = campaign_out(campaign, source)
    await db.commit()
    return out


@router.patch("/campaigns/{campaign_id}", response_model=RecCampaignOut)
async def update_campaign(campaign_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Moving to another lead source needs an active one; keeping a since-deactivated source is allowed (AC2)."""
    require_manager(user)
    campaign = await _locked(db, RecCampaign, campaign_id, "Campaign")
    changes = _body(RecCampaignUpdate, payload).model_dump(exclude_unset=True)
    _check_dates(changes.get("start_date", campaign.start_date), changes.get("end_date", campaign.end_date))
    if changes.get("lead_source_id", campaign.lead_source_id) != campaign.lead_source_id:
        source = await locked_active_lead_source(db, changes["lead_source_id"])
    else:
        source = await db.get(RecLeadSource, campaign.lead_source_id)
    fields = apply_changes(campaign, changes)
    await flush_unique(db, CAMPAIGN_NAME_INDEX, f"A campaign named “{campaign.name}” already exists")
    if fields:
        audit(db, user, UPDATED, RecCampaign.__tablename__, campaign.id, fields)
    out = campaign_out(campaign, source)
    await db.commit()
    return out


# --- the six simple lists -------------------------------------------------------------------------------------------------------
@router.get("/{kind}", response_model=RecValuePage)
async def values(
    kind: str,
    active: bool | None = None,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """In list order (the source order for the seed, then each addition), then name."""
    require_reader(user)
    model = catalogue_model(kind)
    stmt = select(model).where(*active_filters(user, model.active, active), *_matching(like_pattern(q), model.name))
    return await _page(db, stmt, (model.sort_order, func.lower(model.name), model.id), limit, offset, value_out)


def _duplicate(name: str) -> str:
    return f"A value named “{name}” already exists in this list"


@router.post("/{kind}", response_model=RecValueOut, status_code=201)
async def create_value(kind: str, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A new value goes to the end of its list."""
    require_manager(user)
    model = catalogue_model(kind)
    data = _body(RecValueCreate, payload)
    last = await db.scalar(select(func.max(model.sort_order)))
    row = model(name=data.name, sort_order=(last or 0) + 1, active=True)
    db.add(row)
    await flush_unique(db, f"uq_{model.__tablename__}_name", _duplicate(data.name))
    audit(db, user, CREATED, model.__tablename__, row.id, ["name"])
    out = value_out(row)
    await db.commit()
    return out


@router.patch("/{kind}/{value_id}", response_model=RecValueOut)
async def update_value(kind: str, value_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Rename and/or (de)activate. A rename keeps the id, so records keep their link (AC5); never deleted (AC2)."""
    require_manager(user)
    model = catalogue_model(kind)
    row = await _locked(db, model, value_id, "Value")
    fields = apply_changes(row, _body(RecValueUpdate, payload).model_dump(exclude_unset=True))
    await flush_unique(db, f"uq_{model.__tablename__}_name", _duplicate(row.name))
    if fields:
        audit(db, user, UPDATED, model.__tablename__, row.id, fields)
    out = value_out(row)
    await db.commit()
    return out
