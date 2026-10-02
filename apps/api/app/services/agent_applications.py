"""AGN-008 / DEC-SCOPE-050 -- an agency's applications for its students, with or without a login; and the NULL-safe owner join
every shared application list uses.

Functions only (the services/agent_students.py shape): nothing here commits -- the router locks, writes, audits and commits.
Spec: docs/superpowers/specs/2026-10-02-agn-008-agent-applications-design.md.
"""

import calendar
import re
from datetime import UTC, date, datetime
from typing import NamedTuple
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import AgentStudent, ApplicationStatusHistory, AuditLog, OverseasApplication, OverseasCourse, StudentDocument, University, User
from app.services import agent_documents as documents
from app.services.agent_orgs import THROTTLE_WINDOW, org_member_ids, retry_after
from app.services.agent_students import application_scope, student_scope

# DEC-WF-001 / OVS-003: the confirmed stage sequence (moved here from api/workflows.py, which imports it back -- one definition).
OVERSEAS_APPLICATION_STAGES = ["enquiry", "eligibility_evaluation", "university_selection", "offer", "visa_documentation", "status_tracking", "enrolled"]
WITHDRAWN = "withdrawn"  # A1: terminal; only an agent sets it (spec §5.3)
AGENT_MAX_STAGE = "status_tracking"  # A4: `enrolled` stays with counselor, university and admin
DEFAULT_NEXT_ACTION = "Complete profile and required document checklist"
OFFER_STAGES_ON = ("offer", "visa_documentation", "status_tracking")  # QA8-13: only the offer deadline matters from here


def stage_label(status: str) -> str:
    """QA8-10: a readable status -- underscores to spaces, first letter capital (covers every stage, `withdrawn` and legacy values)."""
    text = status.replace("_", " ")
    return text[:1].upper() + text[1:]


class Owner(NamedTuple):
    """An application's student: `id` is their account (None when the student has no login); `full_name` is the account's name,
    else the agency record's."""

    id: UUID | None
    full_name: str | None


OWNER_NAME = func.coalesce(User.full_name, AgentStudent.full_name)


def with_owner(stmt: Select) -> Select:
    """Add the owner (account row + display name) to a query over overseas_applications as OUTER joins, so an application of a
    student with no login is listed instead of silently dropped (A6). School-bridged rows stay out, exactly as the old inner join on
    users left them out (A12)."""
    return (
        stmt.add_columns(User, OWNER_NAME)
        .outerjoin(User, User.id == OverseasApplication.student_id)
        .outerjoin(AgentStudent, AgentStudent.id == OverseasApplication.agent_student_id)
        .where(OverseasApplication.school_student_id.is_(None))
    )


def owned(rows) -> list[tuple]:
    """`with_owner` rows with the trailing (account, name) pair folded into one `Owner`, so `for a, u, s in rows: s.full_name`
    keeps working; `s.id` is None for a student with no login."""
    return [(*row[:-2], Owner(row[-2].id if row[-2] is not None else None, row[-1])) for row in rows]


NOT_FOUND = "Application not found"
PRE_OFFER = ("enquiry", "eligibility_evaluation", "university_selection")


def group_clause(group: str):
    """A7/A9: the sidebar filters. Draft and Submitted split the pre-offer stages by `submitted_on`; All hides withdrawn."""
    status = OverseasApplication.status
    return {
        "draft": and_(status.in_(PRE_OFFER), OverseasApplication.submitted_on.is_(None)),
        "submitted": and_(status.in_(PRE_OFFER), OverseasApplication.submitted_on.is_not(None)),
        "offer": status == "offer",
        "visa": status.in_(("visa_documentation", "status_tracking")),
        "enrolled": status == "enrolled",
        "withdrawn": status == WITHDRAWN,
    }.get(group, status != WITHDRAWN)


def _rows_stmt() -> Select:
    return with_owner(
        select(OverseasApplication, University.name, University.slug, OverseasCourse.title)
        .join(University, University.id == OverseasApplication.university_id)
        .outerjoin(OverseasCourse, OverseasCourse.id == OverseasApplication.course_id)
    )


