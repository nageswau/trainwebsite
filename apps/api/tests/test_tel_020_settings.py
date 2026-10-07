"""tel-020 -- GET/PUT /telecaller/settings (API §12AC; DEC-SCOPE-109 AL1, AL11): any telecaller manager or super_admin reads and sets both
teams' alert thresholds; every other role is 403. The two rows are shared by the whole test database, so each test starts from the
defaults (`restore`) and puts them back when it passes."""

import pytest
import pytest_asyncio
from sqlalchemy import select, update

from app.models import TEL_SETTING_DEFAULTS, AuditLog, TelSetting
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager, make_user

URL = "/api/v1/telecaller/settings"


async def reset_settings(db) -> None:
    await db.execute(update(TelSetting).values(**TEL_SETTING_DEFAULTS, updated_by_user_id=None))
    await db.commit()


@pytest_asyncio.fixture
async def restore(db_session):
    await reset_settings(db_session)


@pytest.mark.asyncio
async def test_a_manager_reads_both_teams(client, db_session, restore):
    await as_user(client, await make_tl_manager(db_session))
    response = await client.get(URL)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [(i["team"], i["team_label"]) for i in items] == [("it", "IT"), ("overseas", "Overseas")]
    assert all({"not_contacted_hours", "hot_pending_hours", "updated_at", "updated_by"} <= set(i) for i in items)


@pytest.mark.asyncio
async def test_a_manager_sets_a_team_and_it_is_audited(client, db_session, restore):
    manager = await make_tl_manager(db_session)
    await as_user(client, manager)
    response = await client.put(f"{URL}/overseas", json={"not_contacted_hours": 12, "hot_pending_hours": 2})
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["team"], body["not_contacted_hours"], body["hot_pending_hours"]) == ("overseas", 12, 2)
    assert body["updated_by"] == {"id": str(manager.id), "full_name": manager.full_name}
    row = await db_session.scalar(select(TelSetting).where(TelSetting.team == "overseas").execution_options(populate_existing=True))
    assert (row.not_contacted_hours, row.hot_pending_hours, row.updated_by_user_id) == (12, 2, manager.id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "tel.settings.update", AuditLog.user_id == manager.id))
    assert audit.entity_id == "overseas" and audit.metadata_json == {
        "from": {"not_contacted_hours": 24, "hot_pending_hours": 4}, "to": {"not_contacted_hours": 12, "hot_pending_hours": 2}}
    assert [i["not_contacted_hours"] for i in (await client.get(URL)).json()["items"]] == [24, 12]  # the other team is untouched
    await reset_settings(db_session)


@pytest.mark.asyncio
async def test_super_admin_may_set_and_a_repeat_is_idempotent(client, db_session, restore):
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    for _ in range(2):
        response = await client.put(f"{URL}/it", json={"not_contacted_hours": 48, "hot_pending_hours": 8})
        assert (response.status_code, response.json()["not_contacted_hours"]) == (200, 48)
    await reset_settings(db_session)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "detail"),
    [
        ({"not_contacted_hours": 0, "hot_pending_hours": 4}, "Lead not contacted after (hours): Input should be greater than or equal to 1"),
        ({"not_contacted_hours": 24, "hot_pending_hours": 169}, "Hot lead pending after (hours): Input should be less than or equal to 168"),
        ({"not_contacted_hours": 24}, "Hot lead pending after (hours) is required"),
        ({"not_contacted_hours": 2.5, "hot_pending_hours": 4}, "Lead not contacted after (hours): Input should be a valid integer"),
        ({"not_contacted_hours": "24", "hot_pending_hours": 4}, "Lead not contacted after (hours): Input should be a valid integer"),
        ({"not_contacted_hours": 24, "hot_pending_hours": 4, "team": "it"}, "Unknown field: team"),
    ],
)
async def test_invalid_values_are_422_with_a_readable_sentence(client, db_session, restore, payload, detail):
    await as_user(client, await make_tl_manager(db_session))
    response = await client.put(f"{URL}/it", json=payload)
    assert (response.status_code, response.json()["detail"]) == (422, detail)


@pytest.mark.asyncio
async def test_an_unknown_team_is_404_and_a_non_object_is_422(client, db_session, restore):
    await as_user(client, await make_tl_manager(db_session))
    assert (await client.put(f"{URL}/global", json={"not_contacted_hours": 24, "hot_pending_hours": 4})).status_code == 404
    assert (await client.put(f"{URL}/it", json=[1])).status_code == 422


@pytest.mark.asyncio
async def test_other_roles_are_403_and_anonymous_is_401(client, db_session, restore):
    manager = await make_tl_manager(db_session)
    people = [await make_telecaller(db_session, manager), await make_user(db_session, "counselor", "it"),
              await make_user(db_session, "it_admin", "it"), await make_user(db_session, "it_student", "it")]
    for person in people:
        await as_user(client, person)
        assert (await client.get(URL)).status_code == 403
        assert (await client.put(f"{URL}/it", json={"not_contacted_hours": 1, "hot_pending_hours": 1})).status_code == 403
    client.cookies.clear()
    assert (await client.get(URL)).status_code == 401
