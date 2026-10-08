"""upc-003 -- the Global University Master API (spec §3; AC1, AC4, N1, E1, R1)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, UniversityAssignmentHistory
from tests.upc003_helpers import (
    BASE,
    as_role,
    catalogue_country,
    create,
    internal_country,
    login,
    make_application,
    make_head,
    make_pm,
    make_user,
    payload,
    url,
)


async def _head_with_team(client, db):
    head = await make_head(db)
    pm, pm2 = await make_pm(db, head), await make_pm(db, head)
    await login(client, head)
    return head, pm, pm2


# --- create (AC1, UM8, N1) ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_head_creates_an_internal_university_with_every_master_field(client, db_session):
    await _head_with_team(client, db_session)
    country = await catalogue_country(db_session)
    sent = payload(country.id)
    response = await client.post(BASE, json=sent)
    assert response.status_code == 201, response.text
    body = response.json()["university"]
    assert body["university_code"].startswith("UNV-") and len(body["university_code"]) == 10
    assert body["catalogue_visible"] is False and body["active"] is True
    assert body["slug"].startswith("abc-university-")
    assert body["website"] == "https://abc.ac.uk"
    for key in (
        "name",
        "city",
        "institution_type",
        "ownership_type",
        "state_region",
        "course_levels",
        "popular_programs",
        "international_office",
        "existing_relationship",
        "priority",
        "partnership_potential",
    ):
        assert body[key] == sent[key], key
    assert body["country"]["id"] == str(country.id) and body["country"]["iso2"] == "GB" and body["country"]["region"] == "UK"
    assert [(r["system"], r["other_name"], r["year"], r["rank"]) for r in body["rankings"]] == [("Other", "Guardian", 2025, "201-250"), ("QS", None, 2026, "145")]
    assert body["primary_manager"] is None and body["application_count"] == 0
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == body["id"], AuditLog.action == "university.create"))
    assert audit.metadata_json["code"] == body["university_code"] and "name" not in audit.metadata_json


@pytest.mark.asyncio
async def test_a_university_may_sit_in_an_internal_country(client, db_session):
    await as_role(client, db_session, "overseas_admin", "overseas")
    body = await create(client, (await internal_country(db_session)).id)
    assert body["country"]["iso2"] == "JP"


@pytest.mark.asyncio
async def test_same_name_gets_a_distinct_slug(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    country = await catalogue_country(db_session)
    name = f"Twin University {uuid.uuid4().hex[:6]}"
    # upc-004: the same name + country is a duplicate, so the second one is a super_admin override
    first, second = await create(client, country.id, name=name), await create(client, country.id, name=name, duplicate_reason="A separate campus, same name")
    assert first["slug"] != second["slug"] and second["slug"].endswith(second["university_code"].lower())


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("partnership_manager", "overseas"), ("counselor", "overseas"), ("it_admin", "it"), ("agent", "overseas")])
async def test_other_roles_cannot_create(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.post(BASE, json=payload((await catalogue_country(db_session)).id))).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "override",
    [
        {"institution_type": "school"},
        {"website": "javascript:alert(1)"},
        {"priority": "D"},
        {"course_levels": ["Masters"]},
        {"rankings": [{"system": "Other", "year": 2026, "rank": "1"}]},
        {"rankings": [{"system": "QS", "other_name": "X", "year": 2026, "rank": "1"}]},
        {"rankings": [{"system": "QS", "year": 2026, "rank": "1"}, {"system": "QS", "year": 2026, "rank": "2"}]},
        {"rankings": [{"system": "QS", "year": 1800, "rank": "1"}]},
        {"name": "   "},
        {"unknown": 1},
    ],
)
async def test_invalid_input_is_422(client, db_session, override):
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.post(BASE, json=payload((await catalogue_country(db_session)).id, **override))).status_code == 422


@pytest.mark.asyncio
async def test_unknown_country_is_422(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    response = await client.post(BASE, json=payload(uuid.uuid4()))
    assert response.status_code == 422 and response.json()["detail"] == "Unknown country"


# --- reads ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_reads_every_university_and_filters_narrow_the_list(client, db_session):
    head, pm, _ = await _head_with_team(client, db_session)
    country = await catalogue_country(db_session)
    tag = uuid.uuid4().hex[:8]
    owned = await create(client, country.id, name=f"Owned {tag}", priority="B")
    other = await create(client, country.id, name=f"Unowned {tag}", priority="C")
    assert (await client.post(url(owned["id"], "assign"), json={"primary_manager_user_id": str(pm.id)})).status_code == 200
    await login(client, pm)
    page = (await client.get(BASE, params={"q": tag})).json()
    assert page["total"] == 2 and [i["name"] for i in page["items"]] == [f"Owned {tag}", f"Unowned {tag}"]
    assert page["items"][0]["permissions"]["can_edit"] is True and page["items"][1]["permissions"]["can_edit"] is False
    assert (await client.get(BASE, params={"q": tag, "manager": "me"})).json()["total"] == 1
    assert [i["id"] for i in (await client.get(BASE, params={"q": tag, "manager": "none"})).json()["items"]] == [other["id"]]
    assert (await client.get(BASE, params={"q": tag, "priority": "C"})).json()["total"] == 1
    assert (await client.get(BASE, params={"q": other["university_code"]})).json()["total"] == 1
    assert (await client.get(BASE, params={"q": tag, "visibility": "public"})).json()["total"] == 0
    assert (await client.get(BASE, params={"q": tag, "region": "UK", "limit": 1})).json()["limit"] == 1
    assert (await client.get(url(other["id"]))).json()["university"]["id"] == other["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "overseas"), ("university_rep", "overseas"), ("bdm", "overseas"), ("it_admin", "it")])
async def test_other_roles_cannot_read(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(BASE)).status_code == 403


@pytest.mark.asyncio
async def test_manager_without_profile_is_403_and_unknown_id_is_404(client, db_session):
    await as_role(client, db_session, "partnership_manager", "overseas")
    assert (await client.get(BASE)).status_code == 403
    await as_role(client, db_session, "overseas_admin", "overseas")
    assert (await client.get(url(uuid.uuid4()))).status_code == 404


# --- edit (AC1, AC4, UM4, UM9) ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_primary_and_backup_edit_a_non_owner_manager_gets_403(client, db_session):
    head, pm, pm2 = await _head_with_team(client, db_session)
    outsider = await make_pm(db_session, await make_head(db_session))
    uni = await create(client, (await catalogue_country(db_session)).id)
    await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id), "backup_manager_user_id": str(pm2.id)})
    for manager, city in ((pm, "Leeds"), (pm2, "York")):
        await login(client, manager)
        response = await client.patch(url(uni["id"]), json={"city": city})
        assert response.status_code == 200 and response.json()["university"]["city"] == city
    await login(client, outsider)
    refused = await client.patch(url(uni["id"]), json={"city": "Hull"})
    assert refused.status_code == 403 and refused.json()["detail"] == "Only the university's partnership managers can edit it"


@pytest.mark.asyncio
async def test_patch_changes_only_sent_fields_replaces_rankings_and_audits_names(client, db_session):
    await as_role(client, db_session, "overseas_admin", "overseas")
    uni = await create(client, (await catalogue_country(db_session)).id)
    response = await client.patch(url(uni["id"]), json={"priority": "C", "rankings": [{"system": "THE", "year": 2026, "rank": "90"}], "overview": "Research led"})
    body = response.json()["university"]
    assert body["priority"] == "C" and body["overview"] == "Research led" and body["name"] == uni["name"]
    assert [(r["system"], r["rank"]) for r in body["rankings"]] == [("THE", "90")]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == uni["id"], AuditLog.action == "university.update"))
    assert audit.metadata_json == {"fields": ["overview", "priority", "rankings"]}
    again = await client.patch(url(uni["id"]), json={"priority": "C"})
    assert again.status_code == 200
    count = len((await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == uni["id"], AuditLog.action == "university.update"))).all())
    assert count == 1  # an equal value is not a change


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"name": None}, {"country_id": None}, {"institution_type": None}, {"slug": "x"}, {"university_code": "UNV-1"}, {"catalogue_visible": True}])
async def test_patch_refuses_nulls_on_required_fields_and_server_owned_keys(client, db_session, body):
    await as_role(client, db_session, "super_admin", "global")
    uni = await create(client, (await catalogue_country(db_session)).id)
    assert (await client.patch(url(uni["id"]), json=body)).status_code == 422


@pytest.mark.asyncio
async def test_head_edits_unowned_and_team_rows_but_not_another_teams(client, db_session):
    head, pm, _ = await _head_with_team(client, db_session)
    other_head = await make_head(db_session)
    other_pm = await make_pm(db_session, other_head)
    country = await catalogue_country(db_session)
    mine, unowned = await create(client, country.id), await create(client, country.id)
    await client.post(url(mine["id"], "assign"), json={"primary_manager_user_id": str(pm.id)})
    await login(client, other_head)
    theirs = await create(client, country.id)
    await client.post(url(theirs["id"], "assign"), json={"primary_manager_user_id": str(other_pm.id)})
    await login(client, head)
    assert (await client.patch(url(mine["id"]), json={"priority": "B"})).status_code == 200
    assert (await client.patch(url(unowned["id"]), json={"priority": "B"})).status_code == 200
    assert (await client.patch(url(theirs["id"]), json={"priority": "B"})).status_code == 403


# --- assign (UM3, R1) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_head_assigns_team_members_and_history_records_each_slot(client, db_session):
    head, pm, pm2 = await _head_with_team(client, db_session)
    uni = await create(client, (await catalogue_country(db_session)).id)
    response = await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id), "backup_manager_user_id": str(pm2.id)})
    body = response.json()["university"]
    assert body["primary_manager"]["id"] == str(pm.id) and body["backup_manager"]["id"] == str(pm2.id)
    swapped = await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm2.id), "backup_manager_user_id": None})
    assert swapped.status_code == 200 and swapped.json()["university"]["backup_manager"] is None
    rows = (
        await db_session.scalars(
            select(UniversityAssignmentHistory)
            .where(UniversityAssignmentHistory.university_id == uuid.UUID(uni["id"]))
            .order_by(UniversityAssignmentHistory.created_at, UniversityAssignmentHistory.slot.desc())
        )
    ).all()
    assert [(r.slot, r.from_user_id, r.to_user_id) for r in rows] == [("primary", None, pm.id), ("backup", None, pm2.id), ("primary", pm.id, pm2.id), ("backup", pm2.id, None)]
    assert all(r.actor_user_id == head.id for r in rows)


@pytest.mark.asyncio
async def test_assign_refusals(client, db_session):
    head, pm, pm2 = await _head_with_team(client, db_session)
    stranger = await make_pm(db_session, await make_head(db_session))
    inactive = await make_pm(db_session, head, active=False)
    uni = await create(client, (await catalogue_country(db_session)).id)
    invalid = "Choose an active partnership manager from your team"
    for body in ({"primary_manager_user_id": str(stranger.id)}, {"primary_manager_user_id": str(inactive.id)}, {"primary_manager_user_id": str(head.id)}):
        response = await client.post(url(uni["id"], "assign"), json=body)
        assert response.status_code == 422 and response.json()["detail"] == invalid
    assert (await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id), "backup_manager_user_id": str(pm.id)})).status_code == 422
    assert (await client.post(url(uni["id"], "assign"), json={"backup_manager_user_id": str(pm.id)})).status_code == 422
    for role, division in (("overseas_admin", "overseas"),):
        await as_role(client, db_session, role, division)
        assert (await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id)})).status_code == 403
    await login(client, pm)
    assert (await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id)})).status_code == 403


@pytest.mark.asyncio
async def test_super_admin_assigns_any_active_manager_and_manager_options_follow_the_team(client, db_session):
    head, pm, _ = await _head_with_team(client, db_session)
    inactive = await make_pm(db_session, head, active=False)
    options = (await client.get(f"{BASE}/manager-options", params={"limit": 50})).json()
    ids = {o["id"] for o in options["items"]}
    assert str(pm.id) in ids and str(inactive.id) not in ids
    stranger = await make_pm(db_session, await make_head(db_session))
    assert str(stranger.id) not in ids
    await as_role(client, db_session, "super_admin", "global")
    uni = await create(client, (await catalogue_country(db_session)).id)
    assert (await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(stranger.id)})).status_code == 200
    await login(client, pm)
    assert (await client.get(f"{BASE}/manager-options")).status_code == 403


# --- publish / deactivate (UM5, UM6, UM10, E1) ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_publish_rules(client, db_session):
    await as_role(client, db_session, "overseas_admin", "overseas")
    bare = await create(client, (await catalogue_country(db_session)).id)
    refused = await client.post(url(bare["id"], "publish"))
    assert refused.status_code == 422 and refused.json()["detail"] == "Add an overview before publishing"
    internal = await create(client, (await internal_country(db_session)).id, overview="Text")
    refused = await client.post(url(internal["id"], "publish"))
    assert refused.status_code == 422 and "country" in refused.json()["detail"]
    await client.patch(url(bare["id"]), json={"overview": "A leading university"})
    published = await client.post(url(bare["id"], "publish"))
    assert published.status_code == 200 and published.json()["university"]["catalogue_visible"] is True
    assert (await client.post(url(bare["id"], "publish"))).status_code == 409
    assert (await client.post(url(bare["id"], "unpublish"))).json()["university"]["catalogue_visible"] is False
    assert (await client.post(url(bare["id"], "unpublish"))).status_code == 409


@pytest.mark.asyncio
async def test_managers_cannot_publish_or_deactivate(client, db_session):
    head, pm, _ = await _head_with_team(client, db_session)
    uni = await create(client, (await catalogue_country(db_session)).id, overview="Text")
    await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id)})
    await login(client, pm)
    for action in ("publish", "deactivate"):
        assert (await client.post(url(uni["id"], action), json={})).status_code == 403


@pytest.mark.asyncio
async def test_deactivate_warns_about_applications_unpublishes_and_reactivates(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    uni = await create(client, (await catalogue_country(db_session)).id, overview="Text")
    await client.post(url(uni["id"], "publish"))
    await make_application(db_session, uuid.UUID(uni["id"]))
    warned = await client.post(url(uni["id"], "deactivate"), json={})
    assert warned.status_code == 409 and warned.json()["detail"]["code"] == "has_applications" and warned.json()["detail"]["count"] == 1
    done = (await client.post(url(uni["id"], "deactivate"), json={"confirm": True})).json()["university"]
    assert done["active"] is False and done["catalogue_visible"] is False and done["application_count"] == 1
    assert (await client.patch(url(uni["id"]), json={"city": "Bath"})).status_code == 409
    assert (await client.post(url(uni["id"], "publish"))).status_code == 409
    back = (await client.post(url(uni["id"], "reactivate"))).json()["university"]
    assert back["active"] is True and back["catalogue_visible"] is False
    assert (await client.post(url(uni["id"], "reactivate"))).status_code == 409


@pytest.mark.asyncio
async def test_list_hides_inactive_unless_asked(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    tag = uuid.uuid4().hex[:8]
    uni = await create(client, (await catalogue_country(db_session)).id, name=f"Closed {tag}")
    await client.post(url(uni["id"], "deactivate"), json={})
    assert (await client.get(BASE, params={"q": tag})).json()["total"] == 0
    assert (await client.get(BASE, params={"q": tag, "include_inactive": True})).json()["total"] == 1


@pytest.mark.asyncio
async def test_existing_catalogue_row_is_editable_and_keeps_its_slug(client, db_session):
    user = await make_user(db_session, "super_admin", "global")
    await login(client, user)
    legacy = await client.post("/api/v1/admin/universities", json={"country_slug": "united-kingdom", "slug": f"legacy-{uuid.uuid4().hex[:8]}", "name": "Legacy U", "city": "Bath"})
    assert legacy.status_code == 201
    body = (await client.get(url(legacy.json()["id"]))).json()["university"]
    assert body["catalogue_visible"] is True and body["university_code"].startswith("UNV-") and body["institution_type"] == "university"
    # unique: the shared database keeps every earlier run's rows, and upc-004 refuses a rename into an existing name
    edited = (await client.patch(url(body["id"]), json={"name": f"Legacy University {uuid.uuid4().hex[:8]}"})).json()["university"]
    assert edited["slug"] == legacy.json()["slug"]
