"""itc-006 (DEC-SCOPE-338, API §12IJ) -- source rules on the distribution-rule routes and the team's fallback strategy.

A source is unique per team and the shared database is never truncated, so every source rule a test creates is deleted in `finally`,
and every strategy change is put back to round robin."""

import pytest
from sqlalchemy import delete, select

from app.models import AuditLog, TelDistributionRule
from tests.tel007_helpers import RULES, login, make_telecaller, make_tl_manager, make_user

STRATEGY = "/api/v1/telecaller/distribution-strategy"


def _source_body(tel, source="exhibition_event", *, team="it", **extra):
    return {"team": team, "kind": "source", "source": source, "telecaller_user_id": str(tel.id), **extra}


async def _clear(db, source, team="it"):
    await db.execute(delete(TelDistributionRule).where(TelDistributionRule.team == team, TelDistributionRule.source == source))
    await db.commit()


@pytest.mark.asyncio
async def test_a_manager_creates_lists_and_deletes_a_source_rule(client, db_session):
    manager = await make_tl_manager(db_session)
    tel = await make_telecaller(db_session, manager)
    await login(client, manager)
    await _clear(db_session, "exhibition_event")
    try:
        response = await client.post(RULES, json=_source_body(tel))
        assert response.status_code == 201, response.text
        data = response.json()
        assert (data["kind"], data["source"], data["product"], data["city"], data["editable"]) == ("source", "exhibition_event", None, None, True)
        audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "telecaller.rule_create", AuditLog.entity_id == data["id"]))
        assert audit.metadata_json == {"team": "it", "kind": "source", "telecaller_user_id": str(tel.id)}
        assert (await client.post(RULES, json=_source_body(tel))).status_code == 409  # one rule per team + source
        listed = (await client.get(RULES, params={"kind": "source", "telecaller_user_id": str(tel.id)})).json()
        assert [r["source"] for r in listed["items"]] == ["exhibition_event"]
        city_rows = (await client.get(RULES, params={"kind": "city", "telecaller_user_id": str(tel.id)})).json()
        assert city_rows["items"] == []
        assert (await client.delete(f"{RULES}/{data['id']}")).status_code == 204
    finally:
        await _clear(db_session, "exhibition_event")


@pytest.mark.asyncio
async def test_source_rule_shape_errors_are_422(client, db_session):
    manager = await make_tl_manager(db_session)
    tel = await make_telecaller(db_session, manager)
    await login(client, manager)
    assert (await client.post(RULES, json=_source_body(tel, source=None))).json()["detail"] == "Choose a source"
    assert (await client.post(RULES, json=_source_body(tel, source="tiktok"))).status_code == 422  # not one of the 13
    assert (await client.post(RULES, json=_source_body(tel, city="Pune"))).json()["detail"] == "A source rule has no product or city"
    assert (await client.post(RULES, json={"team": "it", "kind": "city", "city": "Pune", "source": "google",
                                           "telecaller_user_id": str(tel.id)})).json()["detail"] == "A city rule has no source"


@pytest.mark.asyncio
async def test_source_rule_for_other_team_telecaller_is_422(client, db_session):
    manager = await make_tl_manager(db_session)
    overseas = await make_telecaller(db_session, manager, team="overseas")
    await login(client, manager)
    response = await client.post(RULES, json=_source_body(overseas, "college", team="it"))
    assert response.status_code == 422 and "Overseas team" in response.json()["detail"]


# --- the fallback strategy ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_strategy_roles(client, db_session):
    assert (await client.get(STRATEGY)).status_code == 401
    for role, division in (("it_admin", "it"), ("telecaller", "it"), ("counselor", "overseas")):
        await login(client, await make_user(db_session, role, division))
        assert (await client.get(STRATEGY)).status_code == 403
        assert (await client.put(f"{STRATEGY}/it", json={"strategy": "workload"})).status_code == 403


@pytest.mark.asyncio
async def test_a_manager_of_the_team_switches_the_strategy_and_it_is_audited(client, db_session):
    manager = await make_tl_manager(db_session)
    await make_telecaller(db_session, manager, team="overseas")
    await login(client, manager)
    items = (await client.get(STRATEGY)).json()["items"]
    assert [(i["team"], i["team_label"], i["editable"]) for i in items] == [("it", "IT", False), ("overseas", "Overseas", True)]
    assert {i["strategy"] for i in items} <= {"round_robin", "workload"}
    try:
        response = await client.put(f"{STRATEGY}/overseas", json={"strategy": "workload"})
        assert response.status_code == 200, response.text
        assert response.json() == {"team": "overseas", "team_label": "Overseas", "strategy": "workload", "editable": True}
        audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "telecaller.strategy_update", AuditLog.user_id == manager.id))
        assert audit.entity_id == "overseas" and audit.metadata_json["to"] == "workload"
        assert (await client.put(f"{STRATEGY}/it", json={"strategy": "workload"})).status_code == 403  # no report on the IT team
        assert (await client.put(f"{STRATEGY}/mars", json={"strategy": "workload"})).status_code == 404
        assert (await client.put(f"{STRATEGY}/overseas", json={"strategy": "fastest"})).status_code == 422
        assert (await client.put(f"{STRATEGY}/overseas", json={"strategy": "workload", "x": 1})).status_code == 422
    finally:
        assert (await client.put(f"{STRATEGY}/overseas", json={"strategy": "round_robin"})).status_code == 200
