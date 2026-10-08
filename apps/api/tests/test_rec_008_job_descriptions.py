"""rec-008 -- JD management (spec §1-§3; AC1-AC3; DEC-SCOPE-132 JD1-JD9). Names are unique per test (the database is shared)."""

import uuid
from datetime import timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import AuditLog, CompanyContact, JobDescription
from app.services import job_descriptions as svc
from app.services.candidates import DOCX
from app.services.recruiter_requirements import ist_today
from tests.rec001_helpers import as_role, login, make_recruiter, make_user
from tests.test_rec_007_requirements import BASE, _company, _create, _set_status, _team
from tests.test_rec_009_resumes import PDF, docx, plain_zip


def jd_url(requirement_id, tail=""):
    return f"{BASE}/{requirement_id}/jd{tail}"


async def _requirement(client, db, **body):
    manager, recruiter, company = await _team(client, db)
    req = (await _create(client, company, **body)).json()["requirement"]
    return manager, recruiter, company, req


async def _upload(client, requirement_id, data=PDF, name="Python JD.pdf", content_type="application/pdf"):
    return await client.put(jd_url(requirement_id, "/file"), files={"file": (name, data, content_type)})


def _fields(**over):
    return {
        "role": "Python Developer", "experience": "0–2 years", "qualification": "B.Tech", "skills": "Python, SQL", "salary": "3–6 LPA",
        "location": "Hyderabad", "description": "Build APIs", "responsibilities": "Own services", "requirements": "Git", "openings": 3,
    } | over


# --- AC1 / AC2: create, upload, versions ----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_jd_yet_is_an_empty_list_the_recruiter_can_write(client, db_session):
    _, _, _, req = await _requirement(client, db_session)
    body = (await client.get(jd_url(req["id"]))).json()
    assert body == {"jd_number": None, "versions": [], "can_edit": True}


@pytest.mark.asyncio
async def test_create_then_upload_keeps_versions_with_one_current_and_carries_fields_and_file(client, db_session):
    _, recruiter, _, req = await _requirement(client, db_session)
    created = await client.post(jd_url(req["id"]), json=_fields())
    assert created.status_code == 201, created.text
    jd = created.json()
    assert jd["jd_number"].startswith("JD-") and len(jd["versions"]) == 1
    v1 = jd["versions"][0]
    assert v1["version"] == 1 and v1["is_current"] and v1["role"] == "Python Developer" and v1["openings"] == 3 and v1["file"] is None
    assert v1["created_by"]["id"] == str(recruiter.id)

    uploaded = await _upload(client, req["id"])  # AC1: linked to the requirement by the route, nothing to choose
    assert uploaded.status_code == 201, uploaded.text
    jd = uploaded.json()
    assert [v["version"] for v in jd["versions"]] == [2, 1] and [v["is_current"] for v in jd["versions"]] == [True, False]
    v2 = jd["versions"][0]
    assert v2["role"] == "Python Developer" and v2["responsibilities"] == "Own services"  # the fields carry forward
    assert v2["file"] == {"name": "Python JD.pdf", "content_type": "application/pdf", "size_bytes": len(PDF)}

    edited = (await client.post(jd_url(req["id"]), json=_fields(role="Senior Python Developer"))).json()
    v3 = edited["versions"][0]
    assert v3["version"] == 3 and v3["role"] == "Senior Python Developer" and v3["file"]["name"] == "Python JD.pdf"  # the file carries
    assert edited["jd_number"] == jd["jd_number"]  # JD2: one number for the requirement
    rows = (await db_session.scalars(select(JobDescription).where(JobDescription.job_id == uuid.UUID(req["id"])))).all()
    assert sorted((r.version, r.is_current) for r in rows) == [(1, False), (2, False), (3, True)]
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == req["id"], AuditLog.action.like("job_description.%")))).all()
    assert sorted(actions) == ["job_description.create", "job_description.create", "job_description.upload"]


@pytest.mark.asyncio
async def test_a_first_upload_takes_its_fields_from_the_requirement(client, db_session):
    deadline = ist_today() + timedelta(days=20)
    _, _, _, req = await _requirement(client, db_session, qualification="MCA", vacancies=4, closes_on=str(deadline), description="Team work")
    v1 = (await _upload(client, req["id"], docx(), "jd.docx")).json()["versions"][0]
    assert (v1["role"], v1["location"], v1["qualification"], v1["openings"], v1["closing_date"], v1["description"]) == (
        req["title"], "Hyderabad", "MCA", 4, str(deadline), "Team work",
    )
    assert v1["file"]["content_type"] == DOCX and v1["closing_date_differs"] is False


@pytest.mark.asyncio
async def test_a_closing_date_other_than_the_deadline_is_kept_and_flagged(client, db_session):
    _, _, _, req = await _requirement(client, db_session, closes_on=str(ist_today() + timedelta(days=20)))
    jd = (await client.post(jd_url(req["id"]), json=_fields(closing_date=str(ist_today() + timedelta(days=5))))).json()
    assert jd["versions"][0]["closing_date_differs"] is True


# --- AC3: files ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("data", "code"),
    [(b"", 422), (b"\x89PNG\r\n\x1a\n" + b"0" * 64, 415), (plain_zip(), 415), (b"%PDF-" + b"0" * (5 * 1024 * 1024), 413)],
    ids=["empty", "png", "zip-not-docx", "over-5mb"],
)
async def test_wrong_files_are_refused_and_no_version_is_written(client, db_session, data, code):
    _, _, _, req = await _requirement(client, db_session)
    assert (await _upload(client, req["id"], data)).status_code == code
    assert await db_session.scalar(select(JobDescription.id).where(JobDescription.job_id == uuid.UUID(req["id"]))) is None


