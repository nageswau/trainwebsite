"""ENH-012 -- Digital Portfolio Module.
docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md
"""
import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from app.models import PortfolioEntry, PortfolioProfile
from app.schemas import PortfolioEntryCreate, PORTFOLIO_SECTIONS
from tests.enh005_helpers import mk_school, mk_staff


@pytest.mark.asyncio
async def test_portfolio_entry_and_profile_roundtrip(db_session):
    ctx = await mk_school(db_session, label="ENH012-Model")
    student = ctx["students"][0]
    entry = PortfolioEntry(
        school_student_id=student.id, section="project", title="Robotics club build",
        description="Built a line-following robot.", organization="School STEM Club",
        date_from=date(2026, 1, 10), date_to=date(2026, 3, 1),
        created_by_user_id=ctx["coordinator"].id, updated_by_user_id=ctx["coordinator"].id,
    )
    profile = PortfolioProfile(school_student_id=student.id, personal_statement="I want to study engineering.", updated_by_user_id=ctx["coordinator"].id)
    db_session.add_all([entry, profile])
    await db_session.commit()
    await db_session.refresh(entry)
    await db_session.refresh(profile)
    assert entry.id is not None
    assert entry.section == "project"
    assert profile.school_student_id == student.id


@pytest.mark.asyncio
async def test_portfolio_profile_school_student_id_is_unique(db_session):
    ctx = await mk_school(db_session, label="ENH012-Unique")
    student = ctx["students"][0]
    db_session.add(PortfolioProfile(school_student_id=student.id, personal_statement="First."))
    await db_session.commit()
    db_session.add(PortfolioProfile(school_student_id=student.id, personal_statement="Second."))
    with pytest.raises(Exception):
        await db_session.commit()
    await db_session.rollback()


def test_portfolio_entry_create_rejects_unknown_section():
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="not_a_real_section", title="X")


def test_portfolio_entry_create_rejects_empty_title():
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="project", title="")


def test_portfolio_entry_create_rejects_date_to_before_date_from():
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="project", title="X", date_from="2026-06-01", date_to="2026-01-01")


def test_portfolio_entry_create_rejects_description_over_length_cap():
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="project", title="X", description="a" * 2001)


def test_portfolio_entry_create_accepts_a_valid_payload():
    entry = PortfolioEntryCreate(section="award", title="Regional Science Fair — 1st place", organization="State Science Council", date_from="2026-02-01")
    assert entry.section == "award"
    assert entry.date_to is None


def test_all_ten_section_values_are_defined():
    assert PORTFOLIO_SECTIONS == {"project", "internship", "competition", "sport", "leadership", "volunteering", "extracurricular", "award", "certification", "skill"}


def test_personal_statement_rejects_payload_over_length_cap():
    from app.schemas import PersonalStatementUpdate
    with pytest.raises(ValidationError):
        PersonalStatementUpdate(personal_statement="a" * 4001)


async def _add_academic_team(db_session, admin, school):
    from tests.enh005_helpers import mk_staff
    return await mk_staff(db_session, school, admin, role="academic_team")


