"""upc-007 (DEC-SCOPE-126, spec PS1/PS3): the partnership stages, in source order and wording (EVID-020 §3, L98-L154), and their fixed
groupings (backlog Appendix B, U7): the §4 Kanban column (K), the map / overview group (G) and the §24 probability (P).

Constants only, with no app imports, so the model CHECK, the migration's parity test, the service and the schemas share one list.
Lost/Closed is not a stage: it is a flag (lost_at + lost_reason) on top of the kept stage, excluded from the Kanban columns."""

from typing import NamedTuple


class Stage(NamedTuple):
    key: str
    label: str
    column: str  # K
    group: str  # G: target / in_progress / partner (lost is the flag)
    probability: int  # P, percent (Q-09 open for the stages §24 does not list)


STAGES: tuple[Stage, ...] = (
    Stage("target_university", "Target University", "target", "target", 10),
    Stage("researching", "Researching", "target", "target", 10),
    Stage("contact_identified", "Contact Identified", "target", "target", 10),
    Stage("initial_contact", "Initial Contact", "contacted", "in_progress", 25),
    Stage("interested", "Interested", "interested", "in_progress", 40),
    Stage("meeting_scheduled", "Meeting Scheduled", "meeting_scheduled", "in_progress", 40),
    Stage("meeting_completed", "Meeting Completed", "meeting_scheduled", "in_progress", 60),
    Stage("proposal_sent", "Proposal Sent", "proposal_sent", "in_progress", 75),
    Stage("commercial_discussion", "Commercial Discussion", "negotiation", "in_progress", 75),
    Stage("documents_shared", "Documents Shared", "negotiation", "in_progress", 75),
    Stage("agreement_under_review", "Agreement Under Review", "agreement_pending", "in_progress", 90),
    Stage("agreement_signed", "Agreement Signed", "signed", "in_progress", 100),  # PS3: G2 (Q-08 alternative: Partner)
    Stage("partner_activated", "Partner Activated", "signed", "partner", 100),
    Stage("student_recruitment_started", "Student Recruitment Started", "active_partners", "partner", 100),
    Stage("active_partner", "Active Partner", "active_partners", "partner", 100),
)
STAGE_KEYS: tuple[str, ...] = tuple(s.key for s in STAGES)
FIRST_STAGE = STAGE_KEYS[0]

# EVID-020 §4 (L164-L172), in source order and wording.
COLUMN_LABELS: dict[str, str] = {
    "target": "Target",
    "contacted": "Contacted",
    "interested": "Interested",
    "meeting_scheduled": "Meeting Scheduled",
    "proposal_sent": "Proposal Sent",
    "negotiation": "Negotiation",
    "agreement_pending": "Agreement Pending",
    "signed": "Signed",
    "active_partners": "Active Partners",
}
COLUMNS: tuple[str, ...] = tuple(COLUMN_LABELS)
GROUPS: dict[str, str] = {s.key: s.group for s in STAGES}
PROBABILITY: dict[str, int] = {s.key: s.probability for s in STAGES}
_BY_KEY: dict[str, Stage] = {s.key: s for s in STAGES}


def column_of(key: str) -> str:
    return _BY_KEY[key].column


def label_of(key: str) -> str:
    """A stage key's source label; a key no longer in the catalogue (history after a future change) is shown as stored."""
    stage = _BY_KEY.get(key)
    return stage.label if stage else key
