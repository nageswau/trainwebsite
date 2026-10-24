"""ccrm-026 (DEC-SCOPE-252) -- a visa case's Appendix A lifecycle: the counselor / Overseas Admin update (VC1 lock and correction, VC4
moves, D2 required fields and dates, D3 evidence), the status sync for the stage-only writers (the AGN-012 agency route, the legacy
counselor PATCH) and the application side of a status change (ccrm-014 sub-status, ccrm-015 visa_refused). Nothing here commits, logs
or notifies: the caller scopes, locks, notifies, audits and commits. Spec: docs/superpowers/specs/2026-10-24-ccrm-026-visa-lifecycle-design.md."""

from datetime import UTC, date, datetime

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application_outcome import TERMINAL
from app.application_sub_status import SUB_STATUSES
from app.models import OverseasApplication, StudentDocument, User, VisaCase
from app.schemas import VisaLifecycleUpdate
from app.services import application_outcomes as outcomes
from app.services import application_sub_status as sub_status
from app.services.agent_applications import OVERSEAS_APPLICATION_STAGES
from app.services.agent_visa import INTERVIEW_BEFORE_APPLICATION, VISA_CHECKLIST_LOCKED, VISA_DECIDED, VISA_STALE, ChecklistGateRefused, checklist_status
from app.visa_status import APPLICATION_SUB_STATUS, DECISIONS, STAGE_OF, can_move, label

VISA_MOVE = "That status change is not allowed -- a visa case moves forward, except between Additional information requested and Decision pending"
CORRECTION_REASON = "Give a correction reason to change a recorded visa decision"
CORRECTION_STAYS = "A correction can only change the decision to another decision"
APPOINTMENT_NEEDED = "Add the appointment date before marking the appointment booked"
SUBMISSION_NEEDED = "Add the submission date before marking the visa application submitted"
REFUSAL_REASON_NEEDED = "Add the refusal reason before recording a refusal"
EXPECTED_BEFORE_SUBMISSION = "The expected decision date cannot be before the submission date"
DECISION_IN_FUTURE = "The decision date cannot be in the future"
DECISION_BEFORE_SUBMISSION = "The decision date cannot be before the submission date"
EVIDENCE_MISMATCH = "Choose a document uploaded for this application"
NEEDS_SUBMISSION = frozenset({"submitted", "additional_info_requested", "decision_pending"})
# Request field -> VisaCase column (the submission date is AGN-012's visa_application_date).
COLUMN = {"submission_date": "visa_application_date"}
FIELDS = (
    "readiness_review_date", "visa_category", "checklist", "appointment_date", "appointment_place", "submission_date", "tracking_reference",
    "interview_date", "expected_decision_date", "decision_date", "outcome_document_id", "refusal_reason", "next_steps",
)  # fmt: skip


def _invalid(field: str, message: str, value) -> RequestValidationError:
    """FastAPI's own 422 list, so the form puts the message on its field."""
    return RequestValidationError([{"type": "value_error", "loc": ("body", field), "msg": message, "input": value.isoformat() if isinstance(value, date) else value}])


def _check_dates(get) -> None:
    submitted, interview, expected, decided = get("visa_application_date"), get("interview_date"), get("expected_decision_date"), get("decision_date")
    if submitted and interview and interview < submitted:
        raise _invalid("interview_date", INTERVIEW_BEFORE_APPLICATION, interview)
    if submitted and expected and expected < submitted:
        raise _invalid("expected_decision_date", EXPECTED_BEFORE_SUBMISSION, expected)
    if decided and decided > date.today():
        raise _invalid("decision_date", DECISION_IN_FUTURE, decided)
    if decided and submitted and decided < submitted:
        raise _invalid("decision_date", DECISION_BEFORE_SUBMISSION, decided)


