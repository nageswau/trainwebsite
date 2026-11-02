"""itc-007 (DEC-SCOPE-338, API §12IJ, RBAC §2.240): merge a duplicate lead into the lead that stays. The shared test database is never
truncated: every assertion is about rows the test made."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import (
    Appointment,
    AuditLog,
    Enquiry,
    LeadCall,
    LeadEnquiry,
    LeadFollowUp,
    LeadNote,
    LeadQualification,
    LeadStageHistory,
)
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import lead, make_telecaller, make_tl_manager, make_user, stage_url
from tests.tel018_helpers import make_student

pytestmark = pytest.mark.asyncio

TEL = "/api/v1/telecaller/leads"
ADMIN = "/api/v1/admin/leads"


def merge_url(lead_id, *, admin: bool = False) -> str:
    return f"{ADMIN if admin else TEL}/{lead_id}/merge"


def preview_url(lead_id, code: str, *, admin: bool = False) -> str:
    return f"{ADMIN if admin else TEL}/{lead_id}/merge-preview?victim={code}"


async def stored(db, row) -> Enquiry:
    return await db.scalar(select(Enquiry).where(Enquiry.id == row.id).execution_options(populate_existing=True))


async def team(client, db, *, division: str = "it"):
    """A manager signed in, their telecaller, and two open leads of that telecaller."""
    manager = await make_tl_manager(db)
    tel = await make_telecaller(db, manager, team=division)
    survivor = await lead(db, division=division, telecaller=tel, status="contacted")
    victim = await lead(db, division=division, telecaller=tel, status="new")
    await as_user(client, manager)
    return manager, tel, survivor, victim


async def activity(db, victim: Enquiry, author) -> None:
    now = datetime.now(UTC)
    db.add_all(
        [
            LeadCall(lead_id=victim.id, caller_user_id=author.id, occurred_at=now - timedelta(hours=1), duration_seconds=60, call_type="outgoing", outcome="busy"),
            LeadFollowUp(lead_id=victim.id, due_at=now + timedelta(days=1), reason="course_details", created_by_user_id=author.id),
            LeadNote(lead_id=victim.id, author_user_id=author.id, body="Prefers evenings"),
            LeadEnquiry(lead_id=victim.id, subject="Java", message="Also Java?", source="website"),
        ]
    )
    await db.commit()


async def count(db, model, lead_id) -> int:
    return await db.scalar(select(func.count()).select_from(model).where(model.lead_id == lead_id))


# --- the happy path (AC1, AC2, AC4) ------------------------------------------------------------------------------------------------
async def test_a_manager_merges_two_leads_and_every_activity_moves_to_the_survivor(client, db_session):
    manager, tel, survivor, victim = await team(client, db_session)
    await activity(db_session, victim, tel)
    response = await client.post(merge_url(survivor.id), json={"victim": victim.lead_code.lower(), "reason": "Same phone"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["victim_code"] == victim.lead_code
    assert body["moved"] == {"calls": 1, "follow_ups": 1, "notes": 1, "messages": 0, "meetings": 0, "appointments": 0, "enquiries": 2, "tasks": 0}
    for model in (LeadCall, LeadFollowUp, LeadNote):
        assert await count(db_session, model, victim.id) == 0 and await count(db_session, model, survivor.id) == 1
    # the victim's own enquiry is kept on the survivor, at its original time
    kept = await db_session.scalar(select(LeadEnquiry).where(LeadEnquiry.lead_id == survivor.id, LeadEnquiry.subject == victim.subject))
    assert kept.metadata_json == {"merged_from": victim.lead_code} and kept.created_at == victim.created_at

    closed = await stored(db_session, victim)
    assert closed.status == "duplicate" and closed.duplicate_of_id == survivor.id
    assert closed.merged_by_user_id == manager.id and closed.merged_at is not None
    h = await db_session.scalar(select(LeadStageHistory).where(LeadStageHistory.lead_id == victim.id, LeadStageHistory.to_stage == "duplicate"))
    assert h.event == "merge" and h.reason == "Same phone" and h.actor_user_id == manager.id

    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "lead.merge", AuditLog.entity_id == str(survivor.id)))).all()
    assert len(audits) == 1
    meta = audits[0].metadata_json
    assert meta["victim_id"] == str(victim.id) and meta["moved"]["calls"] == 1 and "Same phone" not in str(meta)

    timeline = (await client.get(f"{TEL}/{survivor.id}/timeline?limit=100")).json()["items"]
    kinds = {row["kind"] for row in timeline}
    assert {"call", "follow_up", "note", "merge"} <= kinds
    merge_row = next(row for row in timeline if row["kind"] == "merge")
    assert merge_row["from_value"] == victim.lead_code and merge_row["actor"]["id"] == str(manager.id)


async def test_the_preview_shows_both_leads_and_what_would_move_without_writing(client, db_session):
    _, tel, survivor, victim = await team(client, db_session)
    await activity(db_session, victim, tel)
    response = await client.get(preview_url(survivor.id, victim.lead_code))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["survivor"]["lead_code"] == survivor.lead_code and body["victim"]["lead_code"] == victim.lead_code
    assert body["victim"]["email"] == victim.email and body["moved"]["calls"] == 1 and body["moved"]["enquiries"] == 2
    assert (await stored(db_session, victim)).status == "new"


# --- the field picker and fill-empty-only ---------------------------------------------------------------------------------------
async def test_empty_fields_fill_from_the_victim_and_picked_fields_take_its_value(client, db_session):
    manager, _, survivor, victim = await team(client, db_session)
    victim.city, victim.phone, victim.name = "Pune", "+91 98765 43210", "Asha Rao"
    survivor.city = None
    db_session.add_all(
        [
            LeadQualification(lead_id=survivor.id, current_org=None, work_experience_years=2, updated_by_user_id=manager.id),
            LeadQualification(lead_id=victim.id, current_org="Infosys", work_experience_years=5, updated_by_user_id=manager.id),
        ]
    )
    await db_session.commit()
    response = await client.post(merge_url(survivor.id), json={"victim": victim.lead_code, "use_victim": ["name"]})
    assert response.status_code == 200, response.text
    kept = await stored(db_session, survivor)
    assert (kept.city, kept.phone, kept.name) == ("Pune", "+91 98765 43210", "Asha Rao")
    q = await db_session.scalar(select(LeadQualification).where(LeadQualification.lead_id == survivor.id).execution_options(populate_existing=True))
    assert (q.current_org, q.work_experience_years) == ("Infosys", 2)  # empty filled, a set value kept
    meta = (await db_session.scalar(select(AuditLog).where(AuditLog.action == "lead.merge", AuditLog.entity_id == str(survivor.id)))).metadata_json
    assert meta["changes"]["city"] == [None, "Pune"] and meta["changes"]["phone"] == "changed"  # itc-001: PII never as a value


async def test_a_survivor_without_qualification_takes_the_victims_row(client, db_session):
    manager, _, survivor, victim = await team(client, db_session)
    db_session.add(LeadQualification(lead_id=victim.id, current_org="TCS", updated_by_user_id=manager.id))
    await db_session.commit()
    assert (await client.post(merge_url(survivor.id), json={"victim": victim.lead_code})).status_code == 200
    q = await db_session.scalar(select(LeadQualification).where(LeadQualification.lead_id == survivor.id))
    assert q is not None and q.current_org == "TCS"


async def test_a_bad_field_name_is_422(client, db_session):
    _, _, survivor, victim = await team(client, db_session)
    response = await client.post(merge_url(survivor.id), json={"victim": victim.lead_code, "use_victim": ["status"]})
    assert response.status_code == 422


# --- edge cases ------------------------------------------------------------------------------------------------------------------
async def test_when_both_have_an_open_appointment_the_victims_is_cancelled_and_moved(client, db_session):
    _, tel, survivor, victim = await team(client, db_session)
    at = datetime.now(UTC) + timedelta(days=2)
    keep = Appointment(division="it", lead_id=survivor.id, scheduled_at=at, appointment_type="counselling", status="scheduled")
    drop = Appointment(division="it", lead_id=victim.id, scheduled_at=at, appointment_type="counselling", status="scheduled")
    db_session.add_all([keep, drop])
    await db_session.commit()
    response = await client.post(merge_url(survivor.id), json={"victim": victim.lead_code})
    assert response.status_code == 200, response.text
    rows = {a.id: a for a in (await db_session.scalars(select(Appointment).where(Appointment.lead_id == survivor.id).execution_options(populate_existing=True))).all()}
    assert rows[keep.id].status == "scheduled" and rows[drop.id].status == "cancelled"


async def test_leads_closed_as_a_duplicate_of_the_victim_now_point_at_the_survivor(client, db_session):
    _, _, survivor, victim = await team(client, db_session)
    other = Enquiry(division="it", name="Dup", email=f"{uuid.uuid4().hex[:8]}@example.local", subject="S", message="", source="website", status="duplicate", duplicate_of_id=victim.id)
    db_session.add(other)
    await db_session.commit()
    assert (await client.post(merge_url(survivor.id), json={"victim": victim.lead_code})).status_code == 200
    assert (await stored(db_session, other)).duplicate_of_id == survivor.id


# --- refusals (AC3; − cases) -----------------------------------------------------------------------------------------------------
async def test_a_telecaller_cannot_merge(client, db_session):
    _, tel, survivor, victim = await team(client, db_session)
    await as_user(client, tel)
    assert (await client.post(merge_url(survivor.id), json={"victim": victim.lead_code})).status_code == 403
    assert (await client.get(preview_url(survivor.id, victim.lead_code))).status_code == 403


async def test_a_victim_outside_the_managers_scope_or_unknown_is_404(client, db_session):
    _, _, survivor, _ = await team(client, db_session)
    other_manager = await make_tl_manager(db_session)
    outside = await lead(db_session, division="it", telecaller=await make_telecaller(db_session, other_manager))
    for code in (outside.lead_code, "LD-999999999"):
        assert (await client.post(merge_url(survivor.id), json={"victim": code})).status_code == 404
    assert (await stored(db_session, outside)).status == "new"


async def test_merging_into_itself_is_422(client, db_session):
    _, _, survivor, _ = await team(client, db_session)
    response = await client.post(merge_url(survivor.id), json={"victim": survivor.lead_code})
    assert response.status_code == 422 and response.json()["detail"][0]["loc"][-1] == "victim"


async def test_leads_of_different_teams_are_409(client, db_session):
    admin = await make_user(db_session, "super_admin", "global")
    survivor, victim = await lead(db_session, division="it"), await lead(db_session, division="overseas")
    await as_user(client, admin)
    assert (await client.post(merge_url(survivor.id), json={"victim": victim.lead_code})).status_code == 409


@pytest.mark.parametrize("which", ["survivor", "victim"])
async def test_a_closed_lead_cannot_be_merged(client, db_session, which):
    _, _, survivor, victim = await team(client, db_session)
    target = survivor if which == "survivor" else victim
    target.status = "no_response"
    await db_session.commit()
    assert (await client.post(merge_url(survivor.id), json={"victim": victim.lead_code})).status_code == 409


async def test_a_victim_linked_to_a_student_is_409(client, db_session):
    manager, _, survivor, victim = await team(client, db_session)
    student = await make_student(db_session)
    victim.converted_user_id, victim.converted_at, victim.converted_by_user_id = student.id, datetime.now(UTC), manager.id
    victim.status = "application_enrollment"
    await db_session.commit()
    assert (await client.post(merge_url(survivor.id), json={"victim": victim.lead_code})).status_code == 409


# --- a merged lead is read only (AC2) --------------------------------------------------------------------------------------------
async def test_a_merged_lead_cannot_be_reopened_or_edited(client, db_session):
    _, _, survivor, victim = await team(client, db_session)
    assert (await client.post(merge_url(survivor.id), json={"victim": victim.lead_code})).status_code == 200
    reopen = await client.post(stage_url(victim.id), json={"to_stage": "follow_up", "reason": "Oops"})
    assert reopen.status_code == 409
    assert (await client.patch(f"{TEL}/{victim.id}", json={"city": "Delhi"})).status_code == 409
    detail = (await client.get(f"{TEL}/{victim.id}")).json()
    assert detail["merged_at"] is not None and detail["duplicate_of"]["lead_code"] == survivor.lead_code
    assert detail["read_only"] is True  # for the manager too: the page shows no control
    admin = await make_user(db_session, "super_admin", "global")
    await as_user(client, admin)
    assert (await client.patch(f"{ADMIN}/{victim.id}", json={"status": "follow_up", "reason": "Oops"})).status_code == 409


# --- the admin route --------------------------------------------------------------------------------------------------------------
async def test_an_it_admin_merges_it_leads_but_not_another_divisions(client, db_session):
    it_admin = await make_user(db_session, "it_admin", "it")
    survivor, victim = await lead(db_session, division="it"), await lead(db_session, division="it")
    overseas = await lead(db_session, division="overseas")
    await as_user(client, it_admin)
    assert (await client.get(preview_url(survivor.id, victim.lead_code, admin=True))).status_code == 200
    assert (await client.post(merge_url(survivor.id, admin=True), json={"victim": overseas.lead_code})).status_code == 404
    assert (await client.post(merge_url(overseas.id, admin=True), json={"victim": victim.lead_code})).status_code == 404
    response = await client.post(merge_url(survivor.id, admin=True), json={"victim": victim.lead_code})
    assert response.status_code == 200, response.text
    assert (await stored(db_session, victim)).duplicate_of_id == survivor.id


async def test_other_roles_are_403_on_the_admin_route(client, db_session):
    _, tel, survivor, victim = await team(client, db_session)
    await as_user(client, tel)
    assert (await client.post(merge_url(survivor.id, admin=True), json={"victim": victim.lead_code})).status_code == 403
