"""bdm-016 -- monthly targets: the BDM's own sheet, the manager's team list, detail, batch save and copy (spec §5; AC2, AC4, AC5, R3-R9)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, BdmTarget
from app.services.bdm_metrics import month_range
from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import make_bdm
from tests.bdm015_helpers import appointment, org_row
from tests.bdm016_helpers import COPY, TARGETS, TEAM_TARGETS, shift, this_month, ym

NOW = this_month()
PAST = shift(NOW, -1)


async def _team(client, db):
    manager = await make_manager(db)
    college, school = await make_bdm(db, manager, "college"), await make_bdm(db, manager, "school")
    inactive = await make_bdm(db, manager, "agent", active=False)
    outsider = await make_bdm(db, await make_manager(db), "college")
    client.cookies.clear()
    await login(client, manager)
    return {"manager": manager, "college": college, "school": school, "inactive": inactive, "outsider": outsider}


async def _as(client, user):
    client.cookies.clear()
    await login(client, user)


def _put(month, *items):
    return {"month": ym(month), "items": [{"bdm_user_id": str(u.id), "kpi_key": k, "target": t} for u, k, t in items]}


def _kpi(sheet: dict, key: str) -> dict:
    return next(k for k in sheet["kpis"] if k["key"] == key)


async def _targets(db, user, month) -> dict:
    rows = (await db.execute(select(BdmTarget).where(BdmTarget.bdm_user_id == user.id, BdmTarget.month == month).execution_options(populate_existing=True))).scalars()
    return {r.kpi_key: r.target for r in rows}


async def _audits(db, user, action: str) -> list[AuditLog]:
    rows = await db.execute(select(AuditLog).where(AuditLog.action == action, AuditLog.entity_id == str(user.id)).order_by(AuditLog.created_at))
    return list(rows.scalars())


@pytest.mark.asyncio
async def test_a_manager_sets_a_target_and_the_bdm_sees_target_achieved_and_percent(client, db_session):
    t = await _team(client, db_session)
    college = await org_row(db_session, t["college"].id, "college")
    start = month_range(NOW)[0]
    for n in range(22):  # AC5: 22 college meetings completed this month
        await appointment(db_session, t["college"].id, college.id, start + timedelta(minutes=n + 1))
    response = await client.put(TEAM_TARGETS, json=_put(NOW, (t["college"], "college_meetings", 30), (t["college"], "meetings", 0)))
    assert response.status_code == 200, response.text
    assert response.json() == {"month": ym(NOW), "changed": 2}
    await _as(client, t["college"])
    sheet = (await client.get(f"{TARGETS}?month={ym(NOW)}")).json()
    assert (sheet["month"], sheet["month_status"], sheet["editable"], sheet["bdm_type"]) == (ym(NOW), "current", False, "college")
    assert {k: _kpi(sheet, "college_meetings")[k] for k in ("target", "achieved", "percent", "tracked")} == {"target": 30, "achieved": 22, "percent": 73, "tracked": True}
    assert (_kpi(sheet, "meetings")["target"], _kpi(sheet, "meetings")["percent"]) == (0, None)  # R5: a target of 0 is "—"
    assert (_kpi(sheet, "mous")["target"], _kpi(sheet, "mous")["percent"]) == (None, None)
    internship = _kpi(sheet, "internship_students")
    assert (internship["tracked"], internship["achieved"], internship["percent"]) == (False, None, None)
    assert (await client.get(TARGETS)).json()["month"] == ym(NOW)  # the default is this IST month


@pytest.mark.asyncio
async def test_saving_audits_each_bdm_from_and_to_and_an_unchanged_save_writes_nothing(client, db_session):
    t = await _team(client, db_session)
    assert (await client.put(TEAM_TARGETS, json=_put(NOW, (t["school"], "proposals", 5)))).status_code == 200
    assert (await client.put(TEAM_TARGETS, json=_put(NOW, (t["school"], "proposals", 8), (t["school"], "mous", 2)))).json()["changed"] == 2
    assert (await client.put(TEAM_TARGETS, json=_put(NOW, (t["school"], "proposals", 8)))).json()["changed"] == 0
    assert (await client.put(TEAM_TARGETS, json=_put(NOW, (t["school"], "mous", None)))).json()["changed"] == 1  # null clears
    assert await _targets(db_session, t["school"], NOW) == {"proposals": 8}
    audits = await _audits(db_session, t["school"], "bdm_target.set")
    assert [a.metadata_json["changes"] for a in audits] == [
        [{"kpi": "proposals", "from": None, "to": 5}],
        [{"kpi": "proposals", "from": 5, "to": 8}, {"kpi": "mous", "from": None, "to": 2}],
        [{"kpi": "mous", "from": 2, "to": None}],
    ]
    assert all(a.user_id == t["manager"].id and a.metadata_json["month"] == ym(NOW) for a in audits)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kpi", "target", "detail"),
    [("active_schools", 3, "Active Schools"), ("no_such_kpi", 3, "no_such_kpi"), ("meetings", -1, None), ("meetings", 100_001, None)],
)
async def test_a_kpi_outside_the_type_or_a_bad_value_is_422_and_nothing_is_written(client, db_session, kpi, target, detail):
    t = await _team(client, db_session)
    response = await client.put(TEAM_TARGETS, json=_put(NOW, (t["college"], "meetings", 9), (t["college"], kpi, target)))
    assert response.status_code == 422, response.text
    if detail:
        assert detail in response.text
    assert await _targets(db_session, t["college"], NOW) == {}


@pytest.mark.asyncio
async def test_month_rules(client, db_session):
    t = await _team(client, db_session)
    past = await client.put(TEAM_TARGETS, json=_put(PAST, (t["college"], "meetings", 9)))
    assert past.status_code == 422 and "super admin" in past.text  # AC4
    assert (await client.put(TEAM_TARGETS, json=_put(shift(NOW, 13), (t["college"], "meetings", 9)))).status_code == 422
    assert (await client.put(TEAM_TARGETS, json=_put(shift(NOW, 12), (t["college"], "meetings", 9)))).status_code == 200
    for bad in ("2026-13", "2026-1", "x", "2026-10-01"):
        assert (await client.get(f"{TEAM_TARGETS}?month={bad}")).status_code == 422
    duplicate = _put(NOW, (t["college"], "meetings", 1), (t["college"], "meetings", 2))
    assert (await client.put(TEAM_TARGETS, json=duplicate)).status_code == 422
    assert (await client.put(TEAM_TARGETS, json={"month": ym(NOW), "items": []})).status_code == 422
    await _as(client, await make_user(db_session, "super_admin", "global"))
    assert (await client.put(TEAM_TARGETS, json=_put(PAST, (t["college"], "meetings", 9)))).status_code == 200
    sheet = (await client.get(f"{TEAM_TARGETS}/{t['college'].id}?month={ym(PAST)}")).json()
    assert (sheet["month_status"], sheet["editable"], _kpi(sheet, "meetings")["target"]) == ("past", True, 9)


@pytest.mark.asyncio
async def test_scope_another_team_is_404_inactive_is_422_and_roles_are_403(client, db_session):
    t = await _team(client, db_session)
    assert (await client.put(TEAM_TARGETS, json=_put(NOW, (t["outsider"], "meetings", 9)))).status_code == 404
    assert (await client.get(f"{TEAM_TARGETS}/{t['outsider'].id}")).status_code == 404
    assert (await client.get(f"{TEAM_TARGETS}/{uuid.uuid4()}")).status_code == 404
    assert (await client.put(TEAM_TARGETS, json=_put(NOW, (t["inactive"], "new_agent_leads", 9)))).status_code == 422
    assert (await client.get(TARGETS)).status_code == 403  # a manager has no own targets
    await _as(client, t["college"])
    assert (await client.get(TEAM_TARGETS)).status_code == 403
    assert (await client.put(TEAM_TARGETS, json=_put(NOW, (t["college"], "meetings", 99)))).status_code == 403
    assert (await client.post(COPY, json={"month": ym(NOW)})).status_code == 403
    await _as(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get(TARGETS)).status_code == 403 and (await client.get(TEAM_TARGETS)).status_code == 403


@pytest.mark.asyncio
async def test_the_team_list_counts_targets_set_for_active_team_bdms(client, db_session):
    t = await _team(client, db_session)
    await client.put(TEAM_TARGETS, json=_put(NOW, (t["school"], "proposals", 5), (t["school"], "mous", 2)))
    response = await client.get(f"{TEAM_TARGETS}?month={ym(NOW)}")
    assert response.status_code == 200, response.text
    data = response.json()
    assert (data["month"], data["month_status"], data["editable"], data["total"]) == (ym(NOW), "current", True, 2)
    rows = {r["bdm"]["id"]: r for r in data["items"]}
    assert set(rows) == {str(t["college"].id), str(t["school"].id)}
    assert (rows[str(t["school"].id)]["targets_set"], rows[str(t["school"].id)]["kpi_count"]) == (2, 15)
    assert (rows[str(t["college"].id)]["targets_set"], rows[str(t["college"].id)]["kpi_count"], rows[str(t["college"].id)]["bdm_type"]) == (0, 14, "college")
    assert (await client.get(f"{TEAM_TARGETS}?month={ym(PAST)}")).json()["editable"] is False


@pytest.mark.asyncio
async def test_a_future_month_has_no_achieved_yet(client, db_session):
    t = await _team(client, db_session)
    sheet = (await client.get(f"{TEAM_TARGETS}/{t['school'].id}?month={ym(shift(NOW, 1))}")).json()
    assert (sheet["month_status"], sheet["editable"]) == ("future", True)
    assert all(k["achieved"] is None and k["percent"] is None for k in sheet["kpis"])


@pytest.mark.asyncio
async def test_copy_fills_missing_targets_from_last_month_without_overwriting(client, db_session):
    t = await _team(client, db_session)
    for kpi, value in (("meetings", 10), ("mous", 3), ("course_promotions", 4)):
        db_session.add(BdmTarget(bdm_user_id=t["college"].id, month=PAST, kpi_key=kpi, target=value, set_by_user_id=t["manager"].id))
    db_session.add(BdmTarget(bdm_user_id=t["outsider"].id, month=PAST, kpi_key="meetings", target=7, set_by_user_id=t["manager"].id))
    db_session.add(BdmTarget(bdm_user_id=t["inactive"].id, month=PAST, kpi_key="new_agent_leads", target=7, set_by_user_id=t["manager"].id))
    await db_session.commit()
    await client.put(TEAM_TARGETS, json=_put(NOW, (t["college"], "mous", 5)))
    response = await client.post(COPY, json={"month": ym(NOW)})
    assert response.status_code == 200, response.text
    assert response.json() == {"month": ym(NOW), "copied": 2}
    assert await _targets(db_session, t["college"], NOW) == {"meetings": 10, "mous": 5, "course_promotions": 4}
    assert await _targets(db_session, t["outsider"], NOW) == {} and await _targets(db_session, t["inactive"], NOW) == {}
    [audit] = await _audits(db_session, t["college"], "bdm_target.copied")
    assert audit.metadata_json == {"month": ym(NOW), "from_month": ym(PAST), "kpis": ["course_promotions", "meetings"]}
    assert (await client.post(COPY, json={"month": ym(NOW)})).json()["copied"] == 0  # a repeat copies nothing
    assert (await client.post(COPY, json={"month": ym(PAST)})).status_code == 422
