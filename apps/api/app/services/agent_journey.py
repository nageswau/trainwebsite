"""AGN-015 / DEC-SCOPE-060 -- one agency student's journey (step tracker) and complete history (timeline).

Spec: docs/superpowers/specs/2026-10-03-agn-015-student-journey-design.md. Read-only: no lock, no write, no cache. Every source is
narrowed by the existing scopes (AGN-004 G4, AGN-008, AGN-009) before a row is read, and audit rows are selected only by entity ids
taken from those scoped sets (§6). Only names, labels, statuses, field NAMES and the notes the same viewer already reads leave this
module -- never field values, amounts, the visa decision, emails, phones or file keys (§3).
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import JSON, BigInteger, Integer, String, Text, Uuid, cast, exists, func, literal_column, null, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AgentStudent,
    AgentStudentCounseling,
    AgentStudentShortlistEntry,
    ApplicationDeposit,
    ApplicationStatusHistory,
    AuditLog,
    DocumentEvent,
    DocumentRequest,
    OverseasApplication,
    StudentDocument,
    University,
    User,
    VisaCase,
)
from app.services.agent_applications import OVERSEAS_APPLICATION_STAGES, WITHDRAWN
from app.services.agent_documents import document_scope, request_scope, student_clause
from app.services.agent_orgs import org_member_ids
from app.services.agent_students import application_scope

_OFFER = OVERSEAS_APPLICATION_STAGES.index("offer")
_DEPOSIT_STATES = {"pending": "in_progress", "paid": "done", "remitted": "done", "not_required": "not_required", "refunded": "refunded"}
_SETTLED = {"done", "not_required", "refunded", "refused"}  # §4: a withdrawn application keeps these; every other step reads withdrawn


@dataclass
class Sources:
    """The student's in-scope rows, read once per request (§6)."""

    apps: list  # [(OverseasApplication, university name)], oldest first
    documents: dict  # StudentDocument by id
    requests: dict  # DocumentRequest by id
    deposits: dict  # ApplicationDeposit by deposit id
    visas: dict  # VisaCase by case id


async def _sources(db: AsyncSession, user: User, record: AgentStudent) -> Sources:
    owner = OverseasApplication.agent_student_id == record.id
    if record.student_id is not None:  # the AGN-008 owner filter: the record, or (rows made before AGN-008) the linked login
        owner = or_(owner, OverseasApplication.student_id == record.student_id)
    apps = (
        await db.execute(
            select(OverseasApplication, University.name)
            .outerjoin(University, University.id == OverseasApplication.university_id)
            .where(OverseasApplication.school_student_id.is_(None), *application_scope(user), owner)
            .order_by(OverseasApplication.created_at, OverseasApplication.id)
        )
    ).all()
    app_ids = [a.id for a, _ in apps]
    documents = {d.id: d for d in (await db.scalars(select(StudentDocument).where(*document_scope(user), student_clause(record)))).all()}
    requests = {r.id: r for r in (await db.scalars(select(DocumentRequest).where(*request_scope(user), DocumentRequest.agent_student_id == record.id))).all()}
    deposits = {d.id: d for d in (await db.scalars(select(ApplicationDeposit).where(ApplicationDeposit.application_id.in_(app_ids)))).all()} if app_ids else {}
    visas = {v.id: v for v in (await db.scalars(select(VisaCase).where(VisaCase.application_id.in_(app_ids)))).all()} if app_ids else {}
    return Sources([(a, name) for a, name in apps], documents, requests, deposits, visas)


def _steps(states: dict[str, str]) -> list[dict]:
    return [{"key": key, "state": state} for key, state in states.items()]


def student_steps(counseling, shortlisted: int, documents: list, open_requests: bool) -> list[dict]:
    """Spec §4, steps 1-4."""
    if counseling is None:
        counseled = "not_started"
    else:
        counseled = "done" if counseling.counseling_completed else "in_progress"
    if not documents and not open_requests:
        docs = "not_started"
    elif documents and not open_requests and all(d.verification_status == "verified" for d in documents):
        docs = "done"
    else:
        docs = "in_progress"
    return _steps({"create": "done", "counseling": counseled, "shortlist": "done" if shortlisted else "not_started", "documents": docs})


def _visa_state(visa) -> str:
    if visa is None:
        return "not_started"
    return {"approved": "done", "refused": "refused", "withdrawn": "withdrawn"}.get(visa.decision, "in_progress")


