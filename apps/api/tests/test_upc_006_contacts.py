"""upc-006 -- university contacts + relationship strength (spec §3; AC1-AC3, P1, N1, E1, R1)."""

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, make_pm, make_user, url

ROLES_URL = "/api/v1/partnership/contact-roles"


def contacts_url(university_id) -> str:
    return url(university_id, "contacts")


def contact_url(contact_id) -> str:
    return f"/api/v1/partnership/contacts/{contact_id}"


async def _owned(client, db):
    """A head creates a university and makes `pm` its primary manager; returns (head, pm, other_pm, university)."""
    head = await make_head(db)
    pm, other = await make_pm(db, head), await make_pm(db, head)
    await login(client, head)
    uni = await create(client, (await catalogue_country(db)).id)
    response = await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id)})
    assert response.status_code == 200, response.text
    return head, pm, other, uni


def contact(**overrides) -> dict:
    body = {
        "name": "Priya Raman",
        "designation": "Regional Manager – India",
        "department": "International Office",
        "role_code": "regional_manager",
        "email": "Priya.Raman@abc.ac.uk",
        "phone": "+44 20 7000 0000",
        "whatsapp": "+91 98450 00000",
        "linkedin": "linkedin.com/in/priya-raman",
        "preferred_channel": "whatsapp",
        "relationship_strength": "strategic",
        "notes": "Met at the Delhi fair.\nPrefers mornings.",
        "shareable": True,
    }
    body.update(overrides)
    return body


async def add(client, university_id, **overrides) -> dict:
    response = await client.post(contacts_url(university_id), json=contact(**overrides))
    assert response.status_code == 201, response.text
    return response.json()["contact"]


# --- university relationship strength (AC2, CT11) ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_university_relationship_strength_is_set_by_hand_and_filterable(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    assert uni["relationship_strength"] is None
    await login(client, pm)
    response = await client.patch(url(uni["id"]), json={"relationship_strength": "at_risk"})
    assert response.status_code == 200, response.text
    assert response.json()["university"]["relationship_strength"] == "at_risk"
    listed = (await client.get("/api/v1/partnership/universities", params={"relationship_strength": "at_risk", "manager": "me"})).json()
    assert [u["id"] for u in listed["items"]] == [uni["id"]] and listed["items"][0]["relationship_strength"] == "at_risk"
    assert (await client.get("/api/v1/partnership/universities", params={"relationship_strength": "strong", "manager": "me"})).json()["total"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["New", "great", "at risk", ""])
async def test_relationship_values_are_exactly_the_seven_of_section_11(client, db_session, value):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    assert (await client.patch(url(uni["id"]), json={"relationship_strength": value})).status_code == 422
    assert (await client.post(contacts_url(uni["id"]), json=contact(relationship_strength=value))).status_code == 422


@pytest.mark.asyncio
async def test_relationship_strength_can_be_set_at_create(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    body = await create(client, (await catalogue_country(db_session)).id, relationship_strength="developing")
    assert body["relationship_strength"] == "developing"


# --- permissions (CT5) -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_can_edit_contacts_follows_the_edit_scope_without_overseas_admin(client, db_session):
    head, pm, other, uni = await _owned(client, db_session)
    assert (await client.get(url(uni["id"]))).json()["university"]["permissions"]["can_edit_contacts"] is True  # head, team row
    await login(client, pm)
    assert (await client.get(url(uni["id"]))).json()["university"]["permissions"]["can_edit_contacts"] is True
    await login(client, other)
    assert (await client.get(url(uni["id"]))).json()["university"]["permissions"]["can_edit_contacts"] is False
    await as_role(client, db_session, "overseas_admin", "overseas")
    perms = (await client.get(url(uni["id"]))).json()["university"]["permissions"]
    assert perms["can_edit"] is True and perms["can_edit_contacts"] is False


# --- roles catalogue (CT2) ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_contact_roles_are_the_seeded_catalogue(client, db_session):
    await as_role(client, db_session, "partnership_head", "global")
    body = (await client.get(ROLES_URL)).json()
    assert body["items"][0] == {"code": "international_director", "label": "International Director"}
    assert len(body["items"]) == 12 and {"code": "country_manager", "label": "Country Manager"} in body["items"]


@pytest.mark.asyncio
async def test_contact_roles_need_master_access(client, db_session):
    await as_role(client, db_session, "counselor", "overseas")
    assert (await client.get(ROLES_URL)).status_code == 403


# --- create + list (AC1, P1) -----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_owner_adds_regional_manager_india_with_every_field(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    body = await add(client, uni["id"])
    assert body["name"] == "Priya Raman" and body["designation"] == "Regional Manager – India"
    assert body["role"] == {"code": "regional_manager", "label": "Regional Manager"}
    assert body["email"] == "priya.raman@abc.ac.uk" and body["linkedin"] == "https://linkedin.com/in/priya-raman"
    assert body["whatsapp"] == "+91 98450 00000" and body["preferred_channel"] == "whatsapp"
    assert body["relationship_strength"] == "strategic" and body["notes"] == "Met at the Delhi fair.\nPrefers mornings."
    assert body["is_primary"] is True and body["shareable"] is True  # the first contact becomes primary (CT6)
    assert body["university_id"] == uni["id"]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == body["id"], AuditLog.action == "university_contact.create"))
    assert audit.metadata_json["university_id"] == uni["id"]
    assert "Priya" not in str(audit.metadata_json) and "abc.ac.uk" not in str(audit.metadata_json)  # ids and field names only


