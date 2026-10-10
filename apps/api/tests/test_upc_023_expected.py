"""upc-023 -- GET /partnership/expected (spec §2 EX1, EX5-EX12, §4; AC1, AC2). Counts are asserted in a fresh manager's scope: the test
database is shared and never truncated, so a head's (team + unowned) or super_admin's figures include other tests' rows."""

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import update

from app.models import University
from app.partnership_stages import effective_probability
from app.services.bdm_appointments import IST
from app.services.partnership_metrics import forecast_windows
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, make_pm, make_user, url

EXPECTED = "/api/v1/partnership/expected"


def _today() -> date:
    return datetime.now(IST).date()


def _next_month(day: date) -> date:
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1)


async def _university(client, db, head, manager=None, **values) -> University:
    """A university created and assigned by the head, then given `values` directly (stage, dates, override)."""
    await login(client, head)
    made = await create(client, (await catalogue_country(db)).id)
    if manager is not None:
        response = await client.post(url(made["id"], "assign"), json={"primary_manager_user_id": str(manager.id)})
        assert response.status_code == 200, response.text
    if values:
        await db.execute(update(University).where(University.id == uuid.UUID(made["id"])).values(**values))
        await db.commit()
    return await db.get(University, uuid.UUID(made["id"]))


async def _get(client, **params) -> dict:
    response = await client.get(EXPECTED, params={"limit": 100} | params)
    assert response.status_code == 200, response.text
    return response.json()


def _windows(body: dict) -> dict:
    return {w["key"]: (w["count"], w["weighted"]) for w in body["windows"]}


def _ids(body: dict) -> list[str]:
    return [row["university"]["id"] for row in body["items"]]


# --- pure rules ---


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 3, 31), {"this_month": (date(2026, 3, 1), date(2026, 3, 31)), "next_month": (date(2026, 4, 1), date(2026, 4, 30)), "this_quarter": (date(2026, 1, 1), date(2026, 3, 31))}),
        (date(2026, 12, 15), {"this_month": (date(2026, 12, 1), date(2026, 12, 31)), "next_month": (date(2027, 1, 1), date(2027, 1, 31)), "this_quarter": (date(2026, 10, 1), date(2026, 12, 31))}),
        (date(2028, 1, 31), {"this_month": (date(2028, 1, 1), date(2028, 1, 31)), "next_month": (date(2028, 2, 1), date(2028, 2, 29)), "this_quarter": (date(2028, 1, 1), date(2028, 3, 31))}),
    ],
)
def test_windows_are_ist_calendar_months_and_quarters(today, expected):
    """AC2: calendar months and quarters, the year and leap-February boundaries included."""
    assert {w.key: (w.first, w.last) for w in forecast_windows(today)} == expected


def test_probability_is_the_stage_band_unless_overridden():
    """EX1/EX2: Appendix B P; an override of 0 is still an override."""
    assert effective_probability("interested", None) == 40
    assert effective_probability("documents_shared", None) == 75
    assert effective_probability("interested", 80) == 80
    assert effective_probability("proposal_sent", 0) == 0


# --- access (EX5) ---


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(EXPECTED)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("overseas_admin", "overseas"), ("counselor", "overseas"), ("bdm", "overseas"), ("agent", "overseas")])
async def test_other_roles_are_refused(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    response = await client.get(EXPECTED)
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_a_manager_without_a_profile_is_refused(client, db_session):
    await login(client, await make_user(db_session, "partnership_manager", "overseas"))
    assert (await client.get(EXPECTED)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"window": "this_year"}, {"limit": 0}, {"limit": 101}, {"offset": -1}])
async def test_bad_parameters_are_422(client, db_session, params):
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.get(EXPECTED, params=params)).status_code == 422


# --- figures (AC1, AC2, EX6-EX12) ---


@pytest.mark.asyncio
async def test_ten_universities_at_80_percent_forecast_8(client, db_session):
    """AC1: 10 universities × 80% = 8 expected partnerships (the source's example)."""
    head = await make_head(db_session)
    manager = await make_pm(db_session, head)
    for _ in range(10):
        await _university(client, db_session, head, manager, stage="interested", expected_agreement_date=_today(), probability_override=80, probability_override_reason="Board approved")
    await login(client, manager)
    body = await _get(client)
    assert _windows(body)["this_month"] == (10, 8.0)
    assert body["total"] == 10 and all(row["probability"] == 80 and row["stage_probability"] == 40 for row in body["items"])


