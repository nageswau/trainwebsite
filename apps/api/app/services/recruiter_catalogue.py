"""rec-002 (DEC-SCOPE-117, spec §4): who may read the recruiter managed lists, and the lookups every later rec item's pickers rely on.

Functions only; nothing here commits -- the route owns the transaction. The tel-002 write helpers (flush_unique, apply_changes, audit)
are reused as they are: the rules are identical."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import REC_CATALOGUE_MODELS, RecCampaign, RecLeadSource, User
from app.services.recruiter import MANAGER_ROLE, ROLE

# C3: recruiters read; managers and super_admin also see inactive values and alone may write (services/recruiter.require_manager).
READERS = frozenset({ROLE, MANAGER_ROLE, "super_admin"})
CAMPAIGN_NAME_INDEX = "uq_rec_campaigns_name"


def require_reader(user: User) -> None:
    if user.role not in READERS:
        raise HTTPException(403, "Your role cannot view the recruiter catalogues")


def active_filters(user: User, column, active: bool | None) -> list:
    """`active` narrows; a recruiter always gets active values only, whatever they ask (AC2 -- what a picker offers)."""
    filters = [] if active is None else [column.is_(active)]
    return [*filters, column.is_(True)] if user.role == ROLE else filters


def catalogue_model(kind: str):
    model = REC_CATALOGUE_MODELS.get(kind)
    if model is None:
        raise HTTPException(404, "Catalogue not found")
    return model


async def locked_active_lead_source(db: AsyncSession, source_id) -> RecLeadSource:
    """FOR SHARE: a concurrent deactivation of this source waits for the campaign's commit (the tel-002 P4 rule)."""
    source = await db.scalar(select(RecLeadSource).where(RecLeadSource.id == source_id).with_for_update(read=True))
    if not source or not source.active:
        raise HTTPException(422, "Choose an active lead source")
    return source


def value_out(row) -> dict:
    return {"id": row.id, "name": row.name, "active": row.active, "sort_order": row.sort_order}


def campaign_out(campaign: RecCampaign, source: RecLeadSource) -> dict:
    return {
        "id": campaign.id,
        "name": campaign.name,
        "lead_source": {"id": source.id, "name": source.name, "active": source.active},
        "start_date": campaign.start_date,
        "end_date": campaign.end_date,
        "active": campaign.active,
    }
