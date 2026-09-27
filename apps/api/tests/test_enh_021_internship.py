"""ENH-021 -- internship entries (spec §5.2, I1-I6, AC21-1/2/4/6/7, AC-R3)."""
import pytest
import pytest_asyncio
from enh005_helpers import login, mk_school

from app.models import PortfolioEntry
from app.schemas import PortfolioEntryOut

ENTRIES = "/api/v1/school/students/{sid}/portfolio/entries"
INTERNSHIP = {
    "section": "internship", "title": "Design intern", "organization": "Acme", "date_from": "2026-05-01", "date_to": "2026-06-30",
    "mentor_name": "R. Rao", "mentor_designation": "Lead designer", "attendance_percent": 92, "completion_status": "completed",
    "feedback": "Strong work.", "skills_acquired": ["Figma", "Research"],
}


@pytest_asyncio.fixture
async def world(db_session):
    return await mk_school(db_session, label="E21", students=2)


def _url(world, i=0, eid=None):
    base = ENTRIES.format(sid=world["students"][i].id)
    return f"{base}/{eid}" if eid else base


@pytest.mark.asyncio
async def test_create_and_read_back_every_section_22_field(client, world):
    await login(client, world["coordinator"].email)
    r = await client.post(_url(world), json=INTERNSHIP)
    assert r.status_code == 201, r.text
    body = r.json()
    for key, value in INTERNSHIP.items():
        assert body[key] == value, key
    assert body["has_certificate"] is False and "certificate_key" not in body
    listed = (await client.get(f"/api/v1/school/students/{world['students'][0].id}/portfolio")).json()["entries"]["internship"][0]
    assert set(listed) == set(body)  # _entry_out and PortfolioEntryOut agree (A3)


def test_serializers_never_expose_the_storage_key():
    assert "certificate_key" not in PortfolioEntryOut.model_fields


@pytest.mark.parametrize("patch,detail", [
    ({"organization": None}, "Company is required"),
    ({"completion_status": "completed", "date_to": None}, "needs an end date"),
    ({"attendance_percent": 101}, None),
])
@pytest.mark.asyncio
async def test_internship_rules_on_create(client, world, patch, detail):
    await login(client, world["coordinator"].email)
    r = await client.post(_url(world), json={**INTERNSHIP, **patch})
    assert r.status_code == 422
    if detail:
        assert detail in r.text


@pytest.mark.asyncio
async def test_tracking_fields_are_refused_on_other_sections(client, world):
    await login(client, world["coordinator"].email)
    r = await client.post(_url(world), json={"section": "project", "title": "P", "mentor_name": "M"})
    assert r.status_code == 422 and "only accepted for the internship section" in r.text
    project = (await client.post(_url(world), json={"section": "project", "title": "P"})).json()
    r = await client.patch(_url(world, eid=project["id"]), json={"feedback": "x"})
    assert (r.status_code, r.json()["detail"]) == (422, "internship fields are only accepted for the internship section")


@pytest.mark.asyncio
async def test_post_merge_rules_on_update(client, world):
    await login(client, world["coordinator"].email)
    e = (await client.post(_url(world), json={**INTERNSHIP, "completion_status": "in_progress", "date_to": None})).json()
    r = await client.patch(_url(world, eid=e["id"]), json={"completion_status": "completed"})
    assert (r.status_code, r.json()["detail"]) == (422, "An internship marked completed needs an end date")
    r = await client.patch(_url(world, eid=e["id"]), json={"organization": None})
    assert (r.status_code, r.json()["detail"]) == (422, "Company is required for an internship")


@pytest.mark.asyncio
async def test_certificate_blocks_leaving_completed(client, world, db_session):
    await login(client, world["coordinator"].email)
    e = (await client.post(_url(world), json=INTERNSHIP)).json()
    row = await db_session.get(PortfolioEntry, e["id"])
    row.certificate_key, row.certificate_content_type = "portfolio-certificates/x", "application/pdf"
    await db_session.commit()
    r = await client.patch(_url(world, eid=e["id"]), json={"completion_status": "in_progress"})
    assert (r.status_code, r.json()["detail"]) == (422, "Remove the certificate first")


@pytest.mark.asyncio
async def test_creating_an_internship_needs_platinum(client, db_session):
    gold = await mk_school(db_session, label="E21-Gold", tier="gold")
    await login(client, gold["coordinator"].email)
    r = await client.post(ENTRIES.format(sid=gold["students"][0].id), json=INTERNSHIP)
    assert r.status_code == 403 and "Internships" in r.json()["detail"]
    other = await client.post(ENTRIES.format(sid=gold["students"][0].id), json={"section": "project", "title": "P"})
    assert other.status_code == 201  # other sections keep the Gold gate


@pytest.mark.asyncio
async def test_gold_school_keeps_basic_edit_and_delete_of_existing_internships(client, db_session):
    gold = await mk_school(db_session, label="E21-Legacy", tier="gold")
    c = gold["coordinator"]
    legacy = PortfolioEntry(school_student_id=gold["students"][0].id, section="internship", title="Old", organization="Acme", created_by_user_id=c.id, updated_by_user_id=c.id)
    db_session.add(legacy)
    await db_session.commit()
    await login(client, c.email)
    url = f"{ENTRIES.format(sid=gold['students'][0].id)}/{legacy.id}"
    assert (await client.patch(url, json={"title": "Renamed", "date_from": "2026-01-01"})).status_code == 200
    assert (await client.patch(url, json={"mentor_name": "M"})).status_code == 403  # tracking needs Platinum
    body = (await client.get(f"/api/v1/school/students/{gold['students'][0].id}/portfolio")).json()["entries"]["internship"][0]
    assert body["completion_status"] is None  # AC21-7: legacy entry, "No status"
    assert (await client.delete(url)).status_code == 204


@pytest.mark.asyncio
async def test_unassigned_teacher_cannot_edit(client, world):
    await login(client, world["coordinator"].email)
    e = (await client.post(_url(world, i=1), json=INTERNSHIP)).json()  # student 1 is not assigned to the teacher
    await login(client, world["teacher"].email)
    assert (await client.patch(_url(world, i=1, eid=e["id"]), json={"title": "x"})).status_code == 403


@pytest.mark.asyncio
async def test_entry_id_under_another_student_is_404(client, world):
    await login(client, world["coordinator"].email)
    e = (await client.post(_url(world, i=0), json=INTERNSHIP)).json()
    assert (await client.patch(_url(world, i=1, eid=e["id"]), json={"title": "x"})).status_code == 404


@pytest.mark.asyncio
async def test_storage_fields_are_not_writable(client, world):
    await login(client, world["coordinator"].email)
    r = await client.post(_url(world), json={**INTERNSHIP, "certificate_key": "portfolio-certificates/evil"})
    assert r.status_code == 422
