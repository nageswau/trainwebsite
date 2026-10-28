"""nehn-016 (DEC-SCOPE-312) -- the recruiter's placement reports in the nehn-009 registry (`completing-soon`, `placement-students`, resource
`reports.placement`) and the read-only training panel on the recruiter candidate page (`GET /recruiter/candidates/{id}/training`).
Population (P1, OD-08 builder's default): opted-in, non-archived IT students only. Every fixture is dated from today (IST) and every read is
narrowed to the fixture's own course: the test database is shared and never truncated."""

import csv
import datetime
import io
import uuid
from zoneinfo import ZoneInfo

import openpyxl
import pytest

from app.core import rbac
from app.models import Attendance, Batch, Company, Interview, JobApplication, JobOffer, PlacementProfile
from app.services.applications import candidate_for_student
from app.services.reports import registry
from tests.bdm001_helpers import login, make_user
from tests.rec038_helpers import make_candidate, make_job
from tests.test_nehn_009_reports import _course, _enrol

pytestmark = pytest.mark.asyncio
API = "/api/v1/reports"
REPORTS = ("completing-soon", "placement-students")
FINANCIAL = ("fee", "fees", "amount", "payment", "payments", "discount", "revenue", "paid", "balance")


def _today() -> datetime.date:
    return datetime.datetime.now(ZoneInfo("Asia/Kolkata")).date()


async def _batch(db, program, days: int) -> Batch:
    """Another batch of `program` whose end date is today + `days`."""
    _, batch, _ = await _course(db, end=_today() + datetime.timedelta(days=days))
    batch.program_id = program.id
    await db.commit()
    return batch


async def _pool(db, student, *, opted_in=True, archived=False):
    candidate = await candidate_for_student(db, student)
    candidate.opted_in = opted_in
    if archived:
        candidate.archived_at = datetime.datetime.now(datetime.UTC)
    await db.commit()
    return candidate


async def _fixture(db) -> dict:
    """Course P. b10 ends in 10 days, b20 in 20 days, b12 in 12 days, b5 in 5 days.
    soon (b10, opted in, 4 classes: 3 present + 1 absent → 75 %, progress 60, readiness "ready"); later (b20, opted in);
    private (b10, not opted in); archived (b10, opted in but archived); dropped (b10 seat dropped, opted in);
    twice (b5 and b12, opted in → one row, b12)."""
    program, b10, _ = await _course(db, end=_today() + datetime.timedelta(days=10))
    b20, b12, b5 = await _batch(db, program, 20), await _batch(db, program, 12), await _batch(db, program, 5)
    soon_seat, soon = await _enrol(db, b10, progress=60, name="Asha N016")
    later_seat, later = await _enrol(db, b20, progress=30, name="Bilal N016")
    _, private = await _enrol(db, b10, name="Chitra N016")
    _, archived = await _enrol(db, b10, name="Dev N016")
    _, dropped = await _enrol(db, b10, status="dropped", name="Esha N016")
    _, twice = await _enrol(db, b5, name="Farah N016")
    second, _ = await _enrol(db, b12, name="Unused")
    second.student_id = twice.id
    for student in (soon, later, dropped, twice):
        await _pool(db, student)
    await _pool(db, private, opted_in=False)
    await _pool(db, archived, archived=True)
    for day, status in enumerate(("present", "present", "present", "absent")):
        db.add(Attendance(student_id=soon.id, batch_id=b10.id, session_date=_today() - datetime.timedelta(days=day + 1), status=status))
    db.add(PlacementProfile(student_id=soon.id, readiness_status="ready"))
    await db.commit()
    return {"program": program, "b10": b10, "b20": b20, "b12": b12, "b5": b5, "soon": soon, "soon_seat": soon_seat, "later": later,
            "later_seat": later_seat, "private": private, "archived": archived, "dropped": dropped, "twice": twice}  # fmt: skip


async def _as(client, db, role):
    user = await make_user(db, role, "global" if role in ("super_admin", "placement_manager") else "it")
    await login(client, user)
    return user


async def _read(client, report, **params) -> dict:
    response = await client.get(f"{API}/{report}", params={"page_size": 200, **params})
    assert response.status_code == 200, response.text
    return response.json()


def _names(body) -> list[str]:
    return [row["student"] for row in body["items"]]


