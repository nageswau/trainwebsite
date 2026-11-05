"""hrc-020 (DEC-SCOPE-401 X1-X7): saved Find Candidates searches. A user sees their own and every shared one; only the owner (or
super_admin) changes or deletes one. `filters` is stored as the canonical search body, so loading it runs the same search (AC1). On read,
keys the search no longer declares -- and, for a reader without the compensation grant, the package filters and sort -- are dropped
and named in `ignored` (the edge case and X5)."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SavedCandidateSearch, User
from app.schemas import CANDIDATE_SEARCH_LABELS, CANDIDATE_SEARCH_PACKAGE_FIELDS, CandidateSearch

logger = logging.getLogger("app.saved_searches")

MAX_PER_OWNER = 50  # X7
NOT_FOUND = "Saved search not found"
NOT_OWNER = "Only the person who saved this search can change it"
DUPLICATE = "You already have a saved search with this name"


def stored(body: CandidateSearch) -> dict:
    """X2: the search body as stored -- defaults left out, JSON types."""
    return body.model_dump(mode="json", exclude_defaults=True)


def visible(user: User):
    return or_(SavedCandidateSearch.owner_user_id == user.id, SavedCandidateSearch.shared.is_(True))


async def listed(db: AsyncSession, user: User) -> list[tuple[SavedCandidateSearch, str]]:
    """Own first, then shared; each by name. With the owner's display name."""
    stmt = (select(SavedCandidateSearch, User.full_name).join(User, User.id == SavedCandidateSearch.owner_user_id).where(visible(user))
            .order_by((SavedCandidateSearch.owner_user_id != user.id), func.lower(SavedCandidateSearch.name), SavedCandidateSearch.id))  # fmt: skip
    return [(row, name) for row, name in (await db.execute(stmt)).all()]


async def load_for_write(db: AsyncSession, user: User, search_id: UUID) -> SavedCandidateSearch:
    """X4: invisible -> 404; visible but someone else's -> 403 (super_admin may change any)."""
    stmt = select(SavedCandidateSearch).where(SavedCandidateSearch.id == search_id)
    if user.role != "super_admin":
        stmt = stmt.where(visible(user))
    row = await db.scalar(stmt.with_for_update())
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    if row.owner_user_id != user.id and user.role != "super_admin":
        raise HTTPException(403, NOT_OWNER)
    return row


async def require_room(db: AsyncSession, user: User) -> None:
    count = await db.scalar(select(func.count()).select_from(SavedCandidateSearch).where(SavedCandidateSearch.owner_user_id == user.id))
    if count >= MAX_PER_OWNER:
        raise HTTPException(422, f"You can keep at most {MAX_PER_OWNER} saved searches; delete one first")


async def name_taken(db: AsyncSession, owner_id: UUID, name: str, exclude: UUID | None = None) -> bool:
    stmt = select(SavedCandidateSearch.id).where(SavedCandidateSearch.owner_user_id == owner_id, func.lower(SavedCandidateSearch.name) == name.lower())
    if exclude is not None:
        stmt = stmt.where(SavedCandidateSearch.id != exclude)
    return (await db.scalar(stmt.limit(1))) is not None


def usable(filters: dict, sees_compensation: bool) -> tuple[dict, list[str]]:
    """The edge case / X5: the stored filters minus keys the search no longer declares (named as stored) and, without the grant, the
    package filters and sort (named by their labels)."""
    kept, ignored = {}, []
    for key, value in filters.items():
        if key not in CandidateSearch.model_fields:
            ignored.append(key)
        elif not sees_compensation and (key in CANDIDATE_SEARCH_PACKAGE_FIELDS or (key == "sort" and value == "package")):
            ignored.append(CANDIDATE_SEARCH_LABELS[key])
        else:
            kept[key] = value
    return kept, ignored


def out(row: SavedCandidateSearch, owner_name: str, user: User, sees_compensation: bool) -> dict:
    filters, ignored = usable(row.filters or {}, sees_compensation)
    return {
        "id": row.id, "name": row.name, "filters": filters, "ignored": ignored, "shared": row.shared, "mine": row.owner_user_id == user.id,
        "can_edit": row.owner_user_id == user.id or user.role == "super_admin", "owner": {"id": row.owner_user_id, "name": owner_name},
        "updated_at": row.updated_at,
    }  # fmt: skip


def log(event: str, user: User, row: SavedCandidateSearch) -> None:
    """Ids and flags only -- never the name or the filters (they can name a person's skills)."""
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "search_id": str(row.id), "shared": row.shared}})
