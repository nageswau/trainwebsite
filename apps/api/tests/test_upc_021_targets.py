"""upc-021 -- targets API (spec §4, TG2-TG7, TG11, TG12; AC3-AC6): who reads and sets which months, the batch save, the audit history and
the per-manager + team comparison."""

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, PartnershipTarget, User
from app.services.bdm_travel import india_today
from tests.upc003_helpers import as_role, login, make_head, make_pm
from tests.upc007_helpers import move_ok, owned_university

TARGETS = "/api/v1/partnership/targets"


def _month(offset: int = 0) -> str:
    today = india_today()
    index = today.year * 12 + today.month - 1 + offset
    return f"{index // 12}-{index % 12 + 1:02d}"


def _sheet_url(manager, month: str | None = None) -> str:
    return f"{TARGETS}/{manager.id}" + (f"?month={month}" if month else "")


async def _put(client, month: str, *items):
    body = {"month": month, "items": [{"manager_user_id": str(m.id), "kpi_key": k, "target": t} for m, k, t in items]}
    return await client.put(TARGETS, json=body)


async def _get_ok(client, path: str) -> dict:
    response = await client.get(path)
    assert response.status_code == 200, response.text
    return response.json()


def _kpis(sheet: dict) -> dict[str, dict]:
    return {k["key"]: k for k in sheet["kpis"]}


@pytest.mark.asyncio
async def test_head_sets_targets_and_history_is_kept(client, db_session):
    """AC3 / Q-23: the batch save, an unchanged repeat writes nothing, null clears; one audit row per change set with from/to."""
    head = await make_head(db_session)
    pm = await make_pm(db_session, head)
    await login(client, head)
    month = _month()
    response = await _put(client, month, (pm, "mous", 5), (pm, "proposals", 15))
    assert response.status_code == 200, response.text
    assert response.json() == {"month": month, "changed": 2}
    sheet = await _get_ok(client, _sheet_url(pm, month))
    assert sheet["editable"] is True and sheet["manager"]["id"] == str(pm.id) and sheet["month_status"] == "current"
    assert [k["label"] for k in sheet["kpis"]][0] == "New universities identified" and len(sheet["kpis"]) == 7
    assert _kpis(sheet)["mous"]["target"] == 5 and _kpis(sheet)["contacted"]["target"] is None
    assert (await _put(client, month, (pm, "mous", 5))).json()["changed"] == 0
    assert (await _put(client, month, (pm, "mous", None), (pm, "proposals", 20))).json()["changed"] == 2
    sheet = await _get_ok(client, _sheet_url(pm, month))
    assert _kpis(sheet)["mous"]["target"] is None and _kpis(sheet)["proposals"]["target"] == 20
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(pm.id), AuditLog.action == "partnership_target.set").order_by(AuditLog.created_at))).all()
    assert [a.metadata_json["changes"] for a in audits] == [
        [{"kpi": "mous", "from": None, "to": 5}, {"kpi": "proposals", "from": None, "to": 15}],
        [{"kpi": "mous", "from": 5, "to": None}, {"kpi": "proposals", "from": 15, "to": 20}],
    ]
    assert all(a.user_id == head.id and a.metadata_json["month"] == month for a in audits)


@pytest.mark.asyncio
async def test_a_manager_reads_only_their_own_targets_and_cannot_set_them(client, db_session):
    """AC4 / TG6 / TG7: own sheet read-only; another manager is a 404; any write (even their own) is a 403."""
    head = await make_head(db_session)
    pm, peer = await make_pm(db_session, head), await make_pm(db_session, head)
    await login(client, head)
    await _put(client, _month(), (pm, "mous", 3))
    await login(client, pm)
    sheet = await _get_ok(client, _sheet_url(pm))
    assert sheet["editable"] is False and _kpis(sheet)["mous"]["target"] == 3
    assert (await client.get(_sheet_url(peer))).status_code == 404
    response = await _put(client, _month(), (pm, "mous", 50))
    assert response.status_code == 403
    team = await _get_ok(client, TARGETS)
    assert [m["manager"]["id"] for m in team["managers"]] == [str(pm.id)] and team["editable"] is False


@pytest.mark.asyncio
async def test_a_head_is_limited_to_direct_reports(client, db_session):
    """TG6 / AC5: another head's manager is a 404 to read or write (nothing is written)."""
    head, other_head = await make_head(db_session), await make_head(db_session)
    mine, theirs = await make_pm(db_session, head), await make_pm(db_session, other_head)
    await login(client, head)
    assert (await client.get(_sheet_url(theirs))).status_code == 404
    assert (await _put(client, _month(), (mine, "mous", 1), (theirs, "mous", 1))).status_code == 404
    assert await db_session.scalar(select(PartnershipTarget).where(PartnershipTarget.manager_user_id == mine.id)) is None
    team = await _get_ok(client, TARGETS)
    assert [m["manager"]["id"] for m in team["managers"]] == [str(mine.id)]


@pytest.mark.asyncio
async def test_month_rules(client, db_session):
    """TG3: a head edits the current month and up to 12 ahead; a past month only super_admin."""
    head = await make_head(db_session)
    pm = await make_pm(db_session, head)
    await login(client, head)
    past = await _put(client, _month(-1), (pm, "mous", 1))
    assert past.status_code == 422 and "super admin" in past.json()["detail"]
    assert (await _put(client, _month(13), (pm, "mous", 1))).status_code == 422
    assert (await _put(client, _month(12), (pm, "mous", 1))).status_code == 200
    assert (await _get_ok(client, _sheet_url(pm, _month(-1))))["editable"] is False
    await as_role(client, db_session, "super_admin", "global")
    assert (await _put(client, _month(-1), (pm, "mous", 1))).status_code == 200
    assert (await client.get(f"{TARGETS}?month=2026-13")).status_code == 422


