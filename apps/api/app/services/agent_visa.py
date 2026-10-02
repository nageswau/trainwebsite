"""AGN-012 -- the visa case of an agency's application (DEC-SCOPE-055; docs/superpowers/specs/2026-10-02-agn-012-agent-visa-design.md §4).

Also the home of the visa stage list and the compliance sentence the counselor/student routes in `api/workflows.py` use: they moved
here unchanged because `workflows.py` imports `services.agent_applications`, which needs them, so this module cannot import the API
layer."""

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StudentDocument, VisaCase

# DATA_MODEL.md #6.5, DEC-SCOPE-006: the four confirmed category names plus a terminal `decision` state. The outcomes are not stages:
# DEC-SCOPE-055 V2 records them for agency cases in their own column, so this list is unchanged.
VISA_CASE_STAGES = ["checklist", "documentation", "interview_prep", "tracking", "decision"]

# VISA-003-AC02: a fixed compliance sentence, sourced from the reference implementation's own compliance language (DATA_MODEL.md
# #6.5) -- never invented, and never varied per case, so no response can ever imply EduSphere decides visa outcomes.
VISA_DECISION_DISCLAIMER = "Visa decisions are made by the relevant government or immigration authority. EduSphere does not decide visa outcomes."

VISA_EXISTS = "A visa case already exists for this application"
VISA_OFFER_NEEDED = "An offer is needed before a visa case"
VISA_ENROLLED = "This application is enrolled, so its visa case can no longer be changed"
VISA_STALE = "This visa case changed since you opened it -- reload to see its current stage"
VISA_DECIDED = "The visa decision is recorded, so this case can no longer be changed"
VISA_CHECKLIST_LOCKED = "The checklist can only be changed at the checklist stage"
VISA_DECISION_STAGE = "Move the case to the decision stage before recording a decision"
VISA_FORWARD_ONLY = "A visa case can only move forward"
INTERVIEW_BEFORE_APPLICATION = "The interview date cannot be before the visa application date"


def stage_index(stage: str) -> int:
    """A stage outside the list (the seed's legacy `not_started`) counts as before `checklist`."""
    return VISA_CASE_STAGES.index(stage) if stage in VISA_CASE_STAGES else -1


def check_dates(application_date: date | None, interview_date: date | None) -> None:
    """V4: on the resulting values (request merged over stored). Same day is fine. Raised as FastAPI's own 422 list so the form puts
    the message on the interview field, whichever route found it."""
    if application_date and interview_date and interview_date < application_date:
        raise RequestValidationError([{"type": "value_error", "loc": ("body", "interview_date"), "msg": INTERVIEW_BEFORE_APPLICATION, "input": interview_date.isoformat()}])


DETAIL_FIELDS = ("checklist", "visa_application_date", "appointment_date", "interview_date")


class ChecklistGateRefused(HTTPException):
    """VISA-001-AC02's 422, carrying how many items blocked it so the route can log a count (never the document names)."""

    def __init__(self, unverified: list[str]):
        super().__init__(422, f"Cannot advance past the checklist stage -- not yet verified: {', '.join(unverified)}.")
        self.unverified = unverified


async def load_case(db: AsyncSession, application_id: UUID) -> VisaCase | None:
    """V7: one case per application. The counselor route refuses a second one; ordering keeps a pre-existing duplicate deterministic."""
    return await db.scalar(select(VisaCase).where(VisaCase.application_id == application_id).order_by(VisaCase.created_at, VisaCase.id).limit(1))


async def checklist_status(db: AsyncSession, application_id: UUID, items: list[str]) -> list[dict]:
    """V6: each item's newest document of that type attached to this application (one query); documents elsewhere do not count.
    `workflows._checklist_verification` keeps its own (unordered) pick for the counselor route."""
    latest: dict[str, str] = {}
    if items:
        rows = await db.execute(
            select(StudentDocument.document_type, StudentDocument.verification_status)
            .where(StudentDocument.application_id == application_id, StudentDocument.document_type.in_(items))
            .order_by(StudentDocument.created_at, StudentDocument.id)
        )
        latest = {document_type: status for document_type, status in rows}  # ascending, so the newest wins
    return [{"item": item, "verification_status": latest.get(item, "not_uploaded")} for item in items]


async def visa_block(db: AsyncSession, application_id: UUID) -> dict | None:
    """§4.5: the agency detail's `visa` key -- agency-only (V8)."""
    case = await load_case(db, application_id)
    if case is None:
        return None
    return {
        "id": case.id,
        "stage": case.status,
        "checklist": await checklist_status(db, application_id, list(case.checklist or [])),
        "visa_application_date": case.visa_application_date,
        "appointment_date": case.appointment_date,
        "interview_date": case.interview_date,
        "decision": case.decision,
        "decided_at": case.decided_at,
        "disclaimer": VISA_DECISION_DISCLAIMER,
    }


async def update_case(db: AsyncSession, case: VisaCase, changes: dict) -> tuple[str, dict] | None:
    """§4.2 checks 2-9 (the route did entry and check 1, under the application row lock). Every check precedes every write, so a
    refusal changes nothing. Returns the audit (action, metadata), or None when nothing changed."""
    if case.decision is not None:
        raise HTTPException(409, VISA_DECIDED)
    if changes["expected_stage"] != case.status:
        raise HTTPException(409, VISA_STALE)
    current = stage_index(case.status)
    if "checklist" in changes and current > 0:
        raise HTTPException(422, VISA_CHECKLIST_LOCKED)
    if "decision" in changes and case.status != "decision":
        raise HTTPException(422, VISA_DECISION_STAGE)
    target = changes.get("to_stage")
    if target is not None and stage_index(target) <= current:
        raise HTTPException(422, VISA_FORWARD_ONLY)
    if target is not None and current <= 0 < stage_index(target):  # VISA-001-AC02, on the checklist this request leaves behind
        checklist = changes.get("checklist", list(case.checklist or []))
        unverified = [c["item"] for c in await checklist_status(db, case.application_id, checklist) if c["verification_status"] != "verified"]
        if unverified:
            raise ChecklistGateRefused(unverified)
    check_dates(changes.get("visa_application_date", case.visa_application_date), changes.get("interview_date", case.interview_date))
    changed = [key for key in DETAIL_FIELDS if key in changes and changes[key] != getattr(case, key)]
    for key in changed:
        setattr(case, key, changes[key])
    fields = {"fields": changed} if changed else {}
    if "decision" in changes:
        case.decision, case.decided_at = changes["decision"], datetime.now(UTC)
        return "visa_decision", {"decision": case.decision, **fields}
    if target is not None:
        old, case.status = case.status, target
        return "visa_advance", {"from_stage": old, "to_stage": target, **fields}
    return ("visa_update", fields) if changed else None
