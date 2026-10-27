"""rec-036 -- program skill tags, course-completed skills and the candidate journey (spec §1-§5; DEC-SCOPE-176 CI1-CI8). The shared test
database is never truncated, so every assertion uses rows created by the test (skills carry a unique suffix)."""

import datetime
import uuid
from datetime import UTC

import pytest
from sqlalchemy import select

from app.models import (
    AuditLog,
    Batch,
    Candidate,
    CandidateSkill,
    Certificate,
    Enquiry,
    Enrollment,
    JobOffer,
    Program,
    ProgramSkill,
    RecCandidateSource,
    Skill,
    SkillCategory,
    User,
)
from app.services.applications import candidate_for_student
from tests.rec001_helpers import as_role, login, make_recruiter, make_user
from tests.rec017_helpers import student_application
from tests.test_emp_004_interview_scheduling import _create_employer, _create_job

ADMIN = "/api/v1/admin/programs"
POOL = "/api/v1/account/placement-pool"
RECRUITER = "/api/v1/recruiter/candidates"
JOIN = {"consent_version": "v1"}
pytestmark = pytest.mark.asyncio


def tags_url(program_id) -> str:
    return f"{ADMIN}/{program_id}/skills"


async def _skills(db, *names: str) -> list[Skill]:
    category = await db.scalar(select(SkillCategory).order_by(SkillCategory.name).limit(1))
    if category is None:
        category = SkillCategory(name=f"Rec036 {uuid.uuid4().hex[:6]}")
        db.add(category)
        await db.flush()
    tag = uuid.uuid4().hex[:6]
    rows = [Skill(name=f"{name} {tag}", category_id=category.id) for name in names]
    db.add_all(rows)
    await db.commit()
    return rows


async def _program(db, title="Python Full Stack") -> Program:
    program = Program(
        slug=f"rec036-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=title,
        summary="",
        duration="8 weeks",
        eligibility="",
        fees=0,
        certification="Cert",
        curriculum=[],
        placement_assistance="",
        trainer_name="T",
        active=True,
    )
    db.add(program)
    await db.commit()
    return program


async def _enrol(db, student: User, program: Program, *, enrolled_on=datetime.date(2026, 1, 5)) -> Enrollment:
    batch = Batch(
        program_id=program.id,
        name=f"B-{uuid.uuid4().hex[:6]}",
        start_date=enrolled_on,
        end_date=enrolled_on + datetime.timedelta(days=60),
        schedule="Mon-Fri",
        capacity=20,
        enrollment_open=True,
        status="active",
    )
    db.add(batch)
    await db.flush()
    enrollment = Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-{uuid.uuid4().hex[:8]}", enrolled_on=enrolled_on, status="completed")
    db.add(enrollment)
    await db.commit()
    return enrollment


async def _certificate(db, student: User, program: Program, enrollment: Enrollment, approver: User | None, issued_on=datetime.date(2026, 3, 9)):
    db.add(
        Certificate(
            student_id=student.id,
            program_id=program.id,
            enrollment_id=enrollment.id,
            certificate_no=f"C-{uuid.uuid4().hex[:10]}",
            verification_code=uuid.uuid4().hex,
            issued_on=issued_on,
            approved_by_id=approver.id if approver else None,
            status="issued",
        )
    )
    await db.commit()


async def _tag(db, program: Program, skills: list[Skill], by: User) -> None:
    db.add_all(ProgramSkill(program_id=program.id, skill_id=s.id, added_by_user_id=by.id) for s in skills)
    await db.commit()


async def _student(db, name="Rahul") -> User:
    return await make_user(db, "it_student", "it", name=f"{name} {uuid.uuid4().hex[:4]}")


async def _opt_in(client, student: User) -> None:
    await login(client, student)
    response = await client.post(f"{POOL}/opt-in", json=JOIN)
    assert response.status_code in (200, 201), response.text


async def _rows(db, candidate_id) -> dict:
    """{skill id: CandidateSkill} fresh from the database."""
    rows = (await db.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id).execution_options(populate_existing=True))).all()
    return {r.skill_id: r for r in rows}