def application_steps(app, deposit, visa) -> list[dict]:
    """Spec §4, steps 5-9, from the application's own columns, its deposit and its visa case."""
    stage = OVERSEAS_APPLICATION_STAGES.index(app.status) if app.status in OVERSEAS_APPLICATION_STAGES else -1
    states = {
        "application": "done" if app.submitted_on else "in_progress",
        "offer": "done" if app.offer_type or stage >= _OFFER else "not_started",
        "deposit": "not_started" if deposit is None else _DEPOSIT_STATES[deposit.status],
        "visa": _visa_state(visa),
        "enrollment": "done" if app.status == "enrolled" else "not_started",
    }
    if app.status == WITHDRAWN:
        states = {key: state if state in _SETTLED else "withdrawn" for key, state in states.items()}
    return _steps(states)


async def _full_name(db: AsyncSession, record: AgentStudent) -> str | None:
    """A linked student's name comes from their own account (AGN-004 F2)."""
    if record.student_id is None:
        return record.full_name
    return await db.scalar(select(User.full_name).where(User.id == record.student_id))


async def journey(db: AsyncSession, user: User, record: AgentStudent) -> dict:
    src = await _sources(db, user, record)
    counseling = await db.scalar(select(AgentStudentCounseling).where(AgentStudentCounseling.agent_student_id == record.id))
    shortlisted = await db.scalar(select(func.count()).select_from(AgentStudentShortlistEntry).where(AgentStudentShortlistEntry.agent_student_id == record.id))
    open_requests = any(r.status == "open" for r in src.requests.values())
    deposit_of = {d.application_id: d for d in src.deposits.values()}
    visa_of = {v.application_id: v for v in src.visas.values()}
    return {
        "student": {"id": record.id, "full_name": await _full_name(db, record), "status": record.status},
        "steps": student_steps(counseling, shortlisted or 0, list(src.documents.values()), open_requests),
        "applications": [{"id": a.id, "university": name, "intake": a.intake, "status": a.status, "steps": application_steps(a, deposit_of.get(a.id), visa_of.get(a.id))} for a, name in src.apps],
    }


# --- timeline (§3, §5) -------------------------------------------------------------------------------------------------------------

MAX_TIMELINE_OFFSET = 10_000

# §3: audit action -> kind. Any other action is not an event: create/advance/withdraw/offer/enroll live in the status history,
# document.* / document_request.* in document_events, the record's creation in the record; checkout and commission are excluded.
STUDENT_AUDIT_KINDS = {
    "agent_student.update": "student_updated",
    "agent_student.duplicate_override": "student_duplicate_override",
    "agent_student.assign": "student_assigned",
    "agent_student.archive": "student_archived",
    "agent_student.unarchive": "student_restored",
    "agent_student.counseling": "counseling_saved",
    "agent_student.shortlist_add": "shortlist_added",
    "agent_student.shortlist_update": "shortlist_updated",
    "agent_student.shortlist_remove": "shortlist_removed",
    "agent_student.task_add": "task_added",
    "agent_student.task_update": "task_updated",
    "agent_student.task_complete": "task_completed",
    "agent_student.task_cancel": "task_cancelled",
}
APPLICATION_AUDIT_KINDS = {
    "overseas.application.update": "application_edited",
    "overseas.application.enrollment_update": "enrollment_updated",
    "overseas.application.visa_start": "visa_started",
    "overseas.application.visa_update": "visa_updated",
    "overseas.application.visa_advance": "visa_stage_changed",
    "overseas.application.visa_decision": "visa_decision_recorded",
    "overseas.application.deposit": "deposit_set",
    "overseas.application.deposit_paid": "deposit_paid",
}
DEPOSIT_AUDIT_KINDS = {"overseas.deposit.remit": "deposit_remitted", "overseas.deposit.refund": "deposit_refunded"}
VISA_AUDIT_KINDS = {"visa.create": "visa_started", "visa.update": "visa_updated"}
AUDIT_KINDS = STUDENT_AUDIT_KINDS | APPLICATION_AUDIT_KINDS | DEPOSIT_AUDIT_KINDS | VISA_AUDIT_KINDS
# The counselor paths (workflows.py) store the changed VALUES as metadata; only their keys are shown (§3).
_KEY_FIELD_ACTIONS = {"overseas.application.update", "visa.update"}

