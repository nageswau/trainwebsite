"""rec-002 (DEC-SCOPE-117, spec §4): the recruiter managed lists and campaigns. Placement managers and super_admin write; recruiters read
active values (C3). The lists are global, so there is no row scope -- only the role checks below, made before anything is read.

Bodies are untyped dicts parsed by services/telecaller._parse, so a 422 is one sentence naming the field (the tel-002 idiom). The
campaign routes are declared first so `campaigns` never reaches the generic `{kind}` routes."""

import logging
import re
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.api.telecaller_catalogue import NOT_AN_OBJECT, _locked, _page
from app.core.database import get_db
from app.models import AuditLog, RecCampaign, RecFxRate, RecLeadSource, User
from app.schemas import (
    FX_RATE_LABELS,
    REC_CATALOGUE_FIELD_LABELS,
    FxRateSet,
    RecCampaignCreate,
    RecCampaignOut,
    RecCampaignPage,
    RecCampaignUpdate,
    RecValueCreate,
    RecValueOut,
    RecValuePage,
    RecValueUpdate,
)
from app.services import candidates, compensation
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
logger = logging.getLogger("app.recruiter_catalogue")
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


# --- hrc-011 (DEC-SCOPE-375 C1/C5): exchange rates -------------------------------------------------------------------------------
def _rate_out(row: RecFxRate, people: dict) -> dict:
    by = people.get(row.updated_by_user_id)
    return {"currency": row.currency, "inr_per_unit": row.inr_per_unit, "updated_at": row.updated_at, "updated_by": {"id": by.id, "full_name": by.full_name} if by else None}


async def _rates_out(db: AsyncSession, rows: list[RecFxRate]) -> list[dict]:
    ids = {r.updated_by_user_id for r in rows} - {None}
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(ids)))).all()} if ids else {}
    return [_rate_out(r, people) for r in rows]


@router.get("/exchange-rates")
async def exchange_rates(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every rate, by currency (a handful). Candidate readers too: the candidate form offers INR plus these currencies."""
    candidates.require_reader(user)
    return {"items": await _rates_out(db, list((await db.scalars(select(RecFxRate).order_by(RecFxRate.currency))).all()))}


@router.put("/exchange-rates/{currency}")
async def set_exchange_rate(currency: str, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Add or change one rate (idempotent), recompute every candidate amount in that currency, one audit row with the old and new rate."""
    require_manager(user)
    code = currency.strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", code):
        raise HTTPException(422, "Currency must be a three-letter code such as USD")
    if code == compensation.INR:
        raise HTTPException(422, "INR is the base currency; it needs no rate")
    rate = _parse(FxRateSet, payload, NOT_AN_OBJECT, FX_RATE_LABELS).inr_per_unit.quantize(Decimal("0.0001"))
    row = await db.get(RecFxRate, code, with_for_update=True)
    old = row.inr_per_unit if row else None
    if row is None:
        row = RecFxRate(currency=code, inr_per_unit=rate, updated_by_user_id=user.id)
        db.add(row)
    else:
        row.inr_per_unit, row.updated_by_user_id = rate, user.id
    await db.flush()
    recomputed = await compensation.recompute(db, code, rate)
    db.add(
        AuditLog(
            user_id=user.id,
            action="recruiter.fx_rate_set",
            entity_type="rec_fx_rates",
            entity_id=code,
            metadata_json={"old": None if old is None else f"{old:.4f}", "new": f"{rate:.4f}", "recomputed": recomputed},
        )
    )
    await db.commit()
    await db.refresh(row)
    logger.info("fx_rate_set", extra={"extra_fields": {"actor_id": str(user.id), "currency": code, "recomputed": recomputed}})
    return (await _rates_out(db, [row]))[0]


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