def nearest_deadline(app: OverseasApplication, today: date) -> dict | None:
    """The earliest deadline that is today or later; if none is upcoming, the most recent past one (the UI marks it past).
    QA8-13: it depends on the stage -- none once withdrawn or enrolled; from the offer stage on only the offer deadline counts."""
    if app.status in (WITHDRAWN, "enrolled"):
        return None
    candidates = (("application", app.application_deadline), ("offer", app.offer_deadline))
    if app.status in OFFER_STAGES_ON:
        candidates = (("offer", app.offer_deadline),)
    dates = [(d, kind) for kind, d in candidates if d]
    if not dates:
        return None
    upcoming = [x for x in dates if x[0] >= today]
    when, kind = min(upcoming) if upcoming else max(dates)
    return {"kind": kind, "date": when}


def item(row: tuple, today: date) -> dict:
    """List shape -- an explicit allowlist: no agent, counselor or account ids, no email or phone."""
    app, university, _slug, course, owner = row
    return {
        "id": app.id,
        "agent_student_id": app.agent_student_id,
        "student": owner.full_name or "Unnamed student",
        "has_login": owner.id is not None,
        "university": university,
        "course": course,
        "intake": app.intake,
        "status": app.status,
        "application_reference": app.application_reference,
        "submitted_on": app.submitted_on,
        "application_deadline": app.application_deadline,
        "offer_deadline": app.offer_deadline,
        "nearest_deadline": nearest_deadline(app, today),
        "next_action": app.next_action,
        "updated_at": app.updated_at,
    }


async def load_scoped(db: AsyncSession, user: User, application_id, *, lock: bool = False) -> OverseasApplication:
    """The caller's application or 404 -- scope is in the WHERE clause, never checked after loading."""
    stmt = (
        select(OverseasApplication).where(OverseasApplication.id == application_id, OverseasApplication.school_student_id.is_(None), *application_scope(user)).execution_options(populate_existing=True)
    )
    row = await db.scalar(stmt.with_for_update(of=OverseasApplication) if lock else stmt)
    if row is None:
        raise HTTPException(404, NOT_FOUND)
    return row


async def owner_record(db: AsyncSession, user: User, app: OverseasApplication) -> AgentStudent | None:
    """The agency record the application belongs to: its own link (AGN-008), else -- an application made before AGN-008 -- the
    caller's record of the same logged-in student."""
    if app.agent_student_id is not None:
        return await db.get(AgentStudent, app.agent_student_id, populate_existing=True)
    if app.student_id is None:
        return None
    return await db.scalar(select(AgentStudent).where(AgentStudent.student_id == app.student_id, *student_scope(user)).order_by(AgentStudent.created_at).limit(1))


Changer = aliased(User)
MISSING = object()  # `detail`'s "record not given" -- None is a real value (no agency record)


async def detail(db: AsyncSession, user: User, app: OverseasApplication, *, record: AgentStudent | None | object = MISSING) -> dict:
    """The detail shape. A write passes the owner `record` it already loaded (its archived status cannot change inside the request);
    otherwise it is looked up here."""
    row = owned([(await db.execute(_rows_stmt().where(OverseasApplication.id == app.id).execution_options(populate_existing=True))).one()])[0]
    found, _university, slug, _course, _owner = row
    history = (
        await db.execute(
            select(ApplicationStatusHistory, Changer.full_name)
            .outerjoin(Changer, Changer.id == ApplicationStatusHistory.changed_by_id)
            .where(ApplicationStatusHistory.application_id == found.id)
            .order_by(ApplicationStatusHistory.created_at, ApplicationStatusHistory.id)
        )
    ).all()
    if record is MISSING:
        record = await owner_record(db, user, found)
    reason = WITHDRAWN if found.status == WITHDRAWN else "archived" if record is not None and record.status == "archived" else None
    return {
        **item(row, date.today()),
        "university_id": found.university_id,
        "university_slug": slug,
        "course_id": found.course_id,
        "created_at": found.created_at,
        "read_only_reason": reason,
        "enrollment_date": found.enrollment_date,
        "university_student_id": found.university_student_id,
        "enrollment_confirmed_at": found.enrollment_confirmed_at,
        "enrollment_check": enrollment_check(found, datetime.now(UTC).date()),
        "history": [{"from_status": h.from_status, "to_status": h.to_status, "next_action": h.next_action, "notes": h.notes, "changed_by": name, "created_at": h.created_at} for h, name in history],
        **await _offer_parts(db, user, found),
    }


