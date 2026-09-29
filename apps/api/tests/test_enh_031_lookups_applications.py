"""ENH-031 (DEC-SCOPE-037) -- GET /lookups/overseas-applications (the _assigned_application scope) and /lookups/it-job-applications."""

import pytest

from app.models import Company, Job, JobApplication
from tests.agn001_helpers import login, mk_active_org, mk_user, uniq
from tests.enh016_helpers import make_school, make_student
from tests.enh031_helpers import mk_application, mk_course, mk_university

APPS = "/api/v1/lookups/overseas-applications"
JOBS = "/api/v1/lookups/it-job-applications"


def ids(response) -> set[str]:
    assert response.status_code == 200, response.text
    return {item["id"] for item in response.json()["items"]}


async def two_applications(db, tag):
    """Two students, two universities; returns (student_a, app_a, student_b, app_b, uni_a)."""
    a = await mk_user(db, role="overseas_student", full_name=f"{tag} Alpha")
    b = await mk_user(db, role="overseas_student", full_name=f"{tag} Beta")
    uni_a = await mk_university(db, name=f"{tag} Uni A")
    uni_b = await mk_university(db, name=f"{tag} Uni B")
    return a, await mk_application(db, student=a, university=uni_a), b, await mk_application(db, student=b, university=uni_b), uni_a


@pytest.mark.asyncio
async def test_admin_sees_all_with_student_label_and_university_course_status_detail(client, db_session):
    tag = uniq("e31")
    student = await mk_user(db_session, role="overseas_student", full_name=f"{tag} Alpha")
    university = await mk_university(db_session, name=f"{tag} Uni")
    course = await mk_course(db_session, university, "MSc Data")
    with_course = await mk_application(db_session, student=student, university=university, course=course, status="offer")
    without = await mk_application(db_session, student=student, university=university)
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    items = {i["id"]: i for i in (await client.get(APPS, params={"q": tag})).json()["items"]}
    assert items[str(with_course.id)] == {"id": str(with_course.id), "label": f"{tag} Alpha", "detail": f"{tag} Uni · MSc Data · offer"}
    assert items[str(without.id)]["detail"] == f"{tag} Uni · enquiry"


@pytest.mark.asyncio
async def test_q_matches_student_university_course_and_reference(client, db_session):
    tag = uniq("e31")
    student = await mk_user(db_session, role="overseas_student", full_name="Plain Name")
    university = await mk_university(db_session)
    course = await mk_course(db_session, university, f"{tag} Course")
    by_course = await mk_application(db_session, student=student, university=university, course=course)
    by_reference = await mk_application(db_session, student=student, university=university, reference=f"REF-{tag}")
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    assert ids(await client.get(APPS, params={"q": tag})) == {str(by_course.id), str(by_reference.id)}


@pytest.mark.asyncio
async def test_counselor_sees_only_own_applications(client, db_session):
    tag = uniq("e31")
    counselor = await mk_user(db_session, role="counselor")
    a = await mk_user(db_session, role="overseas_student", full_name=f"{tag} Alpha")
    university = await mk_university(db_session)
    mine = await mk_application(db_session, student=a, university=university, counselor=counselor)
    await mk_application(db_session, student=a, university=university)
    await login(client, counselor.email)
    assert ids(await client.get(APPS, params={"q": tag})) == {str(mine.id)}


@pytest.mark.asyncio
async def test_university_rep_sees_only_own_university(client, db_session):
    tag = uniq("e31")
    _, app_a, _, _, uni_a = await two_applications(db_session, tag)
    rep = await mk_user(db_session, role="university_rep", profile={"university_id": str(uni_a.id)})
    await login(client, rep.email)
    assert ids(await client.get(APPS, params={"q": tag})) == {str(app_a.id)}


@pytest.mark.asyncio
async def test_university_rep_without_a_university_sees_nothing(client, db_session):
    tag = uniq("e31")
    await two_applications(db_session, tag)
    rep = await mk_user(db_session, role="university_rep")
    await login(client, rep.email)
    assert ids(await client.get(APPS, params={"q": tag})) == set()


