"""AGN-023 follow-up -- GET /lookups/overseas-counselors: the Overseas Admin's type-ahead behind the Assign counsellor picker."""

import pytest

from app.models import User
from tests.agn001_helpers import login, mk_user, uniq

URL = "/api/v1/lookups/overseas-counselors"


async def admin_client(client, db_session):
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)


@pytest.mark.asyncio
async def test_finds_an_older_counselor_by_name_even_with_over_500_newer_users(client, db_session):
    tag = uniq("c23")
    old = await mk_user(db_session, role="counselor", full_name=f"{tag} Old Hand")
    db_session.add_all([
        User(email=f"{uniq('newer')}-{i}@example.local", password_hash="x", full_name=f"Newer {i}", role="counselor", division="overseas", profile={})
        for i in range(501)
    ])
    await db_session.commit()
    await admin_client(client, db_session)
    response = await client.get(URL, params={"q": tag})
    assert response.status_code == 200, response.text
    assert response.json() == {"items": [{"id": str(old.id), "label": old.full_name, "detail": None}], "truncated": False}


@pytest.mark.asyncio
async def test_excludes_inactive_it_and_non_counselor_users(client, db_session):
    tag = uniq("c23")
    ok = await mk_user(db_session, role="counselor", full_name=f"{tag} Active")
    await mk_user(db_session, role="counselor", full_name=f"{tag} Inactive", active=False)
    await mk_user(db_session, role="counselor", division="it", full_name=f"{tag} IT")
    await mk_user(db_session, role="overseas_student", full_name=f"{tag} Student")
    await admin_client(client, db_session)
    items = (await client.get(URL, params={"q": tag})).json()["items"]
    assert [item["id"] for item in items] == [str(ok.id)]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["counselor", "agent", "university_rep", "overseas_student"])
async def test_other_roles_are_refused(client, db_session, role):
    user = await mk_user(db_session, role=role)
    await login(client, user.email)
    response = await client.get(URL)
    assert response.status_code == 403
    assert response.json()["detail"] == "This role cannot use this lookup"


@pytest.mark.asyncio
async def test_an_admin_outside_the_overseas_division_is_refused(client, db_session):
    admin = await mk_user(db_session, role="overseas_admin", division="it")
    await login(client, admin.email, division="it")
    response = await client.get(URL)
    assert response.status_code == 403
    assert response.json()["detail"] == "Wrong EduSphere division"


@pytest.mark.asyncio
async def test_super_admin_may_use_the_lookup(client, db_session):  # documented in 12M: the shared _allow admits super_admin
    tag = uniq("c23")
    counselor = await mk_user(db_session, role="counselor", full_name=f"{tag} Seen")
    boss = await mk_user(db_session, role="super_admin")
    await login(client, boss.email)
    response = await client.get(URL, params={"q": tag})
    assert response.status_code == 200, response.text
    assert [item["id"] for item in response.json()["items"]] == [str(counselor.id)]


@pytest.mark.asyncio
async def test_truncated_when_more_than_limit_match_and_ordered_by_name(client, db_session):
    tag = uniq("c23")
    for i in range(3):
        await mk_user(db_session, role="counselor", full_name=f"{tag} C{i}")
    await admin_client(client, db_session)
    body = (await client.get(URL, params={"q": tag, "limit": 2})).json()
    assert body["truncated"] is True
    assert [item["label"] for item in body["items"]] == [f"{tag} C0", f"{tag} C1"]
    assert (await client.get(URL, params={"q": tag, "limit": 3})).json()["truncated"] is False


@pytest.mark.asyncio
async def test_payload_has_name_and_id_only(client, db_session):
    tag = uniq("c23")
    counselor = await mk_user(db_session, role="counselor", full_name=f"{tag} Name")
    await admin_client(client, db_session)
    response = await client.get(URL, params={"q": tag})
    assert counselor.email not in response.text
    assert set(response.json()["items"][0]) == {"id", "label", "detail"}


@pytest.mark.asyncio
async def test_empty_q_returns_a_first_page_and_limit_is_validated(client, db_session):
    await mk_user(db_session, role="counselor", full_name="Aaa first page")
    await admin_client(client, db_session)
    assert (await client.get(URL)).status_code == 200
    assert (await client.get(URL, params={"limit": 0})).status_code == 422
    assert (await client.get(URL, params={"limit": 51})).status_code == 422
    assert (await client.get(URL, params={"q": "x" * 101})).status_code == 422


@pytest.mark.asyncio
async def test_empty_q_returns_rows_in_alphabetical_order(client, db_session):
    tag = uniq("c23")
    for suffix in ("c", "a", "b"):  # created out of order
        await mk_user(db_session, role="counselor", full_name=f"AAA {tag} {suffix}")
    await admin_client(client, db_session)
    items = (await client.get(URL, params={"limit": 50})).json()["items"]
    assert [item["label"] for item in items if tag in item["label"]] == [f"AAA {tag} {s}" for s in "abc"]
