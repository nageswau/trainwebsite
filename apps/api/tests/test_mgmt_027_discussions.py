"""mgmt-027 -- management discussions & decisions (spec MD1-MD14; AC1-AC3)."""

import datetime
import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, ManagementDiscussion, Notification
from app.services.storage import storage
from tests.bdm001_helpers import login, make_user
from tests.bdm005_helpers import PDF_BYTES

DISCUSSIONS = "/api/v1/management/discussions"
MINE = "/api/v1/me/management-decisions"
TODAY = datetime.datetime.now(ZoneInfo("Asia/Kolkata")).date()
DEADLINE = TODAY + timedelta(days=10)


async def as_user(client, db, role: str = "partner", division: str = "global", **kwargs):
    user = await make_user(db, role, division, **kwargs)
    await login(client, user)
    return user


def japan(responsible_id=None, **overrides) -> dict:
    body = {
        "topic": "Japan University Partnership",
        "discussion_date": TODAY.isoformat(),
        "department": "University partnerships",
        "points": "Tokyo and Osaka universities offered terms; confidential commission figures discussed.",
        "decision": "Proceed with agreement",
        "deadline": DEADLINE.isoformat(),
        "status": "in_progress",
        "follow_up_date": (TODAY + timedelta(days=5)).isoformat(),
    }
    if responsible_id:
        body["responsible_user_id"] = str(responsible_id)
    body.update(overrides)
    return body


async def create(client, body: dict) -> dict:
    response = await client.post(DISCUSSIONS, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def notes_for(db, user_id) -> list[Notification]:
    db.expire_all()
    return list((await db.scalars(select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at))).all())


# --- AC1: the Japan example is stored -----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_japan_example_is_stored_with_all_fields(client, db_session):
    bdm = await make_user(db_session, "partnership_manager", "global", name="University BDM")
    colleague = await make_user(db_session, "partner", "global")
    partner = await as_user(client, db_session)
    created = await create(client, japan(bdm.id, participant_ids=[str(partner.id), str(colleague.id)]))
    detail = (await client.get(f"{DISCUSSIONS}/{created['id']}")).json()
    assert detail["topic"] == "Japan University Partnership"
    assert detail["decision"] == "Proceed with agreement"
    assert detail["responsible"]["full_name"] == "University BDM"
    assert detail["deadline"] == DEADLINE.isoformat()
    assert detail["status"] == "in_progress"
    assert detail["department"] == "University partnerships"
    assert detail["points"].startswith("Tokyo")
    assert detail["follow_up_date"] == (TODAY + timedelta(days=5)).isoformat()
    assert {p["id"] for p in detail["participants"]} == {str(partner.id), str(colleague.id)}
    assert detail["attachments"] == []
    assert detail["created_by"]["id"] == str(partner.id)


@pytest.mark.asyncio
async def test_super_admin_may_record_a_discussion_accountant_and_staff_may_not(client, db_session):
    await as_user(client, db_session, "super_admin")
    assert (await client.post(DISCUSSIONS, json=japan())).status_code == 201
    for role in ("accountant", "bdm", "partnership_manager", "it_admin"):
        await as_user(client, db_session, role, "global" if role != "it_admin" else "it")
        assert (await client.get(DISCUSSIONS)).status_code == 403, role
        assert (await client.post(DISCUSSIONS, json=japan())).status_code == 403, role
        assert (await client.get(f"{DISCUSSIONS}/options")).status_code == 403, role


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(DISCUSSIONS)).status_code == 401
    assert (await client.get(MINE)).status_code == 401


