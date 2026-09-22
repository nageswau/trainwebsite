"""ENH-012 -- Digital Portfolio Module.
docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md
"""
import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from app.models import PortfolioEntry, PortfolioProfile
from app.schemas import PortfolioEntryCreate, PORTFOLIO_SECTIONS
from tests.enh005_helpers import mk_school


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


def test_date_range_error_is_human_readable_not_raw_field_names():
    # QA-02: the raw internal field names ("date_to"/"date_from") must never reach the end user --
    # detailMessage() on the frontend reads exactly this `msg` field verbatim into an alert. (Pydantic's
    # own str(ValidationError) also dumps the raw input dict for debugging -- that's not what a user
    # sees, so this checks the actual `msg` field, not the full exception repr.)
    with pytest.raises(ValidationError) as exc_info:
        PortfolioEntryCreate(section="project", title="X", date_from="2026-06-01", date_to="2026-01-01")
    msg = exc_info.value.errors()[0]["msg"]
    assert "date_to" not in msg
    assert "date_from" not in msg
    assert "End date must not be before start date" in msg


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


# --- Free-text validation fix: `description`/`personal_statement` must follow the `clean_free_text`
# house precedent (permits \n/\t, blocks bidi-override characters), not the single-line
# `_no_control_characters` rule that `title`/`organization` correctly keep. Before the fix, a `\n`
# in either field was rejected with a 422 -- impossible to ever store a line break in a multi-line
# textarea / `white-space: pre-wrap` field. ---


def test_portfolio_entry_create_accepts_description_with_a_newline():
    entry = PortfolioEntryCreate(section="project", title="X", description="Line one.\nLine two.")
    assert entry.description == "Line one.\nLine two."


def test_portfolio_entry_create_rejects_description_with_a_bidi_override_character():
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="project", title="X", description="Normal text ‮reversed text")


def test_portfolio_entry_create_still_rejects_newline_in_title():
    # Regression: title/organization stay single-line -- only description's rule changed.
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="project", title="Line one\nLine two")


def test_personal_statement_accepts_a_value_with_newlines():
    from app.schemas import PersonalStatementUpdate
    stmt = PersonalStatementUpdate(personal_statement="First paragraph.\n\nSecond paragraph.")
    assert stmt.personal_statement == "First paragraph.\n\nSecond paragraph."


def test_personal_statement_rejects_a_bidi_override_character():
    from app.schemas import PersonalStatementUpdate
    with pytest.raises(ValidationError):
        PersonalStatementUpdate(personal_statement="Normal ‮reversed")


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
    from tests.enh005_helpers import login, mk_school, mk_staff
    ctx = await mk_school(db_session, label="ENH012-GET-Academic")
    member = await mk_staff(db_session, ctx["school"], ctx["admin"], role="academic_team")
    await login(client, member.email)
    response = await client.get(f"/api/v1/school/students/{ctx['students'][0].id}/portfolio")
    assert response.status_code == 200
    assert response.json()["can_edit"] is True


@pytest.mark.asyncio
async def test_career_counselor_reads_via_their_portfolio_scope(client, db_session):
    # AC-04 names 7 read-capable roles; career_counselor had no coverage at all before this test.
    from tests.enh005_helpers import login, mk_school, mk_staff
    ctx = await mk_school(db_session, label="ENH012-GET-CareerCounselor")
    member = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    await login(client, member.email)
    response = await client.get(f"/api/v1/school/students/{ctx['students'][0].id}/portfolio")
    assert response.status_code == 200
    assert response.json()["can_edit"] is False


@pytest.mark.asyncio
async def test_psychometric_team_reads_via_their_portfolio_scope(client, db_session):
    # AC-04's other previously-uncovered read-capable role.
    from tests.enh005_helpers import login, mk_school, mk_staff
    ctx = await mk_school(db_session, label="ENH012-GET-Psychometric")
    member = await mk_staff(db_session, ctx["school"], ctx["admin"], role="psychometric_team")
    await login(client, member.email)
    response = await client.get(f"/api/v1/school/students/{ctx['students'][0].id}/portfolio")
    assert response.status_code == 200
    assert response.json()["can_edit"] is False


