"""rec-006 -- the Skills Master API (spec §4; AC2-AC6). The test database is shared and never truncated, so every name is unique per test
and lists are narrowed with `q`. The 0102 seed (Java, React, ...) is read but never edited here."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter

CATS, SKILLS = "/api/v1/recruiter/skill-categories", "/api/v1/recruiter/skills"


def _n(prefix: str = "Sk") -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


async def _manager(client, db):
    manager = await make_pm(db)
    await login(client, manager)
    return manager


async def _category(client, name: str | None = None) -> dict:
    response = await client.post(CATS, json={"name": name or _n("Cat")})
    assert response.status_code == 201, response.text
    return response.json()


async def _skill(client, category_id, name: str | None = None, **extra) -> dict:
    response = await client.post(SKILLS, json={"name": name or _n(), "category_id": category_id, **extra})
    assert response.status_code == 201, response.text
    return response.json()


async def _audits(db, entity_id) -> list[AuditLog]:
    return (await db.scalars(select(AuditLog).where(AuditLog.entity_id == str(entity_id)).order_by(AuditLog.created_at))).all()


# --- categories -----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_creates_renames_and_deactivates_a_category(client, db_session):
    await _manager(client, db_session)
    name = _n("Cat")
    created = await _category(client, name)
    assert created["name"] == name and created["active"] is True and created["sort_order"] > 5
    response = await client.patch(f"{CATS}/{created['id']}", json={"name": f"{name} X", "active": False})
    assert response.status_code == 200, response.text
    assert response.json() == {**created, "name": f"{name} X", "active": False}
    actions = [a.action for a in await _audits(db_session, created["id"])]
    assert actions == ["recruiter.skill_category_create", "recruiter.skill_category_update"]


@pytest.mark.asyncio
async def test_duplicate_category_name_in_any_case_is_409_and_seed_reads_in_source_order(client, db_session):
    await _manager(client, db_session)
    assert (await client.post(CATS, json={"name": "  programming "})).status_code == 409
    page = (await client.get(CATS, params={"limit": 5})).json()
    assert [c["name"] for c in page["items"]] == ["Programming", "Java Technologies", "Frontend", "Database", "Cloud/DevOps"]


@pytest.mark.asyncio
async def test_a_noop_patch_writes_no_audit_and_unknown_category_is_404(client, db_session):
    await _manager(client, db_session)
    created = await _category(client)
    assert (await client.patch(f"{CATS}/{created['id']}", json={"name": created["name"]})).status_code == 200
    assert len(await _audits(db_session, created["id"])) == 1
    assert (await client.patch(f"{CATS}/{uuid.uuid4()}", json={"active": False})).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(("body", "message"), [
    ({"name": "   "}, "Name is required"),
    ({"name": "x" * 81}, "Name must be at most 80 characters"),
    ({"name": "a\x07b"}, "Name contains invalid characters"),
    ({"name": "ok", "extra": 1}, "Unknown field: extra"),
])
async def test_category_body_errors_are_one_readable_sentence(client, db_session, body, message):
    await _manager(client, db_session)
    response = await client.post(CATS, json=body)
    assert response.status_code == 422 and response.json()["detail"] == message


# --- skills -----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_creates_a_skill_with_a_tag_and_reads_it_back(client, db_session):
    await _manager(client, db_session)
    primary, tag = await _category(client), await _category(client)
    created = await _skill(client, primary["id"], tag_category_ids=[tag["id"]])
    assert created["category"]["id"] == primary["id"]
    assert [t["id"] for t in created["tags"]] == [tag["id"]]
    assert created["aliases"] == [] and created["related"] == []
    one = await client.get(f"{SKILLS}/{created['id']}")
    assert one.status_code == 200 and one.json() == created
    assert [a.action for a in await _audits(db_session, created["id"])] == ["recruiter.skill_create"]


@pytest.mark.asyncio
async def test_seeded_javascript_reads_with_its_frontend_tag_and_category_filter_covers_tags(client, db_session):
    """AC1 via the API; `category_id` matches the primary category or a tag."""
    await _manager(client, db_session)
    js = (await client.get(SKILLS, params={"q": "javascript"})).json()["items"][0]
    assert js["category"]["name"] == "Programming" and [t["name"] for t in js["tags"]] == ["Frontend"]
    frontend = js["tags"][0]["id"]
    names = [s["name"] for s in (await client.get(SKILLS, params={"category_id": frontend, "limit": 100})).json()["items"]]
    assert {"JavaScript", "HTML", "React"} <= set(names)


@pytest.mark.asyncio
async def test_search_matches_an_alias_without_duplicating_the_skill(client, db_session):
    """AC2: `q` matches a name or an alias (React has three aliases containing "react")."""
    await _manager(client, db_session)
    page = (await client.get(SKILLS, params={"q": "reactjs"})).json()
    assert [s["name"] for s in page["items"]] == ["React"] and page["total"] == 1
    react = (await client.get(SKILLS, params={"q": "react"})).json()
    assert [s["name"] for s in react["items"]].count("React") == 1


@pytest.mark.asyncio
async def test_skill_name_conflicts(client, db_session):
    """AC3: a duplicate name (any case) or a name equal to an existing alias → 409."""
    await _manager(client, db_session)
    category = await _category(client)
    assert (await client.post(SKILLS, json={"name": "java", "category_id": category["id"]})).status_code == 409
    response = await client.post(SKILLS, json={"name": "  j2ee ", "category_id": category["id"]})
    assert response.status_code == 409 and "already an alias" in response.json()["detail"]


@pytest.mark.asyncio
async def test_rename_keeps_the_id_and_cannot_take_an_alias(client, db_session):
    """AC6 rename; review focus 2."""
    await _manager(client, db_session)
    category = await _category(client)
    skill = await _skill(client, category["id"])
    alias = _n("Al")
    assert (await client.post(f"{SKILLS}/{skill['id']}/aliases", json={"alias": alias})).status_code == 201
    assert (await client.patch(f"{SKILLS}/{skill['id']}", json={"name": alias.upper()})).status_code == 409
    assert (await client.patch(f"{SKILLS}/{skill['id']}", json={"name": "React JS"})).status_code == 409
    renamed = await client.patch(f"{SKILLS}/{skill['id']}", json={"name": f"{skill['name']} 2"})
    assert renamed.status_code == 200 and renamed.json()["id"] == skill["id"]


@pytest.mark.asyncio
async def test_patch_replaces_tags_and_checks_categories(client, db_session):
    await _manager(client, db_session)
    a, b, c = await _category(client), await _category(client), await _category(client)
    skill = await _skill(client, a["id"], tag_category_ids=[b["id"]])
    response = await client.patch(f"{SKILLS}/{skill['id']}", json={"tag_category_ids": [c["id"]]})
    assert [t["id"] for t in response.json()["tags"]] == [c["id"]]
    assert (await client.patch(f"{SKILLS}/{skill['id']}", json={"tag_category_ids": [a["id"]]})).json()["detail"] == "A skill's own category cannot also be a tag"
    await client.patch(f"{CATS}/{b['id']}", json={"active": False})
    assert (await client.patch(f"{SKILLS}/{skill['id']}", json={"category_id": b["id"]})).json()["detail"] == "Choose an active category"
    assert (await client.patch(f"{SKILLS}/{skill['id']}", json={"tag_category_ids": [c["id"], c["id"]]})).json()["detail"] == "Other categories must not repeat"
    assert (await client.patch(f"{SKILLS}/{skill['id']}", json={"category_id": "nope"})).json()["detail"] == "Choose a category from the list"
    cleared = await client.patch(f"{SKILLS}/{skill['id']}", json={"tag_category_ids": []})
    assert cleared.status_code == 200 and cleared.json()["tags"] == []


@pytest.mark.asyncio
async def test_a_skill_keeps_a_since_deactivated_category(client, db_session):
    await _manager(client, db_session)
    category = await _category(client)
    skill = await _skill(client, category["id"])
    await client.patch(f"{CATS}/{category['id']}", json={"active": False})
    response = await client.patch(f"{SKILLS}/{skill['id']}", json={"category_id": category["id"], "name": f"{skill['name']} b"})
    assert response.status_code == 200 and response.json()["category"]["active"] is False


@pytest.mark.asyncio
async def test_deleting_a_skill_or_category_is_not_allowed(client, db_session):
    await _manager(client, db_session)
    category = await _category(client)
    skill = await _skill(client, category["id"])
    assert (await client.delete(f"{SKILLS}/{skill['id']}")).status_code == 405
    assert (await client.delete(f"{CATS}/{category['id']}")).status_code == 405


# --- aliases ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_add_an_alias_and_it_resolves_then_remove_it(client, db_session):
    """AC4 (the backlog's "Java 21" is already seeded, so a new version stands in)."""
    await _manager(client, db_session)
    category = await _category(client)
    skill = await _skill(client, category["id"])
    alias = _n("Java")
    response = await client.post(f"{SKILLS}/{skill['id']}/aliases", json={"alias": f"  {alias}  "})
    assert response.status_code == 201, response.text
    [added] = response.json()["aliases"]
    assert added["alias"] == alias
    found = (await client.get(SKILLS, params={"q": alias.lower()})).json()["items"]
    assert [s["id"] for s in found] == [skill["id"]]
    assert (await client.delete(f"{SKILLS}/{skill['id']}/aliases/{added['id']}")).status_code == 204
    assert (await client.get(f"{SKILLS}/{skill['id']}")).json()["aliases"] == []
    audits = await _audits(db_session, skill["id"])
    assert [a.action for a in audits][-2:] == ["recruiter.skill_alias_add", "recruiter.skill_alias_remove"]
    assert audits[-1].metadata_json == {"alias": alias}


@pytest.mark.asyncio
@pytest.mark.parametrize(("alias", "status"), [("J2EE", 409), ("  core   JAVA ", 409), ("reactjs", 409), ("React", 409)])
async def test_alias_conflicts(client, db_session, alias, status):
    """AC3 + review focus 1: a duplicate alias, or an alias equal to another skill's name, in any case or spacing."""
    await _manager(client, db_session)
    category = await _category(client)
    skill = await _skill(client, category["id"])
    assert (await client.post(f"{SKILLS}/{skill['id']}/aliases", json={"alias": alias})).status_code == status


@pytest.mark.asyncio
async def test_alias_equal_to_its_own_name_is_422_and_unknowns_are_404(client, db_session):
    await _manager(client, db_session)
    category = await _category(client)
    skill = await _skill(client, category["id"])
    own = await client.post(f"{SKILLS}/{skill['id']}/aliases", json={"alias": skill["name"].lower()})
    assert own.status_code == 422 and own.json()["detail"] == "An alias cannot repeat the skill's name"
    assert (await client.post(f"{SKILLS}/{uuid.uuid4()}/aliases", json={"alias": _n()})).status_code == 404
    assert (await client.delete(f"{SKILLS}/{skill['id']}/aliases/{uuid.uuid4()}")).status_code == 404
    java = (await client.get(SKILLS, params={"q": "j2se"})).json()["items"][0]
    j2se = next(a for a in java["aliases"] if a["alias"] == "J2SE")
    assert (await client.delete(f"{SKILLS}/{skill['id']}/aliases/{j2se['id']}")).status_code == 404  # another skill's alias


@pytest.mark.asyncio
async def test_a_deactivated_skills_aliases_stay_reserved(client, db_session):
    """Review focus 3."""
    await _manager(client, db_session)
    category = await _category(client)
    first, second = await _skill(client, category["id"]), await _skill(client, category["id"])
    alias = _n("Al")
    await client.post(f"{SKILLS}/{first['id']}/aliases", json={"alias": alias})
    await client.patch(f"{SKILLS}/{first['id']}", json={"active": False})
    assert (await client.post(f"{SKILLS}/{second['id']}/aliases", json={"alias": alias})).status_code == 409


# --- related skills -------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_relate_two_skills_reads_both_ways_and_unrelate(client, db_session):
    await _manager(client, db_session)
    category = await _category(client)
    a, b = await _skill(client, category["id"]), await _skill(client, category["id"])
    response = await client.post(f"{SKILLS}/{a['id']}/related", json={"skill_id": b["id"]})
    assert response.status_code == 201 and [r["id"] for r in response.json()["related"]] == [b["id"]]
    assert [r["id"] for r in (await client.get(f"{SKILLS}/{b['id']}")).json()["related"]] == [a["id"]]
    assert (await client.post(f"{SKILLS}/{b['id']}/related", json={"skill_id": a["id"]})).status_code == 409
    assert (await client.delete(f"{SKILLS}/{b['id']}/related/{a['id']}")).status_code == 204
    assert (await client.get(f"{SKILLS}/{a['id']}")).json()["related"] == []
    assert (await client.delete(f"{SKILLS}/{b['id']}/related/{a['id']}")).status_code == 404
    actions = [x.action for x in await _audits(db_session, a["id"])]
    assert "recruiter.skill_related_add" in actions


@pytest.mark.asyncio
async def test_related_rules(client, db_session):
    await _manager(client, db_session)
    category = await _category(client)
    a, b = await _skill(client, category["id"]), await _skill(client, category["id"])
    assert (await client.post(f"{SKILLS}/{a['id']}/related", json={"skill_id": a["id"]})).json()["detail"] == "A skill cannot be related to itself"
    await client.patch(f"{SKILLS}/{b['id']}", json={"active": False})
    assert (await client.post(f"{SKILLS}/{a['id']}/related", json={"skill_id": b["id"]})).json()["detail"] == "Choose an active skill"
    assert (await client.post(f"{SKILLS}/{a['id']}/related", json={"skill_id": str(uuid.uuid4())})).status_code == 422


@pytest.mark.asyncio
async def test_seeded_java_is_related_to_core_java(client, db_session):
    await _manager(client, db_session)
    java = next(s for s in (await client.get(SKILLS, params={"q": "java", "limit": 100})).json()["items"] if s["name"] == "Java")
    assert [r["name"] for r in java["related"]] == ["Core Java"]


# --- roles (AC5) and the reader view (AC6) -----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recruiter_reads_active_rows_only_and_cannot_write(client, db_session):
    await _manager(client, db_session)
    category = await _category(client)
    live, gone = await _skill(client, category["id"]), await _skill(client, category["id"])
    await client.post(f"{SKILLS}/{live['id']}/related", json={"skill_id": gone["id"]})
    await client.patch(f"{SKILLS}/{gone['id']}", json={"active": False})
    hidden = await _category(client)
    await client.patch(f"{CATS}/{hidden['id']}", json={"active": False})
    await login(client, await make_recruiter(db_session, await make_pm(db_session)))
    page = (await client.get(SKILLS, params={"category_id": category["id"], "active": "false"})).json()
    assert [s["id"] for s in page["items"]] == [live["id"]]
    assert page["items"][0]["related"] == []  # the inactive related skill is hidden too
    assert (await client.get(f"{SKILLS}/{gone['id']}")).status_code == 404
    cats = (await client.get(CATS, params={"q": hidden["name"], "active": "false"})).json()
    assert cats["items"] == []
    for method, url, body in (
        ("post", CATS, {"name": _n()}),
        ("patch", f"{CATS}/{category['id']}", {"active": False}),
        ("post", SKILLS, {"name": _n(), "category_id": category["id"]}),
        ("patch", f"{SKILLS}/{live['id']}", {"active": False}),
        ("post", f"{SKILLS}/{live['id']}/aliases", {"alias": _n()}),
        ("post", f"{SKILLS}/{live['id']}/related", {"skill_id": gone["id"]}),
    ):
        response = await client.request(method.upper(), url, json=body)
        assert response.status_code == 403, (method, url, response.text)


@pytest.mark.asyncio
async def test_manager_sees_inactive_rows(client, db_session):
    await _manager(client, db_session)
    category = await _category(client)
    gone = await _skill(client, category["id"])
    await client.patch(f"{SKILLS}/{gone['id']}", json={"active": False})
    page = (await client.get(SKILLS, params={"category_id": category["id"]})).json()
    assert [s["active"] for s in page["items"]] == [False]
    only_active = (await client.get(SKILLS, params={"category_id": category["id"], "active": "true"})).json()
    assert only_active["items"] == []


@pytest.mark.asyncio
async def test_super_admin_writes(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.post(CATS, json={"name": _n("Cat")})).status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("hr_team", "it"), ("it_admin", "it"), ("counselor", "it"), ("it_student", "it"), ("telecaller_manager", "global")])
async def test_other_roles_cannot_read_or_write(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(SKILLS)).status_code == 403
    assert (await client.get(CATS)).status_code == 403
    assert (await client.post(CATS, json={"name": _n()})).status_code == 403


@pytest.mark.asyncio
async def test_a_recruiter_without_a_profile_still_reads(client, db_session):
    """The catalogue is not scoped to a profile: a placement_team user created by the generic Users form reads it."""
    await as_role(client, db_session, "placement_team", "it")
    assert (await client.get(SKILLS, params={"q": "python"})).status_code == 200


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(SKILLS)).status_code == 401