# §3 / J4: anyone outside the viewer's organisation is a role, never a name.
ROLE_LABELS = {
    "counselor": "EduSphere counsellor",
    "career_counselor": "EduSphere counsellor",
    "overseas_admin": "EduSphere admin",
    "super_admin": "EduSphere admin",
    "overseas_student": "Student",
    "it_student": "Student",
    "school_parent": "Parent",
    "university_rep": "University",
    "agent": "Agency user",
}
OTHER_USER, SYSTEM = "EduSphere user", "System"

_STR, _INT, _UUID = String(), Integer(), Uuid(as_uuid=True)


def _const(value: str):
    return literal_column(f"'{value}'", _STR)  # module constants only -- never request input


def _typed_null(type_):
    return cast(null(), type_)


def _branch(src: str, rank: int, row_id, at, raw, actor, *, ref=None, ref2=None, seq=None, from_status=None, to_status=None, notes=None, meta=None):
    """One source as the shared column list; UNION ALL needs the same types in every branch, so ids are text and absent columns typed NULLs."""
    return select(
        _const(src).label("src"),
        literal_column(str(rank), _INT).label("rank"),
        cast(row_id, _STR).label("row_id"),
        at.label("at"),
        (seq if seq is not None else cast(literal_column("0"), BigInteger)).label("seq"),
        raw.label("raw"),
        (actor if actor is not None else _typed_null(_UUID)).label("actor"),
        (cast(ref, _STR) if ref is not None else _typed_null(_STR)).label("ref"),
        (cast(ref2, _STR) if ref2 is not None else _typed_null(_STR)).label("ref2"),
        (from_status if from_status is not None else _typed_null(_STR)).label("from_status"),
        (to_status if to_status is not None else _typed_null(_STR)).label("to_status"),
        (notes if notes is not None else _typed_null(Text())).label("notes"),
        (meta if meta is not None else _typed_null(JSON())).label("meta"),
    )


def _audit_branch(src: str, rank: int, entity_type: str, ids, kinds: dict):
    return _branch(src, rank, AuditLog.id, AuditLog.created_at, AuditLog.action, AuditLog.user_id, ref=AuditLog.entity_id, meta=AuditLog.metadata_json).where(
        AuditLog.entity_type == entity_type, AuditLog.entity_id.in_([str(i) for i in ids]), AuditLog.action.in_(list(kinds))
    )


def _branches(record: AgentStudent, src: Sources) -> list:
    """S1-S8 of §3; a source with no scoped ids contributes no branch (never an empty IN)."""
    history, event, document = ApplicationStatusHistory, DocumentEvent, StudentDocument
    app_ids = [a.id for a, _ in src.apps]
    branches = [
        _branch("s1", 1, AgentStudent.id, AgentStudent.created_at, _const("student_created"), AgentStudent.agent_id).where(AgentStudent.id == record.id),
        _audit_branch("s2", 2, "agent_student", [record.id], STUDENT_AUDIT_KINDS),
    ]
    if app_ids:
        branches.append(
            _branch(
                "s3",
                3,
                history.id,
                history.created_at,
                _const("history"),
                history.changed_by_id,
                ref=history.application_id,
                from_status=history.from_status,
                to_status=history.to_status,
                notes=history.notes,
            ).where(history.application_id.in_(app_ids))
        )
        branches.append(_audit_branch("s4", 4, "overseas_application", app_ids, APPLICATION_AUDIT_KINDS))
    if src.deposits:
        branches.append(_audit_branch("s5", 5, "application_deposit", list(src.deposits), DEPOSIT_AUDIT_KINDS))
    if src.visas:
        branches.append(_audit_branch("s6", 6, "visa_case", list(src.visas), VISA_AUDIT_KINDS))
    subject = []
    if src.documents:
        subject.append(event.document_id.in_(list(src.documents)))
    if src.requests:
        subject.append(event.request_id.in_(list(src.requests)))
    if subject:
        branches.append(
            _branch(
                "s7",
                7,
                event.id,
                event.created_at,
                event.event,
                event.actor_user_id,
                ref=event.document_id,
                ref2=event.request_id,
                seq=event.seq,
                from_status=event.from_status,
                to_status=event.to_status,
                notes=event.notes,
            ).where(or_(*subject))
        )
    if src.documents:  # S8: uploads made before AGN-009 have no `uploaded` event; the document row is their only record
        uploaded = exists().where(event.document_id == document.id, event.event == "uploaded")
        branches.append(
            _branch("s8", 8, document.id, document.created_at, _const("legacy_upload"), document.uploaded_by_user_id, ref=document.id).where(document.id.in_(list(src.documents)), ~uploaded)
        )
    return branches


