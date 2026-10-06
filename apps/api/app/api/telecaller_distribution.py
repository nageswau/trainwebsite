"""tel-007 (DEC-SCOPE-087, spec §5): distribution rules, the unassigned queue, the team's assigned leads and manual (re)assignment.

Inline checks per the 2026-09-28 convention: role first (`require_manager`), then scope -- a lead outside tel-004's manager scope is a 404,
a target outside the caller's direct reports a 403 (AC5) -- then the write. Registered before `telecaller.router` in main.py, so a later
`/telecaller/leads/{id}` route cannot shadow the static `/leads/unassigned|assigned|assign` paths."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.lead_stages import label
from app.models import AuditLog, Enquiry, TelDistributionRule, TelecallerProfile, TelProduct, User
from app.schemas import (
    TelDistributionRuleCreate,
    TelDistributionRuleOut,
    TelDistributionRulePage,
    TelDistributionRuleUpdate,
    TelLeadAssign,
    TelLeadAssignOut,
    TelQueueLeadPage,
)
from app.services import lead_distribution, lead_pipeline
from app.services.telecaller import TEAM_LABEL, person_ref, require_manager
from app.services.telecaller_catalogue import flush_unique

router = APIRouter(prefix="/telecaller", tags=["telecaller-distribution"])

RULE_NOT_FOUND = "Rule not found"
DUPLICATE = {"product": "This team already has a rule for this product", "city": "This team already has a rule for this city"}
INDEX = {"product": "uq_tel_distribution_rules_product", "city": "uq_tel_distribution_rules_city"}


# --- rules (DI3, D6) -----------------------------------------------------------------------------------------------------------
def _rule_rows():
    return (
        select(TelDistributionRule, User, TelProduct, TelecallerProfile.reporting_manager_user_id)
        .join(User, User.id == TelDistributionRule.telecaller_user_id)
        .join(TelecallerProfile, TelecallerProfile.user_id == User.id)
        .outerjoin(TelProduct, TelProduct.id == TelDistributionRule.product_id)
    )


def _rule_out(actor: User, rule: TelDistributionRule, tel: User, product: TelProduct | None, manager_id: UUID) -> dict:
    return {
        "id": rule.id, "team": rule.team, "kind": rule.kind, "city": rule.city, "telecaller": person_ref(tel),
        "product": {"id": product.id, "name": product.name, "active": product.active} if product else None,
        "editable": actor.role == "super_admin" or manager_id == actor.id,
    }


async def _rule_one(db: AsyncSession, actor: User, rule_id: UUID) -> dict:
    return _rule_out(actor, *(await db.execute(_rule_rows().where(TelDistributionRule.id == rule_id).execution_options(populate_existing=True))).one())


async def _check_match(db: AsyncSession, data: TelDistributionRuleCreate) -> None:
    if data.kind == "product":
        if data.product_id is None:
            raise HTTPException(422, "Choose a product")
        if data.city is not None:
            raise HTTPException(422, "A product rule has no city")
        product = await db.get(TelProduct, data.product_id)
        if product is None or not product.active:
            raise HTTPException(422, "Choose an active product")
        if product.team is None:
            raise HTTPException(422, "This product has no team: its leads wait in the unassigned queue")
        if product.team != data.team:
            raise HTTPException(422, f"This product belongs to the {TEAM_LABEL[product.team]} team")
    else:
        if data.product_id is not None:
            raise HTTPException(422, "A city rule has no product")
        if data.city is None:
            raise HTTPException(422, "Enter a city")


async def _locked_editable_rule(db: AsyncSession, actor: User, rule_id: UUID) -> TelDistributionRule:
    """404 when missing; 403 unless the rule's telecaller reports to the actor (super_admin: any)."""
    rule = await db.scalar(select(TelDistributionRule).where(TelDistributionRule.id == rule_id).with_for_update())
    if rule is None:
        raise HTTPException(404, RULE_NOT_FOUND)
    if actor.role != "super_admin":
        manager_id = await db.scalar(select(TelecallerProfile.reporting_manager_user_id).where(TelecallerProfile.user_id == rule.telecaller_user_id))
        if manager_id != actor.id:
            raise HTTPException(403, "You can only change rules for your direct reports")
    return rule


def _audit(db: AsyncSession, actor: User, action: str, rule: TelDistributionRule) -> None:
    db.add(AuditLog(user_id=actor.id, action=action, entity_type="tel_distribution_rule", entity_id=str(rule.id),
                    metadata_json={"team": rule.team, "kind": rule.kind, "telecaller_user_id": str(rule.telecaller_user_id)}))