@pytest.mark.asyncio
async def test_parent_reads_their_own_childs_portfolio(client, db_session):
    # AC-04 also names school_parent as a reader; only can_edit=True/False coverage existed for
    # coordinator/principal/academic_team before this test -- no API-level parent-read-200 test.
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-GET-Parent")
    await login(client, ctx["parent"].email)
    response = await client.get(f"/api/v1/school/students/{ctx['students'][0].id}/portfolio")
    assert response.status_code == 200
    assert response.json()["can_edit"] is False


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
async def test_assigned_teacher_creates_an_entry(client, db_session):
    # Positive counterpart to the assignment-scope 403 above -- an assigned teacher must actually be
    # able to write, not just be correctly denied when unassigned.
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-POST-Teacher-Assigned", with_teacher=True)
    assigned_student = ctx["students"][0]  # mk_school assigns students[0] to the teacher
    await login(client, ctx["teacher"].email)
    response = await client.post(f"/api/v1/school/students/{assigned_student.id}/portfolio/entries", json={"section": "project", "title": "Assigned teacher entry"})
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_academic_team_creates_an_entry(client, db_session):
    from tests.enh005_helpers import login, mk_school, mk_staff
    ctx = await mk_school(db_session, label="ENH012-POST-AcademicTeam")
    member = await mk_staff(db_session, ctx["school"], ctx["admin"], role="academic_team")
    await login(client, member.email)
    response = await client.post(f"/api/v1/school/students/{ctx['students'][0].id}/portfolio/entries", json={"section": "award", "title": "Academic team entry"})
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_academic_team_outside_portfolio_gets_403(client, db_session):
    from tests.enh005_helpers import login, mk_school, mk_staff
    ctx_a = await mk_school(db_session, label="ENH012-POST-AcademicTeam-A")
    ctx_b = await mk_school(db_session, label="ENH012-POST-AcademicTeam-B")
    member = await mk_staff(db_session, ctx_a["school"], ctx_a["admin"], role="academic_team")  # only in A's portfolio
    await login(client, member.email)
    response = await client.post(f"/api/v1/school/students/{ctx_b['students'][0].id}/portfolio/entries", json={"section": "award", "title": "Should be denied"})
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
async def test_patching_an_entry_clears_organization_with_explicit_null(client, db_session):
    # Fix for PATCH silently discarding "clear this field" intent: an explicit `{"organization": null}`
    # must actually clear a previously-set value, not be treated the same as "field omitted"
    # (the previous `if value is not None` merge logic could never tell those two apart).
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-PATCH-Clear")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    created = (await client.post(f"/api/v1/school/students/{student.id}/portfolio/entries", json={"section": "project", "title": "Has org", "organization": "Some Org"})).json()
    assert created["organization"] == "Some Org"

    response = await client.patch(f"/api/v1/school/students/{student.id}/portfolio/entries/{created['id']}", json={"organization": None})
    assert response.status_code == 200, response.text
    assert response.json()["organization"] is None

    portfolio = (await client.get(f"/api/v1/school/students/{student.id}/portfolio")).json()
    entry = portfolio["entries"]["project"][0]
    assert entry["organization"] is None