# --- AGN-010: offer details (DEC-SCOPE-056; docs/superpowers/specs/2026-10-02-agn-010-offer-details-design.md) ---

# O5: an offer was received -- the stage reached `offer` (legacy free-text values included) or an offer is recorded, so an application
# withdrawn after its offer still counts. The agent pages only; other roles' counts are ang-018's (RAID).
OFFER_COUNTED_STATUSES = frozenset({"offer", "offer_received", "accepted", "visa_documentation", "status_tracking", "enrolled"})
OFFER_FIELDS = ("offer_type", "offer_date", "offer_deadline", "offer_conditions", "offer_document_id")
OFFER_DOCUMENT_MISMATCH = "Choose an offer letter uploaded for this application"
OFFER_LETTERS_SHOWN = 20  # bounded per application (§4.2): a picker, not a document list


def counts_as_offer(app: OverseasApplication) -> bool:
    return app.status in OFFER_COUNTED_STATUSES or app.offer_type is not None


def before_offer(status: str) -> bool:
    """A stage before `offer`, or a legacy value outside the stage list (index -1, as `check_transition` treats it)."""
    offer = OVERSEAS_APPLICATION_STAGES.index("offer")
    return status not in OVERSEAS_APPLICATION_STAGES or OVERSEAS_APPLICATION_STAGES.index(status) < offer


def offer_values(app: OverseasApplication) -> dict:
    return {field: getattr(app, field) for field in OFFER_FIELDS}


async def check_offer_document(db: AsyncSession, user: User, app: OverseasApplication, document_id: UUID) -> None:
    """O3: the caller's document (404 outside scope, checked first so another agency's ids cannot be probed), attached to this
    application and of the offer-letter type (422)."""
    document = await documents.load_scoped(db, user, document_id)
    if document.application_id != app.id or document.document_type != documents.OFFER_LETTER:
        raise HTTPException(422, OFFER_DOCUMENT_MISMATCH)


def _when(value: date | None) -> str:
    return value.isoformat() if value else "none"


def offer_change_notes(old: dict, new: dict) -> str | None:
    """§4.3: the history note for an offer change, or None when nothing changed (the PUT is then a no-op). Earlier values are kept in
    the note, so replacing the offer (O1) loses nothing."""
    if old == new:
        return None
    kind = new["offer_type"].capitalize()
    if old["offer_type"] is None:
        text = f"Offer recorded: {kind}, offer date {_when(new['offer_date'])}"
        if new["offer_deadline"]:
            text += f", deadline {_when(new['offer_deadline'])}"
        if new["offer_document_id"]:
            text += ", offer letter attached"
        return text + (f". Conditions: {new['offer_conditions']}" if new["offer_conditions"] else ".")
    parts = []
    if old["offer_type"] != new["offer_type"]:
        parts.append(f"{old['offer_type'].capitalize()} → {kind}")
    for field, label in (("offer_date", "offer date"), ("offer_deadline", "deadline")):
        if old[field] != new[field]:
            parts.append(f"{label} {_when(old[field])} → {_when(new[field])}")
    if old["offer_conditions"] != new["offer_conditions"]:
        if new["offer_conditions"] is None:
            parts.append(f"conditions removed (were: {old['offer_conditions']})")
        elif old["offer_conditions"] is None:
            parts.append(f"conditions: {new['offer_conditions']}")
        else:
            parts.append(f"conditions: {new['offer_conditions']} (were: {old['offer_conditions']})")
    if old["offer_document_id"] != new["offer_document_id"]:
        parts.append("offer letter removed" if new["offer_document_id"] is None else "offer letter attached" if old["offer_document_id"] is None else "offer letter replaced")
    return "Offer updated: " + "; ".join(parts)


