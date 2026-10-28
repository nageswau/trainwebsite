"""nehn-009 (DEC-SCOPE-303) -- the report framework: a registry of reports, one catalogue filtered by the caller's grants, a paged JSON
read and CSV/xlsx downloads of the same rows and columns, the standard filter model (an undeclared filter is a 422), a row cap, a
throttle and an audit row per download. The pilot report is `enrollments` (resource `reports.training`)."""

import csv
import datetime
import io
import uuid
from datetime import UTC
from datetime import datetime as dt

import openpyxl
import pytest
from sqlalchemy import delete, func, select

from app.api import reports as reports_api
from app.core import rbac
from app.models import AuditLog, Batch, Enrollment, Program, RolePermission
from app.services.reports import registry
from tests.bdm001_helpers import login, make_user

pytestmark = pytest.mark.asyncio
API = "/api/v1/reports"
URL = f"{API}/enrollments"


async def _course(db, trainer=None, *, end=datetime.date(2020, 2, 1)):
    """A fresh programme and batch (its trainer fresh unless given). Dated in the past so it never crowds the seeded batches."""
    tag = uuid.uuid4().hex[:8]
    trainer = trainer or await make_user(db, "trainer", "it", name=f"Trainer {tag}")
    program = Program(
        slug=f"n009-{tag}", title=f"N009 Course {tag}", category="Testing", summary="-", duration="1 month", eligibility="-", fees=1000,
        certification="-", placement_assistance="-", trainer_name="-",
    )
    db.add(program)
    await db.flush()
    batch = Batch(
        program_id=program.id, trainer_id=trainer.id, name=f"N009-{tag}", start_date=datetime.date(2020, 1, 1), end_date=end,
        schedule="-", capacity=40, enrollment_open=False, status="completed",
    )
    db.add(batch)
    await db.commit()
    return program, batch, trainer


async def _enrol(db, batch, *, on=datetime.date(2020, 1, 10), status="active", progress=40, name=None):
    tag = uuid.uuid4().hex[:8]
    student = await make_user(db, "it_student", "it", name=name or f"Learner {tag}")
    student.student_code = tag[:8].upper()
    enrollment = Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"N009-{tag}", enrolled_on=on, status=status, progress_percent=progress)
    db.add(enrollment)
    await db.commit()
    return enrollment, student


async def _as(client, db, role, division="it"):
    user = await make_user(db, role, division)
    await login(client, user)
    return user


def _codes(body) -> list[str]:
    return [row["enrollment_code"] for row in body["items"]]


# --- catalogue (AC1) --------------------------------------------------------------------------------------------------------------


def test_the_training_reports_resource_is_in_the_catalogue_and_seeded_to_it_admin_and_trainer():
    assert rbac.CATALOGUE["reports.training"]["actions"] == ("view", "download")
    holders = {role for role, keys in rbac.DEFAULT_GRANTS.items() if "reports.training.view" in keys}
    assert holders == {"it_admin", "trainer"} == {role for role, keys in rbac.DEFAULT_GRANTS.items() if "reports.training.download" in keys}


def test_the_pilot_is_registered_with_every_standard_filter_but_recruiter():
    report = registry.REPORTS["enrollments"]
    assert report.resource == "reports.training"
    # nehn-011: attendance_below is the attendance report's; nehn-016: days is the completing-soon window
    assert set(report.filters) == set(registry.STANDARD) - {"recruiter_id", "attendance_below", "days"}


def test_register_refuses_a_duplicate_an_unknown_filter_or_an_unknown_resource():
    report = registry.REPORTS["enrollments"]
    with pytest.raises(ValueError):
        registry.register(report)
    with pytest.raises(ValueError):
        registry.register(registry.Report(**{**report.__dict__, "id": "x1", "filters": ("colour",)}))
    with pytest.raises(ValueError):
        registry.register(registry.Report(**{**report.__dict__, "id": "x2", "resource": "reports.nothing"}))
    assert "x1" not in registry.REPORTS and "x2" not in registry.REPORTS


@pytest.mark.parametrize("role", ["it_admin", "trainer"])
async def test_the_catalogue_lists_the_report_for_a_role_holding_view(client, db_session, role):
    await _as(client, db_session, role)
    response = await client.get(API)
    assert response.status_code == 200 and response.headers["cache-control"] == "private, no-store"
    item = next(i for i in response.json()["items"] if i["id"] == "enrollments")
    assert item["title"] == "Enrollments" and item["can_download"] is True
    assert set(item["filters"]) == set(registry.REPORTS["enrollments"].filters)