@pytest.mark.asyncio
async def test_patching_only_title_leaves_other_fields_untouched(client, db_session):
    # Regression check on the clear-field fix: a field genuinely omitted from the payload must still
    # be left alone, not accidentally cleared now that omitted-vs-explicit-null is distinguished.
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-PATCH-Untouched")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    created = (await client.post(f"/api/v1/school/students/{student.id}/portfolio/entries", json={"section": "project", "title": "Draft title", "organization": "Keep me", "description": "Keep me too"})).json()

    response = await client.patch(f"/api/v1/school/students/{student.id}/portfolio/entries/{created['id']}", json={"title": "Final title"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Final title"
    assert body["organization"] == "Keep me"
    assert body["description"] == "Keep me too"


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
async def test_patching_entry_with_null_title_returns_422(client, db_session):
    # title is NOT NULL at the database level, so an explicit `{"title": null}` must be rejected with
    # a 422 (validation error), not silently discarded or attempt a null insert which would raise 500.
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-PATCH-TitleNull")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    # Create entry with a title
    created = (await client.post(f"/api/v1/school/students/{student.id}/portfolio/entries", json={"section": "project", "title": "Original title"})).json()
    original_title = created["title"]
    # Try to PATCH with an explicit null title
    response = await client.patch(f"/api/v1/school/students/{student.id}/portfolio/entries/{created['id']}", json={"title": None})
    assert response.status_code == 422, response.text
    # Verify the title was NOT changed in the database
    portfolio = (await client.get(f"/api/v1/school/students/{student.id}/portfolio")).json()
    entry = portfolio["entries"]["project"][0]
    assert entry["title"] == original_title


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
async def test_deleting_a_nonexistent_entry_is_404(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-DELETE-404")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    response = await client.delete(f"/api/v1/school/students/{student.id}/portfolio/entries/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_deleting_an_already_deleted_entry_is_404(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-DELETE-Twice")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    created = (await client.post(f"/api/v1/school/students/{student.id}/portfolio/entries", json={"section": "project", "title": "Delete me"})).json()
    first = await client.delete(f"/api/v1/school/students/{student.id}/portfolio/entries/{created['id']}")
    assert first.status_code == 204
    second = await client.delete(f"/api/v1/school/students/{student.id}/portfolio/entries/{created['id']}")
    assert second.status_code == 404


@pytest.mark.asyncio
async def test_deleting_an_entry_that_belongs_to_a_different_student_is_404(client, db_session):
    # DELETE had no ownership-mismatch (IDOR) test even though PATCH did -- this is the one
    # destructive endpoint in this feature, so the gap mattered most here.
    from tests.enh005_helpers import login, mk_school
    ctx_a = await mk_school(db_session, label="ENH012-DELETE-A")
    ctx_b = await mk_school(db_session, label="ENH012-DELETE-B")
    await login(client, ctx_a["coordinator"].email)
    created = (await client.post(f"/api/v1/school/students/{ctx_a['students'][0].id}/portfolio/entries", json={"section": "project", "title": "A's entry"})).json()

    await login(client, ctx_b["coordinator"].email)
    response = await client.delete(f"/api/v1/school/students/{ctx_b['students'][0].id}/portfolio/entries/{created['id']}")
    assert response.status_code == 404


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

    # Verify entry actually survived the failed deletion attempt
    await login(client, ctx["coordinator"].email)
    portfolio = (await client.get(f"/api/v1/school/students/{student.id}/portfolio")).json()
    assert len(portfolio["entries"]["project"]) == 1
    assert portfolio["entries"]["project"][0]["id"] == created["id"]


@pytest.mark.asyncio
async def test_coordinator_sets_the_personal_statement(client, db_session):
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-STMT")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    response = await client.patch(f"/api/v1/school/students/{student.id}/portfolio/personal-statement", json={"personal_statement": "I want to study engineering."})
    assert response.status_code == 200, response.text
    assert response.json()["personal_statement"] == "I want to study engineering."

    portfolio = (await client.get(f"/api/v1/school/students/{student.id}/portfolio")).json()
    assert portfolio["personal_statement"] == "I want to study engineering."


@pytest.mark.asyncio
async def test_setting_the_statement_twice_updates_the_same_row(client, db_session):
    from sqlalchemy import func, select as sa_select

    from app.models import PortfolioProfile
    from tests.enh005_helpers import login, mk_school
    ctx = await mk_school(db_session, label="ENH012-STMT-Twice")
    student = ctx["students"][0]
    await login(client, ctx["coordinator"].email)
    await client.patch(f"/api/v1/school/students/{student.id}/portfolio/personal-statement", json={"personal_statement": "First draft."})
    await client.patch(f"/api/v1/school/students/{student.id}/portfolio/personal-statement", json={"personal_statement": "Revised."})
    count = await db_session.scalar(sa_select(func.count()).select_from(PortfolioProfile).where(PortfolioProfile.school_student_id == student.id))
    assert count == 1
    row = await db_session.scalar(sa_select(PortfolioProfile).where(PortfolioProfile.school_student_id == student.id))
    assert row.personal_statement == "Revised."
