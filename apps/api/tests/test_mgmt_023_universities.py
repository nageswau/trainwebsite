"""mgmt-023 -- GET /management/universities, the §19 University partnership dashboard (EVID-017 §19, spec UD1-UD14; acceptance: the
totals equal upc-029's). Both readers see every university (UD2) and the shared test database is never truncated, so the definitions are
asserted as deltas over fresh universities and the totals by reconciling with /partnership/global-dashboard for the same period."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from tests.test_upc_014_agreements import signed
from tests.test_upc_029_global_dashboard import _manager, _university
from tests.upc003_helpers import as_role, login

pytestmark = pytest.mark.asyncio

URL = "/api/v1/management/universities"
GLOBAL = "/api/v1/partnership/global-dashboard"
KPIS = ("identified", "contacted", "meetings", "negotiations", "mous", "signed", "active", "exclusive", "countries", "applications", "enrollments")


async def dashboard(client, **params) -> dict:
    response = await client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def kpis(body: dict) -> dict[str, int]:
    return {k["key"]: k["value"] for k in body["kpis"]}


def _next_month(today: date) -> date:
    return (today.replace(day=1) + timedelta(days=32)).replace(day=1)


# --- access (UD1) ---


async def test_signed_out_is_401(client):
    assert (await client.get(URL)).status_code == 401


@pytest.mark.parametrize(("role", "division"), [("accountant", "global"), ("partnership_head", "overseas"), ("counselor", "overseas"), ("overseas_admin", "overseas")])
async def test_other_roles_are_refused(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(URL)).status_code == 403


@pytest.mark.parametrize("params", [{"from": "2026-05-02", "to": "2026-05-01"}, {"from": "2025-01-01", "to": "2026-01-02"}, {"from": "2026-02-30"}])
async def test_a_bad_period_is_422(client, db_session, params):
    await as_role(client, db_session, "partner", "global")
    assert (await client.get(URL, params=params)).status_code == 422


# --- the commission rule (UD10, M3 / M13) ---


async def test_the_partner_sees_revenue_and_super_admin_does_not(client, db_session):
    await as_role(client, db_session, "partner", "global")
    body = await dashboard(client)
    assert set(body["revenue"]) == {"expected", "received"}
    assert [k["key"] for k in body["kpis"]] == list(KPIS)  # source order; Revenue is its own key
    await as_role(client, db_session, "super_admin", "global")
    response = await client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert "revenue" not in body and "commission" not in body
    assert all(k["key"] != "revenue" for k in body["kpis"])


# --- acceptance: the totals equal upc-029's for the same period ---


async def test_totals_equal_the_global_partnership_dashboard(client, db_session):
    head, manager = await _manager(client, db_session)
    await _university(client, db_session, head, manager, stage="active_partner")
    await _university(client, db_session, head, manager, stage="interested", lost_at=datetime.now(UTC), lost_reason="No")
    period = {"from": "2025-01-01", "to": "2025-12-31"}
    await as_role(client, db_session, "super_admin", "global")
    upc = (await client.get(GLOBAL, params=period)).json()
    ours = await dashboard(client, **period)
    figures = kpis(ours)
    assert ours["pipeline"] == upc["pipeline"]
    assert figures["identified"] == upc["pipeline"]["total"]
    assert figures["active"] == upc["active"]["count"]
    assert figures["countries"] == len(upc["active"]["countries"])
    assert (figures["applications"], figures["enrollments"]) == (upc["funnel"]["totals"]["applications"], upc["funnel"]["totals"]["enrolled"])
    assert (ours["from"], ours["to"]) == ("2025-01-01", "2025-12-31")
    await as_role(client, db_session, "partner", "global")
    assert (await dashboard(client, **period))["revenue"] == upc["commission"]  # F10/F11, per currency


# --- the definitions (UD4-UD8), as deltas ---


async def test_each_kpi_follows_its_definition(client, db_session):
    head, manager = await _manager(client, db_session)
    await as_role(client, db_session, "partner", "global")
    before = kpis(await dashboard(client))
    await _university(client, db_session, head, manager, stage="target_university")  # identified only
    await _university(client, db_session, head, manager, stage="meeting_completed")  # contacted, meetings
    await _university(client, db_session, head, manager, stage="agreement_under_review")  # ... negotiations, mous
    await _university(client, db_session, head, manager, stage="agreement_signed")  # ... signed, not active
    exclusive = await _university(client, db_session, head, manager, stage="active_partner")  # ... active
    await _university(client, db_session, head, manager, stage="active_partner", lost_at=datetime.now(UTC), lost_reason="No")  # identified only
    today = date.today()
    await login(client, manager)  # an in-force exclusive agreement, through upc-014's own flow
    await signed(client, head, manager, str(exclusive.id), start_date=(today - timedelta(days=30)).isoformat(),
                 expiry_date=(today + timedelta(days=365)).isoformat(), exclusivity="exclusive")  # fmt: skip
    await as_role(client, db_session, "partner", "global")
    after = kpis(await dashboard(client))
    delta = {key: after[key] - before[key] for key in KPIS}
    assert delta == {
        "identified": 6, "contacted": 4, "meetings": 4, "negotiations": 3, "mous": 3, "signed": 2, "active": 1, "exclusive": 1,
        "countries": delta["countries"], "applications": 0, "enrollments": 0,
    }  # fmt: skip
    assert delta["countries"] in (0, 1)  # the catalogue country may already hold an active partner


async def test_expected_lists_next_month_and_counts_the_windows(client, db_session):
    head, manager = await _manager(client, db_session)
    await as_role(client, db_session, "partner", "global")
    today = date.fromisoformat((await dashboard(client))["today"])
    tag = uuid.uuid4().hex[:6]
    nxt = await _university(client, db_session, head, manager, stage="interested", name=f"Next {tag}", expected_agreement_date=_next_month(today))
    await _university(client, db_session, head, manager, stage="interested", name=f"Now {tag}", expected_agreement_date=today)
    await _university(client, db_session, head, manager, stage="active_partner", name=f"Signed {tag}", expected_agreement_date=_next_month(today))
    await as_role(client, db_session, "super_admin", "global")
    body = await dashboard(client)
    expected = body["expected"]
    assert [w["key"] for w in expected["windows"]] == ["this_month", "next_month", "this_quarter"]
    names = {row["university"]["name"] for row in expected["next_month"]["items"]}
    assert nxt.name in names and f"Now {tag}" not in names and f"Signed {tag}" not in names  # EX7: not yet signed
    row = next(r for r in expected["next_month"]["items"] if r["university"]["id"] == str(nxt.id))
    assert (row["stage_label"], row["expected_agreement_date"], row["probability"]) == ("Interested", _next_month(today).isoformat(), 40)
    window = next(w for w in expected["windows"] if w["key"] == "next_month")
    assert window["count"] == expected["next_month"]["total"] >= len(expected["next_month"]["items"])
    assert len(expected["next_month"]["items"]) <= 25