async def test_the_catalogue_is_empty_for_a_role_without_the_grant(client, db_session):
    await _as(client, db_session, "hr_team")  # placement_team holds nehn-016's reports.placement
    response = await client.get(API)
    assert response.status_code == 200 and response.json() == {"items": []}


async def test_the_catalogue_needs_a_session(client):
    assert (await client.get(API)).status_code == 401


async def test_revoking_download_keeps_the_read_and_refuses_the_file(client, db_session):
    await _as(client, db_session, "trainer")
    await db_session.execute(delete(RolePermission).where(RolePermission.role == "trainer", RolePermission.resource == "reports.training", RolePermission.action == "download"))
    await db_session.commit()
    try:
        item = next(i for i in (await client.get(API)).json()["items"] if i["id"] == "enrollments")
        assert item["can_download"] is False
        assert (await client.get(URL)).status_code == 200
        refused = await client.get(f"{URL}.csv")
        assert refused.status_code == 403 and refused.json()["detail"] == reports_api.DOWNLOAD_REFUSED
    finally:
        db_session.add(RolePermission(role="trainer", resource="reports.training", action="download"))
        await db_session.commit()


# --- read: gate order -------------------------------------------------------------------------------------------------------------


async def test_unknown_report_is_404_and_no_grant_is_403(client, db_session):
    await _as(client, db_session, "placement_team")
    assert (await client.get(f"{API}/nothing")).status_code == 404
    assert (await client.get(f"{API}/nothing.csv")).status_code == 404
    refused = await client.get(URL)
    assert refused.status_code == 403 and refused.json()["detail"] == reports_api.VIEW_REFUSED
    assert (await client.get(f"{URL}.xlsx")).status_code == 403


async def test_a_refused_caller_gets_403_before_any_input_check(client, db_session):
    await _as(client, db_session, "placement_team")
    assert (await client.get(URL, params={"from": "garbage"})).status_code == 403


# --- read: shape, paging, scope ---------------------------------------------------------------------------------------------------


async def test_the_read_returns_columns_items_paging_and_options(client, db_session):
    program, batch, trainer = await _course(db_session)
    enrollment, student = await _enrol(db_session, batch, progress=55)
    await _as(client, db_session, "it_admin")
    response = await client.get(URL, params={"course_id": str(program.id)})
    assert response.status_code == 200 and response.headers["cache-control"] == "private, no-store"
    body = response.json()
    assert [c["key"] for c in body["columns"]] == [
        "enrollment_code", "student_code", "student", "course", "batch", "trainer", "enrolled_on", "batch_ends", "status", "progress",
    ]
    assert body["items"] == [{
        "enrollment_code": enrollment.enrollment_code, "student_code": student.student_code, "student": student.full_name,
        "course": program.title, "batch": batch.name, "trainer": trainer.full_name, "enrolled_on": "2020-01-10", "batch_ends": "2020-02-01",
        "status": "active", "progress": 55,
    }]
    assert body["total"] == 1 and body["page"] == 1 and body["page_size"] == 50
    assert body["applied"] == {"course_id": str(program.id)}
    assert set(body["filters"]) == set(registry.REPORTS["enrollments"].filters)
    assert {"value": str(program.id), "label": program.title} in body["options"]["courses"]
    assert {"value": str(batch.id), "label": batch.name} in body["options"]["batches"]
    assert {"value": str(trainer.id), "label": trainer.full_name} in body["options"]["trainers"]
    assert {"value": "active", "label": "active"} in body["options"]["statuses"]


async def test_paging_splits_the_sorted_rows(client, db_session):
    program, batch, _ = await _course(db_session)
    made = [await _enrol(db_session, batch, on=datetime.date(2020, 1, day)) for day in (1, 2, 3, 4, 5)]
    newest_first = [e.enrollment_code for e, _ in reversed(made)]
    await _as(client, db_session, "it_admin")
    pages = [(await client.get(URL, params={"course_id": str(program.id), "page_size": 2, "page": n})).json() for n in (1, 2, 3, 4)]
    assert [_codes(p) for p in pages] == [newest_first[:2], newest_first[2:4], newest_first[4:], []]
    assert all(p["total"] == 5 for p in pages)


