"""ENH-031 (DEC-SCOPE-039) -- GET /lookups/overseas-students: scope per role, the agent link rules, q/limit, logging."""

import logging

import pytest
from sqlalchemy import func, select

from app.models import AgentStudent, AuditLog
from tests.agn001_helpers import login, mk_active_org, mk_user, register_agent, uniq
from tests.enh031_helpers import mk_application, mk_university

URL = "/api/v1/lookups/overseas-students"


async def students(db, tag: str, n: int) -> list:
    return [await mk_user(db, role="overseas_student", full_name=f"{tag} Student {i:02d}") for i in range(n)]


def ids(response) -> set[str]:
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


@pytest.mark.asyncio
async def test_admin_sees_every_overseas_student_matching_q_and_nobody_else(client, db_session):
    tag = uniq("e31")
    a, b = await students(db_session, tag, 2)
    await mk_user(db_session, role="counselor", full_name=f"{tag} Counselor")
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    assert ids(await client.get(URL, params={"q": tag})) == {str(a.id), str(b.id)}


@pytest.mark.asyncio
async def test_item_is_name_with_email_detail(client, db_session):
    tag = uniq("e31")
    (a,) = await students(db_session, tag, 1)
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    response = await client.get(URL, params={"q": tag})
    assert response.json() == {"items": [{"id": str(a.id), "label": a.full_name, "detail": a.email}], "truncated": False}


@pytest.mark.asyncio
async def test_counselor_sees_only_students_on_own_applications(client, db_session):
    tag = uniq("e31")
    mine, other = await students(db_session, tag, 2)
    counselor = await mk_user(db_session, role="counselor")
    university = await mk_university(db_session)
    await mk_application(db_session, student=mine, university=university, counselor=counselor)
    await mk_application(db_session, student=other, university=university)
    await login(client, counselor.email)
    assert ids(await client.get(URL, params={"q": tag})) == {str(mine.id)}


@pytest.mark.asyncio
async def test_agent_sees_only_students_linked_to_its_agency(client, db_session):
    tag = uniq("e31")
    mine, theirs = await students(db_session, tag, 2)
    a = await mk_active_org(db_session, name=f"{tag} A")
    b = await mk_active_org(db_session, name=f"{tag} B")
    db_session.add_all([AgentStudent(agent_id=a["master"].id, student_id=mine.id), AgentStudent(agent_id=b["master"].id, student_id=theirs.id)])
    await db_session.commit()
    await login(client, a["master"].email)
    assert ids(await client.get(URL, params={"q": tag})) == {str(mine.id)}


@pytest.mark.asyncio
@pytest.mark.parametrize("q", [None, "ab", "  ab  "])
async def test_link_needs_three_characters(client, db_session, q):
    a = await mk_active_org(db_session)
    await login(client, a["master"].email)
    params = {"purpose": "link"} | ({"q": q} if q is not None else {})
    assert (await client.get(URL, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_link_masks_email_and_excludes_only_own_agency_links(client, db_session):
    tag = uniq("e31")
    linked_here, linked_elsewhere, free = await students(db_session, tag, 3)
    a = await mk_active_org(db_session, name=f"{tag} A")
    b = await mk_active_org(db_session, name=f"{tag} B")
    db_session.add_all([AgentStudent(agent_id=a["master"].id, student_id=linked_here.id), AgentStudent(agent_id=b["master"].id, student_id=linked_elsewhere.id)])
    await db_session.commit()
    await login(client, a["master"].email)
    items = (await client.get(URL, params={"purpose": "link", "q": tag})).json()["items"]
    assert {i["id"] for i in items} == {str(linked_elsewhere.id), str(free.id)}
    by_id = {i["id"]: i for i in items}
    assert by_id[str(free.id)]["detail"] == f"{free.email[0]}***@example.local"


@pytest.mark.asyncio
async def test_link_returns_at_most_ten(client, db_session):
    tag = uniq("e31")
    await students(db_session, tag, 12)
    a = await mk_active_org(db_session)
    await login(client, a["master"].email)
    body = (await client.get(URL, params={"purpose": "link", "q": tag, "limit": 50})).json()
    assert len(body["items"]) == 10 and body["truncated"] is True


@pytest.mark.asyncio
async def test_link_matches_an_email_only_when_typed_in_full(client, db_session):
    """Owner decision after the final review (2026-09-30): no probing emails by substring."""
    tag = uniq("e31")
    (student,) = await students(db_session, tag, 1)
    a = await mk_active_org(db_session)
    await login(client, a["master"].email)
    partial = (await client.get(URL, params={"purpose": "link", "q": student.email.split("@")[0]})).json()["items"]
    full = (await client.get(URL, params={"purpose": "link", "q": student.email.upper()})).json()["items"]
    assert str(student.id) not in {i["id"] for i in partial}
    assert [i["id"] for i in full] == [str(student.id)]


@pytest.mark.asyncio
async def test_link_matches_names_by_word_prefix_only(client, db_session):
    tag = uniq("e31")
    student = await mk_user(db_session, role="overseas_student", full_name=f"Aarav {tag}")
    a = await mk_active_org(db_session)
    await login(client, a["master"].email)
    by_word_prefix = (await client.get(URL, params={"purpose": "link", "q": tag[:9]})).json()["items"]
    by_first_name = (await client.get(URL, params={"purpose": "link", "q": "aara"})).json()["items"]
    mid_word = (await client.get(URL, params={"purpose": "link", "q": tag[2:9]})).json()["items"]
    assert str(student.id) in {i["id"] for i in by_word_prefix}
    assert str(student.id) in {i["id"] for i in by_first_name}
    assert str(student.id) not in {i["id"] for i in mid_word}


@pytest.mark.asyncio
async def test_link_search_is_rate_limited_per_agent(client, db_session):
    a = await mk_active_org(db_session, name=uniq("E31 A"))
    b = await mk_active_org(db_session, name=uniq("E31 B"))
    await login(client, a["master"].email)
    for _ in range(30):
        assert (await client.get(URL, params={"purpose": "link", "q": "zzz"})).status_code == 200
    limited = await client.get(URL, params={"purpose": "link", "q": "zzz"})
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) >= 1
    await login(client, b["master"].email)
    assert (await client.get(URL, params={"purpose": "link", "q": "zzz"})).status_code == 200


@pytest.mark.asyncio
async def test_link_search_audits_the_attempt_without_the_text(client, db_session):
    a = await mk_active_org(db_session)
    await login(client, a["master"].email)
    secret = uniq("probe")
    await client.get(URL, params={"purpose": "link", "q": secret})
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.user_id == a["master"].id, AuditLog.action == "lookup.agent_link_search"))).all()
    assert len(rows) == 1
    assert secret not in str(rows[0].metadata_json)


