"""upc-016 (DEC-SCOPE-144, spec §1-§3): §15 commercial / commission terms of a university agreement -- RESTRICTED (U2, line 1129).

Functions only; nothing here commits -- the route owns the transaction. It imports nothing from `university_agreements` (that module embeds
the terms in every agreement payload, CM12), so the agreement's freeze rule (CM9) is applied by the route.
- read: `partnership_access.can_see_commission` (super_admin, partnership head, partnership manager with a profile); every other role 403;
- write: the agreement's university `can_manage_agreements`, while the agreement's terms are editable.
Logs and audit rows carry ids, the MoU number and field names only -- never a rate, an amount or a text (CM13).
upc-019 (DEC-SCOPE-163) adds the ledger: Commission Expected computed from enrolled applications x these terms, and the receipts
recorded by the head / super_admin (Q-20), both read by the same commission roles.
"""

import logging
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ApplicationStatusHistory,
    AuditLog,
    Country,
    OverseasApplication,
    OverseasCourse,
    UniversityAgreement,
    UniversityCommissionReceipt,
    UniversityCommissionTerm,
    User,
    VisaCase,
)
from app.services.bdm_appointments import today_ist
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
    if (count or 0) >= MAX_TERMS:
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


def money_str(value) -> str | None:
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
            "commission_percent": money_str(t.commission_percent),
            "fixed_amount": money_str(t.fixed_amount),
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


# --- upc-019 (DEC-SCOPE-163, spec CL1-CL8): Commission Expected, computed live from enrolled applications x the applicable terms -------
# Nothing is stored: an application that leaves `enrolled` simply stops counting. Two queries whatever the number of universities.
EXPECTED_STATUSES = {
    "counted": "Counted",
    "awaiting_visa": "Awaiting visa approval",
    "trigger_not_tracked": "Trigger not tracked (tuition paid)",
    "no_term": "No applicable term",
    "tuition_unknown": "Tuition unknown",
    "date_unknown": "Enrolment date unknown",
}
APPLIED_STATUSES = ("signed", "active", "renewed")  # CL4: in force now, or in force for its own period before a renewal
CENT = Decimal("0.01")


def _enrolled_on(history_at: datetime | None, confirmed_at: datetime | None, recorded: date | None) -> date | None:
    """CL3: the first entry into enrolled, else the enrolment confirmation (IST days), else the agency's recorded enrolment date."""
    at = history_at or confirmed_at
    return today_ist(at) if at is not None else recorded


def _pick(terms: list[tuple[UniversityAgreement, UniversityCommissionTerm]], course_id: UUID | None, day: date) -> UniversityCommissionTerm | None:
    """CL4-CL6: terms of agreements covering `day` that cover the programme and every country; a named programme beats all-programmes,
    then the newest term."""

    def covers(t: UniversityCommissionTerm) -> bool:
        return not t.course_ids or (course_id is not None and str(course_id) in {str(c) for c in t.course_ids})

    fits = [t for a, t in terms if a.start_date <= day <= a.expiry_date and not t.country_ids and covers(t)]
    return max(fits, key=lambda t: (bool(t.course_ids), t.created_at, str(t.id)), default=None)


def _amount(t: UniversityCommissionTerm, course: OverseasCourse | None) -> tuple[str, Decimal] | None:
    """CL8: a fixed amount in the term's currency, or % of the course tuition in the course's currency; no FX."""
    if t.fixed_amount is not None:
        return t.currency, t.fixed_amount
    if course is None or course.tuition_amount is None or course.tuition_currency is None or t.commission_percent is None:
        return None
    return course.tuition_currency, (course.tuition_amount * t.commission_percent / 100).quantize(CENT, rounding=ROUND_HALF_UP)


def _status(day: date | None, t: UniversityCommissionTerm | None, visa_ok: bool, money) -> str:
    if day is None:
        return "date_unknown"
    if t is None:
        return "no_term"
    if t.trigger == "tuition_paid":
        return "trigger_not_tracked"
    if t.trigger == "visa_and_enrolment" and not visa_ok:
        return "awaiting_visa"
    return "counted" if money else "tuition_unknown"


