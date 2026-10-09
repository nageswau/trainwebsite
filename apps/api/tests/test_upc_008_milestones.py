"""upc-008 -- the milestone tracker (spec §3; AC1, AC2, P1, N1, N2, E1, E2, MS2-MS7, MS10, MS11)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import ApplicationStatusHistory, AuditLog
from app.services.bdm_travel import india_today
from tests.upc003_helpers import as_role, login, make_application, make_pm, make_user, url
from tests.upc007_helpers import move_ok, owned_university


def _ms(university_id, kind: str | None = None) -> str:
    return url(university_id, "milestones" + (f"/{kind}" if kind else ""))


async def _page(client, university_id) -> dict:
    response = await client.get(_ms(university_id))
    assert response.status_code == 200, response.text
    return response.json()


def _by_kind(page: dict) -> dict[str, dict]:
    return {m["kind"]: m for m in page["items"]}


async def _patch_ok(client, university_id, kind: str, **body) -> dict:
    response = await client.patch(_ms(university_id, kind), json={k: (v.isoformat() if v is not None else None) for k, v in body.items()})
    assert response.status_code == 200, response.text
    return response.json()


async def _audits(db, university_id) -> list[AuditLog]:
    db.expire_all()
    stmt = select(AuditLog).where(AuditLog.entity_id == str(university_id), AuditLog.action == "university.milestone_updated").order_by(AuditLog.created_at)
    return list((await db.scalars(stmt)).all())


# --- the template + Q-11 statuses -------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_every_university_has_the_13_milestones_in_source_order(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    page = await _page(client, uni["id"])
    assert page["today"] == india_today().isoformat() and page["can_edit"] is True
    assert [m["label"] for m in page["items"]][:4] == ["University Contacted", "Meeting", "Presentation", "Proposal"]
    assert len(page["items"]) == 13 and page["items"][-1]["label"] == "Active Partnership"
    assert [m["status"] for m in page["items"]] == ["in_progress"] + ["pending"] * 12  # MS3: the earliest not-done one is in progress
    first = page["items"][0]
    assert first["target_date"] is None and first["achieved_on"] is None and first["achieved_by"] is None and first["auto_source"] is None
    assert _by_kind(page)["first_application"]["auto_source"] == "application"


@pytest.mark.asyncio
async def test_a_milestone_past_its_target_and_not_achieved_is_delayed(client, db_session):
    """AC1 / MS3: target before today (IST) -> delayed; on the target day itself it is not delayed yet."""
    _, _, uni = await owned_university(client, db_session)
    today = india_today()
    await _patch_ok(client, uni["id"], "university_contacted", target_date=today)
    page = await _patch_ok(client, uni["id"], "agreement", target_date=today - timedelta(days=1))
    items = _by_kind(page)
    assert items["agreement"]["status"] == "delayed" and items["agreement"]["target_date"] == (today - timedelta(days=1)).isoformat()
    assert items["university_contacted"]["status"] == "in_progress"
    page = await _patch_ok(client, uni["id"], "agreement", achieved_on=today)
    assert _by_kind(page)["agreement"]["status"] == "done" and _by_kind(page)["agreement"]["achieved_by"] == "manual"


@pytest.mark.asyncio
async def test_the_abc_example_done_in_progress_pending(client, db_session):
    """P1: the source's ABC University table -- achieved rows done, the next one in progress, the rest pending."""
    _, _, uni = await owned_university(client, db_session)
    today = india_today()
    for i, kind in enumerate(("university_contacted", "meeting", "presentation", "proposal")):
        await _patch_ok(client, uni["id"], kind, target_date=today - timedelta(days=20 - i), achieved_on=today - timedelta(days=20 - i))
    page = await _patch_ok(client, uni["id"], "documents", target_date=today + timedelta(days=5))
    statuses = [m["status"] for m in page["items"]]
    assert statuses[:4] == ["done"] * 4 and statuses[4] == "in_progress" and set(statuses[5:]) == {"pending"}


