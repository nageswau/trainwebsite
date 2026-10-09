"""upc-014 (DEC-SCOPE-142, spec §1-§3): §13 MoU / agreement management -- who reads and writes, the status flow, the derived Expiring /
Expired, signing, renewal, the overlap rule and output.

Functions only; nothing here commits -- the route owns the transaction. Access reuses the University Master's (upc-003):
- the partnership roles and super_admin (CONTACT_ROLES) read every university's agreements; every other role is a 403 (AG13);
- writes follow `can_manage_agreements` (the contacts rule), approval `can_approve_agreements` (head / super_admin, AG6).
One transition table (`TRANSITIONS`) drives both the 409s and the moves offered to the screen. Logs and audit rows carry ids, the MoU
number, statuses and field names only; notes live in `university_agreement_events`.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    UNIVERSITY_AGREEMENT_MOU_SEQ,
    AuditLog,
    Country,
    OverseasCourse,
    University,
    UniversityAgreement,
    UniversityAgreementEvent,
    UniversityDocument,
    User,
)
from app.services import partnership_pipeline as pipeline
from app.services import partnership_tasks
from app.services import partnership_universities as unis
from app.services.bdm_travel import india_today
from app.services.partnership import partnership_context
from app.services.telecaller import person_ref

logger = logging.getLogger("app.partnership")

READ_ROLES = unis.CONTACT_ROLES  # AG13
SIGNATORY_ROLES = ("partnership_manager", "partnership_head", "super_admin")  # who signs for EduSphere
EXPIRING_DAYS = 90  # Q-16 / AG4
TYPE_LABELS = {"mou": "MoU", "partnership_agreement": "Partnership agreement", "commission_agreement": "Commission agreement"}
STATUS_LABELS = {
    "draft": "Draft", "sent": "Sent", "under_review": "Under Review", "negotiation": "Negotiation", "approved": "Approved",
    "signed": "Signed", "active": "Active", "expiring": "Expiring", "expired": "Expired", "renewed": "Renewed",
}  # fmt: skip
EFFECTIVE_STATUSES = tuple(STATUS_LABELS)
IN_FORCE = ("signed", "active")  # the stored statuses that expire, renew and overlap
# AG5: the moves each stored status allows; `renewed` is set only by signing a renewal (AG8).
TRANSITIONS = {
    "draft": ("sent",),
    "sent": ("under_review", "negotiation"),
    "under_review": ("negotiation", "approved"),
    "negotiation": ("under_review", "approved"),
    "approved": ("signed", "negotiation"),
    "signed": ("active",),
    "active": (),
    "renewed": (),
}
TERM_STATUSES = ("draft", "sent", "under_review", "negotiation")  # AG11
SIGNING_STATUSES = (*TERM_STATUSES, "approved")
SIGNING_FIELDS = ("document_id", "edusphere_signatory_user_id", "edusphere_signed_on", "university_signatory_name", "university_signed_on")
TERM_FIELDS = (
    "start_date", "expiry_date", "renewal_date", "commercial_terms", "exclusivity", "territory", "recruitment_rights", "all_courses",
    "course_ids", "country_ids", "payment_terms", "marketing_rights",
)  # fmt: skip
COPIED_ON_RENEWAL = ("agreement_type", "commercial_terms", "exclusivity", "territory", "recruitment_rights", "all_courses", "course_ids", "country_ids", "payment_terms", "marketing_rights")
SIGNING_LABELS = {
    "document_id": "the agreement document", "edusphere_signatory_user_id": "who signed for EduSphere",
    "edusphere_signed_on": "the date EduSphere signed", "university_signatory_name": "who signed for the university",
    "university_signed_on": "the date the university signed",
}  # fmt: skip

NOT_FOUND = "Agreement not found"
STATUS_CHANGED = "This agreement moved to {label} meanwhile"
FROZEN_SIGNED = "A signed agreement can't be changed -- renew it instead"
FROZEN_TERMS = "An approved agreement's terms can't be changed -- move it back to Negotiation first"
OVERLAP = {"message": "This university already has a signed {type} that overlaps these dates", "code": "agreement_overlap"}


# --- access ---------------------------------------------------------------------------------------------------------------------
async def require_reader(db: AsyncSession, user: User) -> None:
    if user.role not in READ_ROLES:
        raise HTTPException(403, "University agreements access required")
    if user.role == "partnership_manager":
        await partnership_context(db, user)  # a manager without a profile is a 403 (upc-001)


async def load(db: AsyncSession, agreement_id: UUID, *, lock: bool = False) -> UniversityAgreement:
    stmt = select(UniversityAgreement).where(UniversityAgreement.id == agreement_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    agreement = await db.scalar(stmt)
    if agreement is None:
        raise HTTPException(404, NOT_FOUND)
    return agreement


# --- status (AG4) -----------------------------------------------------------------------------------------------------------------
def effective_status(a: UniversityAgreement, today: date) -> str:
    """A signed or active agreement reads Expired after its expiry date and Expiring within 90 days of it; nothing else is derived."""
    if a.status in IN_FORCE:
        if a.expiry_date < today:
            return "expired"
        if a.expiry_date <= today + timedelta(days=EXPIRING_DAYS):
            return "expiring"
    return a.status


def effective_status_sql(today: date):
    """`effective_status` as SQL, so the menu filter and the cards always agree (AC3)."""
    in_force = UniversityAgreement.status.in_(IN_FORCE)
    return case(
        (and_(in_force, UniversityAgreement.expiry_date < today), "expired"),
        (and_(in_force, UniversityAgreement.expiry_date <= today + timedelta(days=EXPIRING_DAYS)), "expiring"),
        else_=UniversityAgreement.status,
    )


def check_move(a: UniversityAgreement, from_status: str, to_status: str) -> None:
    if from_status != a.status:
        raise HTTPException(409, {"message": STATUS_CHANGED.format(label=STATUS_LABELS[a.status]), "code": "status_changed", "current_status": a.status})
    if to_status not in TRANSITIONS[a.status]:
        raise HTTPException(409, f"A {STATUS_LABELS[a.status]} agreement can't move to {STATUS_LABELS[to_status]}")


# --- validation (AG7, AG11, AG12) ----------------------------------------------------------------------------------------------


def check_dates(state: dict) -> None:
    if state["expiry_date"] <= state["start_date"]:
        raise HTTPException(422, "The expiry date must be after the start date")
    renewal = state.get("renewal_date")
    if renewal is not None and not state["start_date"] <= renewal <= state["expiry_date"]:
        raise HTTPException(422, "The renewal date must fall between the start and expiry dates")


def check_editable(a: UniversityAgreement, fields: set[str]) -> None:
    if a.status not in SIGNING_STATUSES:
        raise HTTPException(409, FROZEN_SIGNED)
    if a.status not in TERM_STATUSES and fields - set(SIGNING_FIELDS):
        raise HTTPException(409, FROZEN_TERMS)


async def check_values(db: AsyncSession, university_id: UUID, agreement_type: str, values: dict) -> None:
    """The cross-row rules on the values being written: courses of this university, real countries, the document (this university's,
    of the agreement's kind), an EduSphere signatory, signing dates not in the future."""
    if values.get("all_courses") and values.get("course_ids"):
        raise HTTPException(422, "Choose all courses or specific courses, not both")
    if ids := values.get("course_ids"):
        found = await db.scalar(select(func.count()).select_from(OverseasCourse).where(OverseasCourse.id.in_(ids), OverseasCourse.university_id == university_id))
        if found != len(ids):
            raise HTTPException(422, "Choose courses of this university")
    if ids := values.get("country_ids"):
        if await db.scalar(select(func.count()).select_from(Country).where(Country.id.in_(ids))) != len(ids):
            raise HTTPException(422, "Choose countries from the list")
    if (document_id := values.get("document_id")) is not None:
        document = await db.get(UniversityDocument, document_id)
        if document is None or document.university_id != university_id or document.kind != agreement_type:
            raise HTTPException(422, f"Choose a {TYPE_LABELS[agreement_type]} document of this university")
    if (signer_id := values.get("edusphere_signatory_user_id")) is not None:
        signer = await db.get(User, signer_id)
        if signer is None or not signer.active or signer.role not in SIGNATORY_ROLES:
            raise HTTPException(422, "Choose an active partnership manager, head or super admin as the EduSphere signatory")
    for key, who in (("edusphere_signed_on", "EduSphere"), ("university_signed_on", "The university")):
        if values.get(key) is not None and values[key] > india_today():
            raise HTTPException(422, f"{who}'s signing date can't be in the future")


def check_signable(a: UniversityAgreement) -> None:
    """AC2: Signed needs the document and both signatories (name/user + date); the DB CHECK is the backstop."""
    missing = [SIGNING_LABELS[f] for f in SIGNING_FIELDS if getattr(a, f) is None]
    if missing:
        raise HTTPException(422, f"Add {', '.join(missing)} before signing")


async def check_overlap(db: AsyncSession, a: UniversityAgreement) -> None:
    """AG9 under the university lock: no other signed/active agreement of the same type overlapping [start, expiry]; the agreement this
    one renews is excluded (it becomes Renewed now)."""
    stmt = select(UniversityAgreement.id).where(
        UniversityAgreement.university_id == a.university_id,
        UniversityAgreement.agreement_type == a.agreement_type,
        UniversityAgreement.status.in_(IN_FORCE),
        UniversityAgreement.id != a.id,
        UniversityAgreement.start_date <= a.expiry_date,
        UniversityAgreement.expiry_date >= a.start_date,
    )
    if a.previous_agreement_id is not None:
        stmt = stmt.where(UniversityAgreement.id != a.previous_agreement_id)
    if await db.scalar(stmt.limit(1)):
        raise HTTPException(409, {**OVERLAP, "message": OVERLAP["message"].format(type=TYPE_LABELS[a.agreement_type])})


async def next_number(db: AsyncSession) -> str:
    return f"MOU-{await db.scalar(select(UNIVERSITY_AGREEMENT_MOU_SEQ.next_value())):06d}"


async def successor(db: AsyncSession, agreement_id: UUID) -> UniversityAgreement | None:
    return await db.scalar(select(UniversityAgreement).where(UniversityAgreement.previous_agreement_id == agreement_id))


async def sign(db: AsyncSession, user: User, a: UniversityAgreement, uni: University) -> None:
    """approved -> signed on the locked rows: complete (AC2), the university not lost, no overlap (E1); then the predecessor becomes
    Renewed (AC4) and the university moves to Agreement Signed when behind it (AG10)."""
    check_signable(a)
    if uni.lost_at is not None:
        raise HTTPException(409, pipeline.LOST_CONFLICT)
    await check_overlap(db, a)
    if a.previous_agreement_id is not None:
        previous = await load(db, a.previous_agreement_id, lock=True)
        if previous.status in IN_FORCE:
            before, previous.status, previous.status_changed_at = previous.status, "renewed", datetime.now(UTC)
            record(db, user, previous, "status", before, note=f"Renewed by {a.mou_number}")
    if pipeline.advance_to(db, user, uni, "agreement_signed", f"Advanced by agreement {a.mou_number} signed") is not None:
        await partnership_tasks.on_stage_entered(db, user, uni)  # upc-020 Q-22: the same auto-task as a manual move


# --- the record -----------------------------------------------------------------------------------------------------------------
def record(db: AsyncSession, user: User, a: UniversityAgreement, kind: str, before: str | None, *, note: str | None = None, changed: list[str] | None = None) -> None:
    """One history row and one audit row (ids, number, statuses, field names) in the caller's transaction."""
    db.add(UniversityAgreementEvent(agreement_id=a.id, kind=kind, from_status=before, to_status=a.status, actor_user_id=user.id, note=note, changed=changed or []))
    meta = {"mou_number": a.mou_number, "university_id": str(a.university_id), "from": before, "to": a.status, **({"fields": changed} if changed else {})}
    db.add(AuditLog(user_id=user.id, action=f"university_agreement.{kind}", entity_type="university_agreement", entity_id=str(a.id), metadata_json=meta))


def log(event: str, user: User, a: UniversityAgreement, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "agreement_id": str(a.id), "status": a.status, **extra}})