async def _candidate_of(db, user_id) -> Candidate | None:
    return await db.scalar(select(Candidate).where(Candidate.user_id == user_id).execution_options(populate_existing=True))


async def _completer(client, db, skills: list[Skill], *, approver: User | None = None, opt_in: bool = True):
    """A student who holds the issued certificate of a program tagged with `skills`, opted in unless told otherwise."""
    admin = await make_user(db, "it_admin", "it")
    program = await _program(db)
    await _tag(db, program, skills, admin)
    student = await _student(db)
    enrollment = await _enrol(db, student, program)
    await _certificate(db, student, program, enrollment, approver if approver is not None else admin)
    if opt_in:
        await _opt_in(client, student)
    return student, program, admin


# --- program skill tags (CI1) ------------------------------------------------------------------------------------------------------
async def test_it_admin_replaces_a_programs_tags_and_it_is_audited(client, db_session):
    python, django, sql = await _skills(db_session, "Python", "Django", "SQL")
    program = await _program(db_session)
    admin = await as_role(client, db_session, "it_admin", "it")
    assert (await client.get(tags_url(program.id))).json() == {"items": []}

    response = await client.put(tags_url(program.id), json={"skill_ids": [str(python.id), str(django.id)]})
    assert response.status_code == 200, response.text
    assert [i["name"] for i in response.json()["items"]] == sorted([python.name, django.name], key=str.lower)

    response = await client.put(tags_url(program.id), json={"skill_ids": [str(django.id), str(sql.id), str(sql.id)]})
    assert response.status_code == 200, response.text
    assert {i["id"] for i in response.json()["items"]} == {str(django.id), str(sql.id)}
    audit = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "program.skills_update", AuditLog.entity_id == str(program.id), AuditLog.user_id == admin.id).order_by(AuditLog.created_at.desc()).limit(1)
    )
    assert audit.metadata_json["added"] == [str(sql.id)] and audit.metadata_json["removed"] == [str(python.id)]


async def test_super_admin_may_tag_and_other_roles_may_not(client, db_session):
    (python,) = await _skills(db_session, "Python")
    program = await _program(db_session)
    for role, division in (("placement_team", "it"), ("overseas_admin", "overseas"), ("trainer", "it"), ("it_student", "it")):
        await as_role(client, db_session, role, division)
        assert (await client.put(tags_url(program.id), json={"skill_ids": [str(python.id)]})).status_code == 403, role
        assert (await client.get(tags_url(program.id))).status_code == 403, role
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.put(tags_url(program.id), json={"skill_ids": [str(python.id)]})).status_code == 200


@pytest.mark.parametrize("case", ["unknown", "inactive", "too_many", "not_a_list", "bad_id"])
async def test_tag_validation_422(client, db_session, case):
    (python,) = await _skills(db_session, "Python")
    program = await _program(db_session)
    await as_role(client, db_session, "it_admin", "it")
    body = {
        "unknown": {"skill_ids": [str(uuid.uuid4())]},
        "inactive": {"skill_ids": [str(python.id)]},
        "too_many": {"skill_ids": [str(uuid.uuid4()) for _ in range(31)]},
        "not_a_list": {"skill_ids": "python"},
        "bad_id": {"skill_ids": ["nope"]},
    }[case]
    if case == "inactive":
        python.active = False
        await db_session.commit()
    response = await client.put(tags_url(program.id), json=body)
    assert response.status_code == 422, response.text
    assert (await client.get(tags_url(program.id))).json() == {"items": []}


async def test_unknown_program_is_404(client, db_session):
    await as_role(client, db_session, "it_admin", "it")
    assert (await client.get(tags_url(uuid.uuid4()))).status_code == 404
    assert (await client.put(tags_url(uuid.uuid4()), json={"skill_ids": []})).status_code == 404


async def test_skill_options_lookup_lists_active_skills_for_the_it_admin(client, db_session):
    active, inactive = await _skills(db_session, "Kotlin", "Kotlin Old")
    inactive.active = False
    await db_session.commit()
    await as_role(client, db_session, "it_admin", "it")
    response = await client.get(f"{ADMIN}/skill-options", params={"q": active.name})
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert [i["id"] for i in items] == [str(active.id)] and items[0]["category"]
    await as_role(client, db_session, "placement_team", "it")
    assert (await client.get(f"{ADMIN}/skill-options")).status_code == 403


