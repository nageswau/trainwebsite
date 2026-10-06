"""tel-002 (DEC-SCOPE-074, spec §4): the product/interest catalogue and the campaign list. Managers and super_admin write; the P1
readers see active rows. The catalogue is global (T17), so there is no row scope -- only the role checks below.

Bodies are untyped dicts parsed by services/telecaller._parse, so a 422 is one sentence naming the field (the tel-001 idiom)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import Program, TelCampaign, TelProduct, User
from app.schemas import (
    TEL_CATALOGUE_FIELD_LABELS,
    TelCampaignCreate,
    TelCampaignOut,
    TelCampaignPage,
    TelCampaignUpdate,
    TelProductCreate,
    TelProductOut,
    TelProductPage,
    TelProductUpdate,
    TelSource,
)
from app.services.telecaller import _parse, require_manager
from app.services.telecaller_catalogue import (
    CAMPAIGN_NAME_INDEX,
    PRODUCT_NAME_INDEX,
    active_filters,
    active_program,
    apply_changes,
    audit,
    campaign_out,
    check_team,
    flush_unique,
    locked_active_product,
    product_out,
    require_reader,
)

router = APIRouter(prefix="/telecaller", tags=["telecaller-catalogue"])
GROUP_ORDER = case({"it": 0, "overseas": 1}, value=TelProduct.product_group, else_=2)
NOT_AN_OBJECT = "The request body must be an object"


def _body(model, payload):
    return _parse(model, payload, NOT_AN_OBJECT, TEL_CATALOGUE_FIELD_LABELS)


async def _page(db: AsyncSession, stmt, order: tuple, limit: int, offset: int, shape) -> dict:
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(stmt.order_by(*order).limit(limit).offset(offset))).all()
    return {"items": [shape(*row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


async def _locked(db: AsyncSession, model, row_id: UUID, noun: str):
    row = await db.scalar(select(model).where(model.id == row_id).with_for_update())
    if not row:
        raise HTTPException(404, f"{noun} not found")
    return row


# --- products -------------------------------------------------------------------------------------------------------------------
@router.get("/products", response_model=TelProductPage)
async def products(
    group: Literal["it", "overseas", "other"] | None = None,
    active: bool | None = None,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ordered IT, Overseas, Other, then the manager's sort order, then name -- the §3 order for the seed."""
    require_reader(user)
    filters = active_filters(user, TelProduct.active, active) + _matching(like_pattern(q), TelProduct.name)
    if group:
        filters.append(TelProduct.product_group == group)
    stmt = select(TelProduct, Program).outerjoin(Program, Program.id == TelProduct.program_id).where(*filters)
    return await _page(db, stmt, (GROUP_ORDER, TelProduct.sort_order, func.lower(TelProduct.name), TelProduct.id), limit, offset, product_out)


@router.post("/products", response_model=TelProductOut, status_code=201)
async def create_product(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_manager(user)
    data = _body(TelProductCreate, payload)
    team = data.team if data.group == "other" or "team" in data.model_fields_set else data.group
    check_team(data.group, team)
    program = await active_program(db, data.group, data.program_id) if data.program_id else None
    sort_order = data.sort_order
    if sort_order is None:
        last = await db.scalar(select(func.max(TelProduct.sort_order)).where(TelProduct.product_group == data.group))
        sort_order = min((last or 0) + 1, 9999)
    product = TelProduct(product_group=data.group, name=data.name, team=team, program_id=data.program_id, sort_order=sort_order, active=True)
    db.add(product)
    await flush_unique(db, PRODUCT_NAME_INDEX, f"A product named “{data.name}” already exists in this group")
    audit(db, user, "telecaller.product_create", "tel_product", product.id, ["group", "name", "team", "program_id", "sort_order"])
    out = product_out(product, program)
    await db.commit()
    return out


@router.patch("/products/{product_id}", response_model=TelProductOut)
async def update_product(product_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Renaming keeps the id, so leads keep their link (AC6). An Other product's team change affects only later distribution."""
    require_manager(user)
    product = await _locked(db, TelProduct, product_id, "Product")
    changes = _body(TelProductUpdate, payload).model_dump(exclude_unset=True)
    if changes.pop("group", product.product_group) != product.product_group:
        raise HTTPException(422, "Group cannot be changed")
    if "team" in changes:
        check_team(product.product_group, changes["team"])
    if changes.get("program_id") not in (None, product.program_id):
        await active_program(db, product.product_group, changes["program_id"])
    fields = apply_changes(product, changes)
    await flush_unique(db, PRODUCT_NAME_INDEX, f"A product named “{product.name}” already exists in this group")
    if fields:
        audit(db, user, "telecaller.product_update", "tel_product", product.id, fields)
    out = product_out(product, await db.get(Program, product.program_id) if product.program_id else None)
    await db.commit()
    return out


# --- campaigns ------------------------------------------------------------------------------------------------------------------
@router.get("/campaigns", response_model=TelCampaignPage)
async def campaigns(
    product_id: UUID | None = None,
    source: TelSource | None = None,
    active: bool | None = None,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Active first, then the newest start, then name."""
    require_reader(user)
    filters = active_filters(user, TelCampaign.active, active) + _matching(like_pattern(q), TelCampaign.name)
    if product_id:
        filters.append(TelCampaign.product_id == product_id)
    if source:
        filters.append(TelCampaign.source == source)
    stmt = select(TelCampaign, TelProduct).join(TelProduct, TelProduct.id == TelCampaign.product_id).where(*filters)
    order = (TelCampaign.active.desc(), TelCampaign.start_date.desc(), func.lower(TelCampaign.name), TelCampaign.id)
    return await _page(db, stmt, order, limit, offset, campaign_out)


def _check_dates(start, end) -> None:
    if end is not None and end < start:
        raise HTTPException(422, "End date cannot be before the start date")


@router.post("/campaigns", response_model=TelCampaignOut, status_code=201)
async def create_campaign(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_manager(user)
    data = _body(TelCampaignCreate, payload)
    _check_dates(data.start_date, data.end_date)
    product = await locked_active_product(db, data.product_id)
    campaign = TelCampaign(**data.model_dump(), active=True)
    db.add(campaign)
    await flush_unique(db, CAMPAIGN_NAME_INDEX, f"A campaign named “{data.name}” already exists")
    audit(db, user, "telecaller.campaign_create", "tel_campaign", campaign.id, ["name", "source", "product_id", "start_date", "end_date"])
    out = campaign_out(campaign, product)
    await db.commit()
    return out


@router.patch("/campaigns/{campaign_id}", response_model=TelCampaignOut)
async def update_campaign(campaign_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """P4: moving to another product needs an active one; keeping a since-deactivated product is allowed. AC4 on the merged row."""
    require_manager(user)
    campaign = await _locked(db, TelCampaign, campaign_id, "Campaign")
    changes = _body(TelCampaignUpdate, payload).model_dump(exclude_unset=True)
    _check_dates(changes.get("start_date", campaign.start_date), changes.get("end_date", campaign.end_date))
    if changes.get("product_id", campaign.product_id) != campaign.product_id:
        product = await locked_active_product(db, changes["product_id"])
    else:
        product = await db.get(TelProduct, campaign.product_id)
    fields = apply_changes(campaign, changes)
    await flush_unique(db, CAMPAIGN_NAME_INDEX, f"A campaign named “{campaign.name}” already exists")
    if fields:
        audit(db, user, "telecaller.campaign_update", "tel_campaign", campaign.id, fields)
    out = campaign_out(campaign, product)
    await db.commit()
    return out