async def test_a_trainer_sees_only_their_own_batches(client, db_session):
    trainer = await _as(client, db_session, "trainer")
    mine_program, mine, _ = await _course(db_session, trainer)
    other_program, other, other_trainer = await _course(db_session)
    own, _ = await _enrol(db_session, mine)
    await _enrol(db_session, other)
    body = (await client.get(URL)).json()
    assert _codes(body) == [own.enrollment_code]
    assert body["options"]["trainers"] == [{"value": str(trainer.id), "label": trainer.full_name}]
    assert [o["value"] for o in body["options"]["batches"]] == [str(mine.id)]
    assert [o["value"] for o in body["options"]["courses"]] == [str(mine_program.id)]
    # Another trainer's id, batch or course narrows the trainer's own scope to nothing -- it reveals nothing (DEC-SCOPE-303 R4).
    for params in ({"trainer_id": str(other_trainer.id)}, {"batch_id": str(other.id)}, {"course_id": str(other_program.id)}):
        response = await client.get(URL, params=params)
        assert response.status_code == 200 and response.json()["items"] == [] and response.json()["total"] == 0


async def test_a_role_granted_the_report_without_a_scope_rule_sees_no_rows(client, db_session):
    await db_session.merge(RolePermission(role="accountant", resource="reports.training", action="view"))
    await db_session.commit()
    try:
        _, batch, _ = await _course(db_session)
        await _enrol(db_session, batch)
        await _as(client, db_session, "accountant", "global")
        body = (await client.get(URL)).json()
        assert body["items"] == [] and body["total"] == 0 and body["options"]["batches"] == []
    finally:
        await db_session.execute(delete(RolePermission).where(RolePermission.role == "accountant", RolePermission.resource == "reports.training"))
        await db_session.commit()


async def test_super_admin_sees_every_row(client, db_session):
    program, batch, _ = await _course(db_session)
    enrollment, _ = await _enrol(db_session, batch)
    await _as(client, db_session, "super_admin", "global")
    assert _codes((await client.get(URL, params={"course_id": str(program.id)})).json()) == [enrollment.enrollment_code]


# --- the filters (AC2, AC3) -------------------------------------------------------------------------------------------------------


async def test_each_declared_filter_narrows_the_rows(client, db_session):
    program, batch, trainer = await _course(db_session, end=datetime.date(2020, 3, 31))
    _, batch2, trainer2 = await _course(db_session, end=datetime.date(2020, 6, 30))
    batch2.program_id = program.id  # two batches of one course, two trainers
    await db_session.commit()
    a, sa = await _enrol(db_session, batch, on=datetime.date(2020, 1, 5), status="active", name="Asha Zeta")
    b, _ = await _enrol(db_session, batch, on=datetime.date(2020, 1, 15), status="dropped")
    c, _ = await _enrol(db_session, batch2, on=datetime.date(2020, 1, 25), status="active")
    await _as(client, db_session, "it_admin")
    base = {"course_id": str(program.id)}

    async def codes(**params):
        response = await client.get(URL, params={**base, **params})
        assert response.status_code == 200, response.text
        return set(_codes(response.json()))

    everyone = {a.enrollment_code, b.enrollment_code, c.enrollment_code}
    assert await codes() == everyone
    assert await codes(batch_id=str(batch2.id)) == {c.enrollment_code}
    assert await codes(trainer_id=str(trainer.id)) == {a.enrollment_code, b.enrollment_code}
    assert await codes(trainer_id=str(trainer2.id)) == {c.enrollment_code}
    assert await codes(status="dropped") == {b.enrollment_code}
    assert await codes(status="nothing-like-it") == set()
    assert await codes(**{"from": "2020-01-15"}) == {b.enrollment_code, c.enrollment_code}  # inclusive
    assert await codes(to="2020-01-15") == {a.enrollment_code, b.enrollment_code}  # inclusive
    assert await codes(**{"from": "2020-01-15", "to": "2020-01-15"}) == {b.enrollment_code}
    assert await codes(completion_from="2020-04-01") == {c.enrollment_code}
    assert await codes(completion_to="2020-03-31") == {a.enrollment_code, b.enrollment_code}
    assert await codes(student=sa.student_code.lower()) == {a.enrollment_code}  # the code, any case
    assert await codes(student="sha ze") == {a.enrollment_code}  # part of the name
    assert await codes(student=sa.email.split("@")[0].upper()) == {a.enrollment_code}  # part of the email
    assert await codes(student="%") == set()  # a wildcard is a literal character


