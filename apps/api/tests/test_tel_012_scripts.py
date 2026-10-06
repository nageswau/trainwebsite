"""tel-012 -- call scripts API (spec §6; AC6, AC7; DEC-SCOPE-083 C3). The test database is shared and never truncated, so every
product is created per test and lists are narrowed with `product_id`."""

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.tel012_helpers import NON_READERS, READERS, WRITERS, as_role, product, uname

SCRIPTS = "/api/v1/telecaller/scripts"
STEPS = [{"title": "Introduction", "notes": "Greet and confirm the name"}, {"title": "Explain course", "notes": None}]


async def _create(client, product_id, **body):
    return await client.post(SCRIPTS, json={"product_id": str(product_id), "name": uname("Script"), "steps": STEPS, **body})


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), WRITERS)
async def test_writers_create_and_audit(client, db_session, role, division):
    user = await as_role(client, db_session, role, division)
    prod = await product(db_session)
    response = await _create(client, prod.id, name="  Standard  ", steps=[{"title": " Intro ", "notes": "  "}])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body == {
        "id": body["id"],
        "product": {"id": str(prod.id), "name": prod.name, "group": "it", "active": True},
        "name": "Standard",
        "steps": [{"title": "Intro", "notes": None}],
        "active": True,
    }
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == body["id"]))
    assert (audit.action, audit.user_id, audit.entity_type) == ("telecaller.script_create", user.id, "tel_script")
    assert audit.metadata_json == {"fields": ["name", "product_id", "steps"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("telecaller", "it"), *NON_READERS])
async def test_other_roles_cannot_write(client, db_session, role, division):
    prod = await product(db_session)
    await as_role(client, db_session)
    created = (await _create(client, prod.id)).json()
    await as_role(client, db_session, role, division)
    assert (await _create(client, prod.id)).status_code == 403
    assert (await client.patch(f"{SCRIPTS}/{created['id']}", json={"name": "X"})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), NON_READERS)
async def test_non_readers_cannot_list(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(SCRIPTS)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), READERS)
async def test_readers_list_and_telecallers_see_active_only(client, db_session, role, division):
    prod = await product(db_session)
    await as_role(client, db_session)
    old = (await _create(client, prod.id, name="Old")).json()
    await client.patch(f"{SCRIPTS}/{old['id']}", json={"active": False})
    current = (await _create(client, prod.id, name="Current")).json()
    await as_role(client, db_session, role, division)
    page = (await client.get(SCRIPTS, params={"product_id": str(prod.id)})).json()
    names = [i["name"] for i in page["items"]]
    assert names == (["Current"] if role == "telecaller" else ["Current", "Old"])
    assert page["total"] == len(names) and page["limit"] == 50 and page["offset"] == 0
    if role == "telecaller":
        inactive = (await client.get(SCRIPTS, params={"product_id": str(prod.id), "active": "false"})).json()
        assert inactive["items"] == []
    assert current["id"] in {i["id"] for i in page["items"]}


@pytest.mark.asyncio
async def test_a_deactivated_script_keeps_its_place(client, db_session):
    """QA-04: ordered by product then name whatever the status, so deactivating never moves the row away."""
    prod = await product(db_session)
    await as_role(client, db_session)
    first = (await _create(client, prod.id, name="A first")).json()
    await client.patch(f"{SCRIPTS}/{first['id']}", json={"active": False})
    await _create(client, prod.id, name="B second")
    names = [i["name"] for i in (await client.get(SCRIPTS, params={"product_id": str(prod.id)})).json()["items"]]
    assert names == ["A first", "B second"]


@pytest.mark.asyncio
async def test_one_active_script_per_product(client, db_session):
    """C3 / AC7: a second active script → 409; reactivating or moving into a product that has one → 409."""
    prod, other = await product(db_session), await product(db_session)
    await as_role(client, db_session)
    first = (await _create(client, prod.id)).json()
    second = await _create(client, prod.id)
    assert second.status_code == 409 and second.json()["detail"] == f"{prod.name} already has an active script. Deactivate it first."
    await client.patch(f"{SCRIPTS}/{first['id']}", json={"active": False})
    replacement = (await _create(client, prod.id)).json()
    again = await client.patch(f"{SCRIPTS}/{first['id']}", json={"active": True})
    assert again.status_code == 409
    moved = await client.patch(f"{SCRIPTS}/{(await _create(client, other.id)).json()['id']}", json={"product_id": str(prod.id)})
    assert moved.status_code == 409
    assert (await client.patch(f"{SCRIPTS}/{replacement['id']}", json={"name": "Renamed"})).status_code == 200


@pytest.mark.asyncio
async def test_update_changes_steps_and_audits_fields(client, db_session):
    prod = await product(db_session)
    await as_role(client, db_session)
    created = (await _create(client, prod.id)).json()
    steps = [{"title": "Check availability", "notes": "Weekdays?"}]
    response = await client.patch(f"{SCRIPTS}/{created['id']}", json={"steps": steps, "name": created["name"]})
    assert response.status_code == 200 and response.json()["steps"] == steps
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == created["id"], AuditLog.action == "telecaller.script_update"))
    assert audit.metadata_json == {"fields": ["steps"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "detail"),
    [
        ({"steps": []}, "Add between 1 and 20 steps"),
        ({"steps": [{"title": f"S{i}"} for i in range(21)]}, "Add between 1 and 20 steps"),
        ({"steps": [{"title": "  "}]}, "Every step needs a title"),
        ({"steps": [{"title": "x" * 121}]}, "A step title must be at most 120 characters"),
        ({"steps": [{"title": "A", "notes": "n" * 1001}]}, "Talking points must be at most 1000 characters"),
        ({"steps": [{"title": "A", "extra": 1}]}, "Unknown field: steps"),
        ({"name": ""}, "Name is required"),
        ({"name": "x" * 161}, "Name must be at most 160 characters"),
    ],
)
async def test_validation_sentences(client, db_session, body, detail):
    prod = await product(db_session)
    await as_role(client, db_session)
    response = await _create(client, prod.id, **body)
    assert response.status_code == 422 and response.json()["detail"] == detail


@pytest.mark.asyncio
async def test_inactive_or_missing_product_is_refused(client, db_session):
    prod = await product(db_session, active=False)
    await as_role(client, db_session)
    assert (await _create(client, prod.id)).json()["detail"] == "Choose an active product"
    assert (await client.patch(f"{SCRIPTS}/00000000-0000-0000-0000-000000000000", json={"name": "X"})).status_code == 404
