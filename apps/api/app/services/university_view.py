"""upc-030 (DEC-SCOPE-161, spec §2 UV1-UV12): the University 360 view for the roles outside the partnership team (U14).

One university record; each role reads only its slice. The slicing is the confidentiality boundary, so every section is built from an
explicit allow-list (never the master payload with fields removed), and courses also pass `strip_commission`:
- counselor (overseas) / overseas_admin: profile, partnership status, shareable contacts, active courses, shareable documents, applications
  (a counselor's own; overseas_admin all);
- bdm / bdm_manager: profile, partnership status, the primary partnership manager (U13);
- university_rep: their own university's profile and active courses.
No slice has commission data (U2). Functions only; reads are not audited (the route audits a document download).
"""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Country, OverseasApplication, OverseasCourse, University, UniversityContact, UniversityContactRole, UniversityDocument, User
from app.partnership_stages import label_of
from app.services import university_contacts, university_courses, university_documents
from app.services.agent_applications import owned, with_owner
from app.services.bdm import bdm_context
from app.services.partnership_universities import NOT_FOUND, rankings_of

logger = logging.getLogger("app.partnership")

REFUSED = "University view access required"
# UV2: the role -> its slice name; the overseas roles must be in the overseas division.
SLICES = {"counselor": "counselor", "overseas_admin": "overseas_admin", "bdm": "bdm", "bdm_manager": "bdm", "university_rep": "university_rep"}
OVERSEAS_ONLY = frozenset({"counselor", "overseas_admin"})
SECTIONS = {
    "counselor": ("partnership", "contacts", "courses", "documents", "applications"),
    "overseas_admin": ("partnership", "contacts", "courses", "documents", "applications"),
    "bdm": ("partnership", "manager"),
    "university_rep": ("courses",),
}
PROFILE_FIELDS = (
    "id", "university_code", "name", "institution_type", "ownership_type", "state_region", "city", "website", "overview", "eligibility",
    "course_levels", "popular_programs",
)  # fmt: skip
CONTACT_FIELDS = ("id", "name", "designation", "department", "email", "phone", "whatsapp", "linkedin", "preferred_channel", "is_primary")
COURSE_FIELDS = (
    "id", "title", "level", "category", "duration", "tuition_fee", "tuition_amount", "tuition_currency", "application_fee",
    "application_fee_currency", "intakes", "intake", "entry_requirements", "english_test", "english_score", "scholarships",
    "application_process", "deadline",
)  # fmt: skip
MAX_CONTACTS = 50
MAX_COURSES = 200
MAX_APPLICATIONS = 50


async def slice_of(db: AsyncSession, user: User) -> str:
    """UV2: this caller's slice, or 403 (logged, ids only). A BDM needs their profile (the BDM gate)."""
    name = SLICES.get(user.role)
    if name is None or (user.role in OVERSEAS_ONLY and user.division != "overseas"):
        logger.info("university_view_refused", extra={"extra_fields": {"user_id": str(user.id), "role": user.role}})
        raise HTTPException(403, REFUSED)
    if user.role == "bdm":
        await bdm_context(db, user)
    return name


def _rep_university(user: User) -> str | None:
    return (user.profile or {}).get("university_id")


async def visible_university(db: AsyncSession, user: User, slice_name: str, university_id: UUID) -> University:
    """UV3: 404 for an unknown id and for one outside the slice's scope, so neither leaks its existence."""
    uni = await db.get(University, university_id)
    if uni is None or (slice_name == "counselor" and not (uni.catalogue_visible and uni.active)) or (slice_name == "university_rep" and _rep_university(user) != str(university_id)):
        raise HTTPException(404, NOT_FOUND)
    return uni


async def _profile(db: AsyncSession, uni: University) -> dict:
    country = await db.get_one(Country, uni.country_id)
    return {
        **{k: getattr(uni, k) for k in PROFILE_FIELDS},
        "country": {"name": country.name, "iso2": country.iso2, "region": country.region},
        "rankings": [{"system": r.system, "other_name": r.other_name, "year": r.year, "rank": r.rank} for r in await rankings_of(db, uni.id)],
    }


async def _contacts(db: AsyncSession, user: User, uni: University) -> list[dict]:
    stmt = (
        select(UniversityContact, UniversityContactRole)
        .outerjoin(UniversityContactRole, UniversityContactRole.code == UniversityContact.role_code)
        .where(UniversityContact.university_id == uni.id, UniversityContact.shareable.is_(True))
        .order_by(*university_contacts.ORDER)
        .limit(MAX_CONTACTS)
    )
    return [{**{k: getattr(c, k) for k in CONTACT_FIELDS}, "role": {"code": r.code, "label": r.label} if r else None} for c, r in (await db.execute(stmt)).all()]


async def _courses(db: AsyncSession, user: User, uni: University) -> list[dict]:
    rows = list((await db.scalars(select(OverseasCourse).where(OverseasCourse.university_id == uni.id, OverseasCourse.active.is_(True)).order_by(*university_courses.ORDER).limit(MAX_COURSES))).all())
    return [{k: course[k] for k in COURSE_FIELDS} for course in await university_courses.courses_out(db, user, rows, set())]


async def _documents(db: AsyncSession, user: User, uni: University) -> list[dict]:
    stmt = select(UniversityDocument).where(UniversityDocument.university_id == uni.id, *university_documents.visibility(user)).order_by(*university_documents.ORDER)
    return [{k: getattr(d, k) for k in ("id", "kind", "title", "current_version", "updated_at")} for d in (await db.scalars(stmt)).all()]


async def _applications(db: AsyncSession, user: User, uni: University) -> list[dict]:
    stmt = with_owner(select(OverseasApplication).where(OverseasApplication.university_id == uni.id))
    if user.role == "counselor":
        stmt = stmt.where(OverseasApplication.counselor_id == user.id)
    rows = owned((await db.execute(stmt.order_by(OverseasApplication.updated_at.desc(), OverseasApplication.id).limit(MAX_APPLICATIONS))).all())
    return [
        {"id": a.id, "reference": a.application_reference, "student_name": s.full_name, "intake": a.intake, "status": a.status, "next_action": a.next_action, "updated_at": a.updated_at}
        for a, s in rows
    ]


async def _manager(db: AsyncSession, user: User, uni: University) -> dict | None:
    manager = await db.get(User, uni.primary_manager_user_id) if uni.primary_manager_user_id else None
    return {"full_name": manager.full_name, "email": manager.email} if manager else None


async def _partnership(db: AsyncSession, user: User, uni: University) -> dict:
    return {"stage": uni.stage, "stage_label": label_of(uni.stage), "lost": uni.lost_at is not None}


_BUILDERS = {"partnership": _partnership, "contacts": _contacts, "courses": _courses, "documents": _documents, "applications": _applications, "manager": _manager}


async def view_out(db: AsyncSession, user: User, slice_name: str, uni: University) -> dict:
    """UV11: the slice name, the profile, then only this slice's sections (absent, not null, when not in the slice)."""
    return {"slice": slice_name, "university": await _profile(db, uni), **{s: await _BUILDERS[s](db, user, uni) for s in SECTIONS[slice_name]}}