@pytest.mark.asyncio
async def test_coordinator_reads_their_own_institution_students_portfolio(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-GET")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    response = await client.get(f"/api/v1/school/students/{student.id}/portfolio")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["student"]["id"] == str(student.id)
    assert body["completion_percentage"] == 0
    assert body["can_edit"] is True
    assert set(body["entries"].keys()) == {"project", "internship", "competition", "sport", "leadership", "volunteering", "extracurricular", "award", "certification", "skill"}


@pytest.mark.asyncio
async def test_principal_can_read_but_can_edit_is_false(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-GET-Principal")
    student = ctx["students"][0]
    await login(client, ctx["principal"].email)
    response = await client.get(f"/api/v1/school/students/{student.id}/portfolio")
    assert response.status_code == 200
    assert response.json()["can_edit"] is False


@pytest.mark.asyncio
async def test_coordinator_at_a_different_institution_gets_403(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx_a = await mk_school(db_session, label="ENH012-GET-A")
    ctx_b = await mk_school(db_session, label="ENH012-GET-B")
    await login(client, ctx_b["coordinator"].email)
    response = await client.get(f"/api/v1/school/students/{ctx_a['students'][0].id}/portfolio")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_academic_team_reads_via_their_portfolio_scope(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-GET-Academic")
    member = await _add_academic_team(db_session, ctx["admin"], ctx["school"])
    await login(client, member.email)
    response = await client.get(f"/api/v1/school/students/{ctx['students'][0].id}/portfolio")
    assert response.status_code == 200
    assert response.json()["can_edit"] is True


@pytest.mark.asyncio
async def test_coordinator_creates_an_entry(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-POST")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    response = await client.post(f"/api/v1/school/students/{student.id}/portfolio/entries", json={"section": "award", "title": "Regional Science Fair — 1st place", "organization": "State Science Council"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["section"] == "award"
    assert body["school_student_id"] == str(student.id)

    portfolio = (await client.get(f"/api/v1/school/students/{student.id}/portfolio")).json()
    assert len(portfolio["entries"]["award"]) == 1
    assert portfolio["completion_percentage"] == round(1 / 16 * 100)


@pytest.mark.asyncio
async def test_teacher_outside_assignment_cannot_create_an_entry(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-POST-Teacher", students=2, with_teacher=True)
    unassigned_student = ctx["students"][1]  # only students[0] is assigned to the teacher
    await login(client, ctx["teacher"].email)
    response = await client.post(f"/api/v1/school/students/{unassigned_student.id}/portfolio/entries", json={"section": "project", "title": "X"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_parent_cannot_create_an_entry(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-POST-Parent")
    await login(client, ctx["parent"].email)
    response = await client.post(f"/api/v1/school/students/{ctx['students'][0].id}/portfolio/entries", json={"section": "project", "title": "X"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_entry_writes_an_audit_log_without_free_text(client, db_session):
    from sqlalchemy import select as sa_select

    from app.models import AuditLog
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-POST-Audit")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    await client.post(f"/api/v1/school/students/{student.id}/portfolio/entries", json={"section": "project", "title": "Secret project title should not be logged"})
    row = await db_session.scalar(sa_select(AuditLog).where(AuditLog.action == "school.portfolio_entry_create").order_by(AuditLog.created_at.desc()))
    assert row is not None
    assert row.metadata_json == {"section": "project", "school_student_id": str(student.id)}
    assert "Secret project title" not in str(row.metadata_json)


@pytest.mark.asyncio
async def test_coordinator_updates_their_own_entry(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-PATCH")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    created = (await client.post(f"/api/v1/school/students/{student.id}/portfolio/entries", json={"section": "project", "title": "Draft title"})).json()
    response = await client.patch(f"/api/v1/school/students/{student.id}/portfolio/entries/{created['id']}", json={"title": "Final title"})
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Final title"


@pytest.mark.asyncio
async def test_patching_an_entry_that_belongs_to_a_different_student_is_404(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx_a = await mk_school(db_session, label="ENH012-PATCH-A")
    ctx_b = await mk_school(db_session, label="ENH012-PATCH-B")
    await login(client, ctx_a["coordinator"].email)
    created = (await client.post(f"/api/v1/school/students/{ctx_a['students'][0].id}/portfolio/entries", json={"section": "project", "title": "A's entry"})).json()

    await login(client, ctx_b["coordinator"].email)
    response = await client.patch(f"/api/v1/school/students/{ctx_b['students'][0].id}/portfolio/entries/{created['id']}", json={"title": "Hijacked"})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_patching_entry_date_to_before_existing_date_from_returns_422(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-PATCH-DateRange")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    # Create entry with date_from but no date_to
    created = (await client.post(f"/api/v1/school/students/{student.id}/portfolio/entries", json={"section": "project", "title": "Entry with date_from", "date_from": "2026-06-01"})).json()
    # Try to PATCH with only date_to that's before the existing date_from
    response = await client.patch(f"/api/v1/school/students/{student.id}/portfolio/entries/{created['id']}", json={"date_to": "2026-01-01"})
    assert response.status_code == 422, response.text
    # Verify the date_to was NOT changed
    portfolio = (await client.get(f"/api/v1/school/students/{student.id}/portfolio")).json()
    entry = portfolio["entries"]["project"][0]
    assert entry["date_to"] is None


@pytest.mark.asyncio
async def test_patching_entry_date_from_after_existing_date_to_returns_422(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-PATCH-DateRange2")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    # Create entry with date_to but no date_from
    created = (await client.post(f"/api/v1/school/students/{student.id}/portfolio/entries", json={"section": "project", "title": "Entry with date_to", "date_to": "2026-06-01"})).json()
    # Try to PATCH with only date_from that's after the existing date_to
    response = await client.patch(f"/api/v1/school/students/{student.id}/portfolio/entries/{created['id']}", json={"date_from": "2026-12-01"})
    assert response.status_code == 422, response.text
    # Verify the date_from was NOT changed
    portfolio = (await client.get(f"/api/v1/school/students/{student.id}/portfolio")).json()
    entry = portfolio["entries"]["project"][0]
    assert entry["date_from"] is None


@pytest.mark.asyncio
async def test_coordinator_deletes_their_own_entry(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-DELETE")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    created = (await client.post(f"/api/v1/school/students/{student.id}/portfolio/entries", json={"section": "project", "title": "To be deleted"})).json()
    response = await client.delete(f"/api/v1/school/students/{student.id}/portfolio/entries/{created['id']}")
    assert response.status_code == 204

    portfolio = (await client.get(f"/api/v1/school/students/{student.id}/portfolio")).json()
    assert portfolio["entries"]["project"] == []


@pytest.mark.asyncio
async def test_read_only_role_cannot_delete_an_entry(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-DELETE-RO")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    created = (await client.post(f"/api/v1/school/students/{student.id}/portfolio/entries", json={"section": "project", "title": "Should survive"})).json()

    await login(client, ctx["principal"].email)
    response = await client.delete(f"/api/v1/school/students/{student.id}/portfolio/entries/{created['id']}")
    assert response.status_code == 403