@pytest.mark.asyncio
async def test_link_is_for_agents_only(client, db_session):
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    response = await client.get(URL, params={"purpose": "link", "q": "abc"})
    assert response.status_code == 403
    assert response.json()["detail"] == "This role cannot use this lookup"


@pytest.mark.asyncio
@pytest.mark.parametrize("role, division", [("university_rep", "overseas"), ("overseas_student", "overseas"), ("it_student", "it"), ("placement_team", "it")])
async def test_other_roles_are_refused(client, db_session, role, division):
    user = await mk_user(db_session, role=role, division=division)
    await login(client, user.email, division)
    response = await client.get(URL, params={"q": "abc"})
    assert response.status_code == 403
    assert response.json()["detail"] == "This role cannot use this lookup"


@pytest.mark.asyncio
async def test_pending_agent_is_refused_by_the_agent_gate(client):
    await register_agent(client)
    response = await client.get(URL, params={"q": "abc"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Agent registration is pending approval"


@pytest.mark.asyncio
async def test_q_is_matched_literally(client, db_session):
    tag = uniq("e31")
    await mk_user(db_session, role="overseas_student", full_name=f"{tag} 1000 Plain")
    percent = await mk_user(db_session, role="overseas_student", full_name=f"{tag} 100% Sure")
    underscore = await mk_user(db_session, role="overseas_student", full_name=f"{tag} a_b")
    await mk_user(db_session, role="overseas_student", full_name=f"{tag} axb")
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    assert ids(await client.get(URL, params={"q": f"{tag} 100%"})) == {str(percent.id)}
    assert ids(await client.get(URL, params={"q": f"{tag} a_b"})) == {str(underscore.id)}


@pytest.mark.asyncio
async def test_limit_and_truncated(client, db_session):
    tag = uniq("e31")
    await students(db_session, tag, 3)
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    two = (await client.get(URL, params={"q": tag, "limit": 2})).json()
    three = (await client.get(URL, params={"q": tag, "limit": 3})).json()
    assert (len(two["items"]), two["truncated"]) == (2, True)
    assert (len(three["items"]), three["truncated"]) == (3, False)
    assert [i["label"] for i in three["items"]] == sorted(i["label"] for i in three["items"])


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 51}, {"q": "x" * 101}, {"purpose": "browse"}])
async def test_bad_query_parameters_are_422(client, db_session, params):
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    assert (await client.get(URL, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_lookup_logs_counts_never_the_text_and_writes_no_audit_row(client, db_session, caplog):
    tag = uniq("e31")
    await students(db_session, tag, 1)
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    audit_before = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.user_id == admin.id))
    # alembic/env.py's fileConfig() disables loggers that already exist; an earlier migration test leaves this one off
    # (the ENH-013/016/018/024 precedent).
    logging.getLogger("app.lookups").disabled = False
    caplog.set_level(logging.INFO, logger="app.lookups")
    await client.get(URL, params={"q": tag})
    records = [r for r in caplog.records if r.name == "app.lookups"]
    assert records and records[-1].getMessage() == "lookup"
    assert records[-1].extra_fields == {"lookup": "overseas-students", "role": "overseas_admin", "count": 1, "truncated": False}
    assert tag not in caplog.text
    audit_after = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.user_id == admin.id))
    assert audit_after == audit_before
