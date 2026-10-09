"""upc-017 (DEC-SCOPE-146, spec §1-§3): the §16 course master -- a university's courses in `overseas_courses` (U6).

Functions only; nothing here commits -- the route owns the transaction.
- read: the University Master's read roles (upc-003), every university;
- write: the university's `can_edit` rule (CO1: its managers, their head, overseas_admin, super_admin; active university);
- commission (CO2, U2): only `partnership_access.COMMISSION_ROLES` set it, and every payload passes through `strip_commission`.
Audit rows and logs carry ids and field names only -- never a commission value (CO16).
"""

import logging
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import normalize_key
from app.models import AuditLog, OverseasCourse, Scholarship, University, User
from app.services import partnership_universities as unis
from app.services.partnership_access import can_see_commission, strip_commission

logger = logging.getLogger("app.partnership")

NOT_FOUND = "Course not found"
DUPLICATE = "This university already has a course with this title at this level"
COMMISSION_REFUSED = "Your role cannot set course commission"
MAX_SCORE = {"IELTS": Decimal("9"), "TOEFL": Decimal("120"), "PTE": Decimal("90"), "Duolingo": Decimal("160"), "Other": Decimal("999.9")}  # CO8
REQUIRED = ("title", "level", "category", "duration")
PAIRS = (("tuition_amount", "tuition_currency", "tuition fee"), ("application_fee", "application_fee_currency", "application fee"))
COMMISSION_COLUMNS = ("commission_percent", "commission_amount", "commission_currency")
FIELDS = (
    *REQUIRED, "tuition_amount", "tuition_currency", "application_fee", "application_fee_currency", "intakes", "entry_requirements", "english_test",
    "english_score", "scholarship_ids", "application_process", "deadline", "active", *COMMISSION_COLUMNS,
)  # fmt: skip
ORDER = (OverseasCourse.title, OverseasCourse.level, OverseasCourse.id)


async def writable_university(db: AsyncSession, user: User, university_id: UUID, route: str) -> University:
    """The read gate (403), the university row FOR UPDATE (404), then CO1's write rule (403 role/team, 409 inactive)."""
    await unis.require_reader(db, user)
    uni = await unis.load(db, university_id, lock=True)
    unis.require(user, uni, await unis.team_of(db, user), "can_edit", route)
    return uni


async def load(db: AsyncSession, university_id: UUID, course_id: UUID) -> OverseasCourse:
    """A course of this university only (no IDOR through the URL), locked for the write."""
    course = await db.scalar(select(OverseasCourse).where(OverseasCourse.id == course_id, OverseasCourse.university_id == university_id).with_for_update().execution_options(populate_existing=True))
    if course is None:
        raise HTTPException(404, NOT_FOUND)
    return course


def stored(user: User, values: dict) -> dict:
    """The sent values as columns: the commission object becomes its three columns (403 for a non-commission role, CO2); ids as text."""
    values = dict(values)
    if "commission" in values:
        if not can_see_commission(user):
            raise HTTPException(403, COMMISSION_REFUSED)
        rate = values.pop("commission") or {}
        values |= {"commission_percent": rate.get("percent"), "commission_amount": rate.get("amount"), "commission_currency": rate.get("currency")}
    if values.get("scholarship_ids") is not None:
        values["scholarship_ids"] = [str(i) for i in values["scholarship_ids"]]
    return values


def _scholarship_filter(uni: University):
    """CO9: this university's scholarships, or its country's university-wide ones."""
    return or_(Scholarship.university_id == uni.id, (Scholarship.university_id.is_(None)) & (Scholarship.country_id == uni.country_id))


async def scholarship_options(db: AsyncSession, uni: University) -> list[dict]:
    rows = (await db.scalars(select(Scholarship).where(_scholarship_filter(uni), Scholarship.active.is_(True)).order_by(Scholarship.title, Scholarship.id))).all()
    return [{"id": s.id, "title": s.title, "amount": s.amount} for s in rows]


def title_key(title: str, level: str) -> tuple[str, str]:
    """CO12's duplicate key: the title NFKC + casefolded + space-collapsed, and the level."""
    return normalize_key(title, 200), level


def check_rules(state: dict) -> None:
    """The merged row's rules that need no lookup (CO4, CO6, CO8, CO10): 422."""
    for field in REQUIRED:
        if not state.get(field):
            raise HTTPException(422, f"The course {field} is required")
    for amount, currency, word in PAIRS:
        if (state.get(amount) is None) != (state.get(currency) is None):
            raise HTTPException(422, f"Enter both the {word} and its currency, or neither")
    if (score := state.get("english_score")) is not None:
        test = state.get("english_test")
        if test is None:
            raise HTTPException(422, "Choose the English test the score is for")
        if score > MAX_SCORE[test]:
            raise HTTPException(422, f"The {test} score cannot be above {MAX_SCORE[test]}")


