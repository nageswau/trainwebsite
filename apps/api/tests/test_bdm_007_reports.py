"""bdm-007 -- filing, editing and reading meeting reports (spec §5; AC1-AC7)."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select, update

from app.models import AuditLog, BdmMeetingReport, BdmTask
from app.services.bdm_appointments import IST
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm006_helpers import APPTS, bdm_with_org, create_appt, move_to_past
from tests.bdm007_helpers import REPORT, completed


def today() -> str:
    return datetime.now(IST).date().isoformat()


def in_days(n: int) -> str:
    return (datetime.now(IST) + timedelta(days=n)).date().isoformat()


async def follow_ups(db, appt_id) -> list[tuple]:
    rows = await db.execute(
        select(BdmTask.kind, BdmTask.source, BdmTask.status, BdmTask.due_on, BdmTask.assignee_user_id)
        .where(BdmTask.source_appointment_id == appt_id).execution_options(populate_existing=True)
    )
    return [tuple(r) for r in rows.all()]


@pytest.mark.asyncio
async def test_complete_files_the_report_and_one_follow_up(client, db_session):
    """AC1, AC3: Interested + next action 'Send proposal' + a follow-up date (the source example)."""
    _, bdm, org = await bdm_with_org(client, db_session)
    a = await completed(client, db_session, org, next_action="Send proposal", responsible_person="Mrs Rao", next_follow_up_on=in_days(3))
    assert (a["status"], a["outcome"], a["next_follow_up_on"]) == ("completed", "interested", in_days(3))
    r = a["report"]
    assert (r["discussion"], r["next_action"], r["responsible_person"], r["requirements"], r["legacy"]) == (
        REPORT["discussion"], "Send proposal", "Mrs Rao", None, False)
    assert r["author"]["id"] == str(bdm.id)
    assert a["follow_up"]["status"] == "open" and a["follow_up"]["due_on"] == in_days(3)
    assert a["permissions"]["can_edit_report"] is True and a["outcome_pending"] is False
    assert [(k, s, st, str(d), u) for k, s, st, d, u in await follow_ups(db_session, a["id"])] == [
        ("follow_up", "appointment_outcome", "open", in_days(3), bdm.id)]


@pytest.mark.asyncio
async def test_complete_without_a_date_creates_no_follow_up(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await completed(client, db_session, org)
    assert a["follow_up"] is None and await follow_ups(db_session, a["id"]) == []


@pytest.mark.asyncio
async def test_cannot_complete_without_a_report(client, db_session):
    """AC1: the outcome alone (bdm-006's body) is refused; nothing is written."""
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org)
    await move_to_past(db_session, a["id"])
    refused = await client.post(f"{APPTS}/{a['id']}/complete", json={"outcome": "interested"})
    assert refused.status_code == 422 and refused.json()["detail"][0]["loc"][-1] == "discussion"
    assert (await client.get(f"{APPTS}/{a['id']}")).json()["appointment"]["status"] == "scheduled"
    assert await db_session.scalar(select(func.count()).select_from(BdmMeetingReport).where(BdmMeetingReport.appointment_id == a["id"])) == 0


@pytest.mark.asyncio
async def test_report_rules_on_complete(client, db_session):
    """Future appointment -> 422; foreign outcome -> 422; past follow-up -> 422; second complete -> 409."""
    manager = await make_manager(db_session)
    await login(client, await make_bdm(db_session, manager, "agent"))
    org = await create_org(client)
    a = await create_appt(client, org, appointment_type="agent_visit")
    early = await client.post(f"{APPTS}/{a['id']}/complete", json=REPORT)
    assert (early.status_code, early.json()["detail"]) == (422, "You can only complete an appointment after its start time")
    await move_to_past(db_session, a["id"])
    foreign = await client.post(f"{APPTS}/{a['id']}/complete", json={**REPORT, "outcome": "course_promotion_interested"})
    assert (foreign.status_code, foreign.json()["detail"]) == (422, "This outcome is not available for Agent BDMs")
    stale = await client.post(f"{APPTS}/{a['id']}/complete", json={**REPORT, "outcome": "agreement_required", "next_follow_up_on": in_days(-2)})
    assert (stale.status_code, stale.json()["detail"]) == (422, "Next follow-up can't be in the past")
    ok = await client.post(f"{APPTS}/{a['id']}/complete", json={**REPORT, "outcome": "agreement_required", "next_follow_up_on": today()})
    assert ok.status_code == 200
    again = await client.post(f"{APPTS}/{a['id']}/complete", json={**REPORT, "outcome": "agreement_required"})
    assert (again.status_code, again.json()["detail"]) == (409, "Appointment is already completed")


@pytest.mark.asyncio
async def test_manager_reads_the_report_but_cannot_file_it(client, db_session):
    manager, _, org = await bdm_with_org(client, db_session)
    done = await completed(client, db_session, org)
    pending = await create_appt(client, org)
    await move_to_past(db_session, pending["id"])
    await login(client, manager)
    seen = (await client.get(f"{APPTS}/{done['id']}")).json()["appointment"]
    assert seen["report"]["discussion"] == REPORT["discussion"] and seen["permissions"]["can_edit_report"] is False
    refused = await client.post(f"{APPTS}/{pending['id']}/complete", json=REPORT)
    assert (refused.status_code, refused.json()["detail"]) == (403, "Only the appointment's BDM can change it")


@pytest.mark.asyncio
async def test_another_bdm_cannot_see_or_file(client, db_session):
    manager, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org)
    await move_to_past(db_session, a["id"])
    await login(client, await make_bdm(db_session, manager))
    assert (await client.post(f"{APPTS}/{a['id']}/complete", json=REPORT)).status_code == 404  # out of scope, not 403 (IDOR)


@pytest.mark.asyncio
async def test_reschedule_outcome_creates_nothing_server_side(client, db_session):
    """AC6: the UI links to booking; the server books nothing."""
    _, bdm, org = await bdm_with_org(client, db_session)
    await completed(client, db_session, org, outcome="reschedule")
    listed = (await client.get(APPTS, params={"organization_id": org["id"], "date_from": in_days(-3)})).json()
    assert listed["total"] == 1


@pytest.mark.asyncio
async def test_report_text_never_reaches_audit_metadata(client, db_session):
    """AC7."""
    _, _, org = await bdm_with_org(client, db_session)
    secret = "Confidential fee of 9 lakh discussed"
    a = await completed(client, db_session, org, discussion=secret, responsible_person="Mr Secret", next_follow_up_on=in_days(1))
    rows = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == a["id"]))).all()
    assert rows and all(secret not in str(m) and "Mr Secret" not in str(m) for m in rows)
    complete = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == a["id"], AuditLog.action == "bdm_appointment.complete"))).one()
    assert complete == {"from": "scheduled", "to": "completed", "outcome": "interested", "follow_up": True}
