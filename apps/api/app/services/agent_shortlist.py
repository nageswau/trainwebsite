"""AGN-007 / DEC-SCOPE-049 -- an agency's own universities and a student's university shortlist.

Functions only (the shape of services/agent_students.py); write functions never commit -- the router locks the agency, writes,
audits and commits once. Spec: docs/superpowers/specs/2026-10-01-agn-007-student-shortlist-design.md.
"""

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentStudentShortlistEntry, AgentUniversity, User
from app.services.agent_students import _contains

MAX_UNIVERSITIES_PER_AGENCY = 500
DUPLICATE_UNIVERSITY = "This university is already in your agency's list"


def university_item(row: AgentUniversity) -> dict:
    return {"id": row.id, "name": row.name, "country": row.country, "city": row.city, "entry_requirements": row.entry_requirements, "created_at": row.created_at, "updated_at": row.updated_at}


async def university_page(db: AsyncSession, org_id, *, q: str | None, limit: int, offset: int) -> dict:
    filters = [AgentUniversity.org_id == org_id]
    term = (q or "").strip()
    if term:
        filters.append(or_(_contains(AgentUniversity.name, term), _contains(AgentUniversity.country, term), _contains(AgentUniversity.city, term)))
    total = await db.scalar(select(func.count()).select_from(AgentUniversity).where(*filters))
    rows = (await db.scalars(select(AgentUniversity).where(*filters).order_by(func.lower(AgentUniversity.name), AgentUniversity.id).limit(limit).offset(offset))).all()
    return {"items": [university_item(r) for r in rows], "total": total or 0, "limit": limit, "offset": offset}


async def load_university(db: AsyncSession, org_id, university_id, *, lock: bool = False) -> AgentUniversity:
    """The caller's agency's university or 404 -- the agency is in the WHERE clause, never checked after loading."""
    stmt = select(AgentUniversity).where(AgentUniversity.id == university_id, AgentUniversity.org_id == org_id).execution_options(populate_existing=True)
    row = await db.scalar(stmt.with_for_update() if lock else stmt)
    if row is None:
        raise HTTPException(404, "University not found")
    return row


async def ensure_university_capacity(db: AsyncSession, org_id) -> None:
    count = await db.scalar(select(func.count()).select_from(AgentUniversity).where(AgentUniversity.org_id == org_id))
    if count >= MAX_UNIVERSITIES_PER_AGENCY:
        raise HTTPException(422, f"Your agency has reached the limit of {MAX_UNIVERSITIES_PER_AGENCY} universities")


async def ensure_unique_university(db: AsyncSession, org_id, name: str, country: str, exclude_id=None) -> None:
    stmt = select(AgentUniversity.id).where(AgentUniversity.org_id == org_id, func.lower(AgentUniversity.name) == name.lower(), func.lower(AgentUniversity.country) == country.lower())
    if exclude_id is not None:
        stmt = stmt.where(AgentUniversity.id != exclude_id)
    if await db.scalar(stmt.limit(1)) is not None:
        raise HTTPException(409, DUPLICATE_UNIVERSITY)


async def university_usage(db: AsyncSession, university_id) -> int:
    return await db.scalar(select(func.count()).select_from(AgentStudentShortlistEntry).where(AgentStudentShortlistEntry.agent_university_id == university_id)) or 0


def in_use_message(count: int) -> str:
    return f"This university is on {count} shortlist {'entry' if count == 1 else 'entries'}; remove it from them first"


def apply_changes(row, changes: dict, user: User) -> list[str]:
    """Sets only the fields whose value differs; returns their names (sorted). Nothing changed -> [] and no audit (AGN-004)."""
    changed = sorted(k for k, v in changes.items() if getattr(row, k) != v)
    for key in changed:
        setattr(row, key, changes[key])
    if changed:
        row.updated_by_user_id = user.id
    return changed