# --- registration, grants ---------------------------------------------------------------------------------------------------------


def test_the_reports_are_registered_under_the_placement_resource_without_financial_columns():
    for report_id in REPORTS:
        report = registry.REPORTS[report_id]
        assert report.resource == "reports.placement" and not report.classes
        assert not [c.key for c in report.columns if any(word in c.key for word in FINANCIAL)]
    assert registry.REPORTS["completing-soon"].filters == ("days", "course_id", "batch_id", "trainer_id", "student")
    assert rbac.CATALOGUE["reports.placement"]["actions"] == ("view", "download")
    for role in ("placement_team", "placement_manager", "it_admin"):
        assert {"reports.placement.view", "reports.placement.download"} <= set(rbac.DEFAULT_GRANTS[role])
        assert "field.financial.view" not in rbac.DEFAULT_GRANTS[role]
    assert not [key for key in rbac.DEFAULT_GRANTS.get("hr_team", ()) if key.startswith("reports.placement.")]  # nehn-017: HR holds its own keys only


def test_days_is_a_whole_number_from_1_to_365():
    report = registry.REPORTS["completing-soon"]
    assert registry.parse(report, [("days", "30")])[0].days == 30
    assert registry.parse(report, [("days", "")])[0].days is None
    for bad in ("0", "366", "-1", "abc", "1.5"):
        with pytest.raises(registry.ReportInputError, match="Completing within"):
            registry.parse(report, [("days", bad)])
    with pytest.raises(registry.ReportInputError):
        registry.parse(registry.REPORTS["enrollments"], [("days", "15")])  # a report that does not declare it refuses it


# --- access -----------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["placement_team", "placement_manager", "it_admin", "super_admin"])
async def test_recruiters_and_admins_see_the_reports_in_the_catalogue(client, db_session, role):
    await _as(client, db_session, role)
    items = {item["id"]: item for item in (await client.get(API)).json()["items"]}
    assert set(REPORTS) <= set(items) and items["completing-soon"]["can_download"] is True


@pytest.mark.parametrize("role", ["hr_team", "trainer", "it_student"])
async def test_other_roles_are_refused(client, db_session, role):
    await _as(client, db_session, role)
    ids = [item["id"] for item in (await client.get(API)).json()["items"]]
    assert not set(REPORTS) & set(ids)
    for report_id in REPORTS:
        assert (await client.get(f"{API}/{report_id}")).status_code == 403
        assert (await client.get(f"{API}/{report_id}.csv")).status_code == 403


async def test_recruiters_get_no_training_report(client, db_session):
    """Read-only progress without admin access: the training pack stays the admins' and trainers'."""
    await _as(client, db_session, "placement_team")
    assert (await client.get(f"{API}/student-courses")).status_code == 403


# --- completing soon (AC1, AC3, edges) --------------------------------------------------------------------------------------------


async def test_a_student_finishing_in_10_days_is_listed_and_one_in_20_is_not(client, db_session):
    f = await _fixture(db_session)
    await _as(client, db_session, "placement_team")
    body = await _read(client, "completing-soon", course_id=str(f["program"].id))
    assert [c["key"] for c in body["columns"]] == [
        "student_code", "student", "phone", "email", "course", "batch", "trainer", "batch_ends", "days_left", "progress", "attendance_pct",
        "readiness", "candidate_status",
    ]
    assert sorted(_names(body)) == ["Asha N016", "Farah N016"]
    soon = next(row for row in body["items"] if row["student"] == "Asha N016")
    assert (soon["days_left"], soon["progress"], soon["attendance_pct"], soon["readiness"], soon["candidate_status"]) == (10, 60, 75.0, "ready", "available")
    assert soon["batch_ends"] == (_today() + datetime.timedelta(days=10)).isoformat() and soon["email"] == f["soon"].email
    assert _names(body) == ["Asha N016", "Farah N016"]  # soonest end first


async def test_a_wider_window_includes_the_later_student(client, db_session):
    f = await _fixture(db_session)
    await _as(client, db_session, "placement_manager")
    assert sorted(_names(await _read(client, "completing-soon", course_id=str(f["program"].id), days="30"))) == ["Asha N016", "Bilal N016", "Farah N016"]
    assert _names(await _read(client, "completing-soon", course_id=str(f["program"].id), days="11")) == ["Asha N016"]  # Farah's latest seat is day 12


