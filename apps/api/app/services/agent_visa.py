"""AGN-012 -- the visa case of an agency's application (DEC-SCOPE-055; docs/superpowers/specs/2026-10-02-agn-012-agent-visa-design.md §4).

Also the home of the visa stage list and the compliance sentence the counselor/student routes in `api/workflows.py` use: they moved
here unchanged because `workflows.py` imports `services.agent_applications`, which needs them, so this module cannot import the API
layer."""

from datetime import date

from fastapi.exceptions import RequestValidationError

# DATA_MODEL.md #6.5, DEC-SCOPE-006: the four confirmed category names plus a terminal `decision` state. The outcomes are not stages:
# DEC-SCOPE-055 V2 records them for agency cases in their own column, so this list is unchanged.
VISA_CASE_STAGES = ["checklist", "documentation", "interview_prep", "tracking", "decision"]
VISA_DECISIONS = ("approved", "refused", "withdrawn")

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
