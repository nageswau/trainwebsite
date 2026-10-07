"""tel-025 -- GET /admin/telecallers/{id}/open-work, POST .../deactivate and POST .../handover (spec §2; AC1-AC4, AC7; LC1-LC4)."""

import uuid

import pytest
from sqlalchemy import func, select

from app.models import Appointment, Enquiry, LeadCall, LeadFollowUp, LeadStageHistory, Notification, TelDistributionRule, User
from tests.tel016_helpers import make_counselor
from tests.tel025_helpers import (
    TELECALLERS,
    as_user,
    audit_rows,
    call,
    follow_up,
    fresh,
    lead,
    lead_appt,
    make_telecaller,
    make_user,
    post,
    rule_for,
    team,
)


def url(user_id, action: str) -> str:
    return f"{TELECALLERS}/{user_id}/{action}"


async def _work(db, a):
    """A's open work (moves) and history (stays)."""
    counselor = await make_counselor(db)
    open_leads = [await lead(db, telecaller=a, status="new"), await lead(db, telecaller=a, status="follow_up"),
                  await lead(db, telecaller=a, status="counselling_scheduled")]
    handed = await lead(db, telecaller=a, status="interested")
    handed.owner_id = counselor.id  # LC2: handed over to a counselor, still open -- it moves; the counselor stays owner
    await db.commit()
    open_leads.append(handed)
    fups = [await follow_up(db, open_leads[0], a), await follow_up(db, open_leads[1], a)]
    appt = await lead_appt(db, open_leads[2], a, counselor)
    stays = {
        "closed": await lead(db, telecaller=a, status="not_interested"),
        "converted": await lead(db, telecaller=a, status="converted"),
        "done_fup": await follow_up(db, open_leads[0], a, status="done"),
        "call": await call(db, open_leads[0], a),
    }
    return open_leads, fups, appt, counselor, stays


@pytest.mark.asyncio
async def test_open_work_preview_counts_only_open_leads(client, db_session):
    _, a, _ = await team(db_session)
    await _work(db_session, a)
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    response = await client.get(url(a.id, "open-work"))
    assert response.status_code == 200, response.text
    assert response.json() == {"leads": 4, "follow_ups": 2, "appointments": 1}


@pytest.mark.asyncio
async def test_deactivate_to_a_telecaller_moves_open_work_and_keeps_history(client, db_session):
    _, a, b = await team(db_session)
    open_leads, fups, appt, counselor, stays = await _work(db_session, a)
    a_rule = await rule_for(db_session, a)
    admin = await make_user(db_session, "super_admin", "global")
    await as_user(client, admin)

    response = await post(client, url(a.id, "deactivate"), {"target": "telecaller", "reassign_to": str(b.id)})
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(a.id), "active": False, "target": "telecaller",
                               "moved": {"leads": 4, "follow_ups": 2, "appointments": 1}, "rules_removed": 1}
    source = await fresh(db_session, User, a.id)
    assert source.active is False
    # AC1: no open lead (so no open follow-up or appointment, which belong to the lead) stays with A
    for x in open_leads:
        moved = await fresh(db_session, Enquiry, x.id)
        assert moved.telecaller_user_id == b.id
        [audit] = await audit_rows(db_session, "lead.assign", x.id)
        assert audit.user_id == admin.id and audit.metadata_json == {"from": str(a.id), "to": str(b.id), "method": "deactivation"}
    assert (await fresh(db_session, Enquiry, open_leads[3].id)).owner_id == counselor.id  # the counselor stays owner
    assert (await fresh(db_session, Enquiry, open_leads[0].id)).status == "assigned"  # tel-007: a new lead's `assigned` event
    for f in fups:
        assert (await fresh(db_session, LeadFollowUp, f.id)).status == "open"
    assert (await fresh(db_session, Appointment, appt.id)).booked_by_user_id == a.id
    # AC2: history and credit stay with A
    assert (await fresh(db_session, Enquiry, stays["closed"].id)).telecaller_user_id == a.id
    assert (await fresh(db_session, Enquiry, stays["converted"].id)).telecaller_user_id == a.id
    assert (await fresh(db_session, LeadCall, stays["call"].id)).caller_user_id == a.id
    assert (await fresh(db_session, LeadFollowUp, stays["done_fup"].id)).completed_by_user_id == a.id
    # D3: A's routing rule is gone, audited
    assert await db_session.get(TelDistributionRule, a_rule.id, populate_existing=True) is None
    [deact] = await audit_rows(db_session, "telecaller.deactivate", a.id)
    assert deact.metadata_json["target"] == "telecaller" and deact.metadata_json["reassign_to"] == str(b.id)
    assert deact.metadata_json["moved"] == {"leads": 4, "follow_ups": 2, "appointments": 1}
    # D6: B is told
    note = await db_session.scalar(select(Notification).where(Notification.user_id == b.id).order_by(Notification.created_at.desc()))
    assert note is not None and "4 leads" in note.body


