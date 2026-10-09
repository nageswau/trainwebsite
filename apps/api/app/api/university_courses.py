"""upc-017 (DEC-SCOPE-147, spec §3): the §16 course master -- a university's courses (list, add, edit, deactivate), the form's scholarship
options and the "Courses & Programs" menu list. The CSV import lives in `university_course_import`.

Every write: the read gate (403), the university row FOR UPDATE (404), the write permission (403 role/team, 409 inactive), the commission
gate (403, CO2), the course row FOR UPDATE (404, this university's only), the merged-row checks (422 / 409 duplicate), the change and an
audit row, one commit here, then a structured log (ids and field names only). Lists are {items, total, limit, offset}; every course payload
passes through `strip_commission` (U2)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import OFFSET
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import COURSE_LEVELS, Country, OverseasCourse, University, User
from app.schemas import CourseIn, CourseUpdate
from app.services import partnership_universities as unis
from app.services import university_courses as svc

router = APIRouter(prefix="/partnership", tags=["partnership-courses"])
PAGE = Query(50, ge=1, le=50)


async def _one(db: AsyncSession, user: User, course: OverseasCourse) -> dict:
    await db.refresh(course)  # server defaults (timestamps) are expired after a flush
    return {"course": (await svc.courses_out(db, user, [course], {course.university_id}))[0]}


@router.get("/universities/{university_id}/courses")
async def list_courses(
    university_id: UUID,
    include_inactive: bool = False,
    limit: int = PAGE,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """By title; the active offer unless `include_inactive` (CO11)."""
    await unis.require_reader(db, user)
    uni = await unis.load(db, university_id)
    can_edit = unis.permissions(user, uni, await unis.team_of(db, user))["can_edit"]
    base = select(OverseasCourse).where(OverseasCourse.university_id == uni.id, *([] if include_inactive else [OverseasCourse.active.is_(True)]))
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.scalars(base.order_by(*svc.ORDER).limit(limit).offset(offset))).all()
    items = await svc.courses_out(db, user, list(rows), {uni.id} if can_edit else set())
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset, "can_edit": can_edit}


@router.get("/universities/{university_id}/course-options")
async def course_options(university_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """What a writer may pick: the scholarships of this university or its country (CO9)."""
    await unis.require_reader(db, user)
    uni = await unis.load(db, university_id)
    unis.require(user, uni, await unis.team_of(db, user), "can_edit", "course_options")
    return {"scholarships": await svc.scholarship_options(db, uni)}


@router.post("/universities/{university_id}/courses", status_code=201)
async def create_course(university_id: UUID, payload: CourseIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    uni = await svc.writable_university(db, user, university_id, "course_create")
    # The commission gate applies only when the field is sent: a non-commission role creates without ever naming it (CO2).
    values = svc.stored(user, payload.model_dump(exclude=set() if "commission" in payload.model_fields_set else {"commission"}))
    await svc.check_values(db, uni, values)
    course = OverseasCourse(university_id=uni.id, tuition_fee="", intake="", **values)
    svc.derive_texts(course, set(values))
    db.add(course)
    await db.flush()
    svc.record(db, user, course, "create", changed=sorted(k for k, v in values.items() if v not in (None, "", [])))
    await db.commit()
    svc.log("university_course_created", user, course)
    return await _one(db, user, course)


@router.patch("/universities/{university_id}/courses/{course_id}")
async def update_course(university_id: UUID, course_id: UUID, payload: CourseUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Only the fields sent; an equal value is not a change. Deactivating keeps every application's course (CO11)."""
    uni = await svc.writable_university(db, user, university_id, "course_update")
    changes = svc.stored(user, payload.model_dump(exclude_unset=True))
    course = await svc.load(db, uni.id, course_id)
    changed = sorted(k for k, v in changes.items() if getattr(course, k) != v)
    if changed:
        await svc.check_values(db, uni, {k: getattr(course, k) for k in svc.FIELDS} | {k: changes[k] for k in changed}, course.id)
        for key in changed:
            setattr(course, key, changes[key])
        svc.derive_texts(course, set(changed))
        svc.record(db, user, course, "update", changed=changed)
        await db.commit()
        svc.log("university_course_updated", user, course, fields=svc.field_names(changed))
    return await _one(db, user, course)


@router.get("/courses")
async def menu_courses(
    q: str | None = Query(None, max_length=100),
    level: Literal[COURSE_LEVELS] | None = None,
    status: Literal["active", "inactive", "all"] = "active",
    limit: int = PAGE,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """CO15: every university's courses by university then title; `q` matches the title or the university's name or code."""
    await unis.require_reader(db, user)
    filters = []
    if level is not None:
        filters.append(OverseasCourse.level == level)
    if status != "all":
        filters.append(OverseasCourse.active.is_(status == "active"))
    if (pattern := like_pattern(q)) is not None:
        filters.append(or_(*(c.ilike(pattern, escape="\\") for c in (OverseasCourse.title, University.name, University.university_code))))
    base = select(OverseasCourse, University, Country).join(University, University.id == OverseasCourse.university_id).join(Country, Country.id == University.country_id).where(*filters)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = (await db.execute(base.order_by(University.name, *svc.ORDER).limit(limit).offset(offset))).all()
    team = await unis.team_of(db, user)
    editable = {uni.id for _, uni, _ in rows if unis.permissions(user, uni, team)["can_edit"]}
    courses = await svc.courses_out(db, user, [c for c, _, _ in rows], editable)
    items = [item | {"university": {"id": uni.id, "name": uni.name, "university_code": uni.university_code, "country": country.name}} for item, (_, uni, country) in zip(courses, rows, strict=True)]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}
