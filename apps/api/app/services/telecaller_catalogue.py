"""tel-002 (DEC-SCOPE-074, spec §4): the product/interest catalogue and campaign rules every later tel item reads.

Functions only; nothing here commits -- the route owns the transaction. Audit rows carry ids and changed field names only."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Program, TelCampaign, TelProduct, User

# P1: who may read the catalogue; managers and super_admin also see inactive rows (and alone may write, services/telecaller).
READERS = frozenset({"telecaller", "telecaller_manager", "super_admin", "it_admin", "overseas_admin", "counselor"})
FIXED_TEAM_RULE = {"it": "IT products always route to the IT team", "overseas": "Overseas products always route to the Overseas team"}
PRODUCT_NAME_INDEX, CAMPAIGN_NAME_INDEX = "uq_tel_products_group_name", "uq_tel_campaigns_name"


def require_reader(user: User) -> None:
    if user.role not in READERS:
        raise HTTPException(403, "Your role cannot view the telecaller catalogue")


def sees_inactive(user: User) -> bool:
    return user.role in ("telecaller_manager", "super_admin")


def active_filters(user: User, column, active: bool | None) -> list:
    """`active` narrows; a reader who may not see inactive rows always gets active ones only, whatever they ask (AC2)."""
    filters = [] if active is None else [column.is_(active)]
    return filters if sees_inactive(user) else [*filters, column.is_(True)]


def check_team(group: str, team: str | None) -> None:
    """P2: an IT/Overseas product's team is its group; only an Other product's team is chosen (none = the unassigned queue)."""
    if group in FIXED_TEAM_RULE and team != group:
        raise HTTPException(422, FIXED_TEAM_RULE[group])


async def active_program(db: AsyncSession, group: str, program_id) -> Program:
    if group != "it":
        raise HTTPException(422, "Only IT products can link to a course")
    program = await db.get(Program, program_id)
    if not program or not program.active:
        raise HTTPException(422, "Choose an active course")
    return program


async def locked_active_product(db: AsyncSession, product_id) -> TelProduct:
    """FOR SHARE: a concurrent deactivation of this product waits for the campaign's commit, so a campaign is never committed against
    a product deactivated in the same instant (P4)."""
    product = await db.scalar(select(TelProduct).where(TelProduct.id == product_id).with_for_update(read=True))
    if not product or not product.active:
        raise HTTPException(422, "Choose an active product")
    return product


async def flush_unique(db: AsyncSession, index: str, message: str) -> None:
    """The unique index decides a duplicate name (case-insensitive) even under a race; the whole transaction rolls back."""
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if index in str(exc.orig):
            raise HTTPException(409, message) from None
        raise


def apply_changes(row, changes: dict) -> list[str]:
    """Sets only the values that differ; returns their field names (the audit form)."""
    changed = sorted(key for key, value in changes.items() if getattr(row, key) != value)
    for key in changed:
        setattr(row, key, changes[key])
    return changed


def audit(db: AsyncSession, user: User, action: str, entity_type: str, entity_id, fields: list[str]) -> None:
    db.add(AuditLog(user_id=user.id, action=action, entity_type=entity_type, entity_id=str(entity_id), metadata_json={"fields": fields}))


def product_out(product: TelProduct, program: Program | None) -> dict:
    return {
        "id": product.id,
        "group": product.product_group,
        "name": product.name,
        "team": product.team,
        "program": {"id": program.id, "title": program.title} if program else None,
        "active": product.active,
        "sort_order": product.sort_order,
    }


def campaign_out(campaign: TelCampaign, product: TelProduct) -> dict:
    return {
        "id": campaign.id,
        "name": campaign.name,
        "source": campaign.source,
        "product": {"id": product.id, "name": product.name, "group": product.product_group, "active": product.active},
        "start_date": campaign.start_date,
        "end_date": campaign.end_date,
        "active": campaign.active,
    }
