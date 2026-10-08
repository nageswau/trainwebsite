"""rec-005 (DEC-SCOPE-127, spec §2): the EVID-018 §5 company B2B pipeline -- 13 stages in source order and wording, and the events that
move a company. `services/company_pipeline.py` is the only writer; migration 0112 keeps a frozen copy of the keys.

kind: "start" -- where every company begins, never chosen; "manual" -- the recruiter's own moves (P4); "driven" -- set only by
requirement events (P2). Lost is a flag on top of the stage, not a stage (P5)."""

START, MANUAL_KIND, DRIVEN = "start", "manual", "driven"

STAGES: tuple[tuple[str, str, str], ...] = (
    ("new_lead", "New Lead", START),
    ("contacted", "Contacted", MANUAL_KIND),
    ("interested", "Interested", MANUAL_KIND),
    ("meeting_scheduled", "Meeting Scheduled", MANUAL_KIND),
    ("requirement_discussion", "Requirement Discussion", MANUAL_KIND),
    ("requirement_received", "Requirement Received", DRIVEN),
    ("jd_received", "JD Received", DRIVEN),
    ("candidates_sourcing", "Candidates Sourcing", DRIVEN),
    ("profiles_shared", "Profiles Shared", DRIVEN),
    ("interview", "Interview", DRIVEN),
    ("selected", "Selected", DRIVEN),
    ("joined", "Joined", DRIVEN),
    ("requirement_closed", "Requirement Closed", DRIVEN),
)
ORDER = tuple(key for key, _, _ in STAGES)
LABELS = {key: label for key, label, _ in STAGES}
KINDS = {key: kind for key, _, kind in STAGES}
FIRST_STAGE = ORDER[0]
MANUAL = tuple(key for key, _, kind in STAGES if kind == MANUAL_KIND)


def _before(stage: str) -> frozenset[str]:
    return frozenset(ORDER[: ORDER.index(stage)])


# P2 / P3 / P8: event -> (from-set, to). Forward only, so a company sits at its furthest-progressed requirement and a repeated event never
# fires twice. The one way back: a new requirement on a company whose requirements were all closed. Callers arrive with later items.
EVENTS: dict[str, tuple[frozenset[str], str]] = {
    "call_logged": (frozenset({"new_lead"}), "contacted"),  # rec-024 / rec-025
    "meeting_scheduled": (_before("meeting_scheduled"), "meeting_scheduled"),  # rec-028
    "requirement_received": (_before("requirement_received") | {"requirement_closed"}, "requirement_received"),  # rec-007
    "jd_received": (_before("jd_received"), "jd_received"),  # rec-008
    "candidates_sourcing": (_before("candidates_sourcing"), "candidates_sourcing"),  # rec-017
    "profiles_shared": (_before("profiles_shared"), "profiles_shared"),  # rec-019
    "interview_scheduled": (_before("interview"), "interview"),  # rec-020
    "candidate_selected": (_before("selected"), "selected"),  # rec-022
    "candidate_joined": (_before("joined"), "joined"),  # rec-023
    "requirement_closed": (_before("requirement_closed"), "requirement_closed"),  # rec-007: fired when no open requirement is left
}


def label(stage: str) -> str:
    """A key no longer in the catalogue (history after a future change) is shown as stored."""
    return LABELS.get(stage, stage)
