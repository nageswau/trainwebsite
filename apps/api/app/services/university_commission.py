"""upc-016 (DEC-SCOPE-143, spec §1-§3): §15 commercial / commission terms of a university agreement -- RESTRICTED (U2, line 1129).

Functions only; nothing here commits -- the route owns the transaction. It imports nothing from `university_agreements` (that module embeds
the terms in every agreement payload, CM12), so the agreement's freeze rule (CM9) is applied by the route.
- read: `partnership_access.can_see_commission` (super_admin, partnership head, partnership manager with a profile); every other role 403;
- write: the agreement's university `can_manage_agreements`, while the agreement's terms are editable.
Logs and audit rows carry ids, the MoU number and field names only -- never a rate, an amount or a text (CM13).
"""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Country, OverseasCourse, UniversityAgreement, UniversityCommissionTerm, User
from app.services.partnership import partnership_context
from app.services.partnership_access import can_see_commission
from app.services.telecaller import person_ref

logger = logging.getLogger("app.partnership")

TRIGGER_LABELS = {"enrolment": "Student enrolment", "visa_and_enrolment": "Visa approval + enrolment", "tuition_paid": "Tuition paid"}  # CM1
MAX_TERMS = 20  # CM5, per agreement
FIELDS = ("commission_percent", "fixed_amount", "currency", "trigger", "conditions", "course_ids", "country_ids", "payment_timeline", "payment_terms")
LIST_FIELDS = ("course_ids", "country_ids")
ORDER = (UniversityCommissionTerm.created_at, UniversityCommissionTerm.id)  # oldest first
NOT_FOUND = "Commission term not found"
FROZEN = "This agreement's terms are approved -- renew the agreement to change its commission"
TOO_MANY = f"An agreement can have at most {MAX_TERMS} commission terms"


async def require_reader(db: AsyncSession, user: User) -> None:
    if not can_see_commission(user):
        raise HTTPException(403, "Commission terms access required")
    if user.role == "partnership_manager":
        await partnership_context(db, user)  # a manager without a profile is a 403 (upc-001)


async def load(db: AsyncSession, agreement_id: UUID, term_id: UUID) -> UniversityCommissionTerm:
    term = await db.scalar(
        select(UniversityCommissionTerm)
        .where(UniversityCommissionTerm.id == term_id, UniversityCommissionTerm.agreement_id == agreement_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if term is None:
        raise HTTPException(404, NOT_FOUND)
    return term


async def check_room(db: AsyncSession, agreement_id: UUID) -> None:
    """Called under the agreement lock, so two concurrent adds cannot both pass (CM15)."""
    count = await db.scalar(select(func.count()).select_from(UniversityCommissionTerm).where(UniversityCommissionTerm.agreement_id == agreement_id))
    if count >= MAX_TERMS:
        raise HTTPException(409, TOO_MANY)


def stored(values: dict) -> dict:
    """JSON columns hold ids as text."""
    return {k: [str(i) for i in v] if k in LIST_FIELDS else v for k, v in values.items()}


async def check_values(db: AsyncSession, university_id: UUID, state: dict) -> None:
    """The merged row's rules: exactly one rate (CM2), the required currency and trigger, programmes of this university and real
    countries (CM5)."""
    if (state.get("commission_percent") is None) == (state.get("fixed_amount") is None):
        raise HTTPException(422, "Enter a commission percentage or a fixed amount, not both")
    if state.get("currency") is None or state.get("trigger") is None:
        raise HTTPException(422, "The currency and the commission trigger are required")
    if ids := state.get("course_ids"):
        found = await db.scalar(select(func.count()).select_from(OverseasCourse).where(OverseasCourse.id.in_(ids), OverseasCourse.university_id == university_id))
        if found != len(ids):
            raise HTTPException(422, "Choose programmes of this university")
    if ids := state.get("country_ids"):
        if await db.scalar(select(func.count()).select_from(Country).where(Country.id.in_(ids))) != len(ids):
            raise HTTPException(422, "Choose countries from the list")


async def copy_terms(db: AsyncSession, user: User, source: UniversityAgreement, target: UniversityAgreement) -> None:
    """CM10: a renewal starts with the terms of the agreement it renews."""
    rows = (await db.scalars(select(UniversityCommissionTerm).where(UniversityCommissionTerm.agreement_id == source.id).order_by(*ORDER))).all()
    for row in rows:
        copy = UniversityCommissionTerm(agreement_id=target.id, created_by_user_id=user.id, updated_by_user_id=user.id, **{k: getattr(row, k) for k in FIELDS})
        db.add(copy)
        await db.flush()
        record(db, user, copy, target, "create", note=f"copied from {source.mou_number}")


def record(db: AsyncSession, user: User, term: UniversityCommissionTerm, agreement: UniversityAgreement, kind: str, *, changed: list[str] | None = None, note: str | None = None) -> None:
    meta = {"agreement_id": str(agreement.id), "mou_number": agreement.mou_number, **({"fields": changed} if changed else {}), **({"note": note} if note else {})}
    db.add(AuditLog(user_id=user.id, action=f"university_commission_term.{kind}", entity_type="university_commission_term", entity_id=str(term.id), metadata_json=meta))


def log(event: str, user: User, term: UniversityCommissionTerm, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "term_id": str(term.id), "agreement_id": str(term.agreement_id), **extra}})


