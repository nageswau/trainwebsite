"""ccrm-006 (DEC-SCOPE-261, API §12FN, RBAC §2.175): the Duplicate closed stage (D2/D3), Wrong Number shown as Invalid Contact (D1), the
structured loss reason + "lost to" on Lost / Not Interested (D4/D5), call-logged closes unchanged (D6), reopen clears (D7), the reason
list (D8), the Lost Reasons report (D9) and the management "lost" figure (D10). The shared test database is never truncated: every
assertion is about rows the test made."""

import uuid

import pytest
from sqlalchemy import select

from app.lead_stages import CLOSED, label
from app.models import AuditLog, Enquiry, LeadLostReason, LeadStageHistory
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import lead, make_telecaller, make_tl_manager, make_user, stage_url
from tests.tel018_helpers import c_url, handover, setup

pytestmark = pytest.mark.asyncio

REASONS = "/api/v1/telecaller/lost-reasons"
ADMIN = "/api/v1/admin/leads"
REPORT = "/api/v1/telecaller/reports/lost"


async def reason(db, *, active: bool = True) -> LeadLostReason:
    row = LeadLostReason(name=f"Reason {uuid.uuid4().hex[:8]}", active=active)
    db.add(row)
    await db.commit()
    return row


async def stored(db, row) -> Enquiry:
    return await db.scalar(select(Enquiry).where(Enquiry.id == row.id).execution_options(populate_existing=True))


def field_error(response, field: str) -> bool:
    return response.status_code == 422 and any(e["loc"][-1] == field for e in response.json()["detail"])


async def working(client, db, *, division: str = "it"):
    """A manager, their telecaller signed in, and one contacted lead of theirs."""
    manager = await make_tl_manager(db)
    tel = await make_telecaller(db, manager, team=division)
    row = await lead(db, division=division, telecaller=tel, status="contacted")
    await as_user(client, tel)
    return manager, tel, row


# --- D1 / D2: the catalogue --------------------------------------------------------------------------------------------------------
async def test_duplicate_is_a_closed_stage_and_wrong_number_reads_invalid_contact():
    assert "duplicate" in CLOSED and label("duplicate") == "Duplicate"
    assert label("wrong_number") == "Invalid Contact"


# --- D3: Duplicate ---------------------------------------------------------------------------------------------------------------
async def test_closing_as_duplicate_without_a_target_is_422_and_nothing_moves(client, db_session):
    _, _, row = await working(client, db_session)
    assert field_error(await client.post(stage_url(row.id), json={"to_stage": "duplicate"}), "duplicate_of")
    assert (await stored(db_session, row)).status == "contacted"


async def test_closing_as_duplicate_links_the_surviving_lead(client, db_session):
    _, tel, row = await working(client, db_session)
    survivor = await lead(db_session, division="it")  # another telecaller's or unassigned lead of the same team is fine
    response = await client.post(stage_url(row.id), json={"to_stage": "duplicate", "duplicate_of": survivor.lead_code.lower()})
    assert response.status_code == 200, response.text
    lead_row = await stored(db_session, row)
    assert lead_row.status == "duplicate" and lead_row.duplicate_of_id == survivor.id
    detail = (await client.get(f"/api/v1/telecaller/leads/{row.id}")).json()
    assert detail["duplicate_of"] == {"id": str(survivor.id), "lead_code": survivor.lead_code}
    assert detail["status_label"] == "Duplicate"
    h = await db_session.scalar(select(LeadStageHistory).where(LeadStageHistory.lead_id == row.id, LeadStageHistory.to_stage == "duplicate"))
    assert h.reason == f"Duplicate of {survivor.lead_code}" and h.actor_user_id == tel.id


@pytest.mark.parametrize("case", ["self", "other_team", "unknown", "duplicate"])
async def test_a_bad_duplicate_target_is_422(client, db_session, case):
    _, _, row = await working(client, db_session)
    if case == "self":
        code = row.lead_code
    elif case == "other_team":
        code = (await lead(db_session, division="overseas")).lead_code
    elif case == "unknown":
        code = "LD-999999999"
    else:
        survivor = await lead(db_session, division="it")
        dup = Enquiry(division="it", name="Dup", email=f"{uuid.uuid4().hex[:8]}@example.local", subject="S", message="", source="website",
                      status="duplicate", duplicate_of_id=survivor.id)
        db_session.add(dup)
        await db_session.commit()
        code = dup.lead_code
    assert field_error(await client.post(stage_url(row.id), json={"to_stage": "duplicate", "duplicate_of": code}), "duplicate_of")
    assert (await stored(db_session, row)).status == "contacted"


