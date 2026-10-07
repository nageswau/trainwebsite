"""bdm-015 -- the manager's team view: who submitted, who is missing; a team report; the manager comment (spec §5; AC4, R7, R8)."""

from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, BdmProfile
from app.services import bdm_daily_reports as reports
from app.services.bdm_activities import day_range
from app.services.bdm_travel import india_today
from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import make_bdm
from tests.bdm015_helpers import TEAM_REPORTS, submit_url, team_report_url


async def _team(client, db):
    """A manager with three BDMs (one submits today and yesterday; one never; one inactive) and another manager's BDM."""
    manager = await make_manager(db)
    submitter, silent = await make_bdm(db, manager, "college"), await make_bdm(db, manager, "school")
    inactive = await make_bdm(db, manager, "agent", active=False)
    outsider = await make_bdm(db, await make_manager(db), "college")
    started = day_range(india_today() - timedelta(days=10))[0]  # profiles older than the grid: no "not started" days
    await db.execute(update(BdmProfile).where(BdmProfile.user_id.in_([submitter.id, silent.id, outsider.id])).values(created_at=started))
    await db.commit()
    for user in (submitter, outsider):
        client.cookies.clear()
        await login(client, user)
        for day in (india_today(), india_today() - timedelta(days=1)):
            assert (await client.post(submit_url(day), json={"note": "Done"})).status_code == 201
    client.cookies.clear()
    await login(client, manager)
    return {"manager": manager, "submitter": submitter, "silent": silent, "inactive": inactive, "outsider": outsider}


def _row(grid: dict, user) -> dict | None:
    return next((r for r in grid["items"] if r["bdm"]["id"] == str(user.id)), None)


@pytest.mark.asyncio
async def test_the_grid_shows_seven_days_of_submitted_and_missing_for_active_team_bdms(client, db_session):
    t = await _team(client, db_session)
    response = await client.get(TEAM_REPORTS)
    assert response.status_code == 200, response.text
    grid = response.json()
    today = india_today()
    assert grid["dates"] == [str(today - timedelta(days=n)) for n in range(6, -1, -1)]
    assert grid["total"] == 2 and _row(grid, t["inactive"]) is None and _row(grid, t["outsider"]) is None
    submitter = [d["status"] for d in _row(grid, t["submitter"])["days"]]
    assert submitter == ["missing"] * 5 + ["submitted", "submitted"]
    assert _row(grid, t["submitter"])["days"][-1]["submitted_at"] is not None
    assert [d["status"] for d in _row(grid, t["silent"])["days"]] == ["missing"] * 7
    assert _row(grid, t["silent"])["bdm_type"] == "school"


@pytest.mark.asyncio
async def test_days_before_a_bdms_profile_existed_are_not_started(client, db_session):
    manager = await make_manager(db_session)
    newcomer = await make_bdm(db_session, manager, "college")  # profile created today
    await login(client, manager)
    row = _row((await client.get(TEAM_REPORTS)).json(), newcomer)
    assert [d["status"] for d in row["days"]] == ["not_started"] * 6 + ["missing"]


@pytest.mark.asyncio
async def test_the_grid_ends_on_the_chosen_date_and_refuses_the_future(client, db_session):
    await _team(client, db_session)
    chosen = india_today() - timedelta(days=20)
    grid = (await client.get(TEAM_REPORTS, params={"date": str(chosen)})).json()
    assert grid["dates"][-1] == str(chosen)
    assert (await client.get(TEAM_REPORTS, params={"date": str(india_today() + timedelta(days=1))})).status_code == 422


@pytest.mark.asyncio
async def test_a_manager_reads_a_team_report_but_never_another_teams(client, db_session):
    t = await _team(client, db_session)
    data = (await client.get(team_report_url(t["submitter"].id, india_today()))).json()
    assert (data["status"], data["note"], data["can_submit"]) == ("submitted", "Done", False)
    draft = (await client.get(team_report_url(t["silent"].id, india_today()))).json()
    assert (draft["status"], draft["can_submit"], draft["bdm_type"]) == ("draft", False, "school")
    assert (await client.get(team_report_url(t["outsider"].id, india_today()))).status_code == 404
    assert (await client.get(team_report_url(t["manager"].id, india_today()))).status_code == 404


@pytest.mark.asyncio
async def test_the_manager_comments_on_a_submitted_report_only(client, db_session):
    t = await _team(client, db_session)
    url = f"{team_report_url(t['submitter'].id, india_today())}/comment"
    response = await client.put(url, json={"comment": "  Good coverage.  "})
    assert response.status_code == 200, response.text
    comment = response.json()["manager_comment"]
    assert comment["text"] == "Good coverage." and comment["by"]["id"] == str(t["manager"].id)
    assert (await client.put(url, json={"comment": "Replaced"})).json()["manager_comment"]["text"] == "Replaced"
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "bdm_daily_report.commented", AuditLog.user_id == t["manager"].id))).all()
    assert len(audits) == 2 and all("comment" not in str(a.metadata_json) for a in audits)

    missing = await client.put(f"{team_report_url(t['silent'].id, india_today())}/comment", json={"comment": "Where is it?"})
    assert (missing.status_code, missing.json()["detail"]) == (409, reports.NOT_SUBMITTED)
    assert (await client.put(f"{team_report_url(t['outsider'].id, india_today())}/comment", json={"comment": "x"})).status_code == 404
    assert (await client.put(url, json={"comment": "   "})).status_code == 422
    assert (await client.put(url, json={"comment": "x" * 1001})).status_code == 422

    client.cookies.clear()
    await login(client, t["submitter"])  # the BDM sees the comment and can't write one
    own = (await client.get(f"/api/v1/bdm/daily-reports/{india_today()}")).json()
    assert own["manager_comment"]["text"] == "Replaced"
    assert (await client.put(url, json={"comment": "Me too"})).status_code == 403


@pytest.mark.asyncio
async def test_super_admin_sees_every_team_and_other_roles_are_refused(client, db_session):
    t = await _team(client, db_session)
    client.cookies.clear()
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert (await client.get(team_report_url(t["outsider"].id, india_today()))).status_code == 200
    for role, division in (("bdm", "it"), ("student", "it"), ("it_admin", "it")):
        client.cookies.clear()
        await login(client, await make_user(db_session, role, division))
        assert (await client.get(TEAM_REPORTS)).status_code == 403
