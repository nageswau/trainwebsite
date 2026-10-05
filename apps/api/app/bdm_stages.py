"""bdm-004 (DEC-SCOPE-070, spec §4): the three BDM pipelines, in source order and wording (EVID-016 Agent §E, School §D,
College §D).

Constants only, with no app imports, so the model CHECK, the migration's parity test, the service and the schemas share one list.
kind: "manual" -- the BDM sets it; "live" -- read from the onboarded partner record (bdm-018 / bdm-019, S3); "volume" -- counted
from live records (bdm-019 / bdm-021 / bdm-022, S2). Only manual stages are ever stored."""

from typing import NamedTuple

MANUAL, LIVE, VOLUME = "manual", "live", "volume"
FIRST_STAGE = "prospect"


class Step(NamedTuple):
    key: str
    label: str
    kind: str


PIPELINES: dict[str, tuple[Step, ...]] = {
    "agent": (
        Step("prospect", "Agent Prospect", MANUAL),
        Step("contacted", "Contacted", MANUAL),
        Step("meeting_scheduled", "Meeting Scheduled", MANUAL),
        Step("meeting_completed", "Meeting Completed", MANUAL),
        Step("interested", "Interested", MANUAL),
        Step("proposal_agreement", "Proposal / Agreement", MANUAL),
        Step("agreement_signed", "Agreement Signed", MANUAL),
        Step("agent_onboarding", "Agent Onboarding", LIVE),
        Step("master_login_created", "Master Login Created", LIVE),
        Step("staff_logins_created", "Staff Logins Created", LIVE),
        Step("active_agent", "Active Agent", LIVE),
        Step("students", "Students", VOLUME),
        Step("applications", "Applications", VOLUME),
        Step("enrollments", "Enrollments", VOLUME),
    ),
    "school": (
        Step("prospect", "School Prospect", MANUAL),
        Step("contacted", "Contacted", MANUAL),
        Step("meeting", "Meeting", MANUAL),
        Step("presentation", "Presentation", MANUAL),
        Step("proposal", "Proposal", MANUAL),
        Step("negotiation", "Negotiation", MANUAL),
        Step("mou", "MoU", MANUAL),
        Step("signed", "Signed", MANUAL),
        Step("school_onboarding", "School Onboarding", LIVE),
        Step("users_created", "Teachers / Parents / Students Created", LIVE),
        Step("career_guidance", "Career Guidance", LIVE),
        Step("psychometric", "Psychometric", LIVE),
        Step("profile_building", "Student Profile Building", LIVE),
        Step("university_planning", "University Planning", LIVE),
    ),
    "college": (
        Step("prospect", "College Prospect", MANUAL),
        Step("contacted", "Contacted", MANUAL),
        Step("meeting", "Meeting", MANUAL),
        Step("presentation", "Presentation", MANUAL),
        Step("proposal", "Proposal", MANUAL),
        Step("mou_negotiation", "MoU Negotiation", MANUAL),
        Step("mou_signed", "MoU Signed", MANUAL),
        Step("college_activated", "College Activated", MANUAL),
        Step("course_promotion", "Course Promotion", VOLUME),
        Step("student_leads", "Student Leads", VOLUME),
        Step("training", "Training", VOLUME),
        Step("internship", "Internship", VOLUME),
        Step("recruitment", "Recruitment", VOLUME),
        Step("placement", "Placement", VOLUME),
    ),
}
MANUAL_STAGES: dict[str, tuple[str, ...]] = {t: tuple(s.key for s in steps if s.kind == MANUAL) for t, steps in PIPELINES.items()}

# S4 (D13): the 8-value agent status (Agent §B) is derived on read, never stored. "Inactive" needs the linked Agent Organization
# (suspended / rejected), so nothing maps to it until bdm-019.
AGENT_STATUSES = ("Prospect", "Contacted", "Meeting", "Interested", "Agreement", "Onboarding", "Active", "Inactive")
AGENT_STATUS: dict[str, str] = {
    "prospect": "Prospect",
    "contacted": "Contacted",
    "meeting_scheduled": "Meeting",
    "meeting_completed": "Meeting",
    "interested": "Interested",
    "proposal_agreement": "Agreement",
    "agreement_signed": "Agreement",
    "agent_onboarding": "Onboarding",
    "master_login_created": "Onboarding",
    "staff_logins_created": "Onboarding",
    "active_agent": "Active",
}
