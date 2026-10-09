"""upc-008 (DEC-SCOPE-143, spec MS1/MS4): the partnership milestones, in source order and wording (EVID-020 §6, L216-L240), and the ones
that complete themselves from an event (backlog: proposal from the stage, signed from the agreements (upc-014), first application and
first admission from applications). Meeting is reserved for upc-009 and stays manual until then.

Constants only, with no app imports, so the model CHECK, the migration's parity test, the service and the schemas share one list."""

from typing import NamedTuple


class Milestone(NamedTuple):
    key: str
    label: str


MILESTONES: tuple[Milestone, ...] = (
    Milestone("university_contacted", "University Contacted"),
    Milestone("meeting", "Meeting"),
    Milestone("presentation", "Presentation"),
    Milestone("proposal", "Proposal"),
    Milestone("documents", "Documents"),
    Milestone("negotiation", "Negotiation"),
    Milestone("agreement", "Agreement"),
    Milestone("signed", "Signed"),
    Milestone("onboarding", "Onboarding"),
    Milestone("student_recruitment", "Student Recruitment"),
    Milestone("first_application", "First Application"),
    Milestone("first_admission", "First Admission"),
    Milestone("active_partnership", "Active Partnership"),
)
MILESTONE_KEYS: tuple[str, ...] = tuple(m.key for m in MILESTONES)

# MS4: milestone -> the event that achieves it (derived on read, MS5).
AUTO_SOURCES: dict[str, str] = {"proposal": "stage", "signed": "agreement", "first_application": "application", "first_admission": "admission"}
PROPOSAL_STAGE = "proposal_sent"  # Proposal is achieved by the first move into this stage or a later one
SIGNED_STATUSES = ("signed", "active", "renewed")  # upc-014: an agreement that was signed (both signatures recorded, its CHECK)
ADMITTED_STATUS = "enrolled"  # the application status the product shows as "Admitted" (api/schools.py)