async def test_latest_takes_the_n_most_recent_and_combines_with_a_range(client, db_session):
    program, batch, _ = await _course(db_session)
    made = [await _enrol(db_session, batch, on=datetime.date(2020, 1, day)) for day in (1, 2, 3, 4, 5)]
    await _as(client, db_session, "it_admin")
    body = (await client.get(URL, params={"course_id": str(program.id), "latest": 2})).json()
    assert _codes(body) == [made[4][0].enrollment_code, made[3][0].enrollment_code] and body["total"] == 2
    ranged = (await client.get(URL, params={"course_id": str(program.id), "latest": 2, "to": "2020-01-03"})).json()
    assert _codes(ranged) == [made[2][0].enrollment_code, made[1][0].enrollment_code]
    paged = (await client.get(URL, params={"course_id": str(program.id), "latest": 3, "page_size": 2, "page": 2})).json()
    assert _codes(paged) == [made[2][0].enrollment_code] and paged["total"] == 3


async def test_empty_values_count_as_not_given(client, db_session):
    program, batch, _ = await _course(db_session)
    enrollment, _ = await _enrol(db_session, batch)
    await _as(client, db_session, "it_admin")
    response = await client.get(URL, params={"course_id": str(program.id), "status": "", "from": "", "student": "  ", "latest": ""})
    assert response.status_code == 200 and _codes(response.json()) == [enrollment.enrollment_code]
    assert response.json()["applied"] == {"course_id": str(program.id)}


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"recruiter_id": str(uuid.uuid4())}, "This report can't be filtered by Recruiter"),
        ({"colour": "red"}, "This report can't be filtered by colour"),
        ({"from": "2020-02-01", "to": "2020-01-01"}, "'From' must be on or before 'To'"),
        ({"completion_from": "2020-02-01", "completion_to": "2020-01-01"}, "'Completion from' must be on or before 'Completion to'"),
        ({"from": "01/02/2020"}, "Enter From as a date (YYYY-MM-DD)"),
        ({"to": "2020-02-30"}, "Enter To as a date (YYYY-MM-DD)"),
        ({"course_id": "abc"}, "Choose a course from the list"),
        ({"trainer_id": "abc"}, "Choose a trainer from the list"),
        ({"latest": "0"}, "Latest must be a whole number from 1 to 1,000"),
        ({"latest": "1001"}, "Latest must be a whole number from 1 to 1,000"),
        ({"latest": "ten"}, "Latest must be a whole number from 1 to 1,000"),
        ({"page": "0"}, "Page must be a whole number from 1"),
        ({"page_size": "201"}, "Rows per page must be a whole number from 1 to 200"),
        ({"student": "x" * 101}, "Search for a student with at most 100 characters"),
        ({"status": "x" * 31}, "Choose a status from the list"),
    ],
)
async def test_bad_or_undeclared_filters_are_422_naming_the_field(client, db_session, params, message):
    await _as(client, db_session, "it_admin")
    for url in (URL, f"{URL}.csv"):
        response = await client.get(url, params=params)
        assert response.status_code == 422 and response.json()["detail"] == message, (url, response.text)


async def test_a_repeated_filter_is_422(client, db_session):
    await _as(client, db_session, "it_admin")
    response = await client.get(f"{URL}?status=active&status=dropped")
    assert response.status_code == 422 and response.json()["detail"] == "Give Status once"


def test_parse_reads_typed_values():
    report = registry.REPORTS["enrollments"]
    course = uuid.uuid4()
    filters, page, size = registry.parse(report, [("from", "2020-01-01"), ("course_id", str(course)), ("latest", "7"), ("page", "3")])
    assert filters.date_from == datetime.date(2020, 1, 1) and filters.course_id == course and filters.latest == 7
    assert (page, size) == (3, registry.PAGE_SIZE)
    assert filters.given == {"from": "2020-01-01", "course_id": str(course), "latest": "7"}  # paging is not a filter


# --- downloads (AC4, AC5) ---------------------------------------------------------------------------------------------------------


def _csv_rows(text: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text.lstrip("﻿"))))