# --- course-completed skills (CI2-CI6, AC1) --------------------------------------------------------------------------------------------
async def test_ac1_opting_in_after_completing_python_full_stack_adds_its_skills_as_course_completed(client, db_session):
    skills = await _skills(db_session, "Python", "Django", "SQL")
    student, _, admin = await _completer(client, db_session, skills)
    candidate = await _candidate_of(db_session, student.id)
    rows = await _rows(db_session, candidate.id)
    assert set(rows) >= {s.id for s in skills}
    for skill in skills:
        row = rows[skill.id]
        assert (row.source, row.status, row.level, row.verified_by_user_id) == ("course_completed", "verified", "beginner", admin.id)
        assert row.verified_at is not None
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "candidate.skill_course_grant", AuditLog.entity_id == str(candidate.id)))
    assert sorted(audit.metadata_json["skill_ids"]) == sorted(str(s.id) for s in skills)


async def test_a_certificate_without_an_approver_gives_claimed_course_skills(client, db_session):
    (python,) = await _skills(db_session, "Python")
    admin = await make_user(db_session, "it_admin", "it")
    program = await _program(db_session)
    await _tag(db_session, program, [python], admin)
    student = await _student(db_session)
    await _certificate(db_session, student, program, await _enrol(db_session, student, program), None)
    await _opt_in(client, student)
    row = (await _rows(db_session, (await _candidate_of(db_session, student.id)).id))[python.id]
    assert (row.source, row.status, row.verified_by_user_id) == ("course_completed", "claimed", None)


async def test_issuing_a_certificate_to_an_opted_in_student_adds_the_course_skills(client, db_session):
    (java,) = await _skills(db_session, "Java")
    admin = await make_user(db_session, "it_admin", "it")
    program = await _program(db_session, "Java Full Stack")
    await _tag(db_session, program, [java], admin)
    student = await _student(db_session)
    enrollment = await _enrol(db_session, student, program)
    await _opt_in(client, student)
    candidate = await _candidate_of(db_session, student.id)
    assert java.id not in await _rows(db_session, candidate.id)  # enrolled is not completed (CI2)

    coordinator = await make_user(db_session, "coordinator", "it")  # nehn-031: the coordinator issues
    await login(client, coordinator)
    response = await client.post(f"/api/v1/workflows/it/certificates/{enrollment.id}/issue", json={"override": True, "override_reason": "QA"})
    assert response.status_code == 201, response.text
    row = (await _rows(db_session, candidate.id))[java.id]
    assert (row.source, row.status, row.verified_by_user_id) == ("course_completed", "verified", coordinator.id)


async def test_a_certificate_for_a_student_who_has_not_opted_in_adds_nothing(client, db_session):
    (java,) = await _skills(db_session, "Java")
    admin = await make_user(db_session, "it_admin", "it")
    program = await _program(db_session)
    await _tag(db_session, program, [java], admin)
    student = await _student(db_session)
    enrollment = await _enrol(db_session, student, program)
    employer, company = await _create_employer(db_session)
    await student_application(db_session, (await _create_job(db_session, company)).id, student)  # backfilled, not opted in (R6)
    await db_session.commit()
    await login(client, await make_user(db_session, "coordinator", "it"))  # nehn-031: the coordinator issues
    response = await client.post(f"/api/v1/workflows/it/certificates/{enrollment.id}/issue", json={"override": True, "override_reason": "QA"})
    assert response.status_code == 201, response.text
    candidate = await _candidate_of(db_session, student.id)
    assert candidate is not None and not candidate.opted_in
    assert await _rows(db_session, candidate.id) == {}