async def existing_keys(db: AsyncSession, university_id: UUID, exclude_id: UUID | None = None) -> set[tuple[str, str]]:
    others = [] if exclude_id is None else [OverseasCourse.id != exclude_id]
    rows = (await db.execute(select(OverseasCourse.title, OverseasCourse.level).where(OverseasCourse.university_id == university_id, *others))).all()
    return {title_key(title, level) for title, level in rows}


async def check_values(db: AsyncSession, uni: University, state: dict, course_id: UUID | None = None) -> None:
    """The merged row's rules (CO3-CO12); 422 for values, 409 for a duplicate title + level."""
    check_rules(state)
    if ids := state.get("scholarship_ids"):
        found = len((await db.scalars(select(Scholarship.id).where(Scholarship.id.in_([UUID(str(i)) for i in ids]), _scholarship_filter(uni)))).all())
        if found != len(ids):
            raise HTTPException(422, "Choose scholarships of this university or its country")
    if title_key(state["title"], state["level"]) in await existing_keys(db, uni.id, course_id):
        raise HTTPException(409, DUPLICATE)


def _money_text(amount: Decimal, currency: str) -> str:
    text = f"{amount:,.2f}"
    return f"{currency} {text[:-3] if text.endswith('.00') else text}"


def derive_texts(course: OverseasCourse, changed: set[str]) -> None:
    """CO4/CO7: the catalogue's display texts follow the structured values whenever those are saved."""
    if changed & {"tuition_amount", "tuition_currency"}:
        amount, currency = course.tuition_amount, course.tuition_currency
        course.tuition_fee = "" if amount is None or currency is None else _money_text(amount, currency)
    if "intakes" in changed:
        course.intake = ", ".join(course.intakes)


def _money(value) -> str | None:
    return None if value is None else f"{value:.2f}"


def course_out(user: User, course: OverseasCourse, scholarships: dict, can_edit: bool) -> dict:
    payload = {
        "id": course.id,
        "university_id": course.university_id,
        **{k: getattr(course, k) for k in ("title", "level", "category", "duration", "tuition_fee", "intake", "tuition_currency", "application_fee_currency")},
        "tuition_amount": _money(course.tuition_amount),
        "application_fee": _money(course.application_fee),
        "intakes": course.intakes,
        **{k: getattr(course, k) for k in ("entry_requirements", "english_test", "application_process", "deadline", "active", "created_at", "updated_at")},
        "english_score": None if course.english_score is None else f"{course.english_score:.1f}",
        "scholarships": [scholarships[i] for i in course.scholarship_ids if i in scholarships],
        "commission": None
        if course.commission_percent is None and course.commission_amount is None
        else {"percent": _money(course.commission_percent), "amount": _money(course.commission_amount), "currency": course.commission_currency},
        "permissions": {"can_edit": can_edit},
    }
    return strip_commission(user, payload)


async def courses_out(db: AsyncSession, user: User, rows: list[OverseasCourse], editable: set[UUID]) -> list[dict]:
    """Courses with their scholarships in one extra query; `editable` = the university ids this caller may write."""
    ids = {UUID(str(i)) for c in rows for i in c.scholarship_ids}
    found = (await db.scalars(select(Scholarship).where(Scholarship.id.in_(ids)))).all() if ids else []
    scholarships = {str(s.id): {"id": s.id, "title": s.title, "amount": s.amount} for s in found}
    return [course_out(user, c, scholarships, c.university_id in editable) for c in rows]


def field_names(columns) -> list[str]:
    """What an audit row or log names: the commission columns are one field, "commission"."""
    return sorted({"commission" if c in COMMISSION_COLUMNS else c for c in columns})


def record(db: AsyncSession, user: User, course: OverseasCourse, kind: str, *, changed: list[str] | None = None, **meta) -> None:
    changed = field_names(changed) if changed else None
    db.add(
        AuditLog(
            user_id=user.id,
            action=f"university_course.{kind}",
            entity_type="overseas_course",
            entity_id=str(course.id),
            metadata_json={"university_id": str(course.university_id), **({"fields": changed} if changed else {}), **meta},
        )
    )


def log(event: str, user: User, course: OverseasCourse, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "course_id": str(course.id), "university_id": str(course.university_id), **extra}})