# --- D4 / D5: Lost and Not Interested -----------------------------------------------------------------------------------------------
@pytest.mark.parametrize("to_stage", ["lost", "not_interested"])
async def test_lost_or_not_interested_needs_a_reason_from_the_list(client, db_session, to_stage):
    _, _, row = await working(client, db_session)
    assert field_error(await client.post(stage_url(row.id), json={"to_stage": to_stage, "reason": "Too costly"}), "lost_reason_id")
    inactive = await reason(db_session, active=False)
    body = {"to_stage": to_stage, "lost_reason_id": str(inactive.id)}
    assert field_error(await client.post(stage_url(row.id), json=body), "lost_reason_id")
    assert field_error(await client.post(stage_url(row.id), json={**body, "lost_reason_id": str(uuid.uuid4())}), "lost_reason_id")
    assert (await stored(db_session, row)).status == "contacted"


async def test_lost_with_a_reason_and_lost_to_is_stored_and_shown(client, db_session):
    _, _, row = await working(client, db_session)
    why = await reason(db_session)
    response = await client.post(stage_url(row.id), json={"to_stage": "lost", "lost_reason_id": str(why.id), "lost_to": "  Canada  "})
    assert response.status_code == 200, response.text
    lead_row = await stored(db_session, row)
    assert (lead_row.status, lead_row.lost_reason_id, lead_row.lost_to) == ("lost", why.id, "Canada")
    detail = (await client.get(f"/api/v1/telecaller/leads/{row.id}")).json()
    assert detail["lost_reason"] == {"id": str(why.id), "name": why.name} and detail["lost_to"] == "Canada"
    h = await db_session.scalar(select(LeadStageHistory).where(LeadStageHistory.lead_id == row.id, LeadStageHistory.to_stage == "lost"))
    assert h.reason == why.name  # D5: no text sent -> the reason's name


async def test_the_text_reason_is_kept_when_sent(client, db_session):
    _, _, row = await working(client, db_session)
    why = await reason(db_session)
    body = {"to_stage": "not_interested", "lost_reason_id": str(why.id), "reason": "Wants to wait a year"}
    assert (await client.post(stage_url(row.id), json=body)).status_code == 200
    h = await db_session.scalar(select(LeadStageHistory).where(LeadStageHistory.lead_id == row.id, LeadStageHistory.to_stage == "not_interested"))
    assert h.reason == "Wants to wait a year"


async def test_closure_fields_for_another_target_are_422(client, db_session):
    _, _, row = await working(client, db_session)
    why = await reason(db_session)
    assert field_error(await client.post(stage_url(row.id), json={"to_stage": "no_response", "reason": "x", "lost_reason_id": str(why.id)}), "lost_reason_id")
    assert field_error(await client.post(stage_url(row.id), json={"to_stage": "no_response", "reason": "x", "lost_to": "UK"}), "lost_to")
    assert field_error(await client.post(stage_url(row.id), json={"to_stage": "lost", "lost_reason_id": str(why.id), "duplicate_of": row.lead_code}), "duplicate_of")
    # other closed outcomes still need the text reason (unchanged)
    assert field_error(await client.post(stage_url(row.id), json={"to_stage": "wrong_number"}), "reason")


# --- D7: reopen clears ----------------------------------------------------------------------------------------------------------
async def test_reopen_clears_the_closure(client, db_session):
    manager, _, row = await working(client, db_session)
    why = await reason(db_session)
    assert (await client.post(stage_url(row.id), json={"to_stage": "lost", "lost_reason_id": str(why.id), "lost_to": "UK"})).status_code == 200
    await as_user(client, manager)
    assert (await client.post(stage_url(row.id), json={"to_stage": "follow_up", "reason": "Called back"})).status_code == 200
    lead_row = await stored(db_session, row)
    assert (lead_row.status, lead_row.lost_reason_id, lead_row.lost_to, lead_row.duplicate_of_id) == ("follow_up", None, None, None)


# --- counselor and admin routes -------------------------------------------------------------------------------------------------
async def test_counselor_closes_lost_with_a_reason_but_cannot_choose_duplicate(client, db_session):
    _, tel, counselor, row = await setup(db_session, "it")
    assert (await handover(client, tel, row, counselor)).status_code == 200
    await as_user(client, counselor)
    why = await reason(db_session)
    assert field_error(await client.post(c_url(row.id, "/stage"), json={"to_stage": "lost", "reason": "x"}), "lost_reason_id")
    survivor = await lead(db_session, division="it")
    assert (await client.post(c_url(row.id, "/stage"), json={"to_stage": "duplicate", "duplicate_of": survivor.lead_code})).status_code == 422
    response = await client.post(c_url(row.id, "/stage"), json={"to_stage": "lost", "lost_reason_id": str(why.id), "lost_to": "Germany"})
    assert response.status_code == 200, response.text
    detail = (await client.get(c_url(row.id))).json()
    assert detail["lost_reason"]["name"] == why.name and detail["lost_to"] == "Germany"