@pytest.mark.asyncio
async def test_the_stored_file_is_discarded_when_the_write_fails(client, db_session, monkeypatch):
    _, _, _, req = await _requirement(client, db_session)
    discarded = []
    monkeypatch.setattr(svc, "discard", discarded.append)

    async def lost_race(*_args, **_kwargs):
        raise HTTPException(409, "lost a race")

    monkeypatch.setattr(svc, "add_version", lost_race)
    response = await _upload(client, req["id"])
    assert response.status_code == 409
    assert len(discarded) == 1 and discarded[0].startswith("job-descriptions/")


@pytest.mark.asyncio
async def test_a_cancelled_requirement_refuses_an_upload_before_storing_anything(client, db_session, monkeypatch):
    _, _, _, req = await _requirement(client, db_session)
    await _set_status(client, req["id"], "cancelled")
    stored = []
    monkeypatch.setattr(svc, "store", lambda *a: stored.append(a) or "job-descriptions/x")
    assert (await _upload(client, req["id"])).status_code == 409
    assert stored == []


@pytest.mark.asyncio
async def test_download_is_audited_named_by_the_jd_number_and_a_version_without_a_file_is_404(client, db_session):
    _, _, _, req = await _requirement(client, db_session)
    await client.post(jd_url(req["id"]), json=_fields())
    jd = (await _upload(client, req["id"])).json()
    download = await client.get(jd_url(req["id"], "/2/file"))
    assert download.status_code == 200 and download.content == PDF
    assert download.headers["content-disposition"] == f'attachment; filename="{jd["jd_number"]}-v2.pdf"'
    assert download.headers["x-content-type-options"] == "nosniff"
    assert await db_session.scalar(select(AuditLog).where(AuditLog.action == "job_description.download", AuditLog.entity_id == req["id"]))
    assert (await client.get(jd_url(req["id"], "/1/file"))).status_code == 404  # v1 was created without a file
    assert (await client.get(jd_url(req["id"], "/9/file"))).status_code == 404


# --- validation -------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_role_is_required_and_unknown_keys_and_bad_openings_are_422(client, db_session):
    _, _, _, req = await _requirement(client, db_session)
    assert (await client.post(jd_url(req["id"]), json=_fields(role="  "))).status_code == 422
    assert (await client.post(jd_url(req["id"]), json=_fields(openings=0))).status_code == 422
    assert (await client.post(jd_url(req["id"]), json=_fields(company_id=str(uuid.uuid4())))).status_code == 422


@pytest.mark.asyncio
async def test_contact_person_must_be_an_active_contact_of_the_requirements_company(client, db_session):
    _, _, company, req = await _requirement(client, db_session)
    other = await _company(db_session)
    mine = CompanyContact(company_id=company.id, name="Asha HR")
    foreign = CompanyContact(company_id=other.id, name="Ravi")
    gone = CompanyContact(company_id=company.id, name="Old", active=False)
    db_session.add_all([mine, foreign, gone])
    await db_session.commit()
    ok = await client.post(jd_url(req["id"]), json=_fields(contact_id=str(mine.id)))
    assert ok.status_code == 201 and ok.json()["versions"][0]["contact"] == {"id": str(mine.id), "name": "Asha HR", "active": True}
    for contact in (foreign, gone):
        response = await client.post(jd_url(req["id"]), json=_fields(contact_id=str(contact.id)))
        assert response.status_code == 422 and "contact" in response.text


# --- scope and roles (JD7) ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_another_recruiters_requirement_is_404(client, db_session):
    manager, _, _, req = await _requirement(client, db_session)
    await login(client, await make_recruiter(db_session, manager))
    assert (await client.get(jd_url(req["id"]))).status_code == 404
    assert (await client.post(jd_url(req["id"]), json=_fields())).status_code == 404
    assert (await _upload(client, req["id"])).status_code == 404
    assert (await client.get(jd_url(req["id"], "/1/file"))).status_code == 404


@pytest.mark.asyncio
async def test_manager_and_assigned_bdm_read_but_cannot_write(client, db_session):
    manager, _, company, req = await _requirement(client, db_session)
    await client.post(jd_url(req["id"]), json=_fields())
    bdm = await make_user(db_session, "bdm", "it")
    company.assigned_bdm_user_id = bdm.id
    db_session.add(company)
    await db_session.commit()
    for reader in (manager, bdm):
        await login(client, reader)
        body = (await client.get(jd_url(req["id"]))).json()
        assert len(body["versions"]) == 1 and body["can_edit"] is False
        assert (await client.post(jd_url(req["id"]), json=_fields())).status_code == 403
        assert (await _upload(client, req["id"])).status_code == 403


@pytest.mark.asyncio
async def test_roles_outside_the_recruiter_module_are_403(client, db_session):
    _, _, _, req = await _requirement(client, db_session)
    for role, division in (("hr_team", "it"), ("employer", "it")):
        await as_role(client, db_session, role, division)
        assert (await client.get(jd_url(req["id"]))).status_code == 403


@pytest.mark.asyncio
async def test_a_cancelled_requirement_is_read_only(client, db_session):
    _, _, _, req = await _requirement(client, db_session)
    await client.post(jd_url(req["id"]), json=_fields())
    await _set_status(client, req["id"], "cancelled")
    assert (await client.get(jd_url(req["id"]))).json()["can_edit"] is False
    assert (await client.post(jd_url(req["id"]), json=_fields())).status_code == 409
