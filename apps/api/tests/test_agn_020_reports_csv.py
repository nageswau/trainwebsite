"""AGN-020 (DEC-SCOPE-063) -- the CSV export: headers, BOM, escaping, the row cap, the audit row and the export throttle (spec §5.4,
§5.5; AC3, AC6, AC7, AC10, AC11)."""

import csv
import io

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AuditLog
from app.services import agent_reports
from tests.agn001_helpers import client_for
from tests.agn020_helpers import REPORTS, reports_world

KINDS = ["students", "applications", "enrollments", "universities", "countries", "intakes", "staff"]
COMMISSION_CSV = "/api/v1/workflows/overseas/agent/commissions/report.csv"


@pytest_asyncio.fixture
async def world(db_session):
    return await reports_world(db_session)


async def _exports(db, user) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "agent_report.export").order_by(AuditLog.created_at)
    return list((await db.scalars(stmt.execution_options(populate_existing=True))).all())


async def _audit_rows(db, user) -> int:
    return await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.user_id == user.id))


def _parse(text: str) -> list[list[str]]:
    assert text.startswith("﻿")  # Excel reads the file as UTF-8
    return list(csv.reader(io.StringIO(text[1:])))


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
async def test_csv_matches_the_on_screen_report(world, kind):
    async with client_for(world["master"].email) as c:
        body = (await c.get(f"{REPORTS}/{kind}", params={"limit": "100"})).json()
        response = await c.get(f"{REPORTS}/{kind}.csv")
    assert response.status_code == 200 and response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["cache-control"] == "private, no-store"
    rows = _parse(response.text)
    assert rows[0] == [column["label"] for column in body["columns"]]
    expected = [*body["items"], *([body["totals"]] if body["totals"] else [])]
    as_text = [["" if item[c["key"]] is None else str(item[c["key"]]) for c in body["columns"]] for item in expected]
    assert [[cell.removeprefix("'") for cell in row] for row in rows[1:]] == as_text


@pytest.mark.asyncio
async def test_formula_cells_are_neutralised_and_unicode_survives(world):
    async with client_for(world["master"].email) as c:
        rows = _parse((await c.get(f"{REPORTS}/students.csv")).text)
    names = [row[0] for row in rows[1:]]
    r1, r3 = world["records"]["r1"].full_name, world["records"]["r3"].full_name
    assert f"'{r3}" in names and r3 not in names  # "=cmd …" cannot run as a formula
    assert r1 in names and r1.startswith("Zoë")


@pytest.mark.asyncio
async def test_empty_export_is_the_header_only_and_named_by_its_dates(world):
    async with client_for(world["master"].email) as c:
        response = await c.get(f"{REPORTS}/students.csv", params={"date_from": "2000-01-01", "date_to": "2000-01-01"})
    assert len(_parse(response.text)) == 1
    assert response.headers["content-disposition"] == 'attachment; filename="agency-students-2000-01-01-to-2000-01-01.csv"'
    async with client_for(world["master"].email) as c:
        undated = await c.get(f"{REPORTS}/countries.csv", params={"date_to": "2026-09-30"})
    assert undated.headers["content-disposition"] == 'attachment; filename="agency-countries-all-to-2026-09-30.csv"'


@pytest.mark.asyncio
async def test_each_export_writes_one_audit_row_without_names(world, db_session):
    master = world["master"]
    async with client_for(master.email) as c:
        await c.get(f"{REPORTS}/students", params={"status": "all"})  # an on-screen read writes nothing
        assert await _exports(db_session, master) == []
        await c.get(f"{REPORTS}/students.csv", params={"status": "all", "date_to": "2030-12-31"})
    (row,) = await _exports(db_session, master)
    assert (row.entity_type, row.entity_id) == ("agent_report", "students")
    assert row.metadata_json == {"scope": "agency", "filters": {"status": "all", "date_to": "2030-12-31"}, "rows": 5}
    assert world["records"]["r1"].full_name not in str(row.metadata_json)


@pytest.mark.asyncio
async def test_over_the_cap_is_refused_and_not_audited(world, db_session, monkeypatch):
    monkeypatch.setattr(agent_reports, "CSV_ROW_CAP", 2)
    async with client_for(world["master"].email) as c:
        response = await c.get(f"{REPORTS}/students.csv")
        within = await c.get(f"{REPORTS}/countries.csv")  # two groups: within the cap
    assert response.status_code == 422 and response.json()["detail"] == "This report has more than 2 rows; narrow the filters"
    assert within.status_code == 200
    assert [row.entity_id for row in await _exports(db_session, world["master"])] == ["countries"]


@pytest.mark.asyncio
async def test_refused_exports_write_nothing(world, db_session):
    s3 = world["s3"]["user"]  # Reports off
    async with client_for(s3.email) as c:
        assert (await c.get(f"{REPORTS}/students.csv")).status_code == 403
    async with client_for(world["s1"]["user"].email) as c:
        assert (await c.get(f"{REPORTS}/staff.csv")).status_code == 403
        assert (await c.get(f"{REPORTS}/students.csv", params={"date_from": "nope"})).status_code == 422
    assert await _exports(db_session, s3) == [] and await _exports(db_session, world["s1"]["user"]) == []


@pytest.mark.asyncio
async def test_the_31st_export_in_ten_minutes_is_throttled(world, db_session):
    master = world["master"]
    db_session.add_all(AuditLog(user_id=master.id, action="agent_report.export", entity_type="agent_report", entity_id="countries", metadata_json={}) for _ in range(30))
    await db_session.commit()
    async with client_for(master.email) as c:
        response = await c.get(f"{REPORTS}/countries.csv")
    assert response.status_code == 429
    assert 1 <= int(response.headers["retry-after"]) <= 600
    assert len(await _exports(db_session, master)) == 30  # the refused export is not counted
    async with client_for(world["s1"]["user"].email) as c:  # another user's budget is their own
        assert (await c.get(f"{REPORTS}/countries.csv")).status_code == 200


@pytest.mark.asyncio
async def test_the_commission_csv_still_writes_no_audit_row(world, db_session):
    """DEC-SCOPE-051 R7 is unchanged by AGN-020."""
    async with client_for(world["master"].email) as c:
        before = await _audit_rows(db_session, world["master"])  # after sign-in, which writes its own row
        assert (await c.get(COMMISSION_CSV)).status_code == 200
        assert await _audit_rows(db_session, world["master"]) == before
