"""upc-031 -- GET /partnership/reports/{kind}(.csv) (spec RP1-RP14). Each report is checked against the figure it repeats, read through the
existing route in the same session (AC: each report reconciles with its dashboard figure). Figures are asserted in a fresh manager's scope:
the test database is shared and never truncated."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, University, UniversityAgreement
from app.services import partnership_reports as reports
from app.services.bdm_appointments import IST
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_application, make_head, make_pm, make_user, url
from tests.upc019_helpers import agreement

REPORTS = "/api/v1/partnership/reports"
KINDS = ("pipeline", "expected", "performance", "agreements", "targets")


async def _university(client, db, head, manager=None, **values) -> University:
    await login(client, head)
    made = await create(client, (await catalogue_country(db)).id)
    if manager is not None:
        response = await client.post(url(made["id"], "assign"), json={"primary_manager_user_id": str(manager.id)})
        assert response.status_code == 200, response.text
    if values:
        await db.execute(update(University).where(University.id == uuid.UUID(made["id"])).values(**values))
        await db.commit()
    return await db.get(University, uuid.UUID(made["id"]))


async def _agreement(db, uni, actor, status: str, expiry: date) -> UniversityAgreement:
    if status in ("signed", "active"):
        return await agreement(db, uni, actor, status=status, start=date(2024, 1, 1), expiry=expiry)  # the signed-row CHECK's fields
    a = UniversityAgreement(
        mou_number=f"T-{uuid.uuid4().hex[:10]}", university_id=uni.id, agreement_type="mou", status=status, start_date=date(2024, 1, 1),
        expiry_date=expiry, exclusivity="exclusive", created_by_user_id=actor.id,
    )  # fmt: skip
    db.add(a)
    await db.commit()
    return a


async def _team(db):
    head = await make_head(db)
    return head, await make_pm(db, head)


def _today() -> date:
    return datetime.now(IST).date()


# --- access (RP2, RP4) ---


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(f"{REPORTS}/pipeline")).status_code == 401
    assert (await client.get(f"{REPORTS}/pipeline.csv")).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "overseas"), ("overseas_admin", "overseas"), ("bdm", "overseas"), ("agent", "overseas")])
async def test_other_roles_are_refused_before_the_kind_is_checked(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    for path in ("pipeline", "nonsense", "pipeline.csv", "nonsense.csv"):
        assert (await client.get(f"{REPORTS}/{path}")).status_code == 403, path


@pytest.mark.asyncio
async def test_a_manager_without_a_profile_is_refused(client, db_session):
    await login(client, await make_user(db_session, "partnership_manager", "overseas"))
    assert (await client.get(f"{REPORTS}/pipeline")).status_code == 403


@pytest.mark.asyncio
async def test_an_unknown_kind_is_404_for_a_reader(client, db_session):
    await login(client, await make_head(db_session))
    assert (await client.get(f"{REPORTS}/nonsense")).status_code == 404
    assert (await client.get(f"{REPORTS}/nonsense.csv")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", KINDS)
async def test_every_reader_reads_every_kind(client, db_session, kind):
    for user in (await make_head(db_session), (await _team(db_session))[1]):
        await login(client, user)
        response = await client.get(f"{REPORTS}/{kind}")
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "private, no-store"
        body = response.json()
        assert {"kind", "title", "as_of", "filters", "columns", "items", "totals", "total", "truncated"} <= set(body)
        assert all(set(c) == {"key", "label", "numeric"} for c in body["columns"])
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.get(f"{REPORTS}/{kind}")).status_code == 200


# --- inputs (RP10) ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "query", "words"),
    [
        ("performance", "from=2025-02-30", "From"), ("performance", "to=yesterday", "To"), ("performance", "from=2025-03-10&to=2025-03-01", "period"),
        ("performance", "from=2023-01-01&to=2025-01-01", "366"), ("expected", "window=someday", "window"), ("targets", "month=2025-13", "Month"),
    ],
)  # fmt: skip
async def test_bad_inputs_are_422_naming_the_field(client, db_session, kind, query, words):
    await login(client, await make_head(db_session))
    for path in (kind, f"{kind}.csv"):
        response = await client.get(f"{REPORTS}/{path}?{query}")
        assert response.status_code == 422, response.text
        assert words in response.json()["detail"]


# --- reconciliation (AC) ---


@pytest.mark.asyncio
async def test_pipeline_totals_equal_the_dashboard_overview(client, db_session):
    head, manager = await _team(db_session)
    await _university(client, db_session, head, manager, stage="partner_activated")
    await _university(client, db_session, head, manager, stage="proposal_sent", relationship_strength="at_risk")
    await _university(client, db_session, head, manager, stage="target_university")
    await _university(client, db_session, head, manager, stage="proposal_sent", lost_at=datetime.now(UTC), lost_reason="other")
    await _university(client, db_session, head, manager, stage="partner_activated", active=False)  # inactive: in neither
    await login(client, manager)
    report = (await client.get(f"{REPORTS}/pipeline")).json()
    overview = (await client.get("/api/v1/partnership/dashboard")).json()["overview"]
    assert [c["key"] for c in report["columns"]] == ["country", "total", "partners", "in_progress", "targets", "lost", "at_risk"]
    assert len(report["items"]) == 1 and report["items"][0]["country"] == "United Kingdom"
    assert {k: report["totals"][k] for k in overview} == overview == {"total": 4, "partners": 1, "in_progress": 1, "targets": 1, "at_risk": 1, "lost": 1}


@pytest.mark.asyncio
async def test_expected_this_month_equals_the_dashboard_d13(client, db_session):
    head, manager = await _team(db_session)
    today = _today()
    for stage in ("interested", "meeting_completed"):  # 40% + 60%
        await _university(client, db_session, head, manager, stage=stage, expected_agreement_date=today)
    await _university(client, db_session, head, manager, stage="interested")  # undated
    await _university(client, db_session, head, manager, stage="agreement_signed", expected_agreement_date=today)  # signed: not expected
    await login(client, manager)
    month = (await client.get("/api/v1/partnership/dashboard")).json()["this_month"]
    report = (await client.get(f"{REPORTS}/expected?window=this_month")).json()
    assert report["total"] == month["expected_count"] == 2
    assert report["totals"]["weighted"] == month["expected_weighted"] == 1.0
    assert sorted(r["probability"] for r in report["items"]) == [40, 60]
    assert (await client.get(f"{REPORTS}/expected?window=undated")).json()["total"] == 1
    assert (await client.get(f"{REPORTS}/expected")).json()["total"] == 2  # all = every dated row


@pytest.mark.asyncio
async def test_performance_totals_equal_the_performance_page(client, db_session):
    head, manager = await _team(db_session)
    busy = await _university(client, db_session, head, manager, stage="proposal_sent")
    await _university(client, db_session, head, manager, stage="partner_activated")  # a partner: ranked with zeros
    await _university(client, db_session, head, manager, stage="proposal_sent")  # nothing in the period, not a partner: not ranked
    for _ in range(2):
        await make_application(db_session, busy.id)
    await login(client, manager)
    page = (await client.get("/api/v1/partnership/performance?limit=100")).json()
    report = (await client.get(f"{REPORTS}/performance")).json()
    assert report["total"] == page["total"] == 2
    assert {k: report["totals"][k] for k in page["totals"] if page["totals"][k] is not None} == {k: v for k, v in page["totals"].items() if v is not None}
    assert report["items"][0]["university"] == busy.name and report["items"][0]["applications"] == 2
    assert [r["rank"] for r in report["items"]] == [1, 2]
    keys = [c["key"] for c in report["columns"]]
    assert "leads" not in keys and {"commission_expected", "commission_received"} <= set(keys)  # a U2 role


@pytest.mark.asyncio
async def test_performance_empty_period_is_an_empty_report(client, db_session):
    _, manager = await _team(db_session)
    await login(client, manager)
    response = await client.get(f"{REPORTS}/performance?from=2020-01-01&to=2020-01-31")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [] and body["total"] == 0 and body["totals"]["applications"] == 0
    assert body["filters"] == {"from": "2020-01-01", "to": "2020-01-31"}


@pytest.mark.asyncio
async def test_agreements_lists_expiring_in_scope_soonest_first(client, db_session):
    head, manager = await _team(db_session)
    uni = await _university(client, db_session, head, manager, stage="partner_activated")
    other = await _university(client, db_session, head, None)  # unowned: the head's scope, not the manager's
    today = _today()
    later = await _agreement(db_session, uni, head, "active", today + timedelta(days=80))
    soon = await _agreement(db_session, uni, head, "signed", today + timedelta(days=5))
    await _agreement(db_session, uni, head, "active", today + timedelta(days=200))  # not yet expiring
    await _agreement(db_session, uni, head, "signed", today - timedelta(days=1))  # expired
    await _agreement(db_session, uni, head, "draft", today + timedelta(days=5))  # not in force
    await _agreement(db_session, other, head, "active", today + timedelta(days=10))
    await login(client, manager)
    report = (await client.get(f"{REPORTS}/agreements")).json()
    assert [r["mou_number"] for r in report["items"]] == [soon.mou_number, later.mou_number]
    assert report["items"][0]["days_left"] == 5 and report["items"][0]["status"] == "Signed" and report["items"][0]["owner"] == manager.full_name


@pytest.mark.asyncio
async def test_agreements_for_super_admin_equal_the_menu_list(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    report = (await client.get(f"{REPORTS}/agreements")).json()
    menu = (await client.get("/api/v1/partnership/agreements?status=expiring&limit=1")).json()
    assert report["total"] == menu["total"]


@pytest.mark.asyncio
async def test_targets_total_row_equals_the_targets_team_row(client, db_session):
    head, manager = await _team(db_session)
    second = await make_pm(db_session, head)
    month = _today().strftime("%Y-%m")
    await login(client, head)
    saved = await client.put("/api/v1/partnership/targets", json={"month": month, "items": [
        {"manager_user_id": str(manager.id), "kpi_key": "meetings", "target": 4}, {"manager_user_id": str(second.id), "kpi_key": "meetings", "target": 6}]})  # fmt: skip
    assert saved.status_code == 200, saved.text
    team = (await client.get(f"/api/v1/partnership/targets?month={month}")).json()
    report = (await client.get(f"{REPORTS}/targets?month={month}")).json()
    assert [r["manager"] for r in report["items"]] == [m["manager"]["full_name"] for m in team["managers"]]
    for kpi in team["team"]:
        assert report["totals"][f"{kpi['key']}_target"] == kpi["target"]
        assert report["totals"][f"{kpi['key']}_achieved"] == kpi["achieved"]
    assert report["totals"]["meetings_target"] == 10
    await login(client, manager)
    own = (await client.get(f"{REPORTS}/targets?month={month}")).json()
    assert [r["manager"] for r in own["items"]] == [manager.full_name]


# --- scope (RP3) ---


@pytest.mark.asyncio
async def test_a_manager_sees_only_their_universities(client, db_session):
    head, manager = await _team(db_session)
    other = await make_pm(db_session, head)
    await _university(client, db_session, head, manager)
    await _university(client, db_session, head, other)
    await login(client, manager)
    assert (await client.get(f"{REPORTS}/pipeline")).json()["totals"]["total"] == 1


# --- commission (RP12) ---


@pytest.mark.asyncio
async def test_commission_columns_are_stripped_for_a_non_commission_role(db_session):
    caller = await make_user(db_session, "overseas_admin", "overseas")  # not a reader today; the builder must still strip
    payload = await reports.build(db_session, caller, "performance", {})
    assert not any(c["key"].startswith("commission") for c in payload["columns"])
    assert not any(k.startswith("commission") for row in [*payload["items"], payload["totals"]] for k in row)


# --- row cap (RP11) ---


@pytest.mark.asyncio
async def test_the_screen_shows_the_first_rows_and_says_so(client, db_session, monkeypatch):
    head, manager = await _team(db_session)
    for _ in range(3):
        await _university(client, db_session, head, manager)
    monkeypatch.setattr(reports, "SCREEN_ROWS", 2)
    await login(client, manager)
    body = (await client.get(f"{REPORTS}/expected?window=undated")).json()
    assert (len(body["items"]), body["total"], body["truncated"]) == (2, 3, True)


# --- CSV (RP13, RP14) ---


@pytest.mark.asyncio
async def test_csv_is_the_screen_with_a_bom_a_total_row_and_formula_guard(client, db_session):
    head, manager = await _team(db_session)
    uni = await _university(client, db_session, head, manager, stage="interested", expected_agreement_date=_today())
    await db_session.execute(update(University).where(University.id == uni.id).values(name=f"=HYPERLINK(1) {uuid.uuid4().hex[:6]}"))
    await db_session.commit()
    await login(client, manager)
    response = await client.get(f"{REPORTS}/expected.csv?window=this_month")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["content-disposition"].startswith('attachment; filename="partnership-expected-')
    text = response.content.decode("utf-8")
    assert text.startswith("﻿University,Code,Country,Stage")
    lines = text.strip().splitlines()
    assert len(lines) == 3 and lines[1].startswith("'=HYPERLINK(1)") and lines[2].startswith("Total,")
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.user_id == manager.id, AuditLog.action == "partnership_report.export"))).all()
    assert len(audit) == 1 and audit[0].entity_id == "expected" and audit[0].metadata_json == {"filters": ["window"], "rows": 1}


@pytest.mark.asyncio
async def test_csv_over_the_cap_is_refused_not_cut_short(client, db_session, monkeypatch):
    head, manager = await _team(db_session)
    for _ in range(2):
        await _university(client, db_session, head, manager)
    monkeypatch.setattr(reports, "CSV_ROWS", 1)
    await login(client, manager)
    response = await client.get(f"{REPORTS}/pipeline.csv")
    assert response.status_code == 200  # one country row: under the cap
    response = await client.get(f"{REPORTS}/expected.csv?window=undated")
    assert response.status_code == 422 and "narrow" in response.json()["detail"]
    assert not (await db_session.scalars(select(AuditLog).where(AuditLog.user_id == manager.id, AuditLog.action == "partnership_report.export", AuditLog.entity_id == "expected"))).all()