@pytest.mark.asyncio
async def test_agent_sees_only_its_agency_applications(client, db_session):
    tag = uniq("e31")
    a = await mk_active_org(db_session, name=f"{tag} A")
    b = await mk_active_org(db_session, name=f"{tag} B")
    student = await mk_user(db_session, role="overseas_student", full_name=f"{tag} Alpha")
    university = await mk_university(db_session)
    mine = await mk_application(db_session, student=student, university=university, agent=a["master"])
    await mk_application(db_session, student=student, university=university, agent=b["master"])
    await login(client, a["master"].email)
    assert ids(await client.get(APPS, params={"q": tag})) == {str(mine.id)}


@pytest.mark.asyncio
async def test_overseas_student_sees_only_own_applications(client, db_session):
    tag = uniq("e31")
    a, app_a, _, _, _ = await two_applications(db_session, tag)
    await login(client, a.email)
    assert ids(await client.get(APPS, params={"q": tag})) == {str(app_a.id)}


@pytest.mark.asyncio
async def test_student_id_narrows_to_that_student(client, db_session):
    tag = uniq("e31")
    a, app_a, _, _, _ = await two_applications(db_session, tag)
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    assert ids(await client.get(APPS, params={"q": tag, "student_id": str(a.id)})) == {str(app_a.id)}


@pytest.mark.asyncio
async def test_bridged_application_uses_school_student_name(client, db_session):
    tag = uniq("e31")
    ctx = await make_school(db_session)
    school_student = await make_student(db_session, ctx, name=f"{tag} School Kid")
    await db_session.commit()
    university = await mk_university(db_session)
    bridged = await mk_application(db_session, school_student=school_student, university=university)
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    items = (await client.get(APPS, params={"q": tag})).json()["items"]
    assert [(i["id"], i["label"]) for i in items] == [(str(bridged.id), f"{tag} School Kid")]


@pytest.mark.asyncio
@pytest.mark.parametrize("role, division", [("it_student", "it"), ("placement_team", "it"), ("trainer", "it")])
async def test_applications_lookup_refuses_other_roles(client, db_session, role, division):
    user = await mk_user(db_session, role=role, division=division)
    await login(client, user.email, division)
    assert (await client.get(APPS)).status_code == 403


async def job_application(db, tag, *, candidate_name, title, company_name, status="applied"):
    candidate = await mk_user(db, role="it_student", division="it", full_name=candidate_name)
    company = Company(name=f"{company_name} {uniq('co')}")
    db.add(company)
    await db.flush()
    job = Job(company_id=company.id, title=title, location="Remote", description="", skills=[], status="open")
    db.add(job)
    await db.flush()
    application = JobApplication(job_id=job.id, student_id=candidate.id, status=status)
    db.add(application)
    await db.commit()
    return application, company


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["placement_team", "hr_team", "it_admin"])
async def test_it_team_sees_job_applications_with_title_company_status(client, db_session, role):
    tag = uniq("e31")
    application, company = await job_application(db_session, tag, candidate_name=f"{tag} Candidate", title="Backend Engineer", company_name="Acme")
    user = await mk_user(db_session, role=role, division="it")
    await login(client, user.email, "it")
    items = (await client.get(JOBS, params={"q": tag})).json()["items"]
    assert items == [{"id": str(application.id), "label": f"{tag} Candidate", "detail": f"Backend Engineer · {company.name} · applied"}]


@pytest.mark.asyncio
async def test_job_applications_match_title_and_company(client, db_session):
    tag = uniq("e31")
    by_title, _ = await job_application(db_session, tag, candidate_name="Someone", title=f"{tag} Role", company_name="Acme")
    by_company, _ = await job_application(db_session, tag, candidate_name="Other", title="Role", company_name=f"{tag} Corp")
    user = await mk_user(db_session, role="placement_team", division="it")
    await login(client, user.email, "it")
    assert ids(await client.get(JOBS, params={"q": tag})) == {str(by_title.id), str(by_company.id)}


@pytest.mark.asyncio
@pytest.mark.parametrize("role, division", [("it_student", "it"), ("trainer", "it"), ("overseas_admin", "overseas"), ("counselor", "overseas")])
async def test_job_applications_lookup_refuses_other_roles(client, db_session, role, division):
    user = await mk_user(db_session, role=role, division=division)
    await login(client, user.email, division)
    assert (await client.get(JOBS)).status_code == 403