def _document_view(document: StudentDocument) -> dict:
    """Name and status only -- never `file_url` (the AGN-009 download route presigns the file)."""
    return {"id": document.id, "name": document.document_label or document.original_filename or documents.OFFER_LETTER, "verification_status": document.verification_status}


async def _offer_parts(db: AsyncSession, user: User, app: OverseasApplication) -> dict:
    """The detail's `offer` and `offer_letters` (§4.2), both inside the caller's document scope."""
    letters = (
        await db.scalars(
            select(StudentDocument)
            .where(StudentDocument.application_id == app.id, StudentDocument.document_type == documents.OFFER_LETTER, *documents.document_scope(user))
            .order_by(StudentDocument.created_at.desc(), StudentDocument.id)
            .limit(OFFER_LETTERS_SHOWN)
        )
    ).all()
    offer = None
    if app.offer_type is not None:
        linked = None
        if app.offer_document_id is not None:
            linked = await db.scalar(select(StudentDocument).where(StudentDocument.id == app.offer_document_id, *documents.document_scope(user)))
        offer = {
            "type": app.offer_type,
            "date": app.offer_date,
            "deadline": app.offer_deadline,
            "conditions": app.offer_conditions,
            "document": _document_view(linked) if linked else None,
        }
    return {"offer": offer, "offer_letters": [_document_view(d) | {"created_at": d.created_at} for d in letters]}


async def list_page(db: AsyncSession, user: User, *, group: str, agent_student_id, limit: int, offset: int) -> dict:
    filters = [*application_scope(user), group_clause(group)]
    if agent_student_id is not None:
        login = select(AgentStudent.student_id).where(AgentStudent.id == agent_student_id).scalar_subquery()
        filters.append(or_(OverseasApplication.agent_student_id == agent_student_id, and_(OverseasApplication.student_id.is_not(None), OverseasApplication.student_id == login)))
    base = _rows_stmt().where(*filters)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = owned((await db.execute(base.order_by(OverseasApplication.updated_at.desc(), OverseasApplication.id).limit(limit).offset(offset))).all())
    today = date.today()
    return {"items": [item(r, today) for r in rows], "total": total or 0, "limit": limit, "offset": offset}


CREATE_LIMIT = 200  # A14: per agency per rolling 24 hours
ARCHIVED = "Unarchive this student first"
DUPLICATE = "An application for this university/course already exists"
THROTTLED = "Too many applications created today -- try again later"


async def create_wait_seconds(db: AsyncSession, user: User) -> int:
    """A14: counted from the agency's `overseas.application.create` audit rows (every path that creates one), the
    DEC-SCOPE-038 R1 no-new-table pattern; runs under the organisation lock, so it is race-free."""
    now = datetime.now(UTC)
    recent = (
        await db.scalars(
            select(AuditLog.created_at)
            .where(AuditLog.action == "overseas.application.create", AuditLog.user_id.in_(org_member_ids(user)), AuditLog.created_at > now - THROTTLE_WINDOW)
            .order_by(AuditLog.created_at.desc())
            .limit(CREATE_LIMIT)
        )
    ).all()
    return retry_after(list(recent), CREATE_LIMIT, now)


async def check_course(db: AsyncSession, university_id, course_id) -> None:
    if course_id is None:
        return
    course = await db.get(OverseasCourse, course_id)
    if course is None or course.university_id != university_id:
        raise HTTPException(422, "Course does not belong to selected university")