@pytest.mark.asyncio
async def test_deactivate_to_the_queue_unassigns(client, db_session):
    _, a, _ = await team(db_session)
    one = await lead(db_session, telecaller=a, status="contacted")
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    response = await post(client, url(a.id, "deactivate"), {"target": "queue"})
    assert response.status_code == 200, response.text
    assert response.json()["moved"] == {"leads": 1, "follow_ups": 0, "appointments": 0}
    moved = await fresh(db_session, Enquiry, one.id)
    assert moved.telecaller_user_id is None and moved.status == "contacted"
    [audit] = await audit_rows(db_session, "lead.assign", one.id)
    assert audit.metadata_json == {"from": str(a.id), "to": None, "method": "deactivation"}


@pytest.mark.asyncio
async def test_deactivate_with_no_open_work_needs_no_target(client, db_session):
    _, a, _ = await team(db_session)
    await lead(db_session, telecaller=a, status="lost")
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    response = await post(client, url(a.id, "deactivate"), {})
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(a.id), "active": False, "target": None,
                               "moved": {"leads": 0, "follow_ups": 0, "appointments": 0}, "rules_removed": 0}


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"target": "telecaller"}, {"target": "queue", "reassign_to": str(uuid.uuid4())}, {"target": "nobody"}])
async def test_deactivate_without_a_valid_choice_is_422_and_changes_nothing(client, db_session, body):
    """AC3."""
    _, a, _ = await team(db_session)
    one = await lead(db_session, telecaller=a)
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    response = await post(client, url(a.id, "deactivate"), body)
    assert response.status_code == 422, response.text
    assert (await fresh(db_session, User, a.id)).active is True
    assert (await fresh(db_session, Enquiry, one.id)).telecaller_user_id == a.id


@pytest.mark.asyncio
async def test_invalid_targets_are_one_422(client, db_session):
    manager, a, _ = await team(db_session)
    await lead(db_session, telecaller=a)
    other_team = await make_telecaller(db_session, manager, team="overseas")
    inactive = await make_telecaller(db_session, manager)
    inactive.active = False
    await db_session.commit()
    counselor = await make_counselor(db_session)
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    messages = set()
    for target in (other_team.id, inactive.id, counselor.id, a.id, uuid.uuid4()):
        response = await post(client, url(a.id, "deactivate"), {"target": "telecaller", "reassign_to": str(target)})
        assert response.status_code == 422, (target, response.text)
        messages.add(response.json()["detail"])
    assert messages == {"Choose an active telecaller of the same team"}
    assert (await fresh(db_session, User, a.id)).active is True


@pytest.mark.asyncio
async def test_deactivation_ends_the_session(client, db_session):
    """AC7 / D1: session_version moves, so A's cookie is refused at once."""
    _, a, b = await team(db_session)
    await as_user(client, a)
    a_cookie = client.cookies.get("edusphere_access")
    before = (await fresh(db_session, User, a.id)).session_version
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    assert (await post(client, url(a.id, "deactivate"), {})).status_code == 200
    assert (await fresh(db_session, User, a.id)).session_version == before + 1
    client.cookies.clear()
    client.cookies.set("edusphere_access", a_cookie)
    assert (await client.get("/api/v1/telecaller/me")).status_code == 401


