"""upc-007 -- stage moves, Lost / Reopen and stage history (spec §3; AC1, AC3, P1, E1-E3, PS4-PS10)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.upc003_helpers import url
from tests.upc007_helpers import history, login, move, move_ok, owned_university


async def _audits(db, university_id) -> list[AuditLog]:
    db.expire_all()
    stmt = select(AuditLog).where(AuditLog.entity_id == str(university_id), AuditLog.action.like("university.%")).order_by(AuditLog.created_at)
    return list((await db.scalars(stmt)).all())


# --- output ----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_new_university_starts_at_target_with_the_stage_catalogue(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    body = (await client.get(url(uni["id"]))).json()["university"]
    assert body["stage"] == "target_university" and body["stage_label"] == "Target University" and body["lost"] is False
    p = body["pipeline"]
    assert p["stage"] == "target_university" and p["column"] == "target" and p["column_label"] == "Target" and p["lost"] is None
    assert len(p["stages"]) == 15 and p["stages"][4] == {"key": "interested", "label": "Interested", "column": "interested"}
    assert p["changed_at"]
    assert body["permissions"]["can_move_stage"] is True and body["permissions"]["can_reopen"] is False


# --- moves (P1, AC1, PS4) --------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_owner_moves_interested_to_meeting_scheduled_with_history_and_audit(client, db_session):
    _, pm, uni = await owned_university(client, db_session)
    first = await move_ok(client, uni["id"], "target_university", "interested")
    body = await move_ok(client, uni["id"], "interested", "meeting_scheduled", "Call booked for Monday")
    assert body["pipeline"]["stage"] == "meeting_scheduled" and body["pipeline"]["column"] == "meeting_scheduled"
    assert body["pipeline"]["changed_at"] >= first["pipeline"]["changed_at"]
    pm_id = pm.id
    rows = await history(db_session, uni["id"])
    assert [(r.kind, r.from_stage, r.to_stage, r.note, r.actor_user_id) for r in rows] == [
        ("move", "target_university", "interested", None, pm_id),
        ("move", "interested", "meeting_scheduled", "Call booked for Monday", pm_id),
    ]
    audits = [a for a in await _audits(db_session, uni["id"]) if a.action == "university.stage_changed"]
    assert [a.metadata_json for a in audits][-1] == {"from": "interested", "to": "meeting_scheduled", "backward": False, "note": True}
    assert "Call booked" not in str([a.metadata_json for a in audits])  # never the note text


@pytest.mark.asyncio
async def test_backward_move_needs_a_note(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    await move_ok(client, uni["id"], "target_university", "proposal_sent")
    refused = await move(client, uni["id"], "proposal_sent", "interested")
    assert refused.status_code == 422 and refused.json()["detail"][0]["loc"][-1] == "note"
    blank = await move(client, uni["id"], "proposal_sent", "interested", "   ")
    assert blank.status_code == 422
    body = await move_ok(client, uni["id"], "proposal_sent", "interested", "Contact left; restarting")
    assert body["pipeline"]["stage"] == "interested"
    assert (await history(db_session, uni["id"]))[-1].note == "Contact left; restarting"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("to_stage", "field"),
    [("target_university", "to_stage"), ("signed", "to_stage"), ("Interested", "to_stage")],
)
async def test_same_unknown_or_malformed_stage_is_422(client, db_session, to_stage, field):
    _, _, uni = await owned_university(client, db_session)
    response = await move(client, uni["id"], "target_university", to_stage)
    assert response.status_code == 422 and response.json()["detail"][0]["loc"][-1] == field
    assert await history(db_session, uni["id"]) == []


@pytest.mark.asyncio
async def test_stale_from_stage_is_409_with_the_current_stage(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    await move_ok(client, uni["id"], "target_university", "researching")
    response = await move(client, uni["id"], "target_university", "interested")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "stage_changed" and response.json()["detail"]["current_stage"] == "researching"
    assert len(await history(db_session, uni["id"])) == 1


@pytest.mark.asyncio
async def test_extra_fields_are_refused(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    response = await client.post(url(uni["id"], "stage"), json={"from_stage": "target_university", "to_stage": "interested", "stage_changed_at": "2020-01-01"})
    assert response.status_code == 422


# --- Lost / Reopen (AC3, E2, PS6-PS8) ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lost_requires_a_reason_and_keeps_the_stage(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    await move_ok(client, uni["id"], "target_university", "interested")
    for body in ({}, {"reason": ""}, {"reason": "  "}):
        refused = await client.post(url(uni["id"], "lost"), json=body)
        assert refused.status_code == 422, body
    response = await client.post(url(uni["id"], "lost"), json={"reason": "Chose another agency"})
    assert response.status_code == 200, response.text
    body = response.json()["university"]
    assert body["lost"] is True and body["pipeline"]["stage"] == "interested"
    assert body["pipeline"]["lost"]["reason"] == "Chose another agency" and body["pipeline"]["lost"]["at"]
    last = (await history(db_session, uni["id"]))[-1]
    assert (last.kind, last.from_stage, last.to_stage, last.note) == ("lost", "interested", "interested", "Chose another agency")
    assert (await _audits(db_session, uni["id"]))[-1].metadata_json == {"stage": "interested"}


@pytest.mark.asyncio
async def test_a_lost_university_cannot_be_moved_or_lost_again(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    await client.post(url(uni["id"], "lost"), json={"reason": "No reply in a year"})
    moved = await move(client, uni["id"], "target_university", "interested")
    assert moved.status_code == 409 and moved.json()["detail"]["code"] == "university_lost"
    again = await client.post(url(uni["id"], "lost"), json={"reason": "Again"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "university_lost"


@pytest.mark.asyncio
async def test_only_the_head_reopens_and_the_university_is_back_at_its_stage(client, db_session):
    head, pm, uni = await owned_university(client, db_session)
    await move_ok(client, uni["id"], "target_university", "proposal_sent")
    await client.post(url(uni["id"], "lost"), json={"reason": "Budget freeze"})
    refused = await client.post(url(uni["id"], "reopen"), json={"reason": "They called back"})
    assert refused.status_code == 403
    await login(client, head)
    missing = await client.post(url(uni["id"], "reopen"), json={})
    assert missing.status_code == 422
    response = await client.post(url(uni["id"], "reopen"), json={"reason": "They called back"})
    assert response.status_code == 200, response.text
    body = response.json()["university"]
    assert body["lost"] is False and body["pipeline"]["lost"] is None and body["pipeline"]["stage"] == "proposal_sent"
    expected = [("lost", pm.id), ("reopened", head.id)]
    assert [(r.kind, r.actor_user_id) for r in await history(db_session, uni["id"])][-2:] == expected
    not_lost = await client.post(url(uni["id"], "reopen"), json={"reason": "Twice"})
    assert not_lost.status_code == 409 and not_lost.json()["detail"]["code"] == "university_not_lost"


# --- history (AC1, PS9) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_stage_history_newest_first_with_labels_and_paging(client, db_session):
    _, pm, uni = await owned_university(client, db_session)
    await move_ok(client, uni["id"], "target_university", "initial_contact")
    await move_ok(client, uni["id"], "initial_contact", "interested")
    await client.post(url(uni["id"], "lost"), json={"reason": "Went quiet"})
    page = (await client.get(url(uni["id"], "stage-history") + "?limit=2&offset=0")).json()
    assert page["total"] == 3 and page["limit"] == 2 and page["offset"] == 0
    first = page["items"][0]
    assert first["kind"] == "lost" and first["note"] == "Went quiet" and first["actor"] == {"id": str(pm.id), "full_name": pm.full_name}
    second = page["items"][1]
    assert (second["from_label"], second["to_label"]) == ("Initial Contact", "Interested")
    rest = (await client.get(url(uni["id"], "stage-history") + "?limit=2&offset=2")).json()
    assert [i["to_stage"] for i in rest["items"]] == ["initial_contact"]


@pytest.mark.asyncio
async def test_stage_history_of_an_unknown_university_is_404(client, db_session):
    await owned_university(client, db_session)
    assert (await client.get(url(uuid.uuid4(), "stage-history"))).status_code == 404