async def test_tagging_a_program_reaches_its_opted_in_completers_only(client, db_session):
    python, rust = await _skills(db_session, "Python", "Rust")
    opted, program, admin = await _completer(client, db_session, [python])
    other = await _student(db_session)  # completed the same program, never opted in
    await _certificate(db_session, other, program, await _enrol(db_session, other, program), admin)
    archived = await _student(db_session)  # opted in, then archived by a recruiter: read only
    await _certificate(db_session, archived, program, await _enrol(db_session, archived, program), admin)
    await _opt_in(client, archived)
    archived_candidate = await _candidate_of(db_session, archived.id)
    archived_candidate.archived_at = datetime.datetime.now(UTC)
    await db_session.commit()

    await login(client, admin)
    response = await client.put(tags_url(program.id), json={"skill_ids": [str(python.id), str(rust.id)]})
    assert response.status_code == 200, response.text
    assert response.json()["candidates_updated"] == 1
    assert (await _rows(db_session, (await _candidate_of(db_session, opted.id)).id))[rust.id].source == "course_completed"
    assert rust.id not in await _rows(db_session, archived_candidate.id)
    other_candidate = await _candidate_of(db_session, other.id)
    assert other_candidate is None or await _rows(db_session, other_candidate.id) == {}


async def test_removing_a_tag_keeps_the_candidates_skill(client, db_session):
    python, django = await _skills(db_session, "Python", "Django")
    student, program, admin = await _completer(client, db_session, [python, django])
    await login(client, admin)
    assert (await client.put(tags_url(program.id), json={"skill_ids": [str(python.id)]})).status_code == 200
    assert django.id in await _rows(db_session, (await _candidate_of(db_session, student.id)).id)  # CI6: additive


async def test_a_claimed_skill_is_upgraded_and_a_verified_one_is_kept(client, db_session):
    python, sql = await _skills(db_session, "Python", "SQL")
    admin = await make_user(db_session, "it_admin", "it")
    recruiter = await make_recruiter(db_session)
    program = await _program(db_session)
    await _tag(db_session, program, [python, sql], admin)
    student = await _student(db_session)
    await _certificate(db_session, student, program, await _enrol(db_session, student, program), admin)
    candidate = await candidate_for_student(db_session, student)
    verified_at = datetime.datetime(2026, 2, 1, tzinfo=UTC)
    db_session.add_all(
        [
            CandidateSkill(candidate_id=candidate.id, skill_id=python.id, level="advanced", source="resume", added_by_user_id=recruiter.id),
            CandidateSkill(
                candidate_id=candidate.id,
                skill_id=sql.id,
                level="expert",
                source="interview_verified",
                status="verified",
                verified_by_user_id=recruiter.id,
                verified_at=verified_at,
                added_by_user_id=recruiter.id,
            ),
        ]
    )
    await db_session.commit()
    await _opt_in(client, student)
    rows = await _rows(db_session, candidate.id)
    assert (rows[python.id].source, rows[python.id].status, rows[python.id].level) == ("course_completed", "verified", "advanced")
    assert (rows[sql.id].source, rows[sql.id].status, rows[sql.id].verified_by_user_id) == ("interview_verified", "verified", recruiter.id)


async def test_positive_a_java_course_completer_is_found_by_a_java_search(client, db_session):
    (java,) = await _skills(db_session, "Java")
    student, _, _ = await _completer(client, db_session, [java])
    candidate = await _candidate_of(db_session, student.id)
    await as_role(client, db_session, "placement_team", "it")
    response = await client.post(f"{RECRUITER}/search", json={"all": [java.name], "verified_only": True})
    assert response.status_code == 200, response.text
    assert [i["id"] for i in response.json()["items"]] == [str(candidate.id)]


# --- skill merge (CI8) ---------------------------------------------------------------------------------------------------------------
async def test_merging_a_tagged_skill_moves_the_tag(client, db_session):
    old, kept, alone = await _skills(db_session, "Py", "Python", "Flask")
    admin = await make_user(db_session, "it_admin", "it")
    both, single = await _program(db_session), await _program(db_session)
    await _tag(db_session, both, [old, kept], admin)
    await _tag(db_session, single, [old, alone], admin)
    await as_role(client, db_session, "placement_manager", "global")
    response = await client.post(f"/api/v1/recruiter/skills/{old.id}/merge", json={"into_skill_id": str(kept.id)})
    assert response.status_code == 200, response.text
    tags = (await db_session.execute(select(ProgramSkill.program_id, ProgramSkill.skill_id).where(ProgramSkill.program_id.in_([both.id, single.id])))).all()
    assert set(tags) == {(both.id, kept.id), (single.id, kept.id), (single.id, alone.id)}


