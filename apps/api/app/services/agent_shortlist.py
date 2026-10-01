"""AGN-007 / DEC-SCOPE-049 -- an agency's own universities and a student's university shortlist.

Functions only (the shape of services/agent_students.py); write functions never commit -- the router locks the agency, writes,
audits and commits once. Spec: docs/superpowers/specs/2026-10-01-agn-007-student-shortlist-design.md.
"""

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentStudentShortlistEntry, AgentUniversity, Country, OverseasCourse, University, User
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


MAX_ENTRIES_PER_STUDENT = 50
ENTRY_FIELDS = ("university_id", "agent_university_id", "course_id", "course_title", "intake", "tuition_fee", "entry_requirements")
COURSE_MISMATCH = "Course does not belong to selected university"  # verbatim from workflows.py (OVS-002)
Entry = AgentStudentShortlistEntry


def _entry_stmt():
    return (
        select(Entry, University, Country, AgentUniversity, OverseasCourse, User)
        .outerjoin(University, University.id == Entry.university_id)
        .outerjoin(Country, Country.id == University.country_id)
        .outerjoin(AgentUniversity, AgentUniversity.id == Entry.agent_university_id)
        .outerjoin(OverseasCourse, OverseasCourse.id == Entry.course_id)
        .outerjoin(User, User.id == Entry.created_by_user_id)
    )


def entry_item(entry: Entry, university: University | None, country: Country | None, agency: AgentUniversity | None, course: OverseasCourse | None, creator: User | None) -> dict:
    """Explicit allowlist. Country comes from the university, never from the entry (D7)."""
    if university is not None:
        uni = {"source": "catalogue", "id": university.id, "name": university.name, "slug": university.slug, "country": country.name if country else None}
    else:
        uni = {"source": "agency", "id": agency.id, "name": agency.name, "slug": None, "country": agency.country}
    if course is not None:
        course_out = {"id": course.id, "title": course.title}
    elif entry.course_title:
        course_out = {"id": None, "title": entry.course_title}
    else:
        course_out = None
    return {
        "id": entry.id, "university": uni, "course": course_out, "intake": entry.intake, "tuition_fee": entry.tuition_fee,
        "entry_requirements": entry.entry_requirements, "created_by": creator.full_name if creator else None,
        "created_at": entry.created_at, "updated_at": entry.updated_at,
    }


async def entry_page(db: AsyncSession, student_id, *, limit: int, offset: int) -> dict:
    total = await db.scalar(select(func.count()).select_from(Entry).where(Entry.agent_student_id == student_id))
    rows = (await db.execute(_entry_stmt().where(Entry.agent_student_id == student_id).order_by(Entry.created_at, Entry.id).limit(limit).offset(offset))).all()
    return {"items": [entry_item(*r) for r in rows], "total": total or 0, "limit": limit, "offset": offset}


async def entry_detail(db: AsyncSession, entry_id) -> dict:
    return entry_item(*(await db.execute(_entry_stmt().where(Entry.id == entry_id).execution_options(populate_existing=True))).one())


async def load_entry(db: AsyncSession, student_id, entry_id, *, lock: bool = False) -> Entry:
    stmt = select(Entry).where(Entry.id == entry_id, Entry.agent_student_id == student_id).execution_options(populate_existing=True)
    row = await db.scalar(stmt.with_for_update() if lock else stmt)
    if row is None:
        raise HTTPException(404, "Shortlist entry not found")
    return row


def entry_values(entry: Entry) -> dict:
    return {k: getattr(entry, k) for k in ENTRY_FIELDS}


async def validate_entry(db: AsyncSession, org_id, values: dict) -> None:
    """Spec §5.4 steps 1-6 on the complete (created or merged) entry. Another agency's university reads exactly like an unknown id."""
    if (values["university_id"] is None) == (values["agent_university_id"] is None):
        raise HTTPException(422, "Choose a catalogue university or one of your agency's universities")
    if values["university_id"] is not None and await db.get(University, values["university_id"]) is None:
        raise HTTPException(422, "University not found")
    if values["agent_university_id"] is not None:
        found = await db.scalar(select(AgentUniversity.id).where(AgentUniversity.id == values["agent_university_id"], AgentUniversity.org_id == org_id))
        if found is None:
            raise HTTPException(422, "University not found")
    if values["course_id"] is not None and values["course_title"] is not None:
        raise HTTPException(422, "Choose a catalogue course or type a course, not both")
    if values["course_id"] is not None:
        if values["university_id"] is None:
            raise HTTPException(422, "Catalogue courses can only be chosen with a catalogue university")
        course = await db.get(OverseasCourse, values["course_id"])
        if course is None or course.university_id != values["university_id"]:
            raise HTTPException(422, COURSE_MISMATCH)


async def ensure_entry_capacity(db: AsyncSession, student_id) -> None:
    count = await db.scalar(select(func.count()).select_from(Entry).where(Entry.agent_student_id == student_id))
    if count >= MAX_ENTRIES_PER_STUDENT:
        raise HTTPException(422, f"This student's shortlist is full ({MAX_ENTRIES_PER_STUDENT} entries)")
