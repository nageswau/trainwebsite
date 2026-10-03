"""AGN-015 (DEC-SCOPE-061 §4) -- the step tracker: pure state rules per step, then the endpoint against stored rows."""

import datetime as dt
from types import SimpleNamespace as NS

import pytest

from app.services.agent_journey import application_steps, student_steps
from tests.agn001_helpers import client_for
from tests.agn008_helpers import mk_application
from tests.agn009_helpers import mk_doc, world
from tests.agn012_helpers import mk_case
from tests.agn015_helpers import journey_url, mk_deposit

SUBMITTED = dt.date(2026, 5, 1)


def states(steps):
    return {s["key"]: s["state"] for s in steps}


def app_(status="enquiry", submitted_on=None, offer_type=None):
    return NS(status=status, submitted_on=submitted_on, offer_type=offer_type)


def test_student_steps_not_started():
    assert states(student_steps(None, 0, [], False)) == {"create": "done", "counseling": "not_started", "shortlist": "not_started", "documents": "not_started"}


def test_student_steps_in_progress_and_done():
    assert states(student_steps(NS(counseling_completed=False), 0, [NS(verification_status="pending")], False))["counseling"] == "in_progress"
    s = states(student_steps(NS(counseling_completed=True), 2, [NS(verification_status="verified")], False))
    assert (s["counseling"], s["shortlist"], s["documents"]) == ("done", "done", "done")


def test_documents_open_request_or_unverified_is_in_progress():
    assert states(student_steps(None, 0, [], True))["documents"] == "in_progress"
    assert states(student_steps(None, 0, [NS(verification_status="verified")], True))["documents"] == "in_progress"
    assert states(student_steps(None, 0, [NS(verification_status="verified"), NS(verification_status="rejected")], False))["documents"] == "in_progress"


def test_application_steps_fresh():
    assert states(application_steps(app_(), None, None)) == {"application": "in_progress", "offer": "not_started", "deposit": "not_started", "visa": "not_started", "enrollment": "not_started"}


def test_application_steps_progress():
    s = states(application_steps(app_("visa_documentation", SUBMITTED), NS(status="pending"), NS(decision=None)))
    assert s == {"application": "done", "offer": "done", "deposit": "in_progress", "visa": "in_progress", "enrollment": "not_started"}
    s = states(application_steps(app_("enrolled", SUBMITTED, "unconditional"), NS(status="remitted"), NS(decision="approved")))
    assert s == {"application": "done", "offer": "done", "deposit": "done", "visa": "done", "enrollment": "done"}


def test_offer_type_counts_before_the_stage_moves():
    assert states(application_steps(app_("university_selection", offer_type="conditional"), None, None))["offer"] == "done"


@pytest.mark.parametrize("deposit,state", [("paid", "done"), ("not_required", "not_required"), ("refunded", "refunded")])
def test_deposit_states(deposit, state):
    assert states(application_steps(app_(), NS(status=deposit), None))["deposit"] == state


@pytest.mark.parametrize("decision,state", [("refused", "refused"), ("withdrawn", "withdrawn")])
def test_visa_outcomes(decision, state):
    assert states(application_steps(app_(), None, NS(decision=decision)))["visa"] == state


def test_withdrawn_application_marks_unsettled_steps_withdrawn():
    s = states(application_steps(app_("withdrawn", SUBMITTED, "conditional"), NS(status="not_required"), None))
    assert s == {"application": "done", "offer": "done", "deposit": "not_required", "visa": "withdrawn", "enrollment": "withdrawn"}


@pytest.mark.asyncio
async def test_journey_endpoint_matches_stored_data(db_session):
    w = await world(db_session)
    first = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"], status="offer", offer_type="conditional", offer_date=SUBMITTED)
    second = await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"])
    await mk_deposit(db_session, first, by=w["master"])
    await mk_case(db_session, first)
    await mk_doc(db_session, record=w["record"], status="verified")
    async with client_for(w["staff"]["user"].email) as c:
        r = await c.get(journey_url(w["record"].id))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["student"] == {"id": str(w["record"].id), "full_name": w["record"].full_name, "status": "active"}
    assert states(body["steps"]) == {"create": "done", "counseling": "not_started", "shortlist": "not_started", "documents": "done"}
    assert [a["id"] for a in body["applications"]] == [str(first.id), str(second.id)]
    assert set(body["applications"][0]) == {"id", "university", "intake", "status", "steps"}
    assert body["applications"][0]["university"] == w["university"].name
    assert states(body["applications"][0]["steps"]) == {"application": "in_progress", "offer": "done", "deposit": "in_progress", "visa": "in_progress", "enrollment": "not_started"}
    assert states(body["applications"][1]["steps"])["offer"] == "not_started"


@pytest.mark.asyncio
async def test_student_with_no_applications(db_session):
    w = await world(db_session)
    async with client_for(w["master"].email) as c:
        r = await c.get(journey_url(w["unassigned"].id))
    assert r.status_code == 200 and r.json()["applications"] == []
