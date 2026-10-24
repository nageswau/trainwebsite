"""ccrm-026 (DEC-SCOPE-252, VC4): a visa case's Appendix A status and how it maps onto the AGN-012 stage, the decision column and the
ccrm-014 application sub-status. One definition; the web mirrors it in apps/web/lib/visaStatus.ts and migration 0177 repeats the values
in its CHECK. No model imports."""

VISA_STATUSES = (
    "not_started", "preparing", "appointment_booked", "submitted", "additional_info_requested", "decision_pending",
    "approved", "refused", "withdrawn",
)  # fmt: skip
DECISIONS = ("approved", "refused", "withdrawn")
STAGE_OF = {
    "not_started": "checklist", "preparing": "documentation", "appointment_booked": "interview_prep", "submitted": "tracking",
    "additional_info_requested": "tracking", "decision_pending": "tracking", "approved": "decision", "refused": "decision",
    "withdrawn": "decision",
}  # fmt: skip
# The status a stage-only write (the AGN-012 agency route, the legacy counselor PATCH) lands on.
FIRST_OF_STAGE = {"checklist": "not_started", "documentation": "preparing", "interview_prep": "appointment_booked", "tracking": "submitted", "decision": "decision_pending"}
# Forward moves on the application (refused writes the visa_refused outcome instead; withdrawn changes nothing).
APPLICATION_SUB_STATUS = {
    "preparing": "visa_preparation", "appointment_booked": "visa_preparation", "submitted": "visa_applied",
    "additional_info_requested": "visa_applied", "decision_pending": "visa_decision_pending", "approved": "visa_approved",
}  # fmt: skip
LABELS = {
    "not_started": "Not started", "preparing": "Preparing", "appointment_booked": "Appointment booked", "submitted": "Submitted",
    "additional_info_requested": "Additional information requested", "decision_pending": "Decision pending", "approved": "Approved",
    "refused": "Refused", "withdrawn": "Withdrawn",
}  # fmt: skip
_BACK_AND_FORTH = frozenset({"additional_info_requested", "decision_pending"})


def label(status: str | None) -> str | None:
    return LABELS.get(status, status) if status else None


def can_move(current: str, target: str) -> bool:
    """Forward only, except Additional information requested <-> Decision pending; Withdrawn from any open status."""
    if current in DECISIONS:
        return False
    if target == "withdrawn" or {current, target} == _BACK_AND_FORTH:
        return True
    return VISA_STATUSES.index(target) > VISA_STATUSES.index(current)