@pytest.mark.asyncio
async def test_windows_count_and_weight_by_expected_date(client, db_session):
    """E1-E3 over IST dates; `all` lists every dated row, overdue included; month-end is inside its month."""
    head = await make_head(db_session)
    manager = await make_pm(db_session, head)
    today = _today()
    month_end = _next_month(today) - timedelta(days=1)
    next_month = _next_month(today)
    overdue = today.replace(day=1) - timedelta(days=1)
    rows = {
        "month_end": await _university(client, db_session, head, manager, stage="meeting_completed", expected_agreement_date=month_end),  # 60
        "next": await _university(client, db_session, head, manager, stage="agreement_under_review", expected_agreement_date=next_month),  # 90
        "overdue": await _university(client, db_session, head, manager, stage="initial_contact", expected_agreement_date=overdue),  # 25
    }
    await login(client, manager)
    body = await _get(client)
    figures = _windows(body)
    assert figures["this_month"] == (1, 0.6)
    assert figures["next_month"] == (1, 0.9)
    quarter_of = (today.month - 1) // 3
    in_quarter = [d for d in (month_end, next_month, overdue) if d.year == today.year and (d.month - 1) // 3 == quarter_of]
    assert figures["this_quarter"][0] == len(in_quarter)
    assert body["window"] == "all" and body["total"] == 3
    assert _ids(body) == [str(rows[k].id) for k in ("overdue", "month_end", "next")]  # by expected date
    this_month = await _get(client, window="this_month")
    assert _ids(this_month) == [str(rows["month_end"].id)] and this_month["total"] == 1
    assert _ids(await _get(client, window="next_month")) == [str(rows["next"].id)]


@pytest.mark.asyncio
async def test_signed_lost_and_inactive_universities_are_not_expected(client, db_session):
    """EX7: only active, not-lost universities before Agreement Signed."""
    head = await make_head(db_session)
    manager = await make_pm(db_session, head)
    today = _today()
    kept = await _university(client, db_session, head, manager, stage="agreement_under_review", expected_agreement_date=today)
    await _university(client, db_session, head, manager, stage="agreement_signed", expected_agreement_date=today)
    await _university(client, db_session, head, manager, stage="active_partner", expected_agreement_date=today)
    await _university(client, db_session, head, manager, stage="interested", expected_agreement_date=today, lost_at=datetime.now(IST), lost_reason="Closed")
    await _university(client, db_session, head, manager, stage="interested", expected_agreement_date=today, active=False)
    await _university(client, db_session, head, manager, stage="interested")  # undated
    await login(client, manager)
    body = await _get(client)
    assert _ids(body) == [str(kept.id)] and _windows(body)["this_month"] == (1, 0.9)
    assert body["undated_count"] == 1


@pytest.mark.asyncio
async def test_universities_without_an_expected_date_are_listed_separately(client, db_session):
    """Edge case: no expected date -> excluded from every window, listed under `undated`."""
    head = await make_head(db_session)
    manager = await make_pm(db_session, head)
    undated = await _university(client, db_session, head, manager, stage="proposal_sent")
    await login(client, manager)
    body = await _get(client)
    assert body["items"] == [] and body["undated_count"] == 1 and all(count == 0 for count, _ in _windows(body).values())
    listed = await _get(client, window="undated")
    assert _ids(listed) == [str(undated.id)]
    row = listed["items"][0]
    assert row["expected_agreement_date"] is None and row["probability"] == 75 and row["stage_label"] == "Proposal Sent"
    assert row["owner"]["id"] == str(manager.id) and row["country"]


@pytest.mark.asyncio
async def test_scope_manager_head_and_super_admin(client, db_session):
    """EX6 (upc-018 PF6): a manager sees universities they own (primary or backup); the head their team's and unowned ones; another
    head's team is hidden; super_admin sees all."""
    head, other_head = await make_head(db_session), await make_head(db_session)
    manager, colleague, stranger = await make_pm(db_session, head), await make_pm(db_session, head), await make_pm(db_session, other_head)
    today = _today()
    mine = await _university(client, db_session, head, manager, expected_agreement_date=today)
    theirs = await _university(client, db_session, head, colleague, expected_agreement_date=today)
    unowned = await _university(client, db_session, head, None, expected_agreement_date=today)
    backed = await _university(client, db_session, head, colleague, backup_manager_user_id=manager.id, expected_agreement_date=today)
    hidden = await _university(client, db_session, other_head, stranger, expected_agreement_date=today)
    await login(client, manager)
    seen = set(_ids(await _get(client)))
    assert seen == {str(mine.id), str(backed.id)}  # primary or backup; not the colleague's own
    await login(client, head)
    seen = set(_ids(await _get(client, limit=100, window="this_month")))
    assert {str(mine.id), str(theirs.id), str(unowned.id)} <= seen and str(hidden.id) not in seen
    await as_role(client, db_session, "super_admin", "global")
    body = await _get(client, window="this_month", limit=100)
    assert body["total"] >= 5


@pytest.mark.asyncio
async def test_paging_keeps_the_figures(client, db_session):
    head = await make_head(db_session)
    manager = await make_pm(db_session, head)
    for _ in range(3):
        await _university(client, db_session, head, manager, stage="interested", expected_agreement_date=_today())
    await login(client, manager)
    first = await _get(client, limit=2)
    second = await _get(client, limit=2, offset=2)
    beyond = await _get(client, limit=2, offset=10)
    assert len(first["items"]) == 2 and len(second["items"]) == 1 and beyond["items"] == []
    assert first["total"] == second["total"] == beyond["total"] == 3
    assert _windows(first) == _windows(beyond) and _windows(first)["this_month"] == (3, 1.2)
    assert set(_ids(first)).isdisjoint(_ids(second))