async def test_admin_patch_takes_the_closure_fields(client, db_session):
    admin = await make_user(db_session, "it_admin", "it")
    row = await lead(db_session, division="it", status="contacted")
    survivor = await lead(db_session, division="it")
    await as_user(client, admin)
    assert field_error(await client.patch(f"{ADMIN}/{row.id}", json={"status": "duplicate"}), "duplicate_of")
    response = await client.patch(f"{ADMIN}/{row.id}", json={"status": "duplicate", "duplicate_of": survivor.lead_code})
    assert response.status_code == 200, response.text
    assert (await stored(db_session, row)).duplicate_of_id == survivor.id
    items = (await client.get(f"{ADMIN}?q={row.lead_code}")).json()["items"]
    assert items[0]["duplicate_of"]["lead_code"] == survivor.lead_code


# --- D6: a call-logged close is unchanged --------------------------------------------------------------------------------------------
async def test_a_call_logged_close_still_works_without_a_reason_code(client, db_session):
    _, _, row = await working(client, db_session)
    response = await client.post(f"/api/v1/telecaller/leads/{row.id}/calls", json={"duration_seconds": 0, "call_type": "outgoing", "outcome": "already_joined"})
    assert response.status_code == 201, response.text
    lead_row = await stored(db_session, row)
    assert lead_row.status == "lost" and lead_row.lost_reason_id is None


# --- D8: the reason list ----------------------------------------------------------------------------------------------------------
async def test_a_manager_manages_the_reason_list_and_readers_see_active_rows(client, db_session):
    manager = await make_tl_manager(db_session)
    await as_user(client, manager)
    name = f"Chose a rival {uuid.uuid4().hex[:6]}"
    created = await client.post(REASONS, json={"name": name})
    assert created.status_code == 201, created.text
    rid = created.json()["id"]
    assert (await client.post(REASONS, json={"name": name.upper()})).status_code == 409
    assert (await client.post(REASONS, json={"name": "  "})).status_code == 422
    assert (await client.patch(f"{REASONS}/{rid}", json={"active": False})).json()["active"] is False
    assert any(r["id"] == rid for r in (await client.get(f"{REASONS}?limit=100&q={name}")).json()["items"])
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == rid, AuditLog.action == "telecaller.lost_reason_create"))
    assert audit is not None
    tel = await make_telecaller(db_session, manager)
    await as_user(client, tel)
    assert not any(r["id"] == rid for r in (await client.get(f"{REASONS}?limit=100&q={name}")).json()["items"])
    assert (await client.post(REASONS, json={"name": "Mine"})).status_code == 403
    assert (await client.patch(f"{REASONS}/{rid}", json={"active": True})).status_code == 403
    await as_user(client, await make_user(db_session, "it_student", "it"))
    assert (await client.get(REASONS)).status_code == 403


async def test_the_seeded_reasons_exist(db_session):
    names = set(await db_session.scalars(select(LeadLostReason.name)))
    assert {"Fees / budget", "Chose another institution", "Chose another country", "Other"} <= names


# --- D9: the Lost Reasons report --------------------------------------------------------------------------------------------------
async def test_the_lost_report_groups_losses_by_reason(client, db_session):
    manager = await make_tl_manager(db_session)
    tel = await make_telecaller(db_session, manager)
    a, b = await reason(db_session), await reason(db_session)
    rows = [Enquiry(division="it", name="L", email=f"{uuid.uuid4().hex[:8]}@example.local", subject="S", message="", source="website",
                    telecaller_user_id=tel.id, status=status, lost_reason_id=rid)
            for status, rid in (("lost", a.id), ("lost", a.id), ("not_interested", a.id), ("not_interested", b.id), ("lost", None),
                                ("wrong_number", None), ("contacted", None))]
    db_session.add_all(rows)
    await db_session.commit()
    await as_user(client, manager)
    body = (await client.get(REPORT)).json()
    assert [c["key"] for c in body["columns"]] == ["label", "leads", "lost", "not_interested"]
    by = {item["label"]: item for item in body["items"]}
    assert (by[a.name]["leads"], by[a.name]["lost"], by[a.name]["not_interested"]) == (3, 2, 1)
    assert (by[b.name]["leads"], by[b.name]["not_interested"]) == (1, 1)
    assert by["No reason recorded"]["leads"] == 1
    assert body["totals"]["leads"] == 5
    csv = await client.get(f"{REPORT}.csv")
    assert csv.status_code == 200 and a.name in csv.text


# --- D10: the management lost figure --------------------------------------------------------------------------------------------
async def test_management_lost_figure_excludes_duplicates(db_session):
    from datetime import UTC, datetime, timedelta

    from app.services.management_telecalling import _outcomes

    tel = await make_telecaller(db_session, await make_tl_manager(db_session))
    row = await lead(db_session, telecaller=tel)
    db_session.add_all([LeadStageHistory(lead_id=row.id, from_stage="new", to_stage="duplicate", event="manual", actor_user_id=tel.id),
                        LeadStageHistory(lead_id=row.id, from_stage="new", to_stage="lost", event="manual", actor_user_id=tel.id)])
    await db_session.commit()
    now = datetime.now(UTC)
    assert (await _outcomes(db_session, [tel.id], now - timedelta(hours=1), now + timedelta(hours=1)))[tel.id] == (0, 1)
