"""upc-029 -- GET /partnership/global-dashboard (spec GD1-GD17; EVID-020 §31). The sub-views are asserted through the service in a fresh
manager's scope (the test database is shared and never truncated, so a head's or super_admin's figures include other tests' rows); the
route is asserted for its readers and for reconciling with upc-022's dashboard and upc-018's performance totals for the same caller."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import event, update

from app.core.database import engine
from app.models import OverseasCourse, PartnershipTask, University
from app.services.partnership_metrics import global_figures
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, make_pm, make_user, url

GLOBAL = "/api/v1/partnership/global-dashboard"
TODAY = date(2025, 3, 15)


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


def _course(db, uni, level: str, active: bool = True) -> None:
    db.add(OverseasCourse(university_id=uni.id, title=f"Course {uuid.uuid4().hex[:6]}", level=level, category="Business", duration="1 year",
                          tuition_fee="GBP 10,000", intake="September", active=active))  # fmt: skip


def _task(db, uni, assignee, due_on: date, title: str = "Send proposal", status: str = "open") -> None:
    done = datetime.now(UTC) if status == "done" else None
    db.add(PartnershipTask(university_id=uni.id, kind="follow_up", title=title, assignee_user_id=assignee.id, created_by_user_id=assignee.id,
                           due_on=due_on, status=status, source="manual", completed_at=done))  # fmt: skip


async def _manager(client, db):
    head = await make_head(db)
    return head, await make_pm(db, head)


# --- access (GD1) ---


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(GLOBAL)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "overseas"), ("overseas_admin", "overseas"), ("bdm", "overseas"), ("agent", "overseas")])
async def test_other_roles_are_refused(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(GLOBAL)).status_code == 403


@pytest.mark.asyncio
async def test_a_partnership_manager_is_refused(client, db_session):
    """GD1: management only -- a manager's own figures are upc-022's dashboard."""
    _, manager = await _manager(client, db_session)
    await login(client, manager)
    assert (await client.get(GLOBAL)).status_code == 403
    await login(client, await make_user(db_session, "partnership_manager", "overseas"))
    assert (await client.get(GLOBAL)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["partnership_head", "super_admin"])
async def test_head_and_super_admin_read_it_with_commission(client, db_session, role):
    if role == "partnership_head":
        await login(client, await make_head(db_session))
    else:
        await as_role(client, db_session, "super_admin", "global")
    response = await client.get(GLOBAL)
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"today", "from", "to", "active", "in_progress", "target", "pipeline", "funnel", "commission"}
    assert body["from"] == date.fromisoformat(body["today"]).replace(day=1).isoformat() and body["to"] == body["today"]
    assert [s["key"] for s in body["pipeline"]["steps"]] == ["identified", "contacted", "meeting", "proposal", "negotiation", "agreement", "signed", "active_partner"]
    assert body["funnel"]["totals"]["leads"] is None and isinstance(body["funnel"]["totals"]["enrolled"], int)


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["from=2025-03-10&to=2025-03-01", "from=2024-01-01&to=2025-03-01", "from=2025-02-30", "from=March"])
async def test_a_bad_period_is_422(client, db_session, query):
    await login(client, await make_head(db_session))
    assert (await client.get(f"{GLOBAL}?{query}")).status_code == 422


# --- the three columns (GD3-GD12) ---


@pytest.mark.asyncio
async def test_a_new_scope_is_empty(client, db_session):
    _, manager = await _manager(client, db_session)
    body = await global_figures(db_session, manager, frozenset(), TODAY)
    assert body["active"] == {"count": 0, "countries": [], "universities": [], "courses": []}
    assert body["in_progress"]["count"] == 0 and body["in_progress"]["weighted"] == 0 and body["in_progress"]["next_actions"] == []
    assert body["in_progress"]["expected"] == {"earlier": 0, "this_month": 0, "next_month": 0, "later": 0, "undated": 0}
    assert body["target"]["priorities"] == [{"priority": p, "count": 0} for p in ("A", "B", "C", None)]
    assert body["pipeline"]["total"] == 0 and body["pipeline"]["lost"] == 0


@pytest.mark.asyncio
async def test_active_partners_by_country_university_and_course(client, db_session):
    head, manager = await _manager(client, db_session)
    big = await _university(client, db_session, head, manager, stage="active_partner", name="Zeta University")
    small = await _university(client, db_session, head, manager, stage="partner_activated", name="Alpha University")
    await _university(client, db_session, head, manager, stage="active_partner", lost_at=datetime.now(UTC), lost_reason="Closed")  # GD3: lost
    await _university(client, db_session, head, manager, stage="interested")  # G2, not a partner
    for level in ("UG", "UG", "PG"):
        _course(db_session, big, level)
    _course(db_session, big, "PhD", active=False)  # GD6: inactive courses do not count
    _course(db_session, small, "UG")
    await db_session.commit()

    active = (await global_figures(db_session, manager, frozenset(), TODAY))["active"]
    country = (await catalogue_country(db_session)).name
    assert active["count"] == 2
    assert active["countries"] == [{"name": country, "iso2": (await catalogue_country(db_session)).iso2, "count": 2}]
    assert [(u["name"], u["courses"]) for u in active["universities"]] == [("Zeta University", 3), ("Alpha University", 1)]  # GD5
    assert active["universities"][0]["country"] == country and active["universities"][0]["id"] == big.id
    assert active["courses"] == [{"level": "UG", "courses": 3, "universities": 2}, {"level": "PG", "courses": 1, "universities": 1}]


@pytest.mark.asyncio
async def test_in_progress_by_expected_date_probability_and_next_action(client, db_session):
    head, manager = await _manager(client, db_session)
    earlier = await _university(client, db_session, head, manager, stage="proposal_sent", expected_agreement_date=date(2025, 2, 28), name="Earlier U")
    month_end = await _university(client, db_session, head, manager, stage="interested", expected_agreement_date=date(2025, 3, 31), name="March U")
    await _university(client, db_session, head, manager, stage="interested", expected_agreement_date=date(2025, 3, 1), probability_override=0, probability_override_reason="Stalled")
    await _university(client, db_session, head, manager, stage="agreement_signed", expected_agreement_date=date(2025, 4, 30))  # G2 (PS3)
    await _university(client, db_session, head, manager, stage="initial_contact", expected_agreement_date=date(2025, 5, 1))
    await _university(client, db_session, head, manager, stage="initial_contact")  # undated
    _task(db_session, month_end, manager, date(2025, 3, 20), "Call the dean")
    _task(db_session, month_end, manager, date(2025, 3, 18), "Send the deck")  # GD9: the earliest open one wins
    _task(db_session, month_end, manager, date(2025, 3, 1), "Old", status="done")  # closed: ignored
    _task(db_session, earlier, manager, date(2025, 3, 10), "Chase signature")  # overdue on TODAY
    await db_session.commit()

    progress = (await global_figures(db_session, manager, frozenset(), TODAY))["in_progress"]
    assert progress["count"] == 6
    assert progress["expected"] == {"earlier": 1, "this_month": 2, "next_month": 1, "later": 1, "undated": 1}  # GD7
    assert progress["probability"] == [{"probability": 100, "count": 1}, {"probability": 75, "count": 1}, {"probability": 40, "count": 1},
                                       {"probability": 25, "count": 2}, {"probability": 0, "count": 1}]  # fmt: skip
    assert progress["weighted"] == round((100 + 75 + 40 + 25 + 25 + 0) / 100, 1)  # GD8 = E4
    actions = [(a["university"]["name"], a["title"], a["due_on"], a["overdue"]) for a in progress["next_actions"]]
    assert actions == [("Earlier U", "Chase signature", date(2025, 3, 10), True), ("March U", "Send the deck", date(2025, 3, 18), False)]
    assert progress["without_action"] == 4


@pytest.mark.asyncio
async def test_target_list_by_priority_country_and_course(client, db_session):
    head, manager = await _manager(client, db_session)
    await _university(client, db_session, head, manager, stage="target_university", priority="A", course_levels=["UG", "PG"])
    await _university(client, db_session, head, manager, stage="researching", priority="A", course_levels=["PG"])
    await _university(client, db_session, head, manager, stage="contact_identified", priority=None, course_levels=[])
    await _university(client, db_session, head, manager, stage="researching", priority="C", lost_at=datetime.now(UTC), lost_reason="No")  # lost

    target = (await global_figures(db_session, manager, frozenset(), TODAY))["target"]
    assert target["count"] == 3
    assert target["priorities"] == [{"priority": "A", "count": 2}, {"priority": "B", "count": 0}, {"priority": "C", "count": 0}, {"priority": None, "count": 1}]
    assert target["countries"][0]["count"] == 3
    assert target["course_levels"] == [{"level": "PG", "count": 2}, {"level": "UG", "count": 1}]  # GD12: both levels count
    assert target["no_course_levels"] == 1


@pytest.mark.asyncio
async def test_the_pipeline_is_management_section_19(client, db_session):
    """GD13: Identified = K1, Contacted = K2-K3 ... Signed = K8 (Partner Activated included), Active Partner = K9; lost aside."""
    head, manager = await _manager(client, db_session)
    for stage in ("target_university", "initial_contact", "interested", "meeting_completed", "proposal_sent", "documents_shared",
                  "agreement_under_review", "agreement_signed", "partner_activated", "student_recruitment_started"):  # fmt: skip
        await _university(client, db_session, head, manager, stage=stage)
    await _university(client, db_session, head, manager, stage="interested", lost_at=datetime.now(UTC), lost_reason="No")

    pipeline = (await global_figures(db_session, manager, frozenset(), TODAY))["pipeline"]
    assert {s["key"]: s["count"] for s in pipeline["steps"]} == {
        "identified": 1, "contacted": 2, "meeting": 1, "proposal": 1, "negotiation": 1, "agreement": 1, "signed": 2, "active_partner": 1,
    }  # fmt: skip
    assert pipeline["steps"][0]["label"] == "Identified" and pipeline["lost"] == 1 and pipeline["total"] == 11


@pytest.mark.asyncio
async def test_a_head_never_sees_another_heads_universities(client, db_session):
    head, manager = await _manager(client, db_session)
    other_head, other = await _manager(client, db_session)
    mine = await _university(client, db_session, head, manager, stage="active_partner", name=f"Mine {uuid.uuid4().hex[:6]}")
    theirs = await _university(client, db_session, other_head, other, stage="active_partner", name=f"Theirs {uuid.uuid4().hex[:6]}")
    _course(db_session, mine, "UG")
    _course(db_session, theirs, "UG")
    _course(db_session, theirs, "UG")  # ranks it above `mine` if it leaked
    await db_session.commit()
    await login(client, head)
    names = {u["name"] for u in (await client.get(GLOBAL)).json()["active"]["universities"]}
    assert theirs.name not in names


# --- reconciliation (acceptance: the totals reconcile with upc-022 and upc-018) ---


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["partnership_head", "super_admin"])
async def test_totals_reconcile_with_the_dashboard_and_performance(client, db_session, role):
    head, manager = await _manager(client, db_session)
    await _university(client, db_session, head, manager, stage="active_partner")
    await _university(client, db_session, head, manager, stage="interested", lost_at=datetime.now(UTC), lost_reason="No")
    if role == "partnership_head":
        await login(client, head)
    else:
        await as_role(client, db_session, "super_admin", "global")
    period = "from=2025-01-01&to=2025-12-31"
    body = (await client.get(f"{GLOBAL}?{period}")).json()
    overview = (await client.get("/api/v1/partnership/dashboard")).json()["overview"]
    performance = (await client.get(f"/api/v1/partnership/performance?{period}&limit=1")).json()
    assert (body["active"]["count"], body["in_progress"]["count"], body["target"]["count"]) == (overview["partners"], overview["in_progress"], overview["targets"])
    assert body["pipeline"]["total"] == overview["total"] and body["pipeline"]["lost"] == overview["lost"]
    assert sum(s["count"] for s in body["pipeline"]["steps"]) + body["pipeline"]["lost"] == overview["total"]
    assert body["funnel"]["totals"] == performance["totals"] and body["funnel"]["steps"] == performance["steps"]
    assert body["commission"] == performance["commission"]
    assert sum(body["in_progress"]["expected"].values()) == body["in_progress"]["count"]
    assert sum(p["count"] for p in body["target"]["priorities"]) == body["target"]["count"]
    assert sum(c["count"] for c in body["active"]["countries"]) == body["active"]["count"]


@pytest.mark.asyncio
async def test_a_fixed_number_of_statements_whatever_the_data(client, db_session):
    """Performance: no N+1 -- adding universities, courses and tasks does not add statements."""
    head, manager = await _manager(client, db_session)
    await _university(client, db_session, head, manager, stage="active_partner")  # upc-018's reads skip their queries for an empty scope

    async def statements() -> int:
        await login(client, head)
        seen: list[str] = []
        listener = lambda *args: seen.append(args[2])  # noqa: E731 -- (conn, cursor, statement, ...)
        event.listen(engine.sync_engine, "before_cursor_execute", listener)
        try:
            assert (await client.get(GLOBAL)).status_code == 200
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", listener)
        return len(seen)

    small = await statements()
    for stage in ("active_partner", "interested", "target_university"):
        uni = await _university(client, db_session, head, manager, stage=stage)
        _course(db_session, uni, "UG")
        _task(db_session, uni, manager, TODAY + timedelta(days=1))
    await db_session.commit()
    assert await statements() == small