def _as_uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def _history_kind(from_status: str | None, to_status: str) -> str:
    if from_status is None:
        return "application_created"
    if to_status == WITHDRAWN:
        return "application_withdrawn"
    if to_status == "enrolled" and from_status != "enrolled":
        return "application_enrolled"
    return "application_stage_changed" if from_status != to_status else "application_updated"


def _fields(raw: str, meta: dict) -> list[str] | None:
    """Field NAMES only; anything that is not a string is dropped (the AGN-021 rule)."""
    value = meta.get("fields")
    if isinstance(value, list):
        return [f for f in value if isinstance(f, str)]
    if raw in _KEY_FIELD_ACTIONS:
        return sorted(k for k in meta if isinstance(k, str))
    return None


async def _actors(db: AsyncSession, user: User, ids: set) -> dict:
    """At most one query per page: names for the viewer's organisation, role labels for everyone else."""
    if not ids:
        return {}
    member = User.id.in_(org_member_ids(user))
    rows = (await db.execute(select(User.id, User.full_name, User.role, member).where(User.id.in_(ids)))).all()
    return {uid: name if is_member else ROLE_LABELS.get(role, OTHER_USER) for uid, name, role, is_member in rows}


def _document_item(row, src: Sources) -> tuple[dict | None, uuid.UUID | None]:
    doc, request = src.documents.get(_as_uuid(row.ref)), src.requests.get(_as_uuid(row.ref2))
    if doc is not None:
        return {"id": doc.id, "type": doc.document_type}, doc.application_id
    if request is not None:
        return {"id": request.id, "type": request.document_type}, None
    return None, None


def _item(row, src: Sources, universities: dict, actors: dict) -> dict:
    kind, fields, from_status, to_status, notes, app_id, document = None, None, None, None, None, None, None
    if row.src == "s1":
        kind = "student_created"
    elif row.src == "s3":
        kind, from_status, to_status, notes, app_id = _history_kind(row.from_status, row.to_status), row.from_status, row.to_status, row.notes, _as_uuid(row.ref)
    elif row.src in ("s2", "s4", "s5", "s6"):
        meta = row.meta if isinstance(row.meta, dict) else {}
        kind, fields = AUDIT_KINDS[row.raw], _fields(row.raw, meta)
        if row.raw == "overseas.application.visa_advance":
            from_status, to_status = meta.get("from_stage"), meta.get("to_stage")
        ref = _as_uuid(row.ref)
        if row.src == "s4":
            app_id = ref
        elif row.src == "s5":
            app_id = getattr(src.deposits.get(ref), "application_id", None)
        elif row.src == "s6":
            app_id = getattr(src.visas.get(ref), "application_id", None)
    else:  # s7 document events, s8 uploads made before AGN-009
        kind = "document_uploaded" if row.src == "s8" else ("document_request_cancelled" if row.raw == "cancelled" else f"document_{row.raw}")
        if row.src == "s7":
            from_status, to_status, notes = row.from_status, row.to_status, row.notes
        document, app_id = _document_item(row, src)
    return {
        "id": f"{row.src}:{row.row_id}",
        "at": row.at,
        "kind": kind,
        "actor": SYSTEM if row.actor is None else actors.get(row.actor, OTHER_USER),
        "application": {"id": app_id, "university": universities[app_id]} if app_id in universities else None,
        "document": document,
        "from_status": from_status,
        "to_status": to_status,
        "fields": fields,
        "notes": notes,
    }


async def timeline_page(db: AsyncSession, user: User, record: AgentStudent, *, limit: int, offset: int) -> dict:
    """§3/§5: one statement orders and pages every source, newest first; `total` comes from the same snapshot (count(*) OVER ())."""
    src = await _sources(db, user, record)
    events = union_all(*_branches(record, src)).subquery()
    order = (events.c.at.desc(), events.c.rank.desc(), events.c.seq.desc(), events.c.row_id.desc())
    rows = (await db.execute(select(events, func.count().over().label("total")).order_by(*order).limit(limit).offset(offset))).all()
    total = rows[0].total if rows else await db.scalar(select(func.count()).select_from(events))
    universities = {a.id: name for a, name in src.apps}
    actors = await _actors(db, user, {r.actor for r in rows if r.actor is not None})
    return {"items": [_item(r, src, universities, actors) for r in rows], "total": total or 0, "limit": limit, "offset": offset}
