"""ENH-028 -- pre-filled bulk templates (spec §5.2, AC11): role-gated, one row per portfolio student only, spreadsheet-formula
safe, never cached, and a filled-in template uploads cleanly."""

import csv
import io

import pytest

from app.models import SchoolStaffAssignment
from tests.enh005_helpers import mk_student, mk_user
from tests.enh028_helpers import BASE, RESULTS_URL, login, upload, world

TEMPLATES = [
    (f"{BASE}/academic-team/results/bulk-template", "academic_team", "academic-result", ["academic_year", "term", "subject", "max_marks", "marks_obtained", "grade", "teacher_remarks"]),
    (f"{BASE}/psychometric-team/records/bulk-template", "psychometric_team", "psychometric-record", ["assessment_type", "report_url", "test_date", "strengths", "interest_areas", "personality_indicators", "recommended_careers", "recommended_stream", "counsellor_remarks", "parent_discussion_on", "parent_discussion_notes", "follow_up_on"]),
    (f"{BASE}/academic-team/test-prep-records/bulk-template", "academic_team", "test-prep-record", ["test_type", "target_score"]),
    (f"{BASE}/academic-team/language-records/bulk-template", "academic_team", "language-record", ["language", "level"]),
]


def _rows(response) -> list[list[str]]:
    return list(csv.reader(io.StringIO(response.text)))


@pytest.mark.asyncio
@pytest.mark.parametrize(("url", "role", "slug", "columns"), TEMPLATES, ids=[t[2] for t in TEMPLATES])
async def test_each_template_lists_only_portfolio_students(client, db_session, url, role, slug, columns):
    w = await world(db_session, role=role)
    await login(client, w["member"].email)
    response = await client.get(url)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == f"attachment; filename={slug}-bulk-template.csv"
    assert response.headers["cache-control"] == "private, no-store"
    rows = _rows(response)
    assert rows[0] == ["student_code", "student_name", "school_name", *columns]
    assert sorted(r[0] for r in rows[1:]) == sorted(s.student_code for s in w["students"])
    assert all(r[3:] == [""] * len(columns) for r in rows[1:])
    assert w["outsider"].student_code not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(("url", "role"), [(t[0], "school_coordinator" if t[1] == "academic_team" else "academic_team") for t in TEMPLATES])
async def test_other_roles_are_refused(client, db_session, url, role):
    w = await world(db_session)
    other = w["coordinator"] if role == "school_coordinator" else w["member"]
    await login(client, other.email)
    assert (await client.get(url)).status_code == 403


@pytest.mark.asyncio
async def test_a_formula_looking_name_is_neutralised(client, db_session):
    w = await world(db_session)
    trap = await mk_student(db_session, w["school"], w["coordinator"], '=HYPERLINK("http://evil.example")')
    trap.full_name = '=HYPERLINK("http://evil.example")'
    await db_session.commit()
    await login(client, w["member"].email)
    rows = _rows(await client.get(TEMPLATES[0][0]))
    [row] = [r for r in rows if r[0] == trap.student_code]
    assert row[1] == '\'=HYPERLINK("http://evil.example")'


@pytest.mark.asyncio
async def test_an_empty_portfolio_gets_the_header_only(client, db_session):
    member = await mk_user(db_session, role="academic_team", name="No schools yet")
    await db_session.commit()
    await login(client, member.email)
    rows = _rows(await client.get(TEMPLATES[0][0]))
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_a_filled_in_template_uploads_cleanly(client, db_session):
    w = await world(db_session)
    await login(client, w["member"].email)
    rows = _rows(await client.get(TEMPLATES[0][0]))
    rows[1][3:8] = ["2026", "Term 1", "Mathematics", "100", "91"]
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    report = (await upload(client, RESULTS_URL, buffer.getvalue().encode())).json()
    assert (report["total_rows"], report["accepted_count"]) == (1, 1)


@pytest.mark.asyncio
async def test_a_multi_school_portfolio_is_ordered_by_school_then_student(client, db_session):
    w = await world(db_session)
    second = w["outsider"]
    db_session.add(SchoolStaffAssignment(user_id=w["member"].id, school_id=second.school_id, role="academic_team", assigned_by_user_id=w["admin"].id))
    await db_session.commit()
    await login(client, w["member"].email)
    rows = _rows(await client.get(TEMPLATES[0][0]))[1:]
    assert [(r[2], r[1]) for r in rows] == sorted((r[2], r[1]) for r in rows)
    assert second.student_code in [r[0] for r in rows]
