"""ccrm-053 (DEC-SCOPE-325, PF1-PF10) -- counselor performance: the Overseas/IT lead split and the intake and lead-division filters on the
counselor's own report (GET /counselor/performance), and the Overseas Admin's list of every overseas counselor, its CSV / xlsx and the
per-counselor report (GET /overseas-admin/counselor-performance[.csv|.xlsx|/{id}]).

The test database is shared and never truncated, so every figure is read off counselors the test made itself, over a fixed past period."""

import csv
import io
import re
import uuid
from datetime import datetime

import pytest
from sqlalchemy import select

from app.models import AuditLog, Enquiry, LeadQualification, OverseasApplication, VisaCase
from tests.agn003_helpers import mk_university
from tests.bdm001_helpers import login, make_user
from tests.test_ccrm_036_performance import add, me, values
from tests.test_mgmt_018_counseling import IN, OUT, PERIOD, handed

pytestmark = pytest.mark.asyncio

SELF = "/api/v1/counselor/performance"
ADMIN = "/api/v1/overseas-admin/counselor-performance"


async def lead(db, owner, *, division: str = "overseas", at: datetime = IN, intake: str | None = None) -> Enquiry:
    row = await add(db, Enquiry(division=division, name=f"Lead {uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:8]}@example.local", phone="9876543210",
                                subject="Course", message="", source="website", status="follow_up", owner_id=owner.id, created_at=at))  # fmt: skip
    if intake is not None:
        await add(db, LeadQualification(lead_id=row.id, intake=intake, updated_by_user_id=owner.id))
    return row


async def application(db, university, counselor, intake: str, status: str = "enquiry") -> OverseasApplication:
    student = await make_user(db, "overseas_student", "overseas")
    return await add(db, OverseasApplication(university_id=university.id, student_id=student.id, counselor_id=counselor.id, intake=intake, status=status))


async def visa(db, app, status: str) -> None:
    decided = status in {"approved", "refused"}
    await add(db, VisaCase(application_id=app.id, visa_status=status, decision=status if decided else None, status="decision" if decided else "checklist"))


async def mixed_caseload(db, counselor) -> None:
    """3 leads in the period (2 overseas, 1 IT; 2 with intake Sep 2027), 1 outside it; 3 applications (2 for Sep 2027, one approved)."""
    await lead(db, counselor, intake="Sep 2027")
    await lead(db, counselor, division="it", intake="Sep 2027")
    await lead(db, counselor, intake="Jan 2028")
    await lead(db, counselor, at=OUT)
    university = await mk_university(db)
    approved = await application(db, university, counselor, "Sep 2027", "visa_documentation")
    await visa(db, approved, "approved")
    await application(db, university, counselor, "Sep 2027")
    await application(db, university, counselor, "Fall 2027")  # legacy free text: never matches the picker format (PF2)


async def get(client, url: str, **params):
    return await client.get(url, params={**PERIOD, **params})


# --- the counselor's own report (AC1, AC3, AC4, AC5) ---------------------------------------------------------------------------
async def test_the_lead_split_sums_to_the_leads_total(client, db_session):
    counselor = await me(client, db_session)
    await mixed_caseload(db_session, counselor)
    response = await get(client, SELF)
    assert response.status_code == 200, response.text
    period = values(response.json(), "period")
    assert (period["leads"], period["leads_overseas"], period["leads_it"]) == (3, 2, 1)


async def test_the_intake_filter_narrows_the_lead_and_application_figures(client, db_session):
    counselor = await me(client, db_session)
    await mixed_caseload(db_session, counselor)
    body = (await get(client, SELF, intake="Sep 2027")).json()
    period, now = values(body, "period"), values(body, "now")
    assert (period["leads"], period["leads_overseas"], period["leads_it"]) == (2, 1, 1)
    assert (now["applications"], now["students"], now["visas_approved"]) == (2, 2, 1)
    assert body["applications"]["total"] == {"applications": 2, "students": 2}
    assert body["intake"] == "Sep 2027"
    unfiltered = values((await get(client, SELF)).json(), "now")
    assert unfiltered["applications"] == 3


async def test_the_division_filter_narrows_the_lead_figures_only(client, db_session):
    counselor = await me(client, db_session)
    await mixed_caseload(db_session, counselor)
    body = (await get(client, SELF, division="it")).json()
    period = values(body, "period")
    assert (period["leads"], period["leads_overseas"], period["leads_it"]) == (1, 0, 1)
    assert values(body, "now")["applications"] == 3
    assert body["division"] == "it"


@pytest.mark.parametrize("params", [{"intake": "Fall 2027"}, {"intake": "Sep"}, {"intake": "x" * 200}, {"division": "global"}])
async def test_a_malformed_filter_is_422(client, db_session, params):
    await me(client, db_session)
    assert (await get(client, SELF, **params)).status_code == 422


async def test_the_counselor_cannot_name_another_counselor(client, db_session):
    other = await make_user(db_session, "counselor", "overseas")
    await mixed_caseload(db_session, other)
    await me(client, db_session)
    period = values((await get(client, SELF, counselor_id=str(other.id))).json(), "period")
    assert period["leads"] == 0  # the extra parameter is ignored: still their own (empty) figures
    assert (await get(client, ADMIN)).status_code == 403
    assert (await get(client, f"{ADMIN}/{other.id}")).status_code == 403


# --- the Overseas Admin's list (AC2, AC6) ----------------------------------------------------------------------------------------
async def as_admin(client, db, role: str = "overseas_admin"):
    client.cookies.clear()
    user = await make_user(db, role, "overseas" if role == "overseas_admin" else "global")
    await login(client, user)
    return user


def row(body: dict, user) -> dict | None:
    return next((r for r in body["items"] if r["id"] == str(user.id)), None)


