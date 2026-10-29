"""nehn-033 (DEC-SCOPE-332): an overseas student's Progress stepper -- the client's display stages mapped from one application's stored
stage, submission date, offer type, outcome and visa case (the mapping is NEEDS_CONFIRMATION, OD-10). Derived on every read, never
stored. The two offer stages are one step named by the offer type. No model imports. Spec:
docs/superpowers/specs/2026-10-29-nehn-033-overseas-progress-design.md."""

from app.application_outcome import TERMINAL

STEPS = (
    ("submitted", "Application submitted"), ("under_review", "Application under review"), ("university_selected", "University selected"),
    ("offer_processing", "Offer processing"), ("offer", "Offer"), ("documentation", "Documentation"), ("visa_processing", "Visa processing"),
    ("visa_decision", "Visa decision"), ("final", "Final outcome"),
)  # fmt: skip
KEYS = tuple(key for key, _ in STEPS)
OFFER_LABELS = {"conditional": "Conditional offer", "unconditional": "Unconditional offer", "pathway": "Pathway offer", "other": "Offer received"}
DECISION_LABELS = {"approved": "Approved", "refused": "Rejected", "withdrawn": "Withdrawn"}
FINAL_LABELS = {
    "enrolled": "Enrolled", "visa_refused": "Visa rejected", "visa_withdrawn": "Visa withdrawn", "withdrawn": "Withdrawn", "rejected": "Rejected",
    "offer_declined": "Offer declined", "non_arrival": "Did not arrive", "cancelled": "Cancelled",
}  # fmt: skip
VISA_PROCESSING = frozenset({"appointment_booked", "submitted", "additional_info_requested", "decision_pending"})
NOTES = {"on_hold": "On hold", "deferred": "Deferred"}
_AT = {"eligibility_evaluation": 1, "university_review": 3, "offer": 4, "enrolled": 8}  # university_review: the seed's legacy status
_VISA, _FINAL = KEYS.index("visa_decision"), KEYS.index("final")


def _position(status: str | None, *, submitted: bool, visa_status: str | None, visa_decision: str | None) -> int:
    if visa_decision and status != "enrolled":
        return _VISA
    if status == "university_selection":
        return 3 if submitted else 2
    if status in ("visa_documentation", "status_tracking"):
        return 6 if visa_status in VISA_PROCESSING else 5
    return _AT.get(status, 0)  # enquiry or any legacy value: the first step


def _closing(status: str, outcome: str | None, visa_decision: str | None) -> str | None:
    if visa_decision in ("refused", "withdrawn"):
        return f"visa_{visa_decision}"
    if outcome in TERMINAL:
        return outcome
    return "withdrawn" if status == "withdrawn" else None


def progress(status: str, *, reached: str | None, submitted: bool, offer_type: str | None, visa_status: str | None, visa_decision: str | None, docs_complete: bool, outcome: str | None) -> dict:
    """`reached`: for a withdrawn application, the stage it was withdrawn from (its status history), else ignored."""
    at = _position(reached if status == "withdrawn" else status, submitted=submitted, visa_status=visa_status, visa_decision=visa_decision)
    closing = _closing(status, outcome, visa_decision)
    labels = dict(STEPS)
    if offer_type:
        labels["offer"] = OFFER_LABELS.get(offer_type, OFFER_LABELS["other"])
    if at >= KEYS.index("documentation"):
        labels["documentation"] = "Documentation completed" if docs_complete or at > KEYS.index("documentation") else "Documentation pending"
    if visa_decision:
        labels["visa_decision"] = f"Visa decision: {DECISION_LABELS.get(visa_decision, visa_decision)}"
    if closing or status == "enrolled":
        labels["final"] = f"Final outcome: {FINAL_LABELS[closing or 'enrolled']}"

    def state(i: int) -> str:
        if closing:
            return "done" if i < at else "stopped" if i in (at, _FINAL) else "not_reached"
        if status == "enrolled":
            return "done"
        return "done" if i < at else "current" if i == at else "upcoming"

    current = _FINAL if (closing and at != _VISA) or status == "enrolled" else at
    return {
        "current": {"key": KEYS[current], "label": labels[KEYS[current]]},
        "closed": closing is not None,
        "note": None if closing else NOTES.get(outcome),
        "steps": [{"key": key, "label": labels[key], "state": state(i)} for i, key in enumerate(KEYS)],
    }