async def duplicate_exists(db: AsyncSession, *, agent_student_id, student_id, university_id, course_id, exclude_id=None) -> bool:
    """OVS-002's rule for an agency student: same student, university and course (both NULL counts as the same), not withdrawn. The
    student is the agency record or -- when it has a login -- that account, so a row made before AGN-008 still counts."""
    owners = [OverseasApplication.agent_student_id == agent_student_id] if agent_student_id is not None else []
    if student_id is not None:
        owners.append(OverseasApplication.student_id == student_id)
    if not owners:
        return False
    course = OverseasApplication.course_id.is_(None) if course_id is None else OverseasApplication.course_id == course_id
    clauses = [or_(*owners), OverseasApplication.university_id == university_id, course, OverseasApplication.status != WITHDRAWN]
    if exclude_id is not None:
        clauses.append(OverseasApplication.id != exclude_id)
    return (await db.scalar(select(OverseasApplication.id).where(*clauses).limit(1))) is not None


WITHDRAWN_REFUSED = "This application is withdrawn"
STALE = "This application changed since you opened it -- reload to see its current status"
ENROLLED_REFUSED = "Only a counselor, university representative or admin can mark an application enrolled"
ENROLLED_NOT_WITHDRAWABLE = "An enrolled application cannot be withdrawn"


def check_transition(current: str, target: str) -> None:
    """A4: withdraw from any stage but enrolled; otherwise strictly forward, at most to status_tracking. A current value outside the
    stages (legacy free text) counts as before the first stage, as counselor /advance treats it."""
    if target == WITHDRAWN:
        if current == "enrolled":
            raise HTTPException(409, ENROLLED_NOT_WITHDRAWABLE)
        return
    if target == "enrolled":
        raise HTTPException(403, ENROLLED_REFUSED)
    if target not in OVERSEAS_APPLICATION_STAGES:
        raise HTTPException(422, f"'{target}' is not a supported application stage")
    current_index = OVERSEAS_APPLICATION_STAGES.index(current) if current in OVERSEAS_APPLICATION_STAGES else -1
    if OVERSEAS_APPLICATION_STAGES.index(target) <= current_index:
        raise HTTPException(422, f"Cannot move from '{current}' to '{target}' -- an agent can only move an application forward")


ENROLLABLE = OFFER_STAGES_ON  # AGN-013 E6: an offer is needed before enrollment
OFFER_NEEDED = "An offer is needed before enrollment"
MASTER_ONLY_ENROLLMENT = "Only an agency Master can confirm enrollment"
_MONTHS = {
    name: number
    for number, names in enumerate(
        ("jan january", "feb february", "mar march", "apr april", "may", "jun june", "jul july", "aug august", "sep sept september", "oct october", "nov november", "dec december"), 1
    )
    for name in names.split()
}
_NAMED_INTAKE = re.compile(r"\b([a-z]+)\.?\s*,?\s*(\d{4})\b")
_NUMERIC_INTAKE = re.compile(r"\b(?:(\d{1,2})\s*[/-]\s*(\d{4})|(\d{4})\s*[/-]\s*(\d{1,2}))\b")


def intake_end(text: str | None) -> date | None:
    """AGN-013 E2: intake is free text, so this is best effort -- the last day of the month in "Sep 2027", "September 2027",
    "09/2027" or "2027-09"; None when no month and year are found (the caller says so instead of guessing)."""
    value = (text or "").lower()
    found = next(((int(year), _MONTHS[word]) for word, year in _NAMED_INTAKE.findall(value) if word in _MONTHS), None)
    if found is None and (match := _NUMERIC_INTAKE.search(value)):
        found = (int(match[2]), int(match[1])) if match[1] else (int(match[3]), int(match[4]))
    if found is None or not 1 <= found[1] <= 12 or not 2000 <= found[0] <= 2100:
        return None
    year, month = found
    return date(year, month, calendar.monthrange(year, month)[1])


def enrollment_check(app, today: date) -> str | None:
    """AGN-013 E2: a warning, never a block -- a future enrollment date after the intake month, or an intake that cannot be read."""
    if app.enrollment_date is None:
        return None
    end = intake_end(app.intake)
    if end is None:
        return "intake_unrecognised"
    return "after_intake" if app.enrollment_date > end and app.enrollment_date > today else None
