"""ENH-031 (DEC-SCOPE-039 D4) -- pick a school, then search only that school's students."""

import uuid

import pytest

from tests.agn001_helpers import login, mk_active_org, mk_user, uniq
from tests.enh016_helpers import make_school, make_student

SCHOOLS = "/api/v1/lookups/schools"
STUDENTS = "/api/v1/lookups/school-students"


@pytest.mark.asyncio
async def test_schools_match_name_or_code_with_code_detail(client, db_session):
    tag = uniq("e31")
    code = f"E3{uuid.uuid4().hex[:6].upper()}"
    ctx = await make_school(db_session, name=f"{tag} Hill School", school_code=code)
    await db_session.commit()
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    by_name = (await client.get(SCHOOLS, params={"q": tag})).json()["items"]
    by_code = (await client.get(SCHOOLS, params={"q": code.lower()})).json()["items"]
    expected = [{"id": str(ctx["school"].id), "label": f"{tag} Hill School", "detail": code}]
    assert by_name == expected and by_code == expected


@pytest.mark.asyncio
async def test_school_students_only_from_the_chosen_school(client, db_session):
    tag = uniq("e31")
    here = await make_school(db_session)
    there = await make_school(db_session)
    kid = await make_student(db_session, here, name=f"{tag} Kid", grade_or_class="Grade 5")
    await make_student(db_session, there, name=f"{tag} Other Kid")
    await db_session.commit()
    counselor = await mk_user(db_session, role="counselor")
    await login(client, counselor.email)
    items = (await client.get(STUDENTS, params={"school_id": str(here["school"].id), "q": tag})).json()["items"]
    assert items == [{"id": str(kid.id), "label": f"{tag} Kid", "detail": f"Grade 5 · {kid.student_code}"}]


@pytest.mark.asyncio
async def test_school_students_match_student_code(client, db_session):
    here = await make_school(db_session)
    kid = await make_student(db_session, here)
    await db_session.commit()
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    items = (await client.get(STUDENTS, params={"school_id": str(here["school"].id), "q": kid.student_code.lower()})).json()["items"]
    assert [i["id"] for i in items] == [str(kid.id)]


@pytest.mark.asyncio
async def test_school_id_is_required_and_must_exist(client, db_session):
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    assert (await client.get(STUDENTS)).status_code == 422
    missing = await client.get(STUDENTS, params={"school_id": str(uuid.uuid4())})
    assert missing.status_code == 404 and missing.json()["detail"] == "School not found"


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [SCHOOLS, STUDENTS])
@pytest.mark.parametrize("role, division", [("university_rep", "overseas"), ("overseas_student", "overseas"), ("it_admin", "it")])
async def test_bridge_lookups_refuse_other_roles(client, db_session, url, role, division):
    user = await mk_user(db_session, role=role, division=division)
    await login(client, user.email, division)
    response = await client.get(url, params={"school_id": str(uuid.uuid4())})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_bridge_lookups_refuse_agents(client, db_session):
    a = await mk_active_org(db_session)
    await login(client, a["master"].email)
    assert (await client.get(SCHOOLS)).status_code == 403
