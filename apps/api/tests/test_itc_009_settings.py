"""itc-009 (DEC-SCOPE-342; API §12IN) -- `escalate_after_hours` on GET/PUT /telecaller/settings: whole hours 0-168, 0 = off. The key is
optional on PUT so a two-field client (tel-020) keeps working and keeps the stored value."""

import pytest
from sqlalchemy import select

from app.models import AuditLog, TelSetting
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager
from tests.test_tel_020_settings import URL, restore  # noqa: F401 -- fixture

BASE = {"not_contacted_hours": 24, "hot_pending_hours": 4}


async def stored(db, team: str) -> int:
    row = await db.scalar(select(TelSetting).where(TelSetting.team == team).execution_options(populate_existing=True))
    return row.escalate_after_hours


@pytest.mark.asyncio
async def test_get_lists_the_escalation_hours_off_by_default(client, db_session, restore):  # noqa: F811
    await as_user(client, await make_tl_manager(db_session))
    items = (await client.get(URL)).json()["items"]
    assert [i["escalate_after_hours"] for i in items] == [0, 0]


@pytest.mark.asyncio
async def test_put_sets_the_hours_and_audits_them(client, db_session, restore):  # noqa: F811
    manager = await make_tl_manager(db_session)
    await as_user(client, manager)
    response = await client.put(f"{URL}/it", json=BASE | {"escalate_after_hours": 24})
    assert (response.status_code, response.json()["escalate_after_hours"]) == (200, 24), response.text
    assert await stored(db_session, "it") == 24 and await stored(db_session, "overseas") == 0
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "tel.settings.update", AuditLog.user_id == manager.id))
    assert (audit.metadata_json["from"]["escalate_after_hours"], audit.metadata_json["to"]["escalate_after_hours"]) == (0, 24)


@pytest.mark.asyncio
async def test_a_two_field_put_keeps_the_stored_hours(client, db_session, restore):  # noqa: F811
    await as_user(client, await make_tl_manager(db_session))
    await client.put(f"{URL}/it", json=BASE | {"escalate_after_hours": 12})
    response = await client.put(f"{URL}/it", json={"not_contacted_hours": 30, "hot_pending_hours": 4})
    assert (response.status_code, response.json()["escalate_after_hours"], response.json()["not_contacted_hours"]) == (200, 12, 30)


@pytest.mark.asyncio
async def test_zero_is_accepted_and_turns_it_off(client, db_session, restore):  # noqa: F811
    await as_user(client, await make_tl_manager(db_session))
    await client.put(f"{URL}/it", json=BASE | {"escalate_after_hours": 12})
    response = await client.put(f"{URL}/it", json=BASE | {"escalate_after_hours": 0})
    assert (response.status_code, await stored(db_session, "it")) == (200, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "detail"),
    [
        (169, "Escalate overdue follow-ups after (hours): Input should be less than or equal to 168"),
        (-1, "Escalate overdue follow-ups after (hours): Input should be greater than or equal to 0"),
        ("24", "Escalate overdue follow-ups after (hours): Input should be a valid integer"),
        (1.5, "Escalate overdue follow-ups after (hours): Input should be a valid integer"),
        (None, "Escalate overdue follow-ups after (hours) is required"),  # _parse renders null as missing
    ],
)
async def test_invalid_hours_are_422_with_a_readable_sentence(client, db_session, restore, value, detail):  # noqa: F811
    await as_user(client, await make_tl_manager(db_session))
    response = await client.put(f"{URL}/it", json=BASE | {"escalate_after_hours": value})
    assert (response.status_code, response.json()["detail"]) == (422, detail)


@pytest.mark.asyncio
async def test_a_telecaller_cannot_set_the_hours(client, db_session, restore):  # noqa: F811
    await as_user(client, await make_telecaller(db_session, await make_tl_manager(db_session)))
    response = await client.put(f"{URL}/it", json=BASE | {"escalate_after_hours": 1})
    assert response.status_code == 403
    assert await stored(db_session, "it") == 0