async def _lookup(db: AsyncSession, model, ids: set) -> dict:
    return {row.id: row for row in (await db.scalars(select(model).where(model.id.in_(ids)))).all()} if ids else {}


def _money(value) -> str | None:
    return None if value is None else f"{value:.2f}"


async def terms_out(db: AsyncSession, rows: list[UniversityCommissionTerm], editable: set[UUID]) -> list[dict]:
    """Terms with the programmes, countries and people they point at, in a fixed number of queries; `editable` = the agreement ids whose
    terms this caller may change."""
    courses = await _lookup(db, OverseasCourse, {UUID(str(c)) for t in rows for c in t.course_ids})
    countries = await _lookup(db, Country, {UUID(str(c)) for t in rows for c in t.country_ids})
    people = await _lookup(db, User, {t.created_by_user_id for t in rows} | {t.updated_by_user_id for t in rows})
    return [
        {
            "id": t.id,
            "agreement_id": t.agreement_id,
            "commission_percent": _money(t.commission_percent),
            "fixed_amount": _money(t.fixed_amount),
            "currency": t.currency,
            "trigger": t.trigger,
            "trigger_label": TRIGGER_LABELS[t.trigger],
            "conditions": t.conditions,
            "courses": [{"id": c.id, "title": c.title, "level": c.level} for cid in t.course_ids if (c := courses.get(UUID(str(cid))))],
            "countries": sorted(({"id": c.id, "name": c.name} for cid in t.country_ids if (c := countries.get(UUID(str(cid))))), key=lambda c: c["name"]),
            "payment_timeline": t.payment_timeline,
            "payment_terms": t.payment_terms,
            "created_by": person_ref(people[t.created_by_user_id]),
            "updated_by": person_ref(people[t.updated_by_user_id]),
            "created_at": t.created_at,
            "updated_at": t.updated_at,
            "permissions": {"can_edit": t.agreement_id in editable},
        }
        for t in rows
    ]


async def terms_by_agreement(db: AsyncSession, agreement_ids: list[UUID], editable: set[UUID]) -> dict[UUID, list[dict]]:
    """Every term of these agreements, oldest first, grouped by agreement (one page of agreements, CM12)."""
    if not agreement_ids:
        return {}
    stmt = select(UniversityCommissionTerm).where(UniversityCommissionTerm.agreement_id.in_(agreement_ids)).order_by(*ORDER)
    grouped: dict[UUID, list[dict]] = {}
    for item in await terms_out(db, list((await db.scalars(stmt)).all()), editable):
        grouped.setdefault(item["agreement_id"], []).append(item)
    return grouped