async def update(db: AsyncSession, user: User, app: OverseasApplication, case: VisaCase, body: VisaLifecycleUpdate) -> dict | None:
    """Every check precedes every write, so a refusal changes nothing. Returns the audit metadata, or None when nothing changed."""
    current = case.visa_status
    if body.expected_visa_status != current:
        raise HTTPException(409, VISA_STALE)
    decided = current in DECISIONS
    if decided and user.role != "overseas_admin":
        raise HTTPException(409, VISA_DECIDED)
    sent = body.model_fields_set
    target = body.visa_status if "visa_status" in sent and body.visa_status != current else None
    if target is not None:
        if decided and target not in DECISIONS:
            raise HTTPException(422, CORRECTION_STAYS)
        if not decided and not can_move(current, target):
            raise HTTPException(422, VISA_MOVE)
        outcomes.refuse_on_hold(app)
    if "checklist" in sent and current != "not_started":
        raise HTTPException(422, VISA_CHECKLIST_LOCKED)
    values = {COLUMN.get(field, field): getattr(body, field) for field in FIELDS if field in sent}

    def get(column: str):
        return values.get(column, getattr(case, column))

    if target is not None and current == "not_started":  # VISA-001-AC02, on the checklist this request leaves behind
        unverified = [c["item"] for c in await checklist_status(db, case.application_id, list(get("checklist") or [])) if c["verification_status"] != "verified"]
        if unverified:
            raise ChecklistGateRefused(unverified)
    final = target or current
    if target == "appointment_booked" and get("appointment_date") is None:
        raise _invalid("appointment_date", APPOINTMENT_NEEDED, None)
    if target in NEEDS_SUBMISSION and get("visa_application_date") is None:
        raise _invalid("submission_date", SUBMISSION_NEEDED, None)
    if final == "refused" and not get("refusal_reason"):
        raise _invalid("refusal_reason", REFUSAL_REASON_NEEDED, None)
    _check_dates(get)
    if values.get("outcome_document_id") is not None:
        found = await db.scalar(select(StudentDocument.application_id).where(StudentDocument.id == values["outcome_document_id"]))
        if found != app.id:
            raise _invalid("outcome_document_id", EVIDENCE_MISMATCH, str(values["outcome_document_id"]))
    changed = [column for column, value in values.items() if value != getattr(case, column)]
    if not changed and target is None:
        return None
    if decided and not body.correction_reason:
        raise _invalid("correction_reason", CORRECTION_REASON, None)
    for column in changed:
        setattr(case, column, values[column])
    if target is not None:
        case.visa_status, case.status = target, STAGE_OF[target]
        if target in DECISIONS:
            case.decision, case.decided_at = target, datetime.now(UTC)
            case.decision_date = case.decision_date or date.today()
    # Never the values: the refusal reason is restricted, and the rest are on the case.
    return {"fields": changed, "from_status": current, "to_status": final, "correction": decided}


def _later_sub_status(app: OverseasApplication, target: str) -> bool:
    """Whether `target` is after the application's sub-status (ccrm-014 never moves an application back)."""
    stage = sub_status.stage_of(target)
    current = OVERSEAS_APPLICATION_STAGES.index(app.status) if app.status in OVERSEAS_APPLICATION_STAGES else -1
    if OVERSEAS_APPLICATION_STAGES.index(stage) != current:
        return OVERSEAS_APPLICATION_STAGES.index(stage) > current
    subs = SUB_STATUSES[stage]
    return app.sub_status not in subs or subs.index(target) > subs.index(app.sub_status)


async def apply_to_application(db: AsyncSession, user: User, app: OverseasApplication, case: VisaCase, before: str) -> None:
    """VC4: the application side of a status change -- a forward sub-status, or the visa_refused outcome. An application on hold or
    closed is left alone (the stage-only writers keep their AGN-012 contract; the lifecycle route already refused on hold)."""
    if case.visa_status == before or app.status == "enrolled" or app.outcome in TERMINAL or app.outcome == "on_hold":
        return
    note = f"Visa: {label(case.visa_status)}"
    if case.visa_status == "refused":
        outcomes.visa_refused(db, user, app, note=note, next_steps=case.next_steps)
        return
    target = APPLICATION_SUB_STATUS.get(case.visa_status)
    if target is not None and _later_sub_status(app, target):
        sub_status.change(db, user, app, target, note)


# D8: what a student sees -- never the refusal reason, the evidence document or the internal review fields.
STUDENT_FIELDS = ("visa_status", "visa_status_label", "appointment_place", "submission_date", "expected_decision_date", "decision", "decision_date", "next_steps")


def view(case: VisaCase, *, staff: bool) -> dict:
    """The lifecycle fields of a case: every one, with the refusal reason, for the counselor and Overseas Admin; STUDENT_FIELDS else."""
    out = {
        "visa_status": case.visa_status,
        "visa_status_label": label(case.visa_status),
        "readiness_review_date": case.readiness_review_date,
        "visa_category": case.visa_category,
        "appointment_date": case.appointment_date,
        "appointment_place": case.appointment_place,
        "submission_date": case.visa_application_date,
        "tracking_reference": case.tracking_reference,
        "interview_date": case.interview_date,
        "expected_decision_date": case.expected_decision_date,
        "decision": case.decision,
        "decision_date": case.decision_date,
        "outcome_document_id": case.outcome_document_id,
        "next_steps": case.next_steps,
        "refusal_reason": case.refusal_reason,
    }
    return out if staff else {key: out[key] for key in STUDENT_FIELDS}
