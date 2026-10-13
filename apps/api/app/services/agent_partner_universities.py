"""dtu-001 (DEC-SCOPE-209 §6): the agent portal's Partner Universities -- the published catalogue (public_visible) with its courses.
Read-only. The agent commission is added only for a Master (agent_commission_access)."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Country, OverseasCourse, University, User
from app.services.agent_commission_access import with_agent_commission
from app.services.partnership_universities import public_visible

COURSE_KEYS = ("id", "title", "level", "category", "duration", "campus", "fee_text", "intake_text", "tuition_fee", "intake")


def _row(user: User, uni: University, country: Country, course_count: int) -> dict:
    return with_agent_commission(user, uni, {
        "id": uni.id, "slug": uni.slug, "name": uni.name, "logo_url": uni.logo_url, "city": uni.city, "campuses": uni.campuses or [],
        "country": {"id": country.id, "name": country.name, "iso2": country.iso2}, "course_count": course_count,
    })


async def page(db: AsyncSession, user: User, *, q: str | None, country: UUID | None, limit: int, offset: int) -> dict:
    courses = select(OverseasCourse.university_id, func.count().label("n")).where(OverseasCourse.active.is_(True)).group_by(OverseasCourse.university_id).subquery()
    stmt = select(University, Country, func.coalesce(courses.c.n, 0)).join(Country, University.country_id == Country.id).outerjoin(courses, courses.c.university_id == University.id).where(*public_visible())
    if q:
        stmt = stmt.where(or_(University.name.ilike(f"%{q}%"), University.city.ilike(f"%{q}%")))
    if country:
        stmt = stmt.where(University.country_id == country)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(stmt.order_by(University.name, University.id).limit(limit).offset(offset))).all()
    return {"items": [_row(user, u, c, n) for u, c, n in rows], "total": total}


async def detail(db: AsyncSession, user: User, university_id: UUID) -> dict:
    found = (await db.execute(select(University, Country).join(Country, University.country_id == Country.id).where(University.id == university_id, *public_visible()))).first()
    if found is None:
        raise HTTPException(404, "University not found")
    uni, country = found
    cs = (await db.scalars(select(OverseasCourse).where(OverseasCourse.university_id == uni.id, OverseasCourse.active.is_(True)).order_by(OverseasCourse.level, OverseasCourse.title))).all()
    body = {
        **_row(user, uni, country, len(cs)),
        "website": uni.website, "overview": uni.overview, "fee_structure": uni.fee_structure, "deadlines": uni.deadlines, "scholarships": uni.scholarships,
        "courses": [{k: getattr(c, k) for k in COURSE_KEYS} for c in cs],
    }
    return {"university": body}