async def test_the_admin_lists_every_overseas_counselor_with_their_figures(client, db_session):
    busy = await make_user(db_session, "counselor", "overseas")
    await mixed_caseload(db_session, busy)
    await handed(db_session, await lead(db_session, busy), busy, IN)
    idle = await make_user(db_session, "counselor", "overseas")
    it_counselor = await make_user(db_session, "counselor", "it")
    await as_admin(client, db_session)

    response = await get(client, ADMIN)
    assert response.status_code == 200, response.text
    body = response.json()
    mine = row(body, busy)
    assert (mine["leads"], mine["leads_overseas"], mine["leads_it"], mine["leads_assigned"]) == (4, 3, 1, 1)
    assert (mine["applications"], mine["students"], mine["visas_approved"], mine["visas_refused"], mine["enrollments"]) == (3, 3, 1, 0, 0)
    assert row(body, idle)["leads"] == 0 and row(body, idle)["applications"] == 0  # PF7: zero activity still listed
    assert row(body, it_counselor) is None  # overseas counselors only
    assert [c["key"] for c in body["columns"]][:4] == ["full_name", "leads", "leads_overseas", "leads_it"]
    # Browser QA-01: the admin reads about the counselor, never "you"
    assert not [c["key"] for c in body["columns"] if re.search(r"\byour?\b", c["definition"], re.IGNORECASE)]
    assert "revenue" not in response.text.lower()
    total = body["totals"]
    for key in ("leads", "leads_overseas", "leads_it", "applications", "visas_approved"):
        assert total[key] == sum(r[key] for r in body["items"])
    assert total["leads"] == total["leads_overseas"] + total["leads_it"]


async def test_the_admin_list_takes_the_intake_and_division_filters(client, db_session):
    busy = await make_user(db_session, "counselor", "overseas")
    await mixed_caseload(db_session, busy)
    await as_admin(client, db_session)
    mine = row((await get(client, ADMIN, intake="Sep 2027", division="overseas")).json(), busy)
    assert (mine["leads"], mine["leads_overseas"], mine["leads_it"], mine["applications"]) == (1, 1, 0, 2)
    assert (await get(client, ADMIN, intake="Autumn")).status_code == 422


async def test_an_inactive_counselor_is_listed_only_with_activity(client, db_session):
    quiet = await make_user(db_session, "counselor", "overseas")
    busy = await make_user(db_session, "counselor", "overseas")
    await lead(db_session, busy)
    for user in (quiet, busy):
        user.active = False
    await db_session.commit()
    await as_admin(client, db_session)
    body = (await get(client, ADMIN)).json()
    assert row(body, quiet) is None
    assert row(body, busy)["active"] is False and row(body, busy)["leads"] == 1


async def test_super_admin_reads_the_list(client, db_session):
    await as_admin(client, db_session, "super_admin")
    assert (await get(client, ADMIN)).status_code == 200


@pytest.mark.parametrize(("role", "division"), [("it_admin", "it"), ("partner", "global"), ("counselor", "it"), ("telecaller", "overseas"), ("overseas_student", "overseas")])
async def test_everyone_else_is_refused_the_admin_routes(client, db_session, role, division):
    client.cookies.clear()
    await login(client, await make_user(db_session, role, division))
    counselor = await make_user(db_session, "counselor", "overseas")
    for url in (ADMIN, f"{ADMIN}.csv", f"{ADMIN}/{counselor.id}"):
        assert (await get(client, url)).status_code == 403, url


async def test_anonymous_is_refused_the_admin_routes(client):
    client.cookies.clear()
    assert (await client.get(ADMIN)).status_code == 401


async def test_the_csv_matches_the_screen_and_is_audited(client, db_session):
    busy = await make_user(db_session, "counselor", "overseas")
    await mixed_caseload(db_session, busy)
    admin = await as_admin(client, db_session)
    screen = (await get(client, ADMIN, intake="Sep 2027")).json()
    response = await get(client, f"{ADMIN}.csv", intake="Sep 2027")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.text.lstrip("﻿"))))
    assert rows[0] == [c["label"] for c in screen["columns"]]
    assert len(rows) == len(screen["items"]) + 2  # header + counselors + Total
    line = next(r for r in rows if r[0] == busy.full_name)
    mine = row(screen, busy)
    assert line == ["" if mine[c["key"]] is None else str(mine[c["key"]]) for c in screen["columns"]]
    assert rows[-1][0] == "Total"
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.user_id == admin.id, AuditLog.action == "counselor_performance.export"))).all()
    assert len(audit) == 1 and audit[0].metadata_json["intake"] == "Sep 2027" and audit[0].metadata_json["format"] == "csv"
    assert (await get(client, f"{ADMIN}.xlsx")).status_code == 200


# --- the admin's per-counselor report ----------------------------------------------------------------------------------------------
async def test_the_admin_opens_one_counselors_report_with_the_filters(client, db_session):
    busy = await make_user(db_session, "counselor", "overseas")
    await mixed_caseload(db_session, busy)
    await as_admin(client, db_session)
    response = await get(client, f"{ADMIN}/{busy.id}", intake="Sep 2027")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counselor"] == {"id": str(busy.id), "full_name": busy.full_name, "active": True}
    assert values(body, "period")["leads"] == 2 and values(body, "now")["applications"] == 2


async def test_a_detail_id_that_is_not_an_overseas_counselor_is_404(client, db_session):
    it_counselor = await make_user(db_session, "counselor", "it")
    student = await make_user(db_session, "overseas_student", "overseas")
    await as_admin(client, db_session)
    for who in (it_counselor.id, student.id, uuid.uuid4()):
        assert (await get(client, f"{ADMIN}/{who}")).status_code == 404
