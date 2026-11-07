"""rec-005 (DEC-SCOPE-127, spec §2): the company B2B pipeline -- the stages in order and the events that move a company. pob-004
(DEC-SCOPE-417) added the BD stages and the §4 labels; keys never change. `services/company_pipeline.py` is the only writer; migration 0296
keeps a frozen copy of the keys.

kind: "start" -- where every company begins, never chosen; "manual" -- the recruiter's own moves (P4); "driven" -- set only by
requirement events (P2). Lost and Inactive are flags on top of the stage, not stages (P5, pob-004 D3); Follow-up Due is derived (D11)."""

START, MANUAL_KIND, DRIVEN = "start", "manual", "driven"

STAGES: tuple[tuple[str, str, str], ...] = (
    ("new_lead", "Target Identified", START),
    ("research_completed", "Research Completed", MANUAL_KIND),
    ("hr_contact_identified", "HR Contact Identified", MANUAL_KIND),
    ("contacted", "Outreach Sent", MANUAL_KIND),
    ("interested", "Interested", MANUAL_KIND),
    ("meeting_scheduled", "Meeting Booked", MANUAL_KIND),
    ("requirement_discussion", "Requirement Discussion", MANUAL_KIND),
    ("vendor_registration", "Vendor Registration / Agreement", MANUAL_KIND),
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
PRE_OUTREACH = ORDER[: ORDER.index("contacted")]  # pob-004 D10: the stages today's "new lead" figures mean
# pob-004 D2: a company's standing as a client, beside the stage (the requirement-driven stages must keep moving). Forward only.
CLIENT_STATUSES: tuple[tuple[str, str], ...] = (("prospect", "Prospect"), ("active_client", "Active Client"), ("repeat_business", "Repeat Business"))
CLIENT_ORDER = tuple(key for key, _ in CLIENT_STATUSES)
CLIENT_LABELS = dict(CLIENT_STATUSES)
FIRST_CLIENT_STATUS = CLIENT_ORDER[0]


def _before(stage: str) -> frozenset[str]:
    return frozenset(ORDER[: ORDER.index(stage)])


# P2 / P3 / P8: event -> (from-set, to). Forward only, so a company sits at its furthest-progressed requirement and a repeated event never
# fires twice. The one way back: a new requirement on a company whose requirements were all closed. Callers arrive with later items.
EVENTS: dict[str, tuple[frozenset[str], str]] = {
    "hr_contact_added": (_before("hr_contact_identified"), "hr_contact_identified"),  # pob-004 D4
    "call_logged": (_before("contacted"), "contacted"),  # rec-024 / rec-025
    "contract_registration": (_before("vendor_registration"), "vendor_registration"),  # pob-004 D4
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