# --- output -------------------------------------------------------------------------------------------------------------------------
def _moves(a: UniversityAgreement, perms: dict[str, bool]) -> list[dict]:
    allowed = [to for to in TRANSITIONS[a.status] if perms["can_approve_agreements" if to == "approved" else "can_manage_agreements"]]
    return [{"to_status": to, "label": STATUS_LABELS[to]} for to in allowed]


async def _lookup(db: AsyncSession, model, ids: set) -> dict:
    return {row.id: row for row in (await db.scalars(select(model).where(model.id.in_(ids)))).all()} if ids else {}


async def agreements_out(db: AsyncSession, user: User, rows: list[tuple[UniversityAgreement, University]], *, events: bool = True) -> list[dict]:
    """A page of agreements with everything they point at, in a fixed number of queries (no N+1)."""
    today = india_today()
    team = await unis.team_of(db, user)
    ids = [a.id for a, _ in rows]
    courses = await _lookup(db, OverseasCourse, {UUID(str(c)) for a, _ in rows for c in a.course_ids})
    countries = await _lookup(db, Country, {UUID(str(c)) for a, _ in rows for c in a.country_ids})
    documents = await _lookup(db, UniversityDocument, {a.document_id for a, _ in rows} - {None})
    linked = await _lookup(db, UniversityAgreement, {a.previous_agreement_id for a, _ in rows} - {None})
    successors = {s.previous_agreement_id: s for s in (await db.scalars(select(UniversityAgreement).where(UniversityAgreement.previous_agreement_id.in_(ids)))).all()} if ids else {}
    history: dict[UUID, list] = {}
    if events and ids:
        stmt = select(UniversityAgreementEvent).where(UniversityAgreementEvent.agreement_id.in_(ids)).order_by(UniversityAgreementEvent.position)
        for e in (await db.scalars(stmt)).all():
            history.setdefault(e.agreement_id, []).append(e)
    people_ids = {a.created_by_user_id for a, _ in rows} | {a.edusphere_signatory_user_id for a, _ in rows} | {e.actor_user_id for es in history.values() for e in es}
    people = await _lookup(db, User, people_ids - {None})

    def ref(other: UniversityAgreement | None) -> dict | None:
        return {"id": other.id, "mou_number": other.mou_number, "status": other.status, "effective_status": effective_status(other, today)} if other else None

    out = []
    for a, uni in rows:
        perms = unis.permissions(user, uni, team)
        state = effective_status(a, today)
        document = documents.get(a.document_id)
        item = {
            "id": a.id,
            "mou_number": a.mou_number,
            "university": {"id": uni.id, "name": uni.name, "university_code": uni.university_code},
            "agreement_type": a.agreement_type,
            "type_label": TYPE_LABELS[a.agreement_type],
            "status": a.status,
            "effective_status": state,
            "status_label": STATUS_LABELS[state],
            "days_to_expiry": (a.expiry_date - today).days,
            **{
                k: getattr(a, k)
                for k in ("start_date", "expiry_date", "renewal_date", "commercial_terms", "exclusivity", "territory", "recruitment_rights", "all_courses", "payment_terms", "marketing_rights")
            },
            "courses": [{"id": c.id, "title": c.title, "level": c.level} for cid in a.course_ids if (c := courses.get(UUID(str(cid))))],
            "countries": sorted(({"id": c.id, "name": c.name} for cid in a.country_ids if (c := countries.get(UUID(str(cid))))), key=lambda c: c["name"]),
            "document": {"id": document.id, "title": document.title, "kind": document.kind, "current_version": document.current_version} if document else None,
            "edusphere_signatory": person_ref(people[a.edusphere_signatory_user_id]) if a.edusphere_signatory_user_id else None,
            **{k: getattr(a, k) for k in ("edusphere_signed_on", "university_signatory_name", "university_signed_on")},
            "previous": ref(linked.get(a.previous_agreement_id)),
            "renewed_by": ref(successors.get(a.id)),
            "created_by": person_ref(people[a.created_by_user_id]),
            "created_at": a.created_at,
            "updated_at": a.updated_at,
            "permissions": {
                "can_edit_terms": perms["can_manage_agreements"] and a.status in TERM_STATUSES,
                "can_edit_signing": perms["can_manage_agreements"] and a.status in SIGNING_STATUSES,
                "can_renew": perms["can_manage_agreements"] and a.status in IN_FORCE and a.id not in successors,
            },
            "moves": _moves(a, perms),
        }
        if events:
            item["events"] = [
                {"kind": e.kind, "from_status": e.from_status, "to_status": e.to_status, "note": e.note, "changed": e.changed, "actor": person_ref(people[e.actor_user_id]), "created_at": e.created_at}
                for e in history.get(a.id, [])
            ]  # fmt: skip
        out.append(item)
    return out


async def agreement_out(db: AsyncSession, user: User, a: UniversityAgreement) -> dict:
    await db.refresh(a)  # server defaults (timestamps) are expired after a flush
    uni = await db.get_one(University, a.university_id)
    return (await agreements_out(db, user, [(a, uni)]))[0]
