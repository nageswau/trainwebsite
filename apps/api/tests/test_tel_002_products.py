"""tel-002 -- the product/interest catalogue API (spec §4; AC2, AC5, AC6, AC7; DEC-SCOPE-074 P1/P2). The test database is shared and
never truncated, so every name is unique per test and lists are narrowed with `q`."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, Program
from tests.bdm001_helpers import login, make_user

PRODUCTS = "/api/v1/telecaller/products"
READERS = [("telecaller", "it"), ("telecaller_manager", "global"), ("super_admin", "global"), ("it_admin", "it"), ("overseas_admin", "overseas"), ("counselor", "overseas")]
WRITERS = [("telecaller_manager", "global"), ("super_admin", "global")]


def _name(prefix: str = "Prod") -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


async def _as(client, db, role="telecaller_manager", division="global"):
    user = await make_user(db, role, division)
    await login(client, user)
    return user


async def _create(client, **body):
    body.setdefault("group", "other")
    body.setdefault("name", _name())
    return await client.post(PRODUCTS, json=body)


async def _program(db, *, active=True) -> Program:
    program = Program(
        slug=f"p-{uuid.uuid4().hex[:8]}",
        category="it",
        title=_name("Course"),
        summary="s",
        duration="d",
        eligibility="e",
        fees=1,
        certification="c",
        curriculum=[],
        placement_assistance="p",
        trainer_name="t",
        active=active,
    )
    db.add(program)
    await db.commit()
    return program


# --- create ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), WRITERS)
async def test_manager_and_super_admin_create(client, db_session, role, division):
    user = await _as(client, db_session, role, division)
    name = _name()
    response = await _create(client, group="it", name=f"  {name}  ", sort_order=7)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body == {"id": body["id"], "group": "it", "name": name, "team": "it", "program": None, "active": True, "sort_order": 7}
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == body["id"]))
    assert audit.action == "telecaller.product_create" and audit.user_id == user.id and audit.entity_type == "tel_product"


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [r for r in READERS if r not in WRITERS] + [("bdm_manager", "global"), ("it_student", "it")])
async def test_other_roles_cannot_write(client, db_session, role, division):
    """AC5: a telecaller (or any non-manager) POST/PATCH → 403."""
    await _as(client, db_session, role, division)
    assert (await _create(client)).status_code == 403
    seeded = await _seed_product_id(client, db_session, "SAP") if role in dict(READERS) else uuid.uuid4()
    assert (await client.patch(f"{PRODUCTS}/{seeded}", json={"name": "x"})).status_code == 403


async def _seed_product_id(client, db, name):
    from app.models import TelProduct

    return (await db.scalar(select(TelProduct).where(TelProduct.name == name))).id


@pytest.mark.asyncio
async def test_duplicate_name_in_a_group_is_409_case_insensitive(client, db_session):
    await _as(client, db_session)
    name = _name()
    assert (await _create(client, group="it", name=name)).status_code == 201
    duplicate = await _create(client, group="it", name=name.upper())
    assert duplicate.status_code == 409 and "already exists" in duplicate.json()["detail"]
    assert (await _create(client, group="overseas", name=name)).status_code == 201  # another group is fine
    assert (await _create(client, group="it", name="sap")).status_code == 409  # the seed counts too


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"group": "it", "team": "overseas"}, "IT products always route to the IT team"),
        ({"group": "overseas", "team": None}, "Overseas products always route to the Overseas team"),
        ({"group": "global"}, "Group"),
        ({"group": "other", "name": "   "}, "Name is required"),
        ({"group": "other", "name": "x" * 121}, "Name must be at most 120 characters"),
        ({"group": "other", "name": "bad\x07name"}, "Name contains invalid characters"),
        ({"group": "other", "team": "global"}, "Team"),
        ({"group": "other", "colour": "red"}, "Unknown field"),
    ],
)
async def test_create_validation(client, db_session, body, message):
    await _as(client, db_session)
    response = await _create(client, **body)
    assert response.status_code == 422
    assert message in str(response.json()["detail"])


@pytest.mark.asyncio
async def test_without_a_sort_order_a_new_product_goes_to_the_end_of_its_group(client, db_session):
    await _as(client, db_session)
    first = (await _create(client, group="overseas")).json()
    second = (await _create(client, group="overseas")).json()
    assert first["sort_order"] >= 14 and second["sort_order"] == first["sort_order"] + 1


@pytest.mark.asyncio
async def test_other_product_team_is_chosen_or_none(client, db_session):
    """P2/T18: only an Other product's team is editable; none = the unassigned queue."""
    await _as(client, db_session)
    assert (await _create(client, group="other")).json()["team"] is None
    assert (await _create(client, group="other", team="overseas")).json()["team"] == "overseas"