@pytest.mark.asyncio
async def test_seven_contacts_one_primary_listed_primary_first(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    names = ["Zara", "Yusuf", "Xavier", "Wendy", "Victor", "Uma", "Tariq"]
    for n in names:
        await add(client, uni["id"], name=n, email=f"{n.lower()}@abc.ac.uk", role_code=None)
    page = (await client.get(contacts_url(uni["id"]))).json()
    assert page["total"] == 7 and page["limit"] == 50 and page["offset"] == 0
    assert [c["name"] for c in page["items"]] == ["Zara", *sorted(names[1:])]
    assert sum(c["is_primary"] for c in page["items"]) == 1


@pytest.mark.asyncio
async def test_making_another_contact_primary_moves_the_flag(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    first = await add(client, uni["id"], email="a@abc.ac.uk")
    second = await add(client, uni["id"], name="Ben", email="b@abc.ac.uk", is_primary=True)
    assert second["is_primary"] is True
    items = (await client.get(contacts_url(uni["id"]))).json()["items"]
    assert [(c["id"], c["is_primary"]) for c in items] == [(second["id"], True), (first["id"], False)]
    response = await client.patch(contact_url(first["id"]), json={"is_primary": True})
    assert response.status_code == 200 and response.json()["contact"]["is_primary"] is True
    assert [c["id"] for c in (await client.get(contacts_url(uni["id"]))).json()["items"] if c["is_primary"]] == [first["id"]]


@pytest.mark.asyncio
async def test_the_primary_cannot_be_unset_directly(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    first = await add(client, uni["id"])
    response = await client.patch(contact_url(first["id"]), json={"is_primary": False})
    assert response.status_code == 422 and "another contact primary" in response.text


# --- validation (N1) -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "not-an-email"},
        {"phone": "call me"},
        {"whatsapp": "abc"},
        {"linkedin": "javascript:alert(1)"},
        {"role_code": "ceo"},
        {"preferred_channel": "fax"},
        {"name": "  "},
        {"name": "x" * 201},
        {"notes": "x" * 2001},
        {"is_primary": "yes"},
        {"unknown": 1},
    ],
)
async def test_invalid_contact_input_is_a_422(client, db_session, overrides):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    assert (await client.post(contacts_url(uni["id"]), json=contact(**overrides))).status_code == 422


@pytest.mark.asyncio
async def test_invalid_email_on_patch_is_a_422(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    first = await add(client, uni["id"])
    assert (await client.patch(contact_url(first["id"]), json={"email": "bad@"})).status_code == 422
    assert (await client.patch(contact_url(first["id"]), json={"name": None})).status_code == 422


# --- duplicates and the two-universities edge case (E1, CT8) -------------------------------------------------------------
@pytest.mark.asyncio
async def test_same_email_twice_at_one_university_is_a_409_but_two_universities_are_two_rows(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    await login(client, head)
    other_uni = await create(client, (await catalogue_country(db_session)).id)
    await add(client, uni["id"], email="shared@agency.com")
    response = await client.post(contacts_url(uni["id"]), json=contact(name="Again", email="SHARED@agency.com"))
    assert response.status_code == 409
    assert (await add(client, other_uni["id"], email="shared@agency.com"))["university_id"] == other_uni["id"]


@pytest.mark.asyncio
async def test_a_university_holds_at_most_fifty_contacts(client, db_session):
    head, _, _, uni = await _owned(client, db_session)
    for i in range(50):
        await add(client, uni["id"], name=f"C{i}", email=None, notes=None)
    assert (await client.post(contacts_url(uni["id"]), json=contact(email=None))).status_code == 409


# --- PATCH -----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_changes_only_sent_fields_and_skips_audit_for_no_change(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    first = await add(client, uni["id"])
    response = await client.patch(contact_url(first["id"]), json={"phone": None, "relationship_strength": "dormant", "name": "Priya Raman"})
    assert response.status_code == 200, response.text
    body = response.json()["contact"]
    assert body["phone"] is None and body["relationship_strength"] == "dormant" and body["email"] == first["email"]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == first["id"], AuditLog.action == "university_contact.update"))
    assert audit.metadata_json["fields"] == ["phone", "relationship_strength"]
    assert (await client.patch(contact_url(first["id"]), json={"phone": None})).status_code == 200
    updates = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == first["id"], AuditLog.action == "university_contact.update"))).all()
    assert len(updates) == 1