async def test_a_student_in_two_batches_is_one_row_on_the_latest_end(client, db_session):
    f = await _fixture(db_session)
    await _as(client, db_session, "placement_team")
    rows = [row for row in (await _read(client, "completing-soon", course_id=str(f["program"].id)))["items"] if row["student"] == "Farah N016"]
    assert len(rows) == 1 and rows[0]["batch"] == f["b12"].name and rows[0]["days_left"] == 12 and rows[0]["attendance_pct"] is None
    assert rows[0]["readiness"] == "preparation"  # no placement profile yet reads as the default


async def test_non_opted_in_archived_and_dropped_students_are_excluded(client, db_session):
    f = await _fixture(db_session)
    await _as(client, db_session, "it_admin")
    names = _names(await _read(client, "completing-soon", course_id=str(f["program"].id), days="365"))
    assert not {"Chitra N016", "Dev N016", "Esha N016"} & set(names)


async def test_a_placed_student_still_appears(client, db_session):
    f = await _fixture(db_session)
    candidate = await candidate_for_student(db_session, f["soon"])
    candidate.status = "placed"
    await db_session.commit()
    await _as(client, db_session, "placement_team")
    row = next(r for r in (await _read(client, "completing-soon", course_id=str(f["program"].id)))["items"] if r["student"] == "Asha N016")
    assert row["candidate_status"] == "placed"


async def test_filters_narrow_and_options_stay_in_the_population(client, db_session):
    f = await _fixture(db_session)
    await _as(client, db_session, "placement_team")
    body = await _read(client, "completing-soon", batch_id=str(f["b10"].id))
    assert _names(body) == ["Asha N016"]
    assert _names(await _read(client, "completing-soon", course_id=str(f["program"].id), student="farah")) == ["Farah N016"]
    batch_ids = {choice["value"] for choice in body["options"]["batches"]}
    assert {str(f["b10"].id), str(f["b12"].id)} <= batch_ids


async def test_downloads_carry_no_financial_column_and_fee_parameters_are_refused(client, db_session):
    f = await _fixture(db_session)
    await _as(client, db_session, "placement_team")
    response = await client.get(f"{API}/completing-soon.csv", params={"course_id": str(f["program"].id)})
    assert response.status_code == 200, response.text
    header = next(csv.reader(io.StringIO(response.text.lstrip("﻿"))))
    assert "Phone" in header and not [h for h in header if any(word in h.lower() for word in FINANCIAL)]
    workbook = openpyxl.load_workbook(io.BytesIO((await client.get(f"{API}/completing-soon.xlsx", params={"course_id": str(f["program"].id)})).content))
    assert [cell.value for cell in next(workbook.active.iter_rows(max_row=1))] == header
    refused = await client.get(f"{API}/completing-soon", params={"include": "fees"})
    assert refused.status_code == 422


async def test_reports_have_no_write_routes(client, db_session):
    await _as(client, db_session, "placement_team")
    for report_id in REPORTS:
        for method in ("post", "put", "patch", "delete"):
            assert (await getattr(client, method)(f"{API}/{report_id}")).status_code == 405


# --- placement report -------------------------------------------------------------------------------------------------------------