@pytest.mark.asyncio
async def test_a_delayed_earliest_milestone_shows_delayed_not_in_progress(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    page = await _patch_ok(client, uni["id"], "university_contacted", target_date=india_today() - timedelta(days=3))
    assert [m["status"] for m in page["items"]][:2] == ["delayed", "pending"]


# --- writes ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_only_the_fields_sent_change_and_null_clears(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    today = india_today()
    await _patch_ok(client, uni["id"], "meeting", target_date=today + timedelta(days=7))
    page = await _patch_ok(client, uni["id"], "meeting", achieved_on=today)
    meeting = _by_kind(page)["meeting"]
    assert meeting["target_date"] == (today + timedelta(days=7)).isoformat() and meeting["achieved_on"] == today.isoformat()
    page = await _patch_ok(client, uni["id"], "meeting", achieved_on=None)
    assert _by_kind(page)["meeting"]["achieved_on"] is None and _by_kind(page)["meeting"]["target_date"] is not None


@pytest.mark.asyncio
async def test_an_achieved_date_in_the_future_is_422(client, db_session):
    """N1 / MS6."""
    _, _, uni = await owned_university(client, db_session)
    tomorrow = india_today() + timedelta(days=1)
    response = await client.patch(_ms(uni["id"], "meeting"), json={"achieved_on": tomorrow.isoformat()})
    assert response.status_code == 422 and response.json()["detail"][0]["loc"][-1] == "achieved_on"
    assert _by_kind(await _page(client, uni["id"]))["meeting"]["achieved_on"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "body"),
    [("launch", {"target_date": "2026-12-01"}), ("meeting", {}), ("meeting", {"status": "done"}), ("meeting", {"target_date": "soon"})],
)
async def test_unknown_kind_empty_extra_or_malformed_body_is_422(client, db_session, kind, body):
    _, _, uni = await owned_university(client, db_session)
    assert (await client.patch(_ms(uni["id"], kind), json=body)).status_code == 422


@pytest.mark.asyncio
async def test_a_moved_target_after_a_delay_recomputes_and_the_audit_keeps_the_history(client, db_session):
    """E1 / MS7: the status follows the new date; the audit keeps from / to and that it was delayed (never anything else)."""
    _, _, uni = await owned_university(client, db_session)
    today = india_today()
    late, moved = today - timedelta(days=2), today + timedelta(days=10)
    await _patch_ok(client, uni["id"], "proposal", target_date=late)
    page = await _patch_ok(client, uni["id"], "proposal", target_date=moved)
    assert _by_kind(page)["proposal"]["status"] == "pending"
    audits = await _audits(db_session, uni["id"])
    assert [a.metadata_json for a in audits] == [
        {"kind": "proposal", "fields": ["target_date"], "target_date": {"from": None, "to": late.isoformat()}, "was_delayed": False},
        {"kind": "proposal", "fields": ["target_date"], "target_date": {"from": late.isoformat(), "to": moved.isoformat()}, "was_delayed": True},
    ]