async def test_json_csv_and_xlsx_hold_the_same_rows_and_columns(client, db_session):
    program, batch, _ = await _course(db_session)
    for day in (1, 2, 3):
        await _enrol(db_session, batch, on=datetime.date(2020, 1, day), progress=day * 10)
    await _as(client, db_session, "it_admin")
    params = {"course_id": str(program.id)}
    body = (await client.get(URL, params={**params, "page_size": 200})).json()
    labels = [c["label"] for c in body["columns"]]
    shown = [["" if row[c["key"]] is None else str(row[c["key"]]) for c in body["columns"]] for row in body["items"]]

    csv_response = await client.get(f"{URL}.csv", params=params)
    assert csv_response.status_code == 200 and csv_response.headers["content-type"].startswith("text/csv")
    assert csv_response.headers["cache-control"] == "private, no-store"
    assert csv_response.headers["content-disposition"].startswith('attachment; filename="enrollments-')
    assert _csv_rows(csv_response.text) == [labels, *shown]

    xlsx_response = await client.get(f"{URL}.xlsx", params=params)
    assert xlsx_response.status_code == 200 and xlsx_response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    sheet = openpyxl.load_workbook(io.BytesIO(xlsx_response.content)).active
    cells = [[cell for cell in row] for row in sheet.iter_rows(values_only=True)]
    assert list(cells[0]) == labels and len(cells) == 4
    as_text = lambda v: v.date().isoformat() if isinstance(v, dt) else ("" if v is None else str(v))  # noqa: E731
    assert [[as_text(v) for v in row] for row in cells[1:]] == shown


async def test_each_download_writes_one_audit_row_with_the_filters(client, db_session):
    program, batch, _ = await _course(db_session)
    await _enrol(db_session, batch)
    user = await _as(client, db_session, "it_admin")
    for fmt in ("csv", "xlsx"):
        assert (await client.get(f"{URL}.{fmt}", params={"course_id": str(program.id), "status": "active", "page": "2"})).status_code == 200
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "report.export").order_by(AuditLog.created_at))).all()
    assert [(r.action, r.entity_type, r.entity_id) for r in rows] == [("report.export", "report", "enrollments")] * 2
    assert [r.metadata_json for r in rows] == [
        {"filters": {"course_id": str(program.id), "status": "active"}, "rows": 1, "format": fmt} for fmt in ("csv", "xlsx")
    ]


async def test_reads_and_refused_downloads_write_no_audit(client, db_session):
    user = await _as(client, db_session, "it_admin")
    await client.get(URL)
    await client.get(f"{URL}.csv", params={"from": "nope"})
    await client.get(f"{API}/nothing.csv")
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "report.export")) == 0


async def test_an_export_over_the_cap_is_refused_not_cut_short(client, db_session, monkeypatch):
    monkeypatch.setattr(registry, "EXPORT_CAP", 2)
    program, batch, _ = await _course(db_session)
    for day in (1, 2, 3):
        await _enrol(db_session, batch, on=datetime.date(2020, 1, day))
    user = await _as(client, db_session, "it_admin")
    response = await client.get(f"{URL}.csv", params={"course_id": str(program.id)})
    assert response.status_code == 422 and response.json()["detail"] == "This report has more than 2 rows; narrow the filters"
    assert (await client.get(f"{URL}.csv", params={"course_id": str(program.id), "latest": 2})).status_code == 200  # latest fits
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "report.export")) == 1


async def test_downloads_are_throttled_from_the_callers_own_audit_rows(client, db_session):
    user = await _as(client, db_session, "it_admin")
    now = dt.now(UTC)
    for _ in range(30):
        db_session.add(AuditLog(user_id=user.id, action="report.export", entity_type="report", entity_id="enrollments", metadata_json={}, created_at=now))
    await db_session.commit()
    response = await client.get(f"{URL}.xlsx")
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "report.export")) == 30


# --- the field policy (nehn-008) ----------------------------------------------------------------------------------------------------


async def test_a_tagged_column_follows_its_field_grant_on_screen_and_in_files(client, db_session, monkeypatch):
    report = registry.REPORTS["enrollments"]
    tagged = registry.Report(**{**report.__dict__, "columns": tuple(
        registry.Column(c.key, c.label, "financial" if c.key == "progress" else c.cls) for c in report.columns
    )})
    monkeypatch.setitem(registry.REPORTS, "enrollments", tagged)
    program, batch, _ = await _course(db_session)
    await _enrol(db_session, batch)
    params = {"course_id": str(program.id)}
    await _as(client, db_session, "it_admin")  # no field.financial.view
    body = (await client.get(URL, params=params)).json()
    assert "progress" not in [c["key"] for c in body["columns"]] and "progress" not in body["items"][0]
    assert "Progress %" not in _csv_rows((await client.get(f"{URL}.csv", params=params)).text)[0]
    await _as(client, db_session, "super_admin", "global")
    assert "progress" in [c["key"] for c in (await client.get(URL, params=params)).json()["columns"]]
    assert "Progress %" in _csv_rows((await client.get(f"{URL}.csv", params=params)).text)[0]