# --- journey (CI7, AC2) --------------------------------------------------------------------------------------------------------------
async def test_ac2_the_journey_shows_each_stage_with_dates(client, db_session):
    (python,) = await _skills(db_session, "Python")
    converter = await make_user(db_session, "it_admin", "it")
    student, program, _ = await _completer(client, db_session, [python])
    db_session.add(
        Enquiry(
            division="it",
            name="Lead",
            email=f"lead-{uuid.uuid4().hex[:6]}@example.com",
            phone="+91 98765 43210",
            subject="IT courses",
            message="Private note",
            source="college",
            status="new",
            crm_sync_status="pending",
            metadata_json={},
            converted_user_id=student.id,
            converted_at=datetime.datetime(2025, 12, 20, tzinfo=UTC),
            converted_by_user_id=converter.id,
        )
    )
    _, company = await _create_employer(db_session)
    application = await student_application(db_session, (await _create_job(db_session, company)).id, student, status="joined")
    db_session.add(JobOffer(application_id=application.id, position="Python Developer", status="accepted", joining_status="joined", actual_joining_date=datetime.date(2026, 5, 4)))
    await db_session.commit()
    candidate = await _candidate_of(db_session, student.id)

    await as_role(client, db_session, "placement_team", "it")
    response = await client.get(f"{RECRUITER}/{candidate.id}/journey")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lead"]["source"] == "college" and body["lead"]["converted_at"].startswith("2025-12-20")
    assert body["lead"]["lead_code"] and body["lead"]["created_at"]
    assert "phone" not in body["lead"] and "email" not in body["lead"] and "message" not in body["lead"]
    assert [(e["program"], e["enrolled_on"], e["status"]) for e in body["enrolments"]] == [(program.title, "2026-01-05", "completed")]
    assert [(c["program"], c["issued_on"]) for c in body["certificates"]] == [(program.title, "2026-03-09")]
    assert body["candidate"]["added_at"] and body["candidate"]["opted_in_at"]
    assert body["applications"]["count"] == 1 and body["applications"]["first_at"]
    assert body["placements"] == [{"company": company.name, "position": "Python Developer", "joined_on": "2026-05-04"}]


async def test_an_external_candidate_has_no_training_stages(client, db_session):
    source_id = str(await db_session.scalar(select(RecCandidateSource.id).where(RecCandidateSource.active.is_(True)).limit(1)))
    await as_role(client, db_session, "placement_team", "it")
    created = await client.post(RECRUITER, json={"name": "Asha", "email": f"asha-{uuid.uuid4().hex[:6]}@example.com", "source_id": source_id})
    assert created.status_code == 201, created.text
    body = (await client.get(f"{RECRUITER}/{created.json()['id']}/journey")).json()
    assert body["lead"] is None and body["enrolments"] == [] and body["certificates"] == []
    assert body["candidate"]["opted_in_at"] is None and body["applications"] == {"count": 0, "first_at": None} and body["placements"] == []


async def test_negative_a_student_who_has_not_opted_in_is_never_shown(client, db_session):
    (python,) = await _skills(db_session, "Python")
    student, _, _ = await _completer(client, db_session, [python], opt_in=False)
    candidate = await candidate_for_student(db_session, student)
    await db_session.commit()
    await as_role(client, db_session, "placement_team", "it")
    assert (await client.get(f"{RECRUITER}/{candidate.id}/journey")).status_code == 404
    assert (await client.get(f"{RECRUITER}/{uuid.uuid4()}/journey")).status_code == 404


async def test_journey_roles(client, db_session):
    (python,) = await _skills(db_session, "Python")
    student, _, _ = await _completer(client, db_session, [python])
    candidate = await _candidate_of(db_session, student.id)
    await as_role(client, db_session, "hr_team", "it")
    assert (await client.get(f"{RECRUITER}/{candidate.id}/journey")).status_code == 200
    for role, division in (("employer", "it"), ("it_admin", "it"), ("it_student", "it")):
        await as_role(client, db_session, role, division)
        assert (await client.get(f"{RECRUITER}/{candidate.id}/journey")).status_code == 403, role