async def test_the_placement_report_counts_applications_interviews_offers_and_joinings(client, db_session):
    f = await _fixture(db_session)
    recruiter = await make_user(db_session, "placement_team", "it")
    company = Company(name=f"N016 Co {uuid.uuid4().hex[:6]}", assigned_recruiter_user_id=recruiter.id, created_by_user_id=recruiter.id)
    db_session.add(company)
    await db_session.flush()
    candidate = await candidate_for_student(db_session, f["soon"])
    jobs = [await make_job(db_session, company, recruiter) for _ in range(2)]
    first, second = (JobApplication(job_id=job.id, candidate_id=candidate.id, student_id=f["soon"].id, status="interview") for job in jobs)
    db_session.add_all([first, second])
    await db_session.flush()
    now = datetime.datetime.now(datetime.UTC)
    db_session.add_all([Interview(application_id=first.id, scheduled_at=now), Interview(application_id=first.id, scheduled_at=now),
                        Interview(application_id=second.id, scheduled_at=now),
                        JobOffer(application_id=first.id, status="accepted", joining_status="joined", actual_joining_date=_today()),
                        JobOffer(application_id=second.id, status="offer_received")])  # fmt: skip
    external = await make_candidate(db_session, recruiter)  # an external candidate is not a student: never a row
    db_session.add(JobApplication(job_id=jobs[0].id, candidate_id=external.id, status="sourced"))
    await db_session.commit()
    await _as(client, db_session, "placement_team")
    body = await _read(client, "placement-students", course_id=str(f["program"].id))
    assert [c["key"] for c in body["columns"]] == [
        "student_code", "student", "email", "course", "batch_ends", "progress", "readiness", "candidate_status", "applications", "interviews",
        "offers", "joined",
    ]
    assert sorted(_names(body)) == ["Asha N016", "Bilal N016", "Farah N016"]
    rows = {row["student"]: row for row in body["items"]}
    asha = rows["Asha N016"]
    assert (asha["applications"], asha["interviews"], asha["offers"], asha["joined"], asha["readiness"]) == (2, 3, 2, 1, "ready")
    assert (rows["Bilal N016"]["applications"], rows["Bilal N016"]["joined"]) == (0, 0)
    assert rows["Farah N016"]["batch_ends"] == f["b12"].end_date.isoformat()  # the latest seat


# --- training panel (recruiter candidate page) ------------------------------------------------------------------------------------


def _training_url(candidate_id) -> str:
    return f"/api/v1/recruiter/candidates/{candidate_id}/training"


async def test_the_training_panel_matches_the_student_courses_report(client, db_session):
    f = await _fixture(db_session)
    candidate = await candidate_for_student(db_session, f["soon"])
    await _as(client, db_session, "placement_team")
    response = await client.get(_training_url(candidate.id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["student"] is True and body["readiness"]["readiness_status"] == "ready"
    [seat] = body["seats"]
    assert (seat["course"], seat["batch"], seat["status"], seat["progress"], seat["attendance_pct"], seat["attendance_marked"]) == (
        f["program"].title, f["b10"].name, "active", 60, 75.0, 4,
    )
    assert seat["ends"] == f["b10"].end_date.isoformat() and seat["certificate"] == "Not issued"
    assert set(seat) == {"course", "batch", "trainer", "starts", "ends", "status", "progress", "attendance_pct", "attendance_marked",
                         "assignments_graded", "assignments_total", "assessments_passed", "assessments_total", "certificate"}  # fmt: skip


async def test_the_panel_lists_every_seat_latest_end_first(client, db_session):
    f = await _fixture(db_session)
    candidate = await candidate_for_student(db_session, f["twice"])
    await _as(client, db_session, "placement_manager")
    body = (await client.get(_training_url(candidate.id))).json()
    assert [seat["batch"] for seat in body["seats"]] == [f["b12"].name, f["b5"].name] and body["readiness"]["readiness_status"] == "preparation"


async def test_an_external_candidate_has_no_training(client, db_session):
    recruiter = await _as(client, db_session, "placement_team")
    external = await make_candidate(db_session, recruiter)
    await db_session.commit()
    assert (await client.get(_training_url(external.id))).json() == {"student": False, "seats": [], "readiness": None}


async def test_a_student_outside_the_pool_is_not_found(client, db_session):
    f = await _fixture(db_session)
    private = await candidate_for_student(db_session, f["private"])
    await _as(client, db_session, "placement_team")
    assert (await client.get(_training_url(private.id))).status_code == 404
    assert (await client.get(_training_url(uuid.uuid4()))).status_code == 404


@pytest.mark.parametrize("role", ["hr_team", "it_admin", "trainer", "it_student"])
async def test_the_panel_is_the_recruiters_only(client, db_session, role):
    f = await _fixture(db_session)
    candidate = await candidate_for_student(db_session, f["soon"])
    await _as(client, db_session, role)
    assert (await client.get(_training_url(candidate.id))).status_code == 403


async def test_the_panel_has_no_write_route(client, db_session):
    f = await _fixture(db_session)
    candidate = await candidate_for_student(db_session, f["soon"])
    await _as(client, db_session, "placement_team")
    for method in ("post", "put", "patch", "delete"):
        assert (await getattr(client, method)(_training_url(candidate.id))).status_code == 405