@pytest.mark.asyncio
async def test_invalid_bodies_are_refused_and_write_nothing(client, db_session):
    head = await make_head(db_session)
    pm = await make_pm(db_session, head)
    await login(client, head)
    month = _month()
    for items in ([(pm, "revenue", 1)], [(pm, "mous", 100001)], [(pm, "mous", -1)], [(pm, "mous", 1), (pm, "mous", 2)]):
        assert (await _put(client, month, *items)).status_code == 422
    assert (await client.put(TARGETS, json={"month": month, "items": []})).status_code == 422
    assert (await client.put(TARGETS, json={"month": month, "items": [{"manager_user_id": str(pm.id), "kpi_key": "mous", "target": "5"}]})).status_code == 422
    assert await db_session.scalar(select(PartnershipTarget).where(PartnershipTarget.manager_user_id == pm.id)) is None


@pytest.mark.asyncio
async def test_inactive_managers_cannot_be_given_targets_and_are_listed_only_with_targets(client, db_session):
    """TG6 / TG11."""
    head = await make_head(db_session)
    with_target, without = await make_pm(db_session, head), await make_pm(db_session, head)
    await login(client, head)
    await _put(client, _month(), (with_target, "mous", 2))
    await db_session.execute(update(User).where(User.id.in_([with_target.id, without.id])).values(active=False))
    await db_session.commit()
    response = await _put(client, _month(), (with_target, "mous", 3))
    assert response.status_code == 422 and "inactive" in response.json()["detail"]
    team = await _get_ok(client, TARGETS)
    assert [(m["manager"]["id"], m["active"]) for m in team["managers"]] == [(str(with_target.id), False)]
    assert (await _get_ok(client, _sheet_url(with_target)))["editable"] is False


@pytest.mark.asyncio
async def test_other_roles_are_refused(client, db_session):
    """TG7: overseas_admin, counselor and BDM have no targets access."""
    pm = await make_pm(db_session, await make_head(db_session))
    for role, division in (("overseas_admin", "overseas"), ("counselor", "overseas"), ("bdm", "overseas")):
        await as_role(client, db_session, role, division)
        assert (await client.get(TARGETS)).status_code == 403
        assert (await client.get(_sheet_url(pm))).status_code == 403
        assert (await _put(client, _month(), (pm, "mous", 1))).status_code == 403


@pytest.mark.asyncio
async def test_comparison_per_manager_and_team(client, db_session):
    """AC1 / AC6 / TG5 / TG12: actual vs target per manager, the team row, and meetings not tracked."""
    head, pm, uni = await owned_university(client, db_session)
    peer = await make_pm(db_session, head)
    await move_ok(client, uni["id"], "target_university", "proposal_sent")
    await login(client, head)
    month = _month()
    await _put(client, month, (pm, "proposals", 4), (peer, "proposals", 6), (pm, "meetings", 2))
    team = await _get_ok(client, f"{TARGETS}?month={month}")
    assert [k["key"] for k in team["kpis"]] == ["new_universities", "contacted", "meetings", "proposals", "negotiations", "mous", "new_active"]
    rows = {m["manager"]["id"]: {k["key"]: k for k in m["kpis"]} for m in team["managers"]}
    assert rows[str(pm.id)]["proposals"] == {"key": "proposals", "target": 4, "achieved": 1, "percent": 25}
    assert rows[str(pm.id)]["new_universities"]["achieved"] == 1 and rows[str(pm.id)]["new_universities"]["percent"] is None
    assert rows[str(pm.id)]["meetings"] == {"key": "meetings", "target": 2, "achieved": None, "percent": None}
    assert rows[str(peer.id)]["proposals"] == {"key": "proposals", "target": 6, "achieved": 0, "percent": 0}
    totals = {k["key"]: k for k in team["team"]}
    assert totals["proposals"] == {"key": "proposals", "target": 10, "achieved": 1, "percent": 10}
    assert totals["mous"] == {"key": "mous", "target": None, "achieved": 0, "percent": None}
    assert totals["meetings"]["achieved"] is None


@pytest.mark.asyncio
async def test_future_months_have_no_actuals_and_past_months_list_only_managers_who_existed(client, db_session):
    """TG5 / TG11: a future month has targets but no actuals; a month before a manager joined does not list them."""
    head, pm, _ = await owned_university(client, db_session)
    await login(client, head)
    await _put(client, _month(1), (pm, "mous", 1))
    sheet = await _get_ok(client, _sheet_url(pm, _month(1)))
    assert sheet["month_status"] == "future" and _kpis(sheet)["mous"] == {
        "key": "mous", "label": "MoUs", "definition": _kpis(sheet)["mous"]["definition"], "tracked": True, "target": 1, "achieved": None, "percent": None,
    }  # fmt: skip
    assert (await _get_ok(client, f"{TARGETS}?month=2025-03"))["managers"] == []
    assert (await _get_ok(client, f"{TARGETS}?month={_month()}"))["managers"][0]["manager"]["id"] == str(pm.id)
