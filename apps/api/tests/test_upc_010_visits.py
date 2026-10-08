"""upc-010 -- university visits + approval (spec §3; AC1-AC5, P1, N1, E1, R1)."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Notification, UniversityVisitContact
from app.services.bdm_travel import india_today
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, make_pm, make_user, url

VISITS = "/api/v1/partnership/visits"
APPROVALS = f"{VISITS}/approvals"


def visit_url(visit_id, action: str | None = None) -> str:
    return f"{VISITS}/{visit_id}" + (f"/{action}" if action else "")


def day(offset: int) -> str:
    return (india_today() + timedelta(days=offset)).isoformat()


async def _owned(client, db):
    """A head creates a university and makes `pm` its primary manager. Returns (head, pm, other_pm, university), signed in as the head."""
    head = await make_head(db)
    pm, other = await make_pm(db, head), await make_pm(db, head)
    await login(client, head)
    uni = await create(client, (await catalogue_country(db)).id)
    response = await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id)})
    assert response.status_code == 200, response.text
    return head, pm, other, uni


async def _contact(client, university_id, name="Priya Raman") -> dict:
    response = await client.post(url(university_id, "contacts"), json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["contact"]


def visit(university_id, **overrides) -> dict:
    body = {
        "university_id": str(university_id),
        "purpose": "Discuss the MoU and the September intake",
        "proposed_date": day(10),
        "travel_required": True,
        "travel_notes": "Flight DEL-LHR",
        "hotel_required": True,
        "hotel_notes": "Two nights near campus",
        "agenda": "1. MoU\n2. Scholarships",
        "expected_outcome": "Signed MoU draft",
    }
    body.update(overrides)
    return body


async def plan(client, university_id, **overrides) -> dict:
    response = await client.post(VISITS, json=visit(university_id, **overrides))
    assert response.status_code == 201, response.text
    return response.json()["visit"]


async def act(client, visit_id, action: str, expected: int = 200, **body) -> dict:
    response = await client.post(visit_url(visit_id, action), json=body or None)
    assert response.status_code == expected, response.text
    return response.json()


async def _approved(client, db, **overrides):
    """A visit planned by the owning manager and approved by their head. Returns (head, pm, uni, visit), signed in as the manager."""
    head, pm, _, uni = await _owned(client, db)
    await login(client, pm)
    v = await plan(client, uni["id"], **overrides)
    await act(client, v["id"], "submit")
    await login(client, head)
    await act(client, v["id"], "approve")
    await login(client, pm)
    return head, pm, uni, v


# --- create (P1, VS1, VS6, VS11, VS12) -------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_owning_manager_plans_a_visit_with_every_field(client, db_session):
    head, pm, other, uni = await _owned(client, db_session)
    await login(client, pm)
    contact = await _contact(client, uni["id"])
    v = await plan(client, uni["id"], participant_user_ids=[str(other.id), str(head.id)], contact_ids=[contact["id"]], confirmed_date=day(12), city="Oxford")
    assert v["code"].startswith("VIS-") and v["status"] == "planned" and v["approval_state"] == "draft"
    assert v["university"]["id"] == uni["id"] and v["university"]["country"]["name"] == "United Kingdom"
    assert v["city"] == "Oxford" and v["lead"]["id"] == str(pm.id) and v["created_by"]["id"] == str(pm.id)
    assert v["proposed_date"] == day(10) and v["confirmed_date"] == day(12)
    assert v["travel_required"] and v["hotel_required"] and v["travel_notes"] == "Flight DEL-LHR" and v["agenda"] == "1. MoU\n2. Scholarships"
    assert {p["id"] for p in v["participants"]} == {str(other.id), str(head.id)}
    assert [c["id"] for c in v["contacts"]] == [contact["id"]]
    assert [(e["action"], e["to_status"]) for e in v["events"]] == [("create", "planned")]
    assert v["permissions"] == {
        "can_edit": True, "can_submit": True, "can_decide": False, "can_book": False, "can_complete": False, "can_follow_up": False, "can_close": True,
    }  # fmt: skip
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == v["id"]))).all()
    assert [a.action for a in audit] == ["university_visit.create"]


@pytest.mark.asyncio
async def test_city_defaults_to_the_university_city(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    assert (await plan(client, uni["id"]))["city"] == "London"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"purpose": ""},
        {"purpose": "x" * 1001},
        {"proposed_date": None},
        {"agenda": "x" * 2001},
        {"status": "approved"},  # AC1: status is never written directly
        {"participant_user_ids": ["not-a-uuid"]},
    ],
)
async def test_create_validation(client, db_session, overrides):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    assert (await client.post(VISITS, json=visit(uni["id"], **overrides))).status_code == 422


@pytest.mark.asyncio
async def test_dates_must_not_be_in_the_past(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    assert (await client.post(VISITS, json=visit(uni["id"], proposed_date=day(-1)))).status_code == 422
    assert (await client.post(VISITS, json=visit(uni["id"], confirmed_date=day(-1)))).status_code == 422
    assert (await client.post(VISITS, json=visit(uni["id"], proposed_date=day(0)))).status_code == 201


@pytest.mark.asyncio
async def test_contacts_must_belong_to_the_visited_university(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    other_uni = await create(client, (await catalogue_country(db_session)).id)
    foreign = await _contact(client, other_uni["id"], "Someone Else")
    await login(client, pm)
    response = await client.post(VISITS, json=visit(uni["id"], contact_ids=[foreign["id"]]))
    assert response.status_code == 422 and "contact" in response.text.lower()


@pytest.mark.asyncio
async def test_participants_are_active_partnership_staff_other_than_the_lead(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    counselor = await make_user(db_session, "counselor", "overseas")
    inactive = await make_pm(db_session, head, active=False)
    await login(client, pm)
    for ids in ([str(counselor.id)], [str(inactive.id)], [str(pm.id)]):
        assert (await client.post(VISITS, json=visit(uni["id"], participant_user_ids=ids))).status_code == 422, ids
    many = [str((await make_pm(db_session, head)).id) for _ in range(11)]
    assert (await client.post(VISITS, json=visit(uni["id"], participant_user_ids=many))).status_code == 422


@pytest.mark.asyncio
async def test_only_partnership_staff_with_the_university_in_scope_create(client, db_session):
    head, pm, other, uni = await _owned(client, db_session)
    await login(client, other)  # a manager who does not own it
    assert (await client.post(VISITS, json=visit(uni["id"]))).status_code == 403
    for role, division in (("overseas_admin", "overseas"), ("super_admin", "global"), ("counselor", "overseas")):
        await as_role(client, db_session, role, division)
        assert (await client.post(VISITS, json=visit(uni["id"]))).status_code == 403, role
    await login(client, pm)
    assert (await client.post(VISITS, json=visit("00000000-0000-0000-0000-000000000000"))).status_code == 422


@pytest.mark.asyncio
async def test_inactive_university_cannot_get_a_visit(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    assert (await client.post(url(uni["id"], "deactivate"))).status_code == 200
    await login(client, pm)
    assert (await client.post(VISITS, json=visit(uni["id"]))).status_code == 409


@pytest.mark.asyncio
async def test_head_plans_a_visit_led_by_a_direct_report_but_not_by_another_heads_manager(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    stranger = await make_pm(db_session, await make_head(db_session))
    v = await plan(client, uni["id"], lead_user_id=str(pm.id))
    assert v["lead"]["id"] == str(pm.id) and v["created_by"]["id"] == str(head.id)
    assert (await client.post(VISITS, json=visit(uni["id"], lead_user_id=str(stranger.id)))).status_code == 422
    await login(client, pm)  # a manager always leads their own visits
    assert (await client.post(VISITS, json=visit(uni["id"], lead_user_id=str(head.id)))).status_code == 422


# --- read (VS7) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_partnership_roles_read_every_visit_others_are_refused(client, db_session):
    head, pm, other, uni = await _owned(client, db_session)
    await login(client, pm)
    v = await plan(client, uni["id"])
    await login(client, other)
    body = (await client.get(visit_url(v["id"]))).json()["visit"]
    assert body["id"] == v["id"] and body["permissions"]["can_edit"] is False
    listed = (await client.get(VISITS, params={"university_id": uni["id"]})).json()
    assert [r["id"] for r in listed["items"]] == [v["id"]] and listed["total"] == 1
    assert (await client.get(VISITS, params={"university_id": uni["id"], "mine": "true"})).json()["total"] == 0
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.get(visit_url(v["id"]))).status_code == 200
    for role, division in (("overseas_admin", "overseas"), ("counselor", "overseas")):
        await as_role(client, db_session, role, division)
        assert (await client.get(visit_url(v["id"]))).status_code == 403
        assert (await client.get(VISITS)).status_code == 403
    await login(client, pm)
    assert (await client.get(visit_url("00000000-0000-0000-0000-000000000000"))).status_code == 404


@pytest.mark.asyncio
async def test_list_filters_by_status_and_mine(client, db_session):
    head, pm, other, uni = await _owned(client, db_session)
    await login(client, pm)
    a = await plan(client, uni["id"], participant_user_ids=[str(other.id)])
    b = await plan(client, uni["id"], proposed_date=day(20))
    await act(client, b["id"], "submit")
    rows = (await client.get(VISITS, params={"university_id": uni["id"]})).json()["items"]
    assert [r["id"] for r in rows] == [b["id"], a["id"]]  # newest proposed date first
    assert rows[0]["approval_state"] == "waiting" and rows[0]["lead"]["id"] == str(pm.id)
    assert (await client.get(VISITS, params={"university_id": uni["id"], "status": "approved"})).json()["total"] == 0
    await login(client, other)
    mine = (await client.get(VISITS, params={"university_id": uni["id"], "mine": "true"})).json()
    assert [r["id"] for r in mine["items"]] == [a["id"]]  # a participant's visit is theirs too
    assert (await client.get(VISITS, params={"status": "booked"})).status_code == 422


# --- the flow (AC1-AC4, P1, N1) ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_uk_visit_goes_through_every_status_with_history(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    v = await plan(client, uni["id"], proposed_date=day(0))
    waiting = (await act(client, v["id"], "submit"))["visit"]
    assert waiting["status"] == "planned" and waiting["approval_state"] == "waiting" and waiting["permissions"]["can_edit"] is False
    assert (await client.post(visit_url(v["id"], "approve"))).status_code == 403  # AC1
    await login(client, head)
    queue = (await client.get(APPROVALS)).json()
    assert v["id"] in [r["id"] for r in queue["items"]]
    assert (await client.get(visit_url(v["id"]))).json()["visit"]["permissions"]["can_decide"] is True
    approved = (await act(client, v["id"], "approve"))["visit"]
    assert approved["status"] == "approved" and approved["decided_by"]["id"] == str(head.id)
    assert v["id"] not in [r["id"] for r in (await client.get(APPROVALS)).json()["items"]]
    notice = await db_session.scalar(select(Notification).where(Notification.user_id == pm.id, Notification.title == "Visit approved"))
    assert notice is not None and v["code"] in notice.body
    await login(client, pm)
    assert (await client.post(visit_url(v["id"], "book"))).status_code == 422  # no confirmed date yet
    assert (await client.patch(visit_url(v["id"]), json={"confirmed_date": day(0)})).status_code == 200
    booked = (await act(client, v["id"], "book"))["visit"]
    assert booked["status"] == "travel_booked" and booked["permissions"]["can_complete"] is True
    assert (await client.post(visit_url(v["id"], "complete"), json={})).status_code == 422  # AC3
    assert (await client.post(visit_url(v["id"], "complete"), json={"follow_up_date": day(-1)})).status_code == 422
    done = (await act(client, v["id"], "complete", follow_up_date=day(7)))["visit"]
    assert done["status"] == "visit_completed" and done["follow_up_date"] == day(7)
    assert (await act(client, v["id"], "follow-up"))["visit"]["status"] == "follow_up"
    closed = (await act(client, v["id"], "close"))["visit"]
    assert closed["status"] == "closed" and not any(closed["permissions"].values())
    assert [e["action"] for e in closed["events"]] == ["create", "submit", "approve", "edit", "book", "complete", "follow_up", "close"]
    assert [e["to_status"] for e in closed["events"]][-4:] == ["travel_booked", "visit_completed", "follow_up", "closed"]
    assert (await client.patch(visit_url(v["id"]), json={"agenda": "late"})).status_code == 409
    actions = {a.action for a in (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == v["id"]))).all()}
    assert {"university_visit.approve", "university_visit.book", "university_visit.close"} <= actions


@pytest.mark.asyncio
async def test_travel_booked_only_after_approval(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    v = await plan(client, uni["id"], confirmed_date=day(3))
    assert (await client.post(visit_url(v["id"], "book"))).status_code == 409  # AC2 (draft)
    await act(client, v["id"], "submit")
    assert (await client.post(visit_url(v["id"], "book"))).status_code == 409  # AC2 (waiting)
    assert (await client.post(visit_url(v["id"], "complete"), json={"follow_up_date": day(9)})).status_code == 409


@pytest.mark.asyncio
async def test_completing_before_the_confirmed_date_is_refused(client, db_session):
    _, pm, _, v = await _approved(client, db_session, confirmed_date=day(5))
    await act(client, v["id"], "book")
    response = await client.post(visit_url(v["id"], "complete"), json={"follow_up_date": day(9)})
    assert response.status_code == 422 and "confirmed" in response.text  # N1


@pytest.mark.asyncio
async def test_reject_needs_a_reason_and_returns_the_visit_for_editing(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    v = await plan(client, uni["id"])
    await act(client, v["id"], "submit")
    await login(client, head)
    assert (await client.post(visit_url(v["id"], "reject"), json={})).status_code == 422
    assert (await client.post(visit_url(v["id"], "reject"), json={"reason": "   "})).status_code == 422
    returned = (await act(client, v["id"], "reject", reason="Combine with the Leeds visit"))["visit"]
    assert returned["status"] == "planned" and returned["approval_state"] == "returned" and returned["rejection_reason"] == "Combine with the Leeds visit"
    assert returned["events"][-1]["reason"] == "Combine with the Leeds visit"
    await login(client, pm)
    assert (await client.patch(visit_url(v["id"]), json={"purpose": "Leeds + London"})).status_code == 200
    again = (await act(client, v["id"], "submit"))["visit"]
    assert again["approval_state"] == "waiting" and again["rejection_reason"] is None


@pytest.mark.asyncio
async def test_what_stays_editable_per_state(client, db_session):
    head, pm, other, uni = await _owned(client, db_session)
    await login(client, pm)
    v = await plan(client, uni["id"])
    unchanged = await client.patch(visit_url(v["id"]), json={"purpose": v["purpose"]})
    assert unchanged.status_code == 200 and len(unchanged.json()["visit"]["events"]) == 1  # an equal value is not a change
    await act(client, v["id"], "submit")
    assert (await client.patch(visit_url(v["id"]), json={"agenda": "x"})).status_code == 409  # waiting
    await login(client, head)
    await act(client, v["id"], "approve")
    await login(client, pm)
    for frozen in ({"purpose": "x"}, {"proposed_date": day(30)}, {"travel_required": False}, {"participant_user_ids": [str(other.id)]}):
        assert (await client.patch(visit_url(v["id"]), json=frozen)).status_code == 409, frozen
    contact = await _contact(client, uni["id"])
    ok = await client.patch(visit_url(v["id"]), json={"confirmed_date": day(11), "hotel_notes": "Booked: Hotel X", "contact_ids": [contact["id"]]})
    assert ok.status_code == 200 and ok.json()["visit"]["hotel_notes"] == "Booked: Hotel X" and len(ok.json()["visit"]["contacts"]) == 1
    assert (await client.patch(visit_url(v["id"]), json={"university_id": uni["id"]})).status_code == 422  # never editable
    assert (await client.patch(visit_url(v["id"]), json={"follow_up_date": day(20)})).status_code == 409  # only after completion
    await login(client, other)
    assert (await client.patch(visit_url(v["id"]), json={"agenda": "x"})).status_code == 403  # VS8


@pytest.mark.asyncio
async def test_early_close_needs_a_reason(client, db_session):
    _, pm, _, v = await _approved(client, db_session)
    assert (await client.post(visit_url(v["id"], "close"), json={})).status_code == 422
    closed = (await act(client, v["id"], "close", reason="University postponed"))["visit"]
    assert closed["status"] == "closed" and closed["close_reason"] == "University postponed" and closed["events"][-1]["from_status"] == "approved"


@pytest.mark.asyncio
async def test_only_the_lead_or_creator_acts(client, db_session):
    head, pm, other, uni = await _owned(client, db_session)
    await login(client, pm)
    v = await plan(client, uni["id"])
    await login(client, other)
    assert (await client.post(visit_url(v["id"], "submit"))).status_code == 403
    assert (await client.post(visit_url(v["id"], "close"), json={"reason": "x"})).status_code == 403
    await login(client, pm)
    assert (await client.post(visit_url("00000000-0000-0000-0000-000000000000", "submit"))).status_code == 404


# --- approval separation (AC5, E1, VS4) ----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_head_as_traveller_or_creator_never_approves_super_admin_does(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    admin = await make_user(db_session, "super_admin", "global")  # exists before the submits, so it is notified
    await login(client, head)
    led = await plan(client, uni["id"])  # the head leads it (E1)
    created = await plan(client, uni["id"], lead_user_id=str(pm.id))  # the head created it for their manager
    await login(client, pm)
    joined = await plan(client, uni["id"], participant_user_ids=[str(head.id)])  # the head joins it
    await act(client, joined["id"], "submit")
    await login(client, head)
    for v in (led, created):
        await act(client, v["id"], "submit")
    for v in (led, created, joined):
        assert (await client.post(visit_url(v["id"], "approve"))).status_code == 403
        assert (await client.get(visit_url(v["id"]))).json()["visit"]["permissions"]["can_decide"] is False
    await login(client, admin)
    queue = [r["id"] for r in (await client.get(APPROVALS, params={"limit": 100})).json()["items"]]
    assert {led["id"], created["id"], joined["id"]} <= set(queue)
    for v in (led, created, joined):
        assert (await act(client, v["id"], "approve"))["visit"]["decided_by"]["id"] == str(admin.id)
    notices = (await db_session.scalars(select(Notification).where(Notification.user_id == admin.id, Notification.title == "Visit approval needed"))).all()
    assert len(notices) == 3


@pytest.mark.asyncio
async def test_super_admin_approves_only_while_the_head_is_inactive(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    v = await plan(client, uni["id"])
    await act(client, v["id"], "submit")
    admin = await as_role(client, db_session, "super_admin", "global")
    assert (await client.post(visit_url(v["id"], "approve"))).status_code == 403
    assert v["id"] not in [r["id"] for r in (await client.get(APPROVALS, params={"limit": 100})).json()["items"]]
    head.active = False
    db_session.add(head)
    await db_session.commit()
    assert (await client.get(visit_url(v["id"]))).json()["visit"]["permissions"]["can_decide"] is True
    assert (await act(client, v["id"], "approve"))["visit"]["decided_by"]["id"] == str(admin.id)


@pytest.mark.asyncio
async def test_another_head_cannot_decide_and_nothing_is_decided_twice(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    v = await plan(client, uni["id"])
    assert (await client.get(APPROVALS)).status_code == 403  # a manager has no queue
    await act(client, v["id"], "submit")
    await as_role(client, db_session, "partnership_head", "global")
    assert (await client.post(visit_url(v["id"], "approve"))).status_code == 403
    assert (await client.post(visit_url(v["id"], "reject"), json={"reason": "no"})).status_code == 403
    await login(client, head)
    await act(client, v["id"], "approve")
    assert (await client.post(visit_url(v["id"], "approve"))).status_code == 409
    assert (await client.post(visit_url(v["id"], "reject"), json={"reason": "late"})).status_code == 409


# --- options --------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_option_lists_offer_only_what_the_caller_may_submit(client, db_session):
    head, pm, other, uni = await _owned(client, db_session)
    stranger_head = await make_head(db_session)
    await login(client, pm)
    unis = (await client.get(f"{VISITS}/university-options", params={"q": uni["name"]})).json()["items"]
    assert [u["id"] for u in unis] == [uni["id"]]
    await login(client, other)
    assert (await client.get(f"{VISITS}/university-options", params={"q": uni["name"]})).json()["items"] == []
    assert [x["id"] for x in (await client.get(f"{VISITS}/lead-options")).json()["items"]] == [str(other.id)]
    await login(client, head)
    leads = {x["id"] for x in (await client.get(f"{VISITS}/lead-options", params={"limit": 100})).json()["items"]}
    assert leads == {str(head.id), str(pm.id), str(other.id)}
    staff = {x["id"] for x in (await client.get(f"{VISITS}/employee-options", params={"q": stranger_head.full_name, "limit": 100})).json()["items"]}
    assert str(stranger_head.id) in staff
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.get(f"{VISITS}/university-options")).status_code == 403


# --- contacts are PII (VS12) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deleting_a_contact_removes_it_from_visits(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    first, second = await _contact(client, uni["id"], "First Person"), await _contact(client, uni["id"], "Second Person")
    v = await plan(client, uni["id"], contact_ids=[first["id"], second["id"]])
    assert (await client.delete(f"/api/v1/partnership/contacts/{second['id']}")).status_code == 204
    assert [c["id"] for c in (await client.get(visit_url(v["id"]))).json()["visit"]["contacts"]] == [first["id"]]
    assert len((await db_session.scalars(select(UniversityVisitContact).where(UniversityVisitContact.contact_id == second["id"]))).all()) == 0
