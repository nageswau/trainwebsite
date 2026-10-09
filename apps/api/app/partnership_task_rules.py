"""upc-020 (DEC-SCOPE-139, spec TK2-TK5): partnership task values, the §19 title catalogue (EVID-020 L645-L667, source order and wording)
and the Q-22 auto-task rules (recommended defaults, NEEDS_CONFIRMATION).

Constants only, with no app imports, so the model CHECKs, the migration's parity test, the service and the schemas share one list."""

from typing import NamedTuple

KINDS = ("follow_up", "task")
PRIORITIES = ("high", "medium", "low")
STATUSES = ("open", "done", "cancelled")
SOURCES = ("manual", "stage", "meeting", "visit", "agreement")  # meeting / agreement: reserved for upc-009 / upc-014 (TK4)

TITLES = (
    "Follow up with university",
    "Send partnership proposal",
    "Schedule meeting",
    "Send MoU",
    "Follow up on MoU",
    "Arrange university visit",
    "Collect documents",
    "Negotiate commission",
    "Activate university",
    "Conduct training",
    "Send student applications",
    "Follow up on offers",
)


class Rule(NamedTuple):
    kind: str
    title: str
    days: int  # due this many calendar days after the IST day of the event (TK5)
    priority: str


# TK4: entering one of these stages creates one task. Every other stage creates nothing.
STAGE_RULES: dict[str, Rule] = {
    "initial_contact": Rule("follow_up", "Follow up with university", 3, "medium"),
    "interested": Rule("task", "Schedule meeting", 2, "high"),
    "meeting_completed": Rule("task", "Send partnership proposal", 3, "high"),
    "proposal_sent": Rule("follow_up", "Follow up on proposal", 7, "high"),  # AC1
    "commercial_discussion": Rule("task", "Negotiate commission", 7, "medium"),
    "documents_shared": Rule("task", "Send MoU", 5, "medium"),
    "agreement_under_review": Rule("follow_up", "Follow up on MoU", 7, "high"),
    "agreement_signed": Rule("task", "Activate university", 7, "high"),
    "partner_activated": Rule("task", "Conduct training", 14, "medium"),
    "student_recruitment_started": Rule("task", "Send student applications", 14, "medium"),
}
VISIT_RULE = Rule("follow_up", "Follow up after visit", 0, "high")  # due on the visit's follow-up date (upc-010 VS16), not an offset