@pytest.mark.asyncio
async def test_the_same_values_again_change_nothing_and_add_no_audit(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    target = india_today() + timedelta(days=3)
    await _patch_ok(client, uni["id"], "meeting", target_date=target)
    await _patch_ok(client, uni["id"], "meeting", target_date=target)
    assert len(await _audits(db_session, uni["id"])) == 1


# --- auto-completion (AC2, E2, MS4, MS5) ------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_first_application_auto_marks_first_application(client, db_session):
    """AC2: derived on read from the university's first application."""
    _, _, uni = await owned_university(client, db_session)
    await make_application(db_session, uuid.UUID(uni["id"]))
    await make_application(db_session, uuid.UUID(uni["id"]))
    item = _by_kind(await _page(client, uni["id"]))["first_application"]
    assert item["status"] == "done" and item["achieved_by"] == "auto" and item["achieved_on"] == india_today().isoformat()


@pytest.mark.asyncio
async def test_the_first_enrolled_application_auto_marks_first_admission(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    application = await make_application(db_session, uuid.UUID(uni["id"]))
    assert _by_kind(await _page(client, uni["id"]))["first_admission"]["status"] != "done"
    db_session.add(ApplicationStatusHistory(application_id=application.id, from_status="offer", to_status="enrolled"))
    await db_session.commit()
    item = _by_kind(await _page(client, uni["id"]))["first_admission"]
    assert item["status"] == "done" and item["achieved_by"] == "auto" and item["auto_source"] == "admission"


@pytest.mark.asyncio
async def test_a_move_to_proposal_sent_or_later_auto_marks_proposal(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    await move_ok(client, uni["id"], "target_university", "interested")
    assert _by_kind(await _page(client, uni["id"]))["proposal"]["achieved_on"] is None
    await move_ok(client, uni["id"], "interested", "commercial_discussion")  # skipping Proposal Sent still achieves it
    item = _by_kind(await _page(client, uni["id"]))["proposal"]
    assert item["status"] == "done" and item["achieved_by"] == "auto" and item["achieved_on"] == india_today().isoformat()


@pytest.mark.asyncio
async def test_a_recorded_date_wins_over_the_derived_one_and_clearing_falls_back(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    await make_application(db_session, uuid.UUID(uni["id"]))
    earlier = india_today() - timedelta(days=30)
    item = _by_kind(await _patch_ok(client, uni["id"], "first_application", achieved_on=earlier))["first_application"]
    assert item["achieved_on"] == earlier.isoformat() and item["achieved_by"] == "manual"
    item = _by_kind(await _patch_ok(client, uni["id"], "first_application", achieved_on=None))["first_application"]
    assert item["achieved_on"] == india_today().isoformat() and item["achieved_by"] == "auto"


# --- access (N2, MS10, MS11) -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_manager_who_does_not_own_it_reads_but_cannot_edit(client, db_session):
    head, _, uni = await owned_university(client, db_session)
    await login(client, await make_pm(db_session, head))
    assert (await _page(client, uni["id"]))["can_edit"] is False
    response = await client.patch(_ms(uni["id"], "meeting"), json={"target_date": "2027-01-10"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_overseas_admin_reads_only(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    await as_role(client, db_session, "overseas_admin", "overseas")
    assert (await _page(client, uni["id"]))["can_edit"] is False
    assert (await client.patch(_ms(uni["id"], "meeting"), json={"target_date": "2027-01-10"})).status_code == 403


@pytest.mark.asyncio
async def test_the_head_and_super_admin_can_edit(client, db_session):
    head, _, uni = await owned_university(client, db_session)
    await login(client, head)
    await _patch_ok(client, uni["id"], "meeting", target_date=india_today())
    await login(client, await make_user(db_session, "super_admin", "global"))
    await _patch_ok(client, uni["id"], "presentation", target_date=india_today())


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "overseas"), ("overseas_student", "overseas"), ("bdm", "overseas")])
async def test_other_roles_are_refused(client, db_session, role, division):
    _, _, uni = await owned_university(client, db_session)
    await as_role(client, db_session, role, division)
    assert (await client.get(_ms(uni["id"]))).status_code == 403
    assert (await client.patch(_ms(uni["id"], "meeting"), json={"target_date": "2027-01-10"})).status_code == 403


@pytest.mark.asyncio
async def test_unknown_university_is_404_and_inactive_is_409(client, db_session):
    head, pm, uni = await owned_university(client, db_session)
    assert (await client.get(_ms(uuid.uuid4()))).status_code == 404
    assert (await client.patch(_ms(uuid.uuid4(), "meeting"), json={"target_date": "2027-01-10"})).status_code == 404
    await login(client, head)
    assert (await client.post(url(uni["id"], "deactivate"), json={})).status_code == 200
    await login(client, pm)
    response = await client.patch(_ms(uni["id"], "meeting"), json={"target_date": "2027-01-10"})
    assert response.status_code == 409 and response.json()["detail"] == "Reactivate this university first"
    assert (await _page(client, uni["id"]))["can_edit"] is False


@pytest.mark.asyncio
async def test_signed_out_is_401(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    client.cookies.clear()
    assert (await client.get(_ms(uni["id"]))).status_code == 401
