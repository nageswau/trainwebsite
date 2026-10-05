"""bdm-006 -- status actions (AC3, AC4, AC5; spec §5.3, §5.4)."""

from datetime import datetime, timedelta

import pytest

from app.services.bdm_appointments import IST
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm006_helpers import APPTS, audits, bdm_with_org, create_appt, future, move_to_past


def url(appt: dict, action: str) -> str:
    return f"{APPTS}/{appt['id']}/{action}"


@pytest.mark.asyncio
async def test_book_confirm_complete_with_outcome(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org)
    confirmed = (await client.post(url(a, "confirm"))).json()["appointment"]
    assert confirmed["status"] == "confirmed" and confirmed["permissions"]["can_confirm"] is False
    early = await client.post(url(a, "complete"), json={"discussion": "Met", "outcome": "interested"})
    assert (early.status_code, early.json()["detail"]) == (422, "You can only complete an appointment after its start time")
    await move_to_past(db_session, a["id"])
    done = await client.post(url(a, "complete"), json={"discussion": "Met", "outcome": "student_leads_expected", "next_follow_up_on": datetime.now(IST).date().isoformat()})
    assert done.status_code == 200, done.text
    d = done.json()["appointment"]
    assert (d["status"], d["outcome"]) == ("completed", "student_leads_expected") and d["next_follow_up_on"]
    assert [(e["from_status"], e["to_status"]) for e in d["events"]] == [(None, "scheduled"), ("scheduled", "confirmed"), ("confirmed", "completed")]
    assert {k for k, v in d["permissions"].items() if v} == {"can_edit_report"}  # bdm-007: the author may fix the report today
    assert await audits(db_session, a["id"]) == ["bdm_appointment.create", "bdm_appointment.confirm", "bdm_appointment.complete"]


@pytest.mark.asyncio
async def test_reschedule_twice_keeps_both_old_times(client, db_session):
    """AC4: each reschedule records its old time; the status is Rescheduled both times."""
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org, starts_at=future(30))
    t2, t3 = future(40), future(50)
    first = (await client.post(url(a, "reschedule"), json={"starts_at": t2, "reason": "Principal travelling"})).json()["appointment"]
    second = (await client.post(url(a, "reschedule"), json={"starts_at": t3, "duration_minutes": 30})).json()["appointment"]
    assert (second["status"], second["duration_minutes"]) == ("rescheduled", 30)
    moves = [(e["from_status"], e["to_status"], e["old_starts_at"], e["new_starts_at"], e["reason"]) for e in second["events"][1:]]
    assert moves == [
        ("scheduled", "rescheduled", a["starts_at"], first["starts_at"], "Principal travelling"),
        ("rescheduled", "rescheduled", first["starts_at"], second["starts_at"], None),
    ]
    assert (await client.post(url(a, "confirm"))).json()["appointment"]["status"] == "confirmed"  # rescheduled -> confirmed


@pytest.mark.asyncio
async def test_reschedule_rules(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org, starts_at=future(30))
    b = await create_appt(client, org, starts_at=future(60))
    same = await client.post(url(a, "reschedule"), json={"starts_at": a["starts_at"]})
    assert (same.status_code, same.json()["detail"]) == (422, "Choose a different time")
    past = await client.post(url(a, "reschedule"), json={"starts_at": future(-2)})
    assert (past.status_code, past.json()["detail"]) == (422, "Choose a time in the future")
    clash = await client.post(url(a, "reschedule"), json={"starts_at": b["starts_at"]})
    assert clash.status_code == 409 and clash.json()["detail"]["code"] == "possible_overlap"
    ok = await client.post(url(a, "reschedule"), json={"starts_at": b["starts_at"], "confirm_overlap": True})
    assert ok.status_code == 200
    # same transaction => identical created_at, UUID ids: relative order is not defined
    assert sorted((await audits(db_session, a["id"]))[-2:]) == ["bdm_appointment.overlap_override", "bdm_appointment.reschedule"]


@pytest.mark.asyncio
async def test_cancel_and_no_show_need_a_reason_and_are_terminal(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org, starts_at=future(30))
    b = await create_appt(client, org, starts_at=future(60))
    assert (await client.post(url(a, "cancel"), json={})).status_code == 422
    assert (await client.post(url(a, "cancel"), json={"reason": "  "})).status_code == 422
    cancelled = (await client.post(url(a, "cancel"), json={"reason": "College closed"})).json()["appointment"]
    assert cancelled["status"] == "cancelled" and cancelled["events"][-1]["reason"] == "College closed"
    for action, body in (("confirm", None), ("cancel", {"reason": "x"}), ("reschedule", {"starts_at": future(90)})):
        response = await client.post(url(a, action), json=body)
        assert (response.status_code, response.json()["detail"]) == (409, "Appointment is already cancelled"), action
    early = await client.post(url(b, "no-show"), json={"reason": "Nobody came"})
    assert (early.status_code, early.json()["detail"]) == (422, "You can only mark a no-show after the start time")
    await move_to_past(db_session, b["id"])
    assert (await client.post(url(b, "no-show"), json={"reason": "Nobody came"})).json()["appointment"]["status"] == "no_show"
    again = await client.post(url(b, "complete"), json={"discussion": "Met", "outcome": "interested"})
    assert (again.status_code, again.json()["detail"]) == (409, "Appointment is already marked as a no-show")


@pytest.mark.asyncio
async def test_complete_validates_outcome_per_type_and_follow_up_date(client, db_session):
    manager = await make_manager(db_session)
    await login(client, await make_bdm(db_session, manager, "agent"))
    org = await create_org(client)
    a = await create_appt(client, org, appointment_type="agent_visit")
    await move_to_past(db_session, a["id"])
    foreign = await client.post(url(a, "complete"), json={"discussion": "Met", "outcome": "course_promotion_interested"})
    assert (foreign.status_code, foreign.json()["detail"]) == (422, "This outcome is not available for Agent BDMs")
    two_days_ago = (datetime.now(IST) - timedelta(days=2)).date().isoformat()
    stale = await client.post(url(a, "complete"), json={"discussion": "Met", "outcome": "agreement_required", "next_follow_up_on": two_days_ago})
    assert (stale.status_code, stale.json()["detail"]) == (422, "Next follow-up can't be in the past")
    assert (await client.post(url(a, "complete"), json={"discussion": "Met", "outcome": "agreement_required"})).status_code == 200


@pytest.mark.asyncio
async def test_confirm_twice_is_409(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org)
    assert (await client.post(url(a, "confirm"))).status_code == 200
    again = await client.post(url(a, "confirm"))
    assert (again.status_code, again.json()["detail"]) == (409, "Appointment is already confirmed")
