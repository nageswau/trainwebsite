"""nehn-033 (DEC-SCOPE-332): the student's Progress stepper -- the pure mapping in app/overseas_progress.py from the stored application,
offer and visa data onto the client's display stages (NEEDS_CONFIRMATION, OD-10). Derived on every read, never stored."""

import pytest

from app.overseas_progress import KEYS, progress


def run(status: str, **kw):
    args = {"submitted": False, "offer_type": None, "visa_status": None, "visa_decision": None, "docs_complete": False, "outcome": None, "reached": None} | kw
    return progress(status, **args)


def states(result) -> list[str]:
    return [s["state"] for s in result["steps"]]


def test_nine_steps_in_order():
    assert KEYS == ("submitted", "under_review", "university_selected", "offer_processing", "offer", "documentation", "visa_processing", "visa_decision", "final")


@pytest.mark.parametrize(
    ("status", "kw", "current"),
    [
        ("enquiry", {}, "submitted"),
        ("profile_evaluation", {}, "submitted"),  # a legacy value reads the first step
        ("eligibility_evaluation", {}, "under_review"),
        ("university_selection", {}, "university_selected"),
        ("university_selection", {"submitted": True}, "offer_processing"),
        ("university_review", {}, "offer_processing"),
        ("offer", {}, "offer"),
        ("visa_documentation", {}, "documentation"),
        ("visa_documentation", {"visa_status": "preparing"}, "documentation"),
        ("status_tracking", {"visa_status": "submitted"}, "visa_processing"),
        ("status_tracking", {"visa_status": "decision_pending"}, "visa_processing"),
        ("status_tracking", {"visa_status": "approved", "visa_decision": "approved"}, "visa_decision"),
    ],
)
def test_each_stored_state_maps_to_one_current_step(status, kw, current):
    result = run(status, **kw)
    assert result["current"]["key"] == current
    at = KEYS.index(current)
    assert states(result) == ["done"] * at + ["current"] + ["upcoming"] * (len(KEYS) - at - 1)
    assert result["closed"] is False


def test_ac1_a_conditional_offer_is_the_current_step_with_earlier_steps_done():
    result = run("offer", offer_type="conditional", submitted=True)
    assert result["current"] == {"key": "offer", "label": "Conditional offer"}
    assert states(result)[:5] == ["done", "done", "done", "done", "current"]


@pytest.mark.parametrize(("offer_type", "label"), [("unconditional", "Unconditional offer"), ("pathway", "Pathway offer"), ("other", "Offer received"), (None, "Offer")])
def test_the_offer_step_names_the_offer_type(offer_type, label):
    assert run("offer", offer_type=offer_type)["steps"][4]["label"] == label


def test_documentation_reads_pending_until_the_visa_checklist_is_complete():
    assert run("visa_documentation")["current"]["label"] == "Documentation pending"
    assert run("visa_documentation", docs_complete=True)["current"]["label"] == "Documentation completed"
    assert run("status_tracking", visa_status="submitted")["steps"][5]["label"] == "Documentation completed"
    assert run("offer")["steps"][5]["label"] == "Documentation"


def test_ac2_a_refused_visa_shows_visa_decision_rejected_as_the_final_outcome():
    result = run("status_tracking", visa_status="refused", visa_decision="refused", outcome="visa_refused")
    assert result["closed"] is True
    assert result["current"] == {"key": "visa_decision", "label": "Visa decision: Rejected"}
    assert result["steps"][7] == {"key": "visa_decision", "label": "Visa decision: Rejected", "state": "stopped"}
    assert result["steps"][8] == {"key": "final", "label": "Final outcome: Visa rejected", "state": "stopped"}
    assert states(result)[:7] == ["done"] * 7


def test_a_withdrawn_visa_decision_closes_the_application():
    result = run("status_tracking", visa_status="withdrawn", visa_decision="withdrawn")
    assert result["current"]["label"] == "Visa decision: Withdrawn"
    assert result["steps"][8]["label"] == "Final outcome: Visa withdrawn"


def test_an_approved_visa_leaves_the_final_outcome_current_until_enrolled():
    result = run("status_tracking", visa_status="approved", visa_decision="approved")
    assert result["steps"][7] == {"key": "visa_decision", "label": "Visa decision: Approved", "state": "current"}
    assert result["steps"][8]["state"] == "upcoming"


def test_enrolled_completes_every_step():
    result = run("enrolled", visa_decision="approved")
    assert states(result) == ["done"] * 9
    assert result["current"] == {"key": "final", "label": "Final outcome: Enrolled"}
    assert result["closed"] is False


def test_a_withdrawn_application_stops_at_the_step_it_reached():
    result = run("withdrawn", reached="offer", offer_type="conditional")
    assert result["closed"] is True
    assert states(result) == ["done"] * 4 + ["stopped", "not_reached", "not_reached", "not_reached", "stopped"]
    assert result["current"] == {"key": "final", "label": "Final outcome: Withdrawn"}


def test_a_withdrawn_application_without_history_stops_at_the_first_step():
    assert states(run("withdrawn"))[0] == "stopped"


@pytest.mark.parametrize(("outcome", "label"), [("rejected", "Rejected"), ("offer_declined", "Offer declined"), ("non_arrival", "Did not arrive"), ("cancelled", "Cancelled")])
def test_a_terminal_outcome_closes_the_application(outcome, label):
    result = run("offer", outcome=outcome)
    assert result["closed"] is True
    assert result["steps"][4]["state"] == "stopped"
    assert result["current"]["label"] == f"Final outcome: {label}"


@pytest.mark.parametrize(("outcome", "note"), [("on_hold", "On hold"), ("deferred", "Deferred"), (None, None)])
def test_on_hold_and_deferred_stay_live_with_a_note(outcome, note):
    result = run("university_selection", outcome=outcome)
    assert (result["closed"], result["note"]) == (False, note)
