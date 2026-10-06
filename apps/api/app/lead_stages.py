"""tel-004 (DEC-SCOPE-078, spec §2): the EVID-019 §19 lead pipeline -- 11 ordered stages and 5 closed outcomes, with the system
events that move a lead. `services/lead_pipeline.py` is the only writer; migration 0079 keeps a frozen copy of STAGES."""

OPEN_STAGES = (
    ("new", "New Lead"),
    ("assigned", "Assigned"),
    ("first_call_pending", "First Call Pending"),
    ("contacted", "Contacted"),
    ("qualified", "Qualified"),
    ("interested", "Interested"),
    ("follow_up", "Follow-up"),
    ("counselling_scheduled", "Counselling Scheduled"),
    ("counselling_completed", "Counselling Completed"),
    ("application_enrollment", "Application/Enrollment"),
    ("converted", "Converted"),
)
CLOSED_STAGES = (
    ("not_interested", "Not Interested"),
    ("not_eligible", "Not Eligible"),
    ("wrong_number", "Wrong Number"),
    ("no_response", "No Response"),
    ("lost", "Lost"),
)
STAGE_LABELS = dict(OPEN_STAGES + CLOSED_STAGES)
STAGES = tuple(STAGE_LABELS)
ORDER = tuple(key for key, _ in OPEN_STAGES)
CLOSED = frozenset(key for key, _ in CLOSED_STAGES)
MANUAL = frozenset({"qualified", "interested", "follow_up"})  # T13: the telecaller's own moves (plus the closed outcomes)
REOPEN_TO = "follow_up"  # T13: a manager reopens a closed lead here
MANUAL_BEFORE = ORDER.index("application_enrollment")  # D2: manual moves stop once the counselor's link is in place


def _through(last: str) -> frozenset[str]:
    return frozenset(ORDER[: ORDER.index(last) + 1])


# PL2 / PL4 (spec §2): event -> (from-set, to). A lead outside the from-set doesn't move, so a repeated event never fires twice.
EVENTS: dict[str, tuple[frozenset[str], str]] = {
    "assigned": (frozenset({"new"}), "assigned"),
    "call_unconnected": (frozenset({"new", "assigned"}), "first_call_pending"),
    "call_connected": (frozenset({"new", "assigned", "first_call_pending"}), "contacted"),
    "appointment_booked": (_through("follow_up"), "counselling_scheduled"),
    "appointment_completed": (_through("counselling_scheduled"), "counselling_completed"),
    "student_linked": (_through("counselling_completed"), "application_enrollment"),
    "student_unlinked": (frozenset({"application_enrollment"}), "follow_up"),
    "converted": (frozenset({"application_enrollment"}), "converted"),
}


def label(stage: str) -> str:
    """A key no longer in the catalogue (history after a future change) is shown as stored."""
    return STAGE_LABELS.get(stage, stage)