async def expected_rows(db: AsyncSession, university_ids: list[UUID]) -> dict[UUID, list[dict]]:
    """Every enrolled application of these universities (CL2) with its Expected status, term and amount; newest enrolment first."""
    if not university_ids:
        return {}
    H = ApplicationStatusHistory
    first_in = select(H.application_id, func.min(H.created_at).label("at")).where(H.to_status == "enrolled").group_by(H.application_id).subquery()
    visa = exists().where(VisaCase.application_id == OverseasApplication.id, VisaCase.decision == "approved")
    apps = await db.execute(
        select(OverseasApplication, OverseasCourse, first_in.c.at, visa.label("visa"))
        .outerjoin(OverseasCourse, OverseasCourse.id == OverseasApplication.course_id)
        .outerjoin(first_in, first_in.c.application_id == OverseasApplication.id)
        .where(OverseasApplication.university_id.in_(university_ids), OverseasApplication.status == "enrolled")
    )
    terms: dict[UUID, list] = {}
    in_force = await db.execute(
        select(UniversityAgreement, UniversityCommissionTerm)
        .join(UniversityCommissionTerm, UniversityCommissionTerm.agreement_id == UniversityAgreement.id)
        .where(UniversityAgreement.university_id.in_(university_ids), UniversityAgreement.status.in_(APPLIED_STATUSES))
    )
    for a, t in in_force.all():
        terms.setdefault(a.university_id, []).append((a, t))
    found: dict[UUID, list[dict]] = {}
    for app, course, history_at, visa_ok in apps.all():
        day = _enrolled_on(history_at, app.enrollment_confirmed_at, app.enrollment_date)
        chosen = _pick(terms.get(app.university_id, []), app.course_id, day) if day else None
        money = _amount(chosen, course) if chosen else None
        status = _status(day, chosen, visa_ok, money)
        currency, amount = money if status == "counted" and money else (None, None)
        found.setdefault(app.university_id, []).append({
            "id": app.id, "course": course.title if course else None, "intake": app.intake,
            "reference": app.application_reference, "enrolled_on": day, "status": status, "status_label": EXPECTED_STATUSES[status],
            "term_id": chosen.id if chosen else None, "currency": currency, "amount": amount,
        })  # fmt: skip
    for rows in found.values():
        rows.sort(key=lambda r: (r["enrolled_on"] is None, -(r["enrolled_on"] or date.min).toordinal(), str(r["id"])))
    return found


async def received_sums(db: AsyncSession, university_ids: list[UUID], first: date | None = None, last: date | None = None) -> dict[UUID, dict[str, Decimal]]:
    """Σ receipts per university and currency, optionally only those received within the inclusive days (F11). One query."""
    if not university_ids:
        return {}
    R = UniversityCommissionReceipt
    when = [R.received_on.between(first, last)] if first is not None and last is not None else []
    rows = await db.execute(select(R.university_id, R.currency, func.sum(R.amount)).where(R.university_id.in_(university_ids), *when).group_by(R.university_id, R.currency))
    found: dict[UUID, dict[str, Decimal]] = {}
    for university_id, currency, total in rows.all():
        found.setdefault(university_id, {})[currency] = total
    return found


def currency_sums(rows: list[dict], first: date | None = None, last: date | None = None) -> dict[str, Decimal]:
    """Σ Expected per currency over the counted rows, optionally only those enrolled within the inclusive days (F10)."""
    sums: dict[str, Decimal] = {}
    for r in rows:
        if r["status"] == "counted" and (first is None or last is None or first <= r["enrolled_on"] <= last):
            sums[r["currency"]] = sums.get(r["currency"], Decimal(0)) + r["amount"]
    return sums


# --- upc-019 (CL9-CL12, CL14): receipts, recorded by hand until a Finance module is decided (U4) --------------------------------------
RECORD_ROLES = frozenset({"partnership_head", "super_admin"})  # Q-20 / CL9; managers read only
RECEIPT_NOT_FOUND = "Commission receipt not found"
DUPLICATE_REFERENCE = "This reference is already recorded for this university"


def can_record(user: User) -> bool:
    return user.role in RECORD_ROLES


def require_recorder(user: User) -> None:
    if not can_record(user):
        raise HTTPException(403, "Only the partnership head or a super admin records commission received")


async def check_receipt(db: AsyncSession, university_id: UUID, received_on: date, reference: str, application_ids: list[UUID]) -> None:
    """Under the university lock: not in the future, linked applications enrolled at this university (422), and a reference recorded once
    per university, any case (409; the unique index is the backstop)."""
    if received_on > today_ist(datetime.now(tz=UTC)):
        raise HTTPException(422, "The date received can't be in the future")
    if application_ids:
        A = OverseasApplication
        found = await db.scalar(select(func.count()).select_from(A).where(A.id.in_(application_ids), A.university_id == university_id, A.status == "enrolled"))
        if found != len(application_ids):
            raise HTTPException(422, "Link only this university's enrolled applications")
    R = UniversityCommissionReceipt
    if await db.scalar(select(exists().where(R.university_id == university_id, func.lower(R.reference) == reference.lower()))):
        raise HTTPException(409, DUPLICATE_REFERENCE)


async def receipts_out(db: AsyncSession, rows: list[UniversityCommissionReceipt]) -> list[dict]:
    """Receipts with who recorded them, in one extra query."""
    people = await _lookup(db, User, {r.created_by_user_id for r in rows})
    return [
        {
            "id": r.id,
            "amount": money_str(r.amount),
            "currency": r.currency,
            "received_on": r.received_on,
            "reference": r.reference,
            "note": r.note,
            "application_ids": [str(i) for i in r.application_ids],
            "created_by": person_ref(people[r.created_by_user_id]),
            "created_at": r.created_at,
        }
        for r in rows
    ]


def record_receipt(db: AsyncSession, user: User, r: UniversityCommissionReceipt, kind: str) -> None:
    """CL14: ids, the currency and the number of linked applications -- never the amount, the reference or the note."""
    meta = {"university_id": str(r.university_id), "currency": r.currency, "linked_applications": len(r.application_ids)}
    db.add(AuditLog(user_id=user.id, action=f"university_commission_receipt.{kind}", entity_type="university_commission_receipt", entity_id=str(r.id), metadata_json=meta))


def log_receipt(event: str, user: User, r: UniversityCommissionReceipt) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "receipt_id": str(r.id), "university_id": str(r.university_id)}})