@router.get("/distribution-rules", response_model=TelDistributionRulePage)
async def rules(
    team: Literal["it", "overseas"] | None = None,
    kind: Literal["product", "city"] | None = None,
    telecaller_user_id: UUID | None = None,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DI3: every manager reads every rule of both teams; `editable` says which they may change."""
    require_manager(user)
    filters = [column == value for column, value in (
        (TelDistributionRule.team, team), (TelDistributionRule.kind, kind), (TelDistributionRule.telecaller_user_id, telecaller_user_id)) if value]
    stmt = _rule_rows().where(*filters)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    order = (TelDistributionRule.team, TelDistributionRule.kind, func.lower(func.coalesce(TelProduct.name, TelDistributionRule.city)), TelDistributionRule.id)
    rows = (await db.execute(stmt.order_by(*order).limit(limit).offset(offset))).all()
    return {"items": [_rule_out(user, *row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.post("/distribution-rules", status_code=201, response_model=TelDistributionRuleOut)
async def create_rule(payload: TelDistributionRuleCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_manager(user)
    await _check_match(db, payload)
    await lead_distribution.assignee(db, user, payload.telecaller_user_id, payload.team)
    rule = TelDistributionRule(team=payload.team, kind=payload.kind, product_id=payload.product_id, city=payload.city,
                               telecaller_user_id=payload.telecaller_user_id)
    db.add(rule)
    await flush_unique(db, INDEX[payload.kind], DUPLICATE[payload.kind])
    _audit(db, user, "telecaller.rule_create", rule)
    out = await _rule_one(db, user, rule.id)
    await db.commit()
    return out


@router.patch("/distribution-rules/{rule_id}", response_model=TelDistributionRuleOut)
async def update_rule(rule_id: UUID, payload: TelDistributionRuleUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """D6: only the telecaller changes; a different match is a delete and a create."""
    require_manager(user)
    rule = await _locked_editable_rule(db, user, rule_id)
    await lead_distribution.assignee(db, user, payload.telecaller_user_id, rule.team)
    rule.telecaller_user_id = payload.telecaller_user_id
    _audit(db, user, "telecaller.rule_update", rule)
    await db.flush()
    out = await _rule_one(db, user, rule.id)
    await db.commit()
    return out


@router.delete("/distribution-rules/{rule_id}", status_code=204)
async def delete_rule(rule_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_manager(user)
    rule = await _locked_editable_rule(db, user, rule_id)
    _audit(db, user, "telecaller.rule_delete", rule)
    await db.delete(rule)
    await db.commit()
    return Response(status_code=204)


# --- the queue, the team's leads and manual assignment (DI4, D3) -------------------------------------------------------------------
def _reports(user: User):
    return select(TelecallerProfile.user_id).where(TelecallerProfile.reporting_manager_user_id == user.id)


async def _lead_page(db: AsyncSession, filters: list, q: str | None, newest: bool, limit: int, offset: int) -> dict:
    filters = filters + _matching(like_pattern(q), Enquiry.lead_code, Enquiry.name, Enquiry.city)
    stmt = (select(Enquiry, TelProduct, User).outerjoin(TelProduct, TelProduct.id == Enquiry.product_id)
            .outerjoin(User, User.id == Enquiry.telecaller_user_id).where(*filters))
    total = await db.scalar(select(func.count()).select_from(Enquiry).where(*filters))
    order = (Enquiry.created_at.desc(), Enquiry.id.desc()) if newest else (Enquiry.created_at, Enquiry.id)
    rows = (await db.execute(stmt.order_by(*order).limit(limit).offset(offset))).all()
    items = [
        {
            "id": x.id, "lead_code": x.lead_code, "name": x.name, "division": x.division, "city": x.city, "source": x.source,
            "product": {"id": product.id, "name": product.name} if product else None,
            "status": x.status, "status_label": label(x.status), "telecaller": person_ref(tel) if tel else None, "created_at": x.created_at,
        }
        for x, product, tel in rows
    ]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


@router.get("/leads/unassigned", response_model=TelQueueLeadPage)
async def unassigned_leads(team: Literal["it", "overseas"] | None = None, q: str | None = SEARCH, limit: int = LIMIT, offset: int = OFFSET,
                           user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """T23: the unassigned leads of the teams the manager's reports are on (super_admin: all), oldest first -- a queue."""
    require_manager(user)
    filters = [Enquiry.telecaller_user_id.is_(None)]
    if user.role != "super_admin":
        filters.append(Enquiry.division.in_(select(TelecallerProfile.team).where(TelecallerProfile.reporting_manager_user_id == user.id)))
    if team:
        filters.append(Enquiry.division == team)
    return await _lead_page(db, filters, q, False, limit, offset)


@router.get("/leads/assigned", response_model=TelQueueLeadPage)
async def assigned_leads(telecaller_user_id: UUID | None = None, team: Literal["it", "overseas"] | None = None, q: str | None = SEARCH,
                         limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """DI4: the leads of the manager's direct reports (super_admin: every assigned lead), newest first. Another manager's report is a 404."""
    require_manager(user)
    filters = [Enquiry.telecaller_user_id.is_not(None) if user.role == "super_admin" else Enquiry.telecaller_user_id.in_(_reports(user))]
    if telecaller_user_id:
        mine = select(TelecallerProfile.user_id).where(TelecallerProfile.user_id == telecaller_user_id)
        if user.role != "super_admin":
            mine = mine.where(TelecallerProfile.reporting_manager_user_id == user.id)
        if await db.scalar(mine) is None:
            raise HTTPException(404, "Telecaller not found")
        filters.append(Enquiry.telecaller_user_id == telecaller_user_id)
    if team:
        filters.append(Enquiry.division == team)
    return await _lead_page(db, filters, q, True, limit, offset)


@router.post("/leads/assign", response_model=TelLeadAssignOut)
async def assign_leads(payload: TelLeadAssign, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """D3: all or nothing. Leads are locked in id order (two bulk assignments never deadlock); one audit row per changed lead (D4)."""
    require_manager(user)
    _, scope = lead_pipeline.scope(user)
    leads = (await db.scalars(select(Enquiry).where(Enquiry.id.in_(payload.lead_ids), *scope).order_by(Enquiry.id)
                              .with_for_update().execution_options(populate_existing=True))).all()
    if len(leads) != len(payload.lead_ids):
        raise HTTPException(404, lead_pipeline.LEAD_NOT_FOUND)
    teams = {x.division for x in leads}
    if len(teams) > 1:
        raise HTTPException(422, "Choose leads from one team")
    target = await lead_distribution.assignee(db, user, payload.telecaller_user_id, teams.pop())
    changed = [x for x in leads if x.telecaller_user_id != target.id]
    for x in changed:
        await lead_distribution.assign(db, x, target.id, "manual", user)
    await db.commit()
    return {"assigned": len(changed), "unchanged": len(leads) - len(changed)}
