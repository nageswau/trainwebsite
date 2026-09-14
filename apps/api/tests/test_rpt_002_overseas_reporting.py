"""RPT-002 -- Overseas reporting.

Tester feedback (2026-09-04, WhatsApp, RAID.md I-14): "ADMINISTRATOR: reports not
working." The role was ambiguous in the raw report, so it was reproduced directly
against the running app for every candidate "Administrator" role before touching any
code: IT Admin's and Placement Team's own Reports pages (RPT-001) both rendered real
data correctly. Overseas Admin's own "Reports" link showed "Access unavailable --
Workspace not found" -- `PORTAL_NAV["overseas/admin"]` lists "Reports", but `RPT-002`
(the feature that owns this role's own report) was `NOT_STARTED` in the catalog, not a
regression. `RPT-002-AC01`'s named scope: "application funnel by stage, agent
commission report, visa-status aging". Dependencies (`OVS-004`, `AGT-003`) were already
confirmed sufficient for this read-only report. Built as a new `services/portal.py`
handler, mirroring `RPT-001`'s/`CNS-001`'s/`UNI-001`'s own precedent for this exact bug
class (nav lists a section, no handler exists).

Payload shape: `metrics` carries the funnel (all 7 confirmed `OVERSEAS_APPLICATION_
STAGES`, always present even at zero -- `RPT-002-AC02`), the primary `rows` table
carries visa-status aging (division-wide, unscoped -- this role's own confirmed RBAC),
and `panels` carries a per-agent commission summary (kept out of the primary table to
avoid duplicating the already-existing dedicated "commissions" nav section).
"""

import uuid

import pytest

from app.core.security import hash_password
from app.models import AgentCommission, Country, OverseasApplication, University, User, VisaCase