# --- AC2 / AC3: the responsible person's slice ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac2_ac3_responsible_sees_only_the_decision_line_and_updates_status(client, db_session):
    bdm = await make_user(db_session, "partnership_manager", "global")
    await as_user(client, db_session)
    created = await create(client, japan(bdm.id))
    await login(client, bdm)
    mine = (await client.get(MINE)).json()
    item = next(i for i in mine["items"] if i["id"] == created["id"])
    assert item["decision"] == "Proceed with agreement"
    assert item["deadline"] == DEADLINE.isoformat()
    assert item["status"] == "in_progress"
    assert set(item) == {"id", "decision", "deadline", "status", "attachments", "updated_at"}  # AC3: no topic, points, participants
    assert "Tokyo" not in str(mine) and "Japan" not in str(mine)
    assert (await client.get(f"{DISCUSSIONS}/{created['id']}")).status_code == 403
    changed = await client.patch(f"{MINE}/{created['id']}", json={"status": "completed"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["status"] == "completed"
    row = await db_session.get(ManagementDiscussion, uuid.UUID(created["id"]))
    await db_session.refresh(row)
    assert row.status == "completed"


@pytest.mark.asyncio
async def test_another_users_decision_is_404_and_cancelled_is_409(client, db_session):
    bdm = await make_user(db_session, "bdm", "global")
    other = await make_user(db_session, "telecaller", "global")
    await as_user(client, db_session)
    created = await create(client, japan(bdm.id))
    cancelled = await create(client, japan(bdm.id, status="cancelled"))
    await login(client, other)
    assert (await client.patch(f"{MINE}/{created['id']}", json={"status": "completed"})).status_code == 404
    assert all(i["id"] != created["id"] for i in (await client.get(MINE)).json()["items"])
    assert (await client.patch(f"{MINE}/{uuid.uuid4()}", json={"status": "completed"})).status_code == 404
    await login(client, bdm)
    assert all(i["id"] != cancelled["id"] for i in (await client.get(MINE)).json()["items"])
    assert (await client.patch(f"{MINE}/{cancelled['id']}", json={"status": "completed"})).status_code == 409
    assert (await client.patch(f"{MINE}/{created['id']}", json={"status": "cancelled"})).status_code == 422


# --- field rules ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_inactive_or_non_staff_responsible_is_422(client, db_session):
    inactive = await make_user(db_session, "partnership_manager", "global", active=False)
    student = await make_user(db_session, "it_student", "it")
    await as_user(client, db_session)
    for who in (inactive, student):
        response = await client.post(DISCUSSIONS, json=japan(who.id))
        assert response.status_code == 422, response.text
        assert response.json()["detail"][0]["loc"][-1] == "responsible_user_id"
    response = await client.post(DISCUSSIONS, json=japan(participant_ids=[str(student.id)]))
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "participant_ids"
    assert (await client.post(DISCUSSIONS, json=japan(uuid.uuid4()))).status_code == 422


@pytest.mark.asyncio
async def test_decision_and_date_rules(client, db_session):
    bdm = await make_user(db_session, "bdm", "global")
    await as_user(client, db_session)
    no_decision = await client.post(DISCUSSIONS, json=japan(bdm.id, decision=None))
    assert no_decision.status_code == 422
    early = await client.post(DISCUSSIONS, json=japan(deadline=(TODAY - timedelta(days=1)).isoformat()))
    assert early.status_code == 422
    future = await client.post(DISCUSSIONS, json=japan(discussion_date=(TODAY + timedelta(days=1)).isoformat()))
    assert future.status_code == 422
    assert (await client.post(DISCUSSIONS, json=japan(topic="x"))).status_code == 422
    assert (await client.post(DISCUSSIONS, json=japan(status="done"))).status_code == 422
    minimal = await create(client, {"topic": "Weekly sync", "discussion_date": TODAY.isoformat()})
    assert minimal["status"] == "open" and minimal["decision"] is None and minimal["responsible"] is None


@pytest.mark.asyncio
async def test_patch_changes_fields_clears_optional_and_replaces_participants(client, db_session):
    p1 = await make_user(db_session, "partner", "global")
    await as_user(client, db_session)
    created = await create(client, japan(participant_ids=[str(p1.id)]))
    response = await client.patch(f"{DISCUSSIONS}/{created['id']}", json={"department": None, "participant_ids": [], "status": "completed"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["department"] is None and body["participants"] == [] and body["status"] == "completed"
    # clearing the decision while someone is responsible is refused
    bdm = await make_user(db_session, "bdm", "global")
    assigned = await create(client, japan(bdm.id))
    assert (await client.patch(f"{DISCUSSIONS}/{assigned['id']}", json={"decision": None})).status_code == 422
    assert (await client.patch(f"{DISCUSSIONS}/{uuid.uuid4()}", json={"status": "open"})).status_code == 404


# --- notifications (MD9) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_responsible_is_notified_on_assign_change_and_reassign_not_on_own_update(client, db_session):
    first = await make_user(db_session, "partnership_manager", "global")
    second = await make_user(db_session, "counselor", "overseas")
    first_id, second_id = first.id, second.id
    await as_user(client, db_session)
    created = await create(client, japan(first.id))
    notes = await notes_for(db_session, first_id)
    assert len(notes) == 1
    assert "Proceed with agreement" in notes[0].body and "Tokyo" not in notes[0].body and "Japan" not in notes[0].body
    assert notes[0].action_url == "/account/management-decisions"
    await client.patch(f"{DISCUSSIONS}/{created['id']}", json={"points": "More confidential notes"})
    assert len(await notes_for(db_session, first_id)) == 1  # notes are not the assignee's business
    await client.patch(f"{DISCUSSIONS}/{created['id']}", json={"deadline": (DEADLINE + timedelta(days=3)).isoformat()})
    assert len(await notes_for(db_session, first_id)) == 2  # a decision changed after assignment
    await client.patch(f"{DISCUSSIONS}/{created['id']}", json={"responsible_user_id": str(second_id)})
    assert len(await notes_for(db_session, second_id)) == 1
    assert len(await notes_for(db_session, first_id)) == 2
    await db_session.refresh(second)
    await login(client, second)
    assert (await client.patch(f"{MINE}/{created['id']}", json={"status": "completed"})).status_code == 200
    assert len(await notes_for(db_session, second_id)) == 1


# --- audit (MD11) ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_writes_are_audited_with_field_names_only(client, db_session):
    bdm = await make_user(db_session, "bdm", "global")
    partner = await as_user(client, db_session)
    created = await create(client, japan())
    await client.patch(f"{DISCUSSIONS}/{created['id']}", json={"decision": "Pause the agreement", "responsible_user_id": str(bdm.id)})
    await client.patch(f"{DISCUSSIONS}/{created['id']}", json={"department": "Partnerships"})
    partner_id, bdm_id = partner.id, bdm.id
    await login(client, bdm)
    await client.patch(f"{MINE}/{created['id']}", json={"status": "completed"})
    db_session.expire_all()
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == created["id"]).order_by(AuditLog.created_at))).all()
    assert [r.action for r in rows] == ["mgmt.decision.create", "mgmt.decision.decide", "mgmt.decision.update", "mgmt.decision.complete"]
    assert rows[0].user_id == partner_id and rows[-1].user_id == bdm_id
    assert all("values" not in r.metadata_json for r in rows)
    assert set(rows[1].metadata_json["fields"]) == {"decision", "responsible_user_id"}


# --- list (MD12) ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_filters_and_pending_order(client, db_session):
    bdm = await make_user(db_session, "bdm", "global")
    await as_user(client, db_session)
    late = await create(client, japan(bdm.id, deadline=(TODAY + timedelta(days=30)).isoformat()))
    soon = await create(client, japan(bdm.id, deadline=(TODAY + timedelta(days=2)).isoformat(), status="open"))
    undated = await create(client, japan(bdm.id, deadline=None))
    done = await create(client, japan(bdm.id, status="completed"))
    pending = (await client.get(DISCUSSIONS, params={"pending": "true", "responsible": str(bdm.id)})).json()
    assert [i["id"] for i in pending["items"]] == [soon["id"], late["id"], undated["id"]]
    assert pending["total"] == 3
    completed = (await client.get(DISCUSSIONS, params={"status": "completed", "responsible": str(bdm.id)})).json()
    assert [i["id"] for i in completed["items"]] == [done["id"]]
    first = (await client.get(DISCUSSIONS, params={"limit": 1, "responsible": str(bdm.id)})).json()
    assert first["total"] == 4 and len(first["items"]) == 1
    assert "points" not in first["items"][0]  # the list never carries the notes
    assert (await client.get(DISCUSSIONS, params={"status": "bogus"})).status_code == 422


@pytest.mark.asyncio
async def test_options_list_active_staff_only(client, db_session):
    staff = await make_user(db_session, "trainer", "it")
    gone = await make_user(db_session, "trainer", "it", active=False)
    student = await make_user(db_session, "it_student", "it")
    await as_user(client, db_session)
    ids = {u["id"] for u in (await client.get(f"{DISCUSSIONS}/options")).json()["users"]}
    assert str(staff.id) in ids and str(gone.id) not in ids and str(student.id) not in ids


# --- attachments (MD10) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_attachments_shareable_slice_and_removal(client, db_session):
    bdm = await make_user(db_session, "partnership_manager", "global")
    await as_user(client, db_session)
    created = await create(client, japan(bdm.id))
    url = f"{DISCUSSIONS}/{created['id']}/attachments"
    shared = await client.post(url, files={"file": ("terms.pdf", PDF_BYTES, "application/pdf")}, data={"shareable": "true"})
    assert shared.status_code == 201, shared.text
    private = await client.post(url, files={"file": ("notes.pdf", PDF_BYTES, "application/pdf")})
    assert private.status_code == 201
    detail = (await client.get(f"{DISCUSSIONS}/{created['id']}")).json()
    assert [(a["name"], a["shareable"]) for a in detail["attachments"]] == [("terms.pdf", True), ("notes.pdf", False)]
    shared_id, private_id = (a["id"] for a in detail["attachments"])
    download = await client.get(f"{url}/{private_id}")
    assert download.status_code == 200 and download.content == PDF_BYTES
    assert (await client.post(url, files={"file": ("x.txt", b"hello", "text/plain")})).status_code == 415

    await login(client, bdm)
    item = next(i for i in (await client.get(MINE)).json()["items"] if i["id"] == created["id"])
    assert [a["id"] for a in item["attachments"]] == [shared_id]
    assert (await client.get(f"{MINE}/{created['id']}/attachments/{shared_id}")).status_code == 200
    assert (await client.get(f"{MINE}/{created['id']}/attachments/{private_id}")).status_code == 404

    await as_user(client, db_session)
    row = (await client.get(f"{DISCUSSIONS}/{created['id']}")).json()["attachments"][1]
    key_count = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == created["id"], AuditLog.action == "mgmt.decision.download"))
    assert key_count == 2  # the partner's and the responsible person's downloads
    assert (await client.delete(f"{url}/{row['id']}")).status_code == 204
    assert len((await client.get(f"{DISCUSSIONS}/{created['id']}")).json()["attachments"]) == 1
    assert (await client.delete(f"{url}/{row['id']}")).status_code == 404


@pytest.mark.asyncio
async def test_eleventh_attachment_is_409(client, db_session):
    await as_user(client, db_session)
    created = await create(client, japan())
    url = f"{DISCUSSIONS}/{created['id']}/attachments"
    for _ in range(10):
        assert (await client.post(url, files={"file": ("a.pdf", PDF_BYTES, "application/pdf")})).status_code == 201
    assert (await client.post(url, files={"file": ("a.pdf", PDF_BYTES, "application/pdf")})).status_code == 409


@pytest.mark.asyncio
async def test_failed_write_discards_the_stored_attachment(client, db_session, monkeypatch):
    from app.services import management_audit

    await as_user(client, db_session)
    created = await create(client, japan())
    stored: list[str] = []
    original = storage.write_bytes
    monkeypatch.setattr(storage, "write_bytes", lambda key, data, ct: (stored.append(key), original(key, data, ct))[1])

    def boom(*args, **kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(management_audit, "record", boom)
    with pytest.raises(RuntimeError):
        await client.post(f"{DISCUSSIONS}/{created['id']}/attachments", files={"file": ("a.pdf", PDF_BYTES, "application/pdf")})
    assert stored
    with pytest.raises(FileNotFoundError):
        storage.read_bytes(stored[0])
