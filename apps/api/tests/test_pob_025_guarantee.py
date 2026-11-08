"""pob-025 -- the replacement guarantee, early dropouts and the expiry alert (DEC-SCOPE-436 G1-G12; AC1-AC3 + the edge). The shared test
database is never truncated, so every value is unique per test."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Company, Job, JobOffer, Notification, Placement, RecruiterContract
from app.services import placements as svc
from tests.rec001_helpers import login, make_recruiter, make_user
from tests.test_pob_024_placements import JOINED, PLACEMENTS, _accept, _join, _placement, _world
from tests.test_rec_017_tracking import _add, _candidate, _move, _requirement
from tests.test_rec_022_offers import _offer, _status

TODAY = date.today()
ALERT = "it.recruitment.guarantee_expiring"


async def _guaranteed(client, db, days=90) -> dict:
    """A joined placement on a requirement with its own guarantee."""
    s = await _world(client, db)
    job = await db.scalar(select(Job).where(Job.id == s["job"].id))
    job.guarantee_days = days
    await db.commit()
    s["placement_id"] = (await _accept(client, s))["placement_id"]
    await _join(client, s)
    return s


async def _dropout(client, placement_id, on=TODAY, reason="Left for a higher offer"):
    return await client.post(f"{PLACEMENTS}/{placement_id}/dropout", json={"dropout_on": on.isoformat(), "reason": reason})


async def _second_hire(client, db, s) -> dict:
    """Another candidate on the same requirement, Selected, with an offer (not yet accepted)."""
    candidate = await _candidate(db, s["recruiter"])
    application = (await _add(client, s["job"], candidate)).json()["application"]
    assert (await _move(client, application["id"], "selected")).status_code == 200
    return {**s, "candidate": candidate, "application": application, "offer": await _offer(client, application["id"])}


async def _alerts(db, placement_id) -> list[str]:
    rows = await db.scalars(select(Notification.user_id).where(Notification.event_type == ALERT, Notification.entity_id == placement_id))
    return sorted(str(u) for u in rows)


# --- AC1: the end date is computed from the joining date (G1/G2/G3) -----------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_end_date_is_computed_from_the_joining_date(client, db_session):
    s = await _world(client, db_session)
    job = await db_session.scalar(select(Job).where(Job.id == s["job"].id))
    job.guarantee_days = 90
    await db_session.commit()
    placement_id = (await _accept(client, s))["placement_id"]
    pending = (await _placement(client, placement_id))["guarantee"]
    assert (pending["status"], pending["end_date"], pending["days"]) == ("none", None, None)
    await _join(client, s)
    g = (await _placement(client, placement_id))["guarantee"]
    assert (g["days"], g["end_date"], g["status"], g["status_label"], g["days_left"]) == (90, (TODAY + timedelta(days=90)).isoformat(), "active", "In guarantee", 90)
    assert (g["dropout"], g["replacement"], g["replaces"]) == (None, None, None)
    job.guarantee_days = 10  # a later term edit does not move a joined placement's end date
    await db_session.commit()
    assert (await _placement(client, placement_id))["guarantee"]["end_date"] == (TODAY + timedelta(days=90)).isoformat()


@pytest.mark.asyncio
async def test_the_requirement_inherits_the_contract_guarantee(client, db_session):
    s = await _world(client, db_session)
    db_session.add(RecruiterContract(company_id=s["job"].company_id, created_by_user_id=s["recruiter"].id, status="discussion", guarantee_days=60))
    await db_session.commit()
    terms = (await client.get(f"/api/v1/recruiter/requirements/{s['job'].id}")).json()["requirement"]["commercial_terms"]
    assert terms["guarantee_days"] == {"value": 60, "inherited": True}
    placement_id = (await _accept(client, s))["placement_id"]
    await _join(client, s)
    assert (await _placement(client, placement_id))["guarantee"]["end_date"] == (TODAY + timedelta(days=60)).isoformat()
    saved = await client.patch(f"/api/v1/recruiter/requirements/{s['job'].id}", json={"guarantee_days": 30})
    assert saved.status_code == 200, saved.text
    assert saved.json()["requirement"]["commercial_terms"]["guarantee_days"] == {"value": 30, "inherited": False}
    assert (await client.patch(f"/api/v1/recruiter/requirements/{s['job'].id}", json={"guarantee_days": 366})).status_code == 422


@pytest.mark.asyncio
async def test_the_contract_carries_structured_guarantee_days(client, db_session):
    s = await _world(client, db_session)
    url = f"/api/v1/recruiter/companies/{s['job'].company_id}/contracts"
    assert (await client.post(url, json={"guarantee_days": 0})).status_code == 422
    created = await client.post(url, json={"guarantee_days": 90, "replacement_policy": "Free replacement within 90 days"})
    assert created.status_code == 201, created.text
    assert created.json()["contract"]["guarantee_days"] == 90


@pytest.mark.asyncio
async def test_no_guarantee_days_means_no_guarantee(client, db_session):
    s = await _world(client, db_session)
    placement_id = (await _accept(client, s))["placement_id"]
    await _join(client, s)
    g = (await _placement(client, placement_id))["guarantee"]
    assert (g["status"], g["status_label"], g["end_date"], g["days_left"]) == ("none", "No guarantee", None, None)
    assert (await _dropout(client, placement_id)).json()["placement"]["guarantee"]["replacement"] is None


# --- AC2: a dropout inside the guarantee opens a replacement (G4/G5) ----------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_dropout_inside_the_guarantee_opens_a_replacement(client, db_session):
    s = await _guaranteed(client, db_session)
    placement_id = s["placement_id"]
    assert (await _dropout(client, placement_id, on=TODAY + timedelta(days=1))).status_code == 422  # not in the future
    assert (await _dropout(client, placement_id, on=TODAY - timedelta(days=1))).status_code == 422  # not before joining
    assert (await _dropout(client, placement_id, reason="x")).status_code == 422
    saved = await _dropout(client, placement_id)
    assert saved.status_code == 200, saved.text
    g = saved.json()["placement"]["guarantee"]
    assert (g["status"], g["status_label"], g["dropout"]) == ("dropped_out", "Dropped out", {"on": TODAY.isoformat(), "reason": "Left for a higher offer"})
    assert (g["replacement"]["status"], g["replacement"]["status_label"], g["replacement"]["requirement"]) == ("open", "Replacement owed", None)
    assert saved.json()["placement"]["permissions"]["can_request_replacement"] is True
    assert (await _dropout(client, placement_id)).status_code == 409  # recorded once
    owed = (await client.get(PLACEMENTS, params={"view": "replacements", "limit": 100})).json()
    assert placement_id in {i["id"] for i in owed["items"]} and owed["counts"]["replacements"] >= 1
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "placement.dropout", AuditLog.entity_id == placement_id))
    assert audit.metadata_json == {"dropout_on": TODAY.isoformat(), "replacement_owed": True}


@pytest.mark.asyncio
async def test_a_dropout_after_the_guarantee_owes_no_replacement(client, db_session):
    s = await _guaranteed(client, db_session, days=30)
    offer = await db_session.scalar(select(JobOffer).where(JobOffer.id == s["offer"]["id"]))
    offer.actual_joining_date = TODAY - timedelta(days=40)
    row = await db_session.scalar(select(Placement).where(Placement.id == s["placement_id"]))
    row.guarantee_end_date = TODAY - timedelta(days=10)
    await db_session.commit()
    assert (await _placement(client, s["placement_id"]))["guarantee"]["status"] == "ended"
    g = (await _dropout(client, s["placement_id"], on=TODAY - timedelta(days=2))).json()["placement"]["guarantee"]
    assert (g["status"], g["replacement"]) == ("dropped_out", None)
    assert (await client.post(f"{PLACEMENTS}/{s['placement_id']}/replacement", json={"job_id": str(s["job"].id)})).status_code == 409


@pytest.mark.asyncio
async def test_a_dropout_needs_a_joined_placement(client, db_session):
    s = await _world(client, db_session)
    placement_id = (await _accept(client, s))["placement_id"]
    assert (await _dropout(client, placement_id)).status_code == 409
    assert (await _placement(client, placement_id))["permissions"]["can_record_dropout"] is False


# --- G6-G8: the replacement request, its fill and a replacement that does not join --------------------------------------------------
@pytest.mark.asyncio
async def test_the_replacement_is_linked_filled_and_carries_no_fee(client, db_session):
    s = await _guaranteed(client, db_session)
    original = s["placement_id"]
    await _dropout(client, original)
    other = await _requirement(db_session, s["recruiter"])  # another client's requirement
    url = f"{PLACEMENTS}/{original}/replacement"
    assert (await client.post(url, json={"job_id": str(other.id)})).status_code == 422
    linked = await client.post(url, json={"job_id": str(s["job"].id)})
    assert linked.status_code == 200, linked.text
    r = linked.json()["placement"]["guarantee"]["replacement"]
    assert (r["status"], r["status_label"], r["requirement"]["id"]) == ("requested", "Replacement in progress", str(s["job"].id))
    second = await _second_hire(client, db_session, s)
    accepted = await _status(client, second["offer"]["id"], "accepted")
    assert accepted.status_code == 200, accepted.text
    replacement_id = accepted.json()["offer"]["placement_id"]
    new = await _placement(client, replacement_id)
    assert new["guarantee"]["replaces"]["id"] == original and new["commercials"]["expected_fee"] == "0.00"
    filled = (await _placement(client, original))["guarantee"]["replacement"]
    assert (filled["status"], filled["status_label"], filled["placement"]["id"]) == ("filled", "Replaced", replacement_id)
    joined = await client.put(f"/api/v1/recruiter/offers/{second['offer']['id']}/joining", json=JOINED)
    assert joined.status_code == 200, joined.text
    assert (await _placement(client, replacement_id))["commercials"]["invoice"]["status"] == "none"  # no new fee, no draft
    assert (await client.post(url, json={"job_id": str(s["job"].id)})).status_code == 409  # filled


@pytest.mark.asyncio
async def test_a_replacement_that_does_not_join_reopens_the_request(client, db_session):
    s = await _guaranteed(client, db_session)
    original = s["placement_id"]
    await _dropout(client, original)
    await client.post(f"{PLACEMENTS}/{original}/replacement", json={"job_id": str(s["job"].id)})
    second = await _second_hire(client, db_session, s)
    await _status(client, second["offer"]["id"], "accepted")
    refused = await client.put(f"/api/v1/recruiter/offers/{second['offer']['id']}/joining", json={"joining_status": "did_not_join", "reason": "Declined late"})
    assert refused.status_code == 200, refused.text
    r = (await _placement(client, original))["guarantee"]["replacement"]
    assert (r["status"], r["placement"]) == ("requested", None)


@pytest.mark.asyncio
async def test_guarantee_scope_and_writers(client, db_session):
    s = await _guaranteed(client, db_session)
    placement_id = s["placement_id"]
    bdm = await make_user(db_session, "bdm", "it")
    company = await db_session.scalar(select(Company).where(Company.id == s["job"].company_id))
    company.assigned_bdm_user_id = bdm.id
    await db_session.commit()
    await login(client, bdm)
    p = await _placement(client, placement_id)
    assert p["guarantee"]["status"] == "active"
    assert (p["permissions"]["can_record_dropout"], p["permissions"]["can_request_replacement"]) == (False, False)
    assert (await _dropout(client, placement_id)).status_code == 403
    await login(client, await make_recruiter(db_session, await make_user(db_session, "placement_manager", "global")))
    assert (await _dropout(client, placement_id)).status_code == 404
    assert (await client.post(f"{PLACEMENTS}/{placement_id}/replacement", json={"job_id": str(s["job"].id)})).status_code == 404


# --- AC3: the expiry alert fires once (G10) ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_expiry_alert_fires_once(client, db_session):
    near = await _guaranteed(client, db_session)
    past = await _guaranteed(client, db_session)
    far = await _guaranteed(client, db_session)
    dropped = await _guaranteed(client, db_session)
    await _dropout(client, dropped["placement_id"])
    for s, end in ((near, TODAY + timedelta(days=3)), (past, TODAY - timedelta(days=1)), (far, TODAY + timedelta(days=20)), (dropped, TODAY + timedelta(days=2))):
        row = await db_session.scalar(select(Placement).where(Placement.id == s["placement_id"]))
        row.guarantee_end_date = end
    await db_session.commit()
    for _ in range(2):
        await svc.run_guarantee_alerts()
    assert await _alerts(db_session, near["placement_id"]) == sorted({str(near["recruiter"].id), str(near["manager"].id)})
    for s in (past, far, dropped):
        assert await _alerts(db_session, s["placement_id"]) == []
    note = await db_session.scalar(select(Notification).where(Notification.event_type == ALERT, Notification.entity_id == near["placement_id"]).limit(1))
    assert note.action_url == f"/recruiter/placements/{near['placement_id']}" and near["candidate"].name not in note.body
    row = await db_session.scalar(select(Placement).where(Placement.id == near["placement_id"]).execution_options(populate_existing=True))
    assert row.guarantee_alerted_at is not None


def test_the_guarantee_worker_task_imports_in_a_fresh_interpreter():
    import subprocess
    import sys

    code = "import app.worker; import app.services.telecaller_alerts; from app.services.placements import run_guarantee_alerts; app.worker.placement_guarantee_alerts_task"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd="/app")
    assert result.returncode == 0, result.stderr[-2000:]
    from app.worker import celery

    assert celery.conf.beat_schedule["pob025-guarantee-alerts"]["task"] == "app.worker.placement_guarantee_alerts_task"