async def _create_user(db_session, *, role: str, division: str = "overseas", **overrides) -> User:
    defaults = dict(
        email=f"rpt002-{role}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name=f"Test {role.title()}",
        role=role,
        division=division,
        active=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    await db_session.commit()
    return user


async def _make_university(db_session) -> University:
    country = Country(
        slug=f"rpt002-country-{uuid.uuid4().hex[:8]}",
        name="Testland",
        overview="A test destination.",
        tuition="USD 20,000/year",
        living_expenses="USD 1,000/month",
        visa_process=[],
        work_opportunities="",
        post_study_work="",
        pr_opportunities="",
        faq=[],
    )
    db_session.add(country)
    await db_session.flush()
    university = University(
        country_id=country.id,
        slug=f"rpt002-university-{uuid.uuid4().hex[:8]}",
        name=f"RPT-002 Test University {uuid.uuid4().hex[:8]}",
        city="Testville",
        overview="A test university.",
        eligibility="",
        requirements=[],
        deadlines=[],
        scholarships=[],
    )
    db_session.add(university)
    await db_session.commit()
    return university


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "overseas"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_reports_renders_instead_of_404ing_with_a_full_funnel_including_honest_zeros(db_session, client):
    admin = await _create_user(db_session, role="overseas_admin")
    university = await _make_university(db_session)
    student = await _create_user(db_session, role="overseas_student")
    db_session.add(OverseasApplication(student_id=student.id, university_id=university.id, status="enquiry", next_action="", intake="September 2027"))
    await db_session.commit()

    await _login(client, admin.email)
    response = await client.get("/api/v1/portal/overseas/admin/reports")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Overseas Partner Reports"
    metrics = {m["label"]: m["value"] for m in body["metrics"]}
    # RPT-002-AC02: every confirmed stage appears, even ones with zero applications --
    # never a silently omitted row. The shared dev DB has no test-DB isolation (RAID.md
    # I-06) and already carries applications from many other tests/sessions, so this
    # asserts presence and a real (not omitted) row for every stage rather than an exact
    # count -- an isolated total isn't obtainable here, only that the stage this test's
    # own application is in went up by at least one, and no stage is silently missing.
    expected_stages = {"Enquiry", "Eligibility Evaluation", "University Selection", "Offer", "Visa Documentation", "Status Tracking", "Enrolled"}
    assert set(metrics.keys()) == expected_stages
    assert metrics["Enquiry"] >= 1
    assert all(isinstance(v, int) and v >= 0 for v in metrics.values())


@pytest.mark.asyncio
async def test_reports_shows_visa_status_aging_across_the_division(db_session, client):
    admin = await _create_user(db_session, role="overseas_admin")
    university = await _make_university(db_session)
    student = await _create_user(db_session, role="overseas_student")
    application = OverseasApplication(student_id=student.id, university_id=university.id, status="visa_documentation", next_action="", intake="September 2027")
    db_session.add(application)
    await db_session.flush()
    db_session.add(VisaCase(application_id=application.id, status="checklist"))
    await db_session.commit()

    await _login(client, admin.email)
    response = await client.get("/api/v1/portal/overseas/admin/reports")
    assert response.status_code == 200
    row = next(r for r in response.json()["rows"] if r["student"] == student.full_name)
    assert row["status"] == "checklist"
    assert row["days_since_update"] >= 0


@pytest.mark.asyncio
async def test_reports_shows_a_real_agent_commission_summary(db_session, client):
    admin = await _create_user(db_session, role="overseas_admin")
    # RAID.md I-09: `_create_user`'s default `full_name` ("Test Agent") is not unique
    # per test run -- every other test's own agent shares it in this shared, unisolated
    # dev DB (RAID.md I-06). uuid-suffix it so this test's assertion can only ever match
    # the row it created itself, never a leftover from another test/session.
    agent_name = f"RPT-002 Test Agent {uuid.uuid4().hex[:8]}"
    agent = await _create_user(db_session, role="agent", full_name=agent_name)
    university = await _make_university(db_session)
    student = await _create_user(db_session, role="overseas_student")
    application = OverseasApplication(student_id=student.id, university_id=university.id, agent_id=agent.id, status="enrolled", next_action="", intake="September 2027")
    db_session.add(application)
    await db_session.flush()
    db_session.add(AgentCommission(agent_id=agent.id, application_id=application.id, amount=5000, currency="INR", status="eligible", created_by="system_trigger"))
    await db_session.commit()

    await _login(client, admin.email)
    response = await client.get("/api/v1/portal/overseas/admin/reports")
    assert response.status_code == 200
    panels = response.json()["panels"]
    commission_panel = next(p for p in panels if p["title"] == "Agent commission report")
    assert any(agent_name in item and "INR 5,000.00" in item for item in commission_panel["items"])


@pytest.mark.asyncio
async def test_reports_never_fabricates_a_commission_for_an_agent_with_none(db_session, client):
    # The shared dev DB always has leftover commissions from other tests/sessions
    # (RAID.md I-06), so an "empty panel" assertion isn't obtainable here -- instead,
    # prove a specific, uniquely-named agent with zero real commissions is never
    # invented into the report.
    admin = await _create_user(db_session, role="overseas_admin")
    agent_name = f"RPT-002 No Commission Agent {uuid.uuid4().hex[:8]}"
    await _create_user(db_session, role="agent", full_name=agent_name)

    await _login(client, admin.email)
    response = await client.get("/api/v1/portal/overseas/admin/reports")
    assert response.status_code == 200
    commission_panel = next(p for p in response.json()["panels"] if p["title"] == "Agent commission report")
    assert not any(agent_name in item for item in commission_panel["items"])


@pytest.mark.asyncio
async def test_a_non_overseas_admin_role_cannot_view_this_report(db_session, client):
    student = await _create_user(db_session, role="overseas_student")
    await _login(client, student.email)
    response = await client.get("/api/v1/portal/overseas/admin/reports")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_reports_requires_authentication(client):
    response = await client.get("/api/v1/portal/overseas/admin/reports")
    assert response.status_code == 401