@pytest.mark.asyncio
async def test_already_inactive_is_409(client, db_session):
    _, a, _ = await team(db_session)
    a.active = False
    await db_session.commit()
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    assert (await post(client, url(a.id, "deactivate"), {})).status_code == 409


@pytest.mark.asyncio
async def test_division_admin_scope(client, db_session):
    """LC1: an IT admin manages IT telecallers only; another team is 403; a non-telecaller is 404; a manager is 403 (not an admin)."""
    manager, a, b = await team(db_session)
    overseas = await make_telecaller(db_session, manager, team="overseas")
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    assert (await post(client, url(overseas.id, "deactivate"), {})).status_code == 403
    assert (await client.get(url(overseas.id, "open-work"))).status_code == 403
    assert (await post(client, url(manager.id, "deactivate"), {})).status_code == 404
    assert (await post(client, url(uuid.uuid4(), "deactivate"), {})).status_code == 404
    assert (await post(client, url(a.id, "deactivate"), {})).status_code == 200
    await as_user(client, manager)
    assert (await post(client, url(b.id, "deactivate"), {})).status_code == 403
    await as_user(client, b)
    assert (await client.get(url(b.id, "open-work"))).status_code == 403
    assert (await fresh(db_session, User, overseas.id)).active is True


@pytest.mark.asyncio
async def test_handover_from_an_inactive_telecaller(client, db_session):
    """LC4: work left on an inactive telecaller (deactivated before tel-025, or routed in the deactivation instant) moves later."""
    _, a, b = await team(db_session)
    one, two = await lead(db_session, telecaller=a), await lead(db_session, telecaller=a, status="interested")
    admin = await make_user(db_session, "super_admin", "global")
    await as_user(client, admin)
    assert (await post(client, url(a.id, "handover"), {"target": "queue"})).status_code == 409  # still active
    a.active = False
    await db_session.commit()
    assert (await post(client, url(a.id, "handover"), {})).status_code == 422  # a handover always names a target
    response = await post(client, url(a.id, "handover"), {"target": "telecaller", "reassign_to": str(b.id)})
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(a.id), "target": "telecaller", "moved": {"leads": 2, "follow_ups": 0, "appointments": 0}}
    for x in (one, two):
        assert (await fresh(db_session, Enquiry, x.id)).telecaller_user_id == b.id
        [audit] = await audit_rows(db_session, "lead.assign", x.id)
        assert audit.metadata_json["method"] == "handover"
    assert len(await audit_rows(db_session, "telecaller.handover", a.id)) == 1
    assert (await post(client, url(a.id, "handover"), {"target": "queue"})).status_code == 409  # nothing left


@pytest.mark.asyncio
async def test_lead_stage_history_keeps_the_original_actor(client, db_session):
    """AC2: the `assigned` event of a moved new lead is the admin's; earlier history rows are untouched."""
    _, a, b = await team(db_session)
    one = await lead(db_session, telecaller=a, status="new")
    admin = await make_user(db_session, "super_admin", "global")
    await as_user(client, admin)
    assert (await post(client, url(a.id, "deactivate"), {"target": "telecaller", "reassign_to": str(b.id)})).status_code == 200
    rows = (await db_session.scalars(select(LeadStageHistory).where(LeadStageHistory.lead_id == one.id))).all()
    assert [(r.from_stage, r.to_stage, r.actor_user_id) for r in rows] == [("new", "assigned", admin.id)]
    assert await db_session.scalar(select(func.count()).select_from(Enquiry).where(Enquiry.telecaller_user_id == a.id,
                                                                                   Enquiry.status.notin_(("converted", "lost")))) == 0

