"""ccrm-043 (DEC-SCOPE-317) -- GET /counselor/students lists ALL the counselor's students (csc-001 link ∪ the students of the counselor's
applications), not archived, each once, with how the student arrived (`source`), the student's application count and since when the
counselor has had them; `source` and `q` narrow the list."""

import pytest
import pytest_asyncio

from app.models import AgentStudent, OverseasApplication, OverseasStudentArchive, OverseasStudentCounselor
from tests.agn001_helpers import login, mk_user, uniq
from tests.enh031_helpers import mk_application, mk_university

URL = "/api/v1/counselor/students"


@pytest_asyncio.fixture
async def world(db_session):
    counselor = await mk_user(db_session, role="counselor", full_name="Nora Counselor")
    other = await mk_user(db_session, role="counselor", full_name="Omar Counselor")
    agent = await mk_user(db_session, role="agent", full_name="Agency Master")
    tag = uniq("c43")

    async def student(label: str, source: str | None) -> object:
        return await mk_user(db_session, role="overseas_student", full_name=f"{tag} {label}", profile={"registration_source": source} if source else {})

    walk_in = await student("Walk-in", "counselor_walk_in")
    converted = await student("Converted", "lead_conversion")
    self_reg = await student("Self", "self_service")
    legacy = await student("Legacy", None)
    agency = await student("Agency", "self_service")
    theirs = await student("Theirs", "self_service")
    archived = await student("Archived", "counselor_walk_in")
    for linked in (walk_in, converted, archived):
        db_session.add(OverseasStudentCounselor(student_user_id=linked.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    db_session.add(OverseasStudentArchive(student_user_id=archived.id, archived_by_user_id=counselor.id, reason="Done"))
    db_session.add(AgentStudent(agent_id=agent.id, student_id=agency.id, status="active"))
    self_reg.phone = "+91 98765-43210"
    await db_session.commit()
    uni = await mk_university(db_session)
    await mk_application(db_session, student=walk_in, university=uni, counselor=counselor)  # linked AND an application: listed once
    await mk_application(db_session, student=self_reg, university=uni, counselor=counselor)
    await mk_application(db_session, student=self_reg, university=await mk_university(db_session), counselor=other)  # counted, not mine
    await mk_application(db_session, student=legacy, university=uni, counselor=counselor)
    await mk_application(db_session, student=agency, university=uni, counselor=counselor, agent=agent)
    await mk_application(db_session, student=theirs, university=uni, counselor=other)
    return {"counselor": counselor, "other": other, "tag": tag, "walk_in": walk_in, "converted": converted, "self": self_reg, "legacy": legacy,
            "agency": agency, "theirs": theirs, "archived": archived, "uni": uni}  # fmt: skip


async def listed(client, world, **params) -> dict:
    await login(client, world["counselor"].email)
    response = await client.get(URL, params={"limit": 50, **params})
    assert response.status_code == 200, response.text
    return {item["full_name"].removeprefix(f"{world['tag']} "): item for item in response.json()["items"]}


@pytest.mark.asyncio
async def test_every_student_of_mine_is_listed_once_with_its_source_ac1_to_ac4_and_ac6_ac7(client, world):
    items = await listed(client, world)
    assert {name: item["source"] for name, item in items.items()} == {
        "Walk-in": "walk_in", "Converted": "lead_conversion", "Self": "self_registered", "Legacy": "self_registered", "Agency": "agency",
    }  # fmt: skip


@pytest.mark.asyncio
async def test_each_row_carries_applications_linked_since_and_whether_it_is_my_walk_in_link(client, world):
    items = await listed(client, world)
    assert {name: (item["applications"], item["linked"]) for name, item in items.items()} == {
        "Walk-in": (1, True), "Converted": (0, True), "Self": (2, False), "Legacy": (1, False), "Agency": (1, False),
    }  # fmt: skip
    assert all(item["linked_since"] for item in items.values())
    walk_in = items["Walk-in"]
    assert walk_in["id"] == str(world["walk_in"].id) and walk_in["email"] == world["walk_in"].email
    assert set(walk_in) >= {"id", "full_name", "email", "phone", "student_code", "setup", "source", "applications", "linked_since", "linked"}


@pytest.mark.asyncio
async def test_newest_first_by_linked_since(client, world):
    await login(client, world["counselor"].email)
    body = (await client.get(URL, params={"limit": 50})).json()
    since = [item["linked_since"] for item in body["items"]]
    assert since == sorted(since, reverse=True)
    assert body["total"] == 5


@pytest.mark.asyncio
@pytest.mark.parametrize(("source", "expected"), [("walk_in", {"Walk-in"}), ("lead_conversion", {"Converted"}), ("self_registered", {"Self", "Legacy"}), ("agency", {"Agency"})])
async def test_the_source_filter_narrows_and_the_total_follows_ac5(client, world, source, expected):
    await login(client, world["counselor"].email)
    body = (await client.get(URL, params={"source": source, "limit": 50})).json()
    assert {i["full_name"].removeprefix(f"{world['tag']} ") for i in body["items"]} == expected
    assert body["total"] == len(expected)


@pytest.mark.asyncio
async def test_an_unknown_source_is_422(client, world):
    await login(client, world["counselor"].email)
    assert (await client.get(URL, params={"source": "telecaller"})).status_code == 422
    assert (await client.get(URL, params={"q": "x" * 101})).status_code == 422


@pytest.mark.asyncio
async def test_search_matches_name_email_and_phone_digits_literally(client, world):
    assert set(await listed(client, world, q=f"{world['tag']} conv")) == {"Converted"}
    assert set(await listed(client, world, q=world["legacy"].email.upper())) == {"Legacy"}
    assert set(await listed(client, world, q="9876543210")) == {"Self"}
    assert set(await listed(client, world, q=f"{world['tag']}%")) == set()  # `%` is literal
    assert len(await listed(client, world, q="   ")) == 5  # blank is no filter
    assert set(await listed(client, world, q=world["tag"], source="walk_in")) == {"Walk-in"}


@pytest.mark.asyncio
async def test_a_student_whose_application_moves_to_another_counselor_drops_off(client, world, db_session):
    from sqlalchemy import update

    await db_session.execute(update(OverseasApplication).where(OverseasApplication.student_id == world["legacy"].id).values(counselor_id=world["other"].id))
    await db_session.commit()
    assert "Legacy" not in await listed(client, world)


@pytest.mark.asyncio
async def test_another_counselors_list_has_only_theirs(client, world):
    await login(client, world["other"].email)
    names = {i["full_name"].removeprefix(f"{world['tag']} ") for i in (await client.get(URL, params={"limit": 50})).json()["items"]}
    assert names == {"Self", "Theirs"}


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "it"), ("overseas_admin", "overseas"), ("overseas_student", "overseas"), ("agent", "overseas")])
async def test_other_roles_are_403(client, db_session, role, division):
    user = await mk_user(db_session, role=role, division=division)
    await login(client, user.email, division)
    assert (await client.get(URL, params={"source": "walk_in", "q": "a"})).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_401(client):
    assert (await client.get(URL, params={"source": "walk_in"})).status_code == 401
