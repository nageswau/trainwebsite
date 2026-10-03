"""AGN-015 / DEC-SCOPE-060 -- one agency student's journey (step tracker) and complete history (timeline).

Spec: docs/superpowers/specs/2026-10-03-agn-015-student-journey-design.md. Read-only: no lock, no write, no cache. Every source is
narrowed by the existing scopes (AGN-004 G4, AGN-008, AGN-009) before a row is read, and audit rows are selected only by entity ids
taken from those scoped sets (§6). Only names, labels, statuses, field NAMES and the notes the same viewer already reads leave this
module -- never field values, amounts, the visa decision, emails, phones or file keys (§3).
"""

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AgentStudent,
    AgentStudentCounseling,
    AgentStudentShortlistEntry,
    ApplicationDeposit,
    DocumentRequest,
    OverseasApplication,
    StudentDocument,
    University,
    User,
    VisaCase,
)
from app.services.agent_applications import OVERSEAS_APPLICATION_STAGES, WITHDRAWN
from app.services.agent_documents import document_scope, request_scope, student_clause
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
        "applications": [
            {"id": a.id, "university": name, "intake": a.intake, "status": a.status, "steps": application_steps(a, deposit_of.get(a.id), visa_of.get(a.id))}
            for a, name in src.apps
        ],
    }