@pytest.mark.asyncio
async def test_course_link_is_it_only_and_must_be_an_active_program(client, db_session):
    await _as(client, db_session)
    program, retired = await _program(db_session), await _program(db_session, active=False)
    linked = await _create(client, group="it", program_id=str(program.id))
    assert linked.status_code == 201 and linked.json()["program"] == {"id": str(program.id), "title": program.title}
    refused = await _create(client, group="overseas", program_id=str(program.id))
    assert refused.status_code == 422 and "Only IT products" in refused.json()["detail"]
    for missing in (retired.id, uuid.uuid4()):
        response = await _create(client, group="it", program_id=str(missing))
        assert response.status_code == 422 and "active course" in response.json()["detail"]


# --- update ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rename_keeps_the_id_and_audits_field_names(client, db_session):
    """AC6: a rename keeps the row (and so every lead link)."""
    user = await _as(client, db_session)
    created = (await _create(client, group="other")).json()
    new_name = _name("Renamed")
    response = await client.patch(f"{PRODUCTS}/{created['id']}", json={"name": new_name, "team": "it", "sort_order": 3})
    assert response.status_code == 200
    assert response.json() | {} == {**created, "name": new_name, "team": "it", "sort_order": 3}
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == created["id"], AuditLog.action == "telecaller.product_update"))).one()
    assert audit.user_id == user.id and sorted(audit.metadata_json["fields"]) == ["name", "sort_order", "team"]


@pytest.mark.asyncio
async def test_update_rules(client, db_session):
    await _as(client, db_session)
    it_product = (await _create(client, group="it")).json()
    url = f"{PRODUCTS}/{it_product['id']}"
    assert (await client.patch(url, json={"team": "overseas"})).status_code == 422
    assert (await client.patch(url, json={"team": "it"})).status_code == 200  # the same team is a no-op
    group = await client.patch(url, json={"group": "overseas"})
    assert group.status_code == 422 and "Group cannot be changed" in group.json()["detail"]
    assert (await client.patch(url, json={"name": None})).status_code == 422
    assert (await client.patch(url, json={"active": None})).status_code == 422
    assert (await client.patch(f"{PRODUCTS}/{uuid.uuid4()}", json={"name": "x"})).status_code == 404
    other = (await _create(client, group="other")).json()
    duplicate = await client.patch(f"{PRODUCTS}/{other['id']}", json={"name": "general enquiry"})
    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_unlink_course_and_deactivate_then_reactivate(client, db_session):
    await _as(client, db_session)
    program = await _program(db_session)
    created = (await _create(client, group="it", program_id=str(program.id))).json()
    url = f"{PRODUCTS}/{created['id']}"
    assert (await client.patch(url, json={"program_id": None})).json()["program"] is None
    assert (await client.patch(url, json={"active": False})).json()["active"] is False
    assert (await client.patch(url, json={"active": True})).json()["active"] is True


# --- reads (P1, AC2) ------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), READERS)
async def test_readers_list_and_non_managers_see_active_only(client, db_session, role, division):
    tag = uuid.uuid4().hex[:8]
    await _as(client, db_session)
    live = (await _create(client, group="it", name=f"Live {tag}")).json()
    gone = (await _create(client, group="it", name=f"Gone {tag}")).json()
    await client.patch(f"{PRODUCTS}/{gone['id']}", json={"active": False})
    await _as(client, db_session, role, division)
    names = lambda body: {r["name"] for r in body["items"]}  # noqa: E731
    everything = (await client.get(PRODUCTS, params={"q": tag})).json()
    asked_inactive = (await client.get(PRODUCTS, params={"q": tag, "active": "false"})).json()
    if role in dict(WRITERS):
        assert names(everything) == {live["name"], gone["name"]}
        assert names(asked_inactive) == {gone["name"]}
    else:
        assert names(everything) == {live["name"]}  # AC2: a deactivated product is gone from pickers
        assert names(asked_inactive) == set()  # an `active` param cannot widen a reader's view


@pytest.mark.asyncio
async def test_list_shape_order_and_group_filter(client, db_session):
    await _as(client, db_session, "telecaller", "it")
    body = (await client.get(PRODUCTS, params={"limit": 100})).json()
    assert set(body) == {"items", "total", "limit", "offset"}
    groups = [r["group"] for r in body["items"]]
    assert groups == sorted(groups, key=["it", "overseas", "other"].index)
    seed = ["Digital Marketing", "SAP", "Cyber Security", "Python Full Stack", "Java"]
    assert [r["name"] for r in body["items"] if r["name"] in seed] == seed  # the §3 order (sort_order) within a group
    overseas = (await client.get(PRODUCTS, params={"group": "overseas", "limit": 100})).json()
    assert overseas["items"] and {r["group"] for r in overseas["items"]} == {"overseas"}
    assert (await client.get(PRODUCTS, params={"group": "global"})).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("bdm", "it"), ("it_student", "it"), ("agent", "overseas")])
async def test_other_roles_cannot_read(client, db_session, role, division):
    await _as(client, db_session, role, division)
    assert (await client.get(PRODUCTS)).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(PRODUCTS)).status_code == 401