# --- delete (CT7) ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_rules(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    first = await add(client, uni["id"], email="a@abc.ac.uk")
    second = await add(client, uni["id"], name="Ben", email="b@abc.ac.uk")
    assert (await client.delete(contact_url(first["id"]))).status_code == 409  # the primary, with another contact left
    assert (await client.delete(contact_url(second["id"]))).status_code == 204
    assert (await client.delete(contact_url(first["id"]))).status_code == 204  # the last one may go
    assert (await client.get(contacts_url(uni["id"]))).json()["total"] == 0
    assert await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == first["id"], AuditLog.action == "university_contact.delete"))


# --- access and scope (AC3, R1) ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_overseas_admin_reads_shareable_contacts_only_without_notes_and_cannot_write(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    shared = await add(client, uni["id"], email="s@abc.ac.uk", shareable=True)
    private = await add(client, uni["id"], name="Internal", email="i@abc.ac.uk", shareable=False)
    await as_role(client, db_session, "overseas_admin", "overseas")
    page = (await client.get(contacts_url(uni["id"]))).json()
    assert [c["id"] for c in page["items"]] == [shared["id"]] and page["total"] == 1
    assert page["items"][0]["notes"] is None and page["items"][0]["email"] == "s@abc.ac.uk"
    assert (await client.post(contacts_url(uni["id"]), json=contact(email="x@abc.ac.uk"))).status_code == 403
    assert (await client.patch(contact_url(shared["id"]), json={"phone": None})).status_code == 403
    assert (await client.delete(contact_url(private["id"]))).status_code == 403


@pytest.mark.asyncio
async def test_non_owner_manager_reads_but_cannot_write(client, db_session):
    _, pm, other, uni = await _owned(client, db_session)
    await login(client, pm)
    first = await add(client, uni["id"])
    await login(client, other)
    page = (await client.get(contacts_url(uni["id"]))).json()
    assert page["total"] == 1 and page["items"][0]["notes"] is not None  # partnership roles read every contact (management visibility)
    assert (await client.post(contacts_url(uni["id"]), json=contact(email="o@abc.ac.uk"))).status_code == 403
    assert (await client.patch(contact_url(first["id"]), json={"phone": None})).status_code == 403
    assert (await client.delete(contact_url(first["id"]))).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "overseas"), ("bdm", "overseas"), ("overseas_student", "overseas")])
async def test_other_roles_have_no_contact_access(client, db_session, role, division):
    _, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    first = await add(client, uni["id"])
    user = await make_user(db_session, role, division)
    await login(client, user)
    assert (await client.get(contacts_url(uni["id"]))).status_code == 403
    assert (await client.patch(contact_url(first["id"]), json={"phone": None})).status_code == 403


@pytest.mark.asyncio
async def test_inactive_university_contacts_are_read_only(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    await login(client, pm)
    first = await add(client, uni["id"])
    await login(client, head)
    assert (await client.post(url(uni["id"], "deactivate"), json={})).status_code == 200
    assert (await client.post(contacts_url(uni["id"]), json=contact(email="n@abc.ac.uk"))).status_code == 409
    assert (await client.patch(contact_url(first["id"]), json={"phone": None})).status_code == 409
    assert (await client.get(contacts_url(uni["id"]))).json()["total"] == 1


@pytest.mark.asyncio
async def test_unknown_ids_are_404(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.get(contacts_url(missing))).status_code == 404
    assert (await client.post(contacts_url(missing), json=contact())).status_code == 404
    assert (await client.patch(contact_url(missing), json={"phone": None})).status_code == 404
    assert (await client.delete(contact_url(missing))).status_code == 404
