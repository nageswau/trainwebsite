"""upc-023 -- PUT /partnership/universities/{id}/probability and the detail's `probability` block (spec §2 EX2-EX4, §4; negative scenario:
an override outside 0-100 -> 422)."""

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, make_pm, url

ACTION = "university.probability_overridden"


async def _owned(client, db):
    """A head, their manager and a university the manager owns (stage Target University, 10%)."""
    head = await make_head(db)
    manager = await make_pm(db, head)
    await login(client, head)
    uni = await create(client, (await catalogue_country(db)).id)
    assert (await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(manager.id)})).status_code == 200
    return head, manager, uni


async def _audits(db, uni) -> list[AuditLog]:
    return list((await db.scalars(select(AuditLog).where(AuditLog.entity_id == uni["id"], AuditLog.action == ACTION).order_by(AuditLog.created_at))).all())


@pytest.mark.asyncio
async def test_the_detail_shows_the_stage_probability(client, db_session):
    _, _, uni = await _owned(client, db_session)
    body = (await client.get(url(uni["id"]))).json()["university"]
    assert body["probability"] == {"stage": 10, "override": None, "reason": None, "effective": 10}


@pytest.mark.asyncio
async def test_the_owner_sets_and_clears_an_override_audited(client, db_session):
    _, manager, uni = await _owned(client, db_session)
    await login(client, manager)
    response = await client.put(url(uni["id"], "probability"), json={"probability": 70, "reason": "  Dean confirmed the budget  "})
    assert response.status_code == 200, response.text
    assert response.json()["university"]["probability"] == {"stage": 10, "override": 70, "reason": "Dean confirmed the budget", "effective": 70}
    same = await client.put(url(uni["id"], "probability"), json={"probability": 70, "reason": "Dean confirmed the budget"})
    assert same.status_code == 200
    assert len(await _audits(db_session, uni)) == 1  # no change, no audit
    cleared = await client.put(url(uni["id"], "probability"), json={"probability": None})
    assert cleared.json()["university"]["probability"] == {"stage": 10, "override": None, "reason": None, "effective": 10}
    audits = await _audits(db_session, uni)
    assert [(a.metadata_json["from"], a.metadata_json["to"]) for a in audits] == [(None, 70), (70, None)]
    assert all(a.user_id == manager.id for a in audits) and "Dean" not in str(audits[0].metadata_json)  # no free text in the audit


@pytest.mark.asyncio
async def test_zero_is_an_override(client, db_session):
    head, _, uni = await _owned(client, db_session)
    response = await client.put(url(uni["id"], "probability"), json={"probability": 0, "reason": "Frozen by the ministry"})
    assert response.status_code == 200 and response.json()["university"]["probability"]["effective"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"probability": 101, "reason": "x"},
        {"probability": -1, "reason": "x"},
        {"probability": 50},
        {"probability": 50, "reason": "   "},
        {"probability": None, "reason": "no value"},
        {"probability": "50", "reason": "string"},
        {"probability": 50.5, "reason": "fraction"},
        {"probability": 50, "reason": "x" * 501},
        {"probability": 50, "reason": "x", "stage": "active_partner"},
        {},
    ],
)
async def test_invalid_overrides_are_422(client, db_session, body):
    _, _, uni = await _owned(client, db_session)
    response = await client.put(url(uni["id"], "probability"), json=body)
    assert response.status_code == 422, response.text
    assert await _audits(db_session, uni) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("body", "message"), [({"probability": 50}, "Give a reason"), ({"probability": None, "reason": "x"}, "takes no reason")])
async def test_the_reason_rule_is_reported_on_the_reason_field(client, db_session, body, message):
    """So the form can show it under the reason input."""
    _, _, uni = await _owned(client, db_session)
    detail = (await client.put(url(uni["id"], "probability"), json=body)).json()["detail"]
    assert [(d["loc"], message in d["msg"]) for d in detail] == [(["body", "reason"], True)]


@pytest.mark.asyncio
async def test_other_teams_and_read_only_roles_are_refused(client, db_session):
    head, manager, uni = await _owned(client, db_session)
    body = {"probability": 60, "reason": "x"}
    await login(client, await make_pm(db_session, head))  # a colleague who does not own it
    assert (await client.put(url(uni["id"], "probability"), json=body)).status_code == 403
    await login(client, await make_head(db_session))  # another head
    assert (await client.put(url(uni["id"], "probability"), json=body)).status_code == 403
    await as_role(client, db_session, "overseas_admin", "overseas")  # reads the master, never moves stages
    assert (await client.put(url(uni["id"], "probability"), json=body)).status_code == 403
    await as_role(client, db_session, "counselor", "overseas")
    assert (await client.put(url(uni["id"], "probability"), json=body)).status_code == 403
    assert await _audits(db_session, uni) == []


@pytest.mark.asyncio
async def test_an_inactive_university_is_409_and_unknown_is_404(client, db_session):
    head, _, uni = await _owned(client, db_session)
    assert (await client.post(url(uni["id"], "deactivate"), json={})).status_code == 200
    assert (await client.put(url(uni["id"], "probability"), json={"probability": 60, "reason": "x"})).status_code == 409
    assert (await client.put(url("00000000-0000-0000-0000-000000000000", "probability"), json={"probability": 60, "reason": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.put(url("00000000-0000-0000-0000-000000000000", "probability"), json={"probability": 1, "reason": "x"})).status_code == 401
