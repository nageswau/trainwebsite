"""upc-025 -- Global partnership map (spec §2 MP1-MP14, §5 AC1-AC9; DEC-SCOPE-166). The map counts exactly what the upc-024 search would
list for the same filters (MP2/MP3), per country and partner status. The test database is shared and never truncated, so every
university carries a per-test tag in its name and each request sends `q=<tag>` (reused from the upc-024 tests)."""

from datetime import date

import pytest
from sqlalchemy import event

from app.core.database import engine
from tests.test_upc_014_agreements import signed
from tests.test_upc_024_search import SEARCH, course, head_in, mk, names, tag
from tests.upc003_helpers import as_role, login, make_head, make_pm, make_user

MAP = "/api/v1/partnership/universities/map"
COUNTS = ("partner", "in_progress", "target", "lost")


async def counts(client, t: str, **params) -> dict[str, dict]:
    """The map's rows by ISO-2 code, as {partner, in_progress, target, lost, total}."""
    response = await client.get(MAP, params={"q": t, **params})
    assert response.status_code == 200, response.text
    return {row["iso2"]: {k: row[k] for k in (*COUNTS, "total")} for row in response.json()["countries"]}


async def world(db, t: str) -> None:
    """GB 2 / 1 / 1 / 1, DE 1 partner, SG one lost (a small country), IN 1 target and FI 1 target (FI's name holds "in")."""
    await mk(db, t, "GB", "UkP1", stage="active_partner")
    await mk(db, t, "GB", "UkP2", stage="partner_activated")
    await mk(db, t, "GB", "UkTalk", stage="agreement_signed")  # PS3: Agreement Signed is In Progress (G2)
    await mk(db, t, "GB", "UkTarget")
    await mk(db, t, "GB", "UkLost", stage="active_partner", lost=True)  # lost wins over the stage's group
    await mk(db, t, "DE", "DePartner", stage="student_recruitment_started")
    await mk(db, t, "SG", "SgLost", stage="interested", lost=True)
    await mk(db, t, "IN", "InTarget", stage="researching")
    await mk(db, t, "FI", "FiTarget")


# --- AC1: per-country counts equal the list totals ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_counts_per_country_and_totals(client, db_session):
    t = tag()
    await world(db_session, t)
    await head_in(client, db_session)
    body = (await client.get(MAP, params={"q": t})).json()
    rows = {r["iso2"]: r for r in body["countries"]}
    assert set(rows) == {"GB", "DE", "SG", "IN", "FI"}
    assert {k: rows["GB"][k] for k in (*COUNTS, "total")} == {"partner": 2, "in_progress": 1, "target": 1, "lost": 1, "total": 5}
    assert rows["GB"]["name"] == "United Kingdom" and rows["GB"]["region"] == "UK"
    assert rows["SG"]["lost"] == 1 and rows["DE"]["partner"] == 1
    assert [r["name"] for r in body["countries"]] == sorted(r["name"] for r in body["countries"])
    assert body["totals"] == {"partner": 3, "in_progress": 1, "target": 3, "lost": 2, "total": 9}
    assert body["stages"][0] == {"key": "target_university", "label": "Target University"} and len(body["stages"]) == 15


@pytest.mark.asyncio
async def test_each_country_matches_the_search_for_the_same_filters(client, db_session):
    """AC1/MP3: for every row, the search with the same filters plus iso2 has the same total and partner-status facet."""
    t = tag()
    await world(db_session, t)
    await head_in(client, db_session)
    for params in ({}, {"region": "Asia"}, {"partner_status": "not_partnered"}, {"stage": "active_partner"}):
        for iso2, row in (await counts(client, t, **params)).items():
            found = (await client.get(SEARCH, params={"q": t, "iso2": iso2, **params})).json()
            assert found["total"] == row["total"], (params, iso2)
            facet = found["facets"]["partner_status"]
            if "partner_status" not in params:  # the facet ignores its own filter (SR14); the map row does not
                assert facet == {k: row[k] for k in COUNTS}, (params, iso2)


# --- AC4 + AC8: the §2 filters, on the map and on the search ------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_iso2_is_an_exact_country_match(client, db_session):
    """MP4: `country=IN` also matches every name holding "in" (Finland, United Kingdom, Singapore); `iso2=IN` does not."""
    t = tag()
    await world(db_session, t)
    await head_in(client, db_session)
    assert await names(client, t, country="IN") == {"InTarget", "FiTarget", "UkP1", "UkP2", "UkTalk", "UkTarget", "UkLost", "SgLost"}
    assert await names(client, t, iso2="in") == {"InTarget"}
    assert set(await counts(client, t, iso2="IN")) == {"IN"}


@pytest.mark.asyncio
async def test_stage_priority_activity_and_region_filters(client, db_session):
    t = tag()
    await mk(db_session, t, "GB", "Signed", stage="agreement_signed", priority="A")
    await mk(db_session, t, "GB", "Lost", stage="agreement_signed", lost=True, priority="B")
    await mk(db_session, t, "JP", "Asleep", active=False, priority="A")
    await mk(db_session, t, "JP", "Awake", priority="C")
    await head_in(client, db_session)

    assert await names(client, t, stage="agreement_signed") == {"Signed", "Lost"}  # MP5: the stored stage, lost or not
    assert await counts(client, t, stage="agreement_signed") == {"GB": {"partner": 0, "in_progress": 1, "target": 0, "lost": 1, "total": 2}}
    assert await names(client, t, priority="A") == {"Signed"}  # MP6 (inactive rows are not counted by default)
    assert await names(client, t) == {"Signed", "Lost", "Awake"}  # MP7: activity defaults to active
    assert await names(client, t, activity="inactive") == {"Asleep"}
    assert await names(client, t, activity="all") == {"Signed", "Lost", "Asleep", "Awake"}
    assert await counts(client, t, activity="inactive") == {"JP": {"partner": 0, "in_progress": 0, "target": 1, "lost": 0, "total": 1}}
    assert set(await counts(client, t, region="Asia")) == {"JP"}


@pytest.mark.asyncio
async def test_the_upc024_filters_narrow_the_map(client, db_session):
    """MP9: partner status, type, ranking, course, manager and expected date are the search's own filters."""
    t = tag()
    head = await make_head(db_session)
    pm = await make_pm(db_session, head)
    await mk(db_session, t, "GB", "Mine", stage="active_partner", primary_manager_user_id=pm.id, target_partnership_date=date(2027, 3, 1),
             rankings=[("QS", "120", 2026)], courses=[course("MBA", category="Business", level="PG")])  # fmt: skip
    await mk(db_session, t, "GB", "College", institution_type="college", courses=[course("BSc Computing", category="IT", level="UG")])
    await login(client, head)
    one = {"GB": {"partner": 1, "in_progress": 0, "target": 0, "lost": 0, "total": 1}}
    for params in ({"partner_status": "partner"}, {"ranking_max": 200}, {"course": "Business"}, {"level": "PG"}, {"manager": str(pm.id)},
                   {"expected_from": "2027-01-01", "expected_to": "2027-12-31"}, {"institution_type": "university"}):  # fmt: skip
        assert await counts(client, t, **params) == one, params
    assert await counts(client, t, partner_status="target") == {"GB": {"partner": 0, "in_progress": 0, "target": 1, "lost": 0, "total": 1}}
    assert await counts(client, t, region="Europe") == {}


@pytest.mark.asyncio
async def test_exclusivity_follows_the_in_force_agreements(client, db_session):
    """MP8 (Q-07): exclusive = an in-force exclusive agreement; non-exclusive = in-force agreements, none exclusive; none = neither."""
    t = tag()
    head = await make_head(db_session)
    pm = await make_pm(db_session, head)
    excl = await mk(db_session, t, "GB", "Excl", primary_manager_user_id=pm.id)
    open_ = await mk(db_session, t, "GB", "Open", primary_manager_user_id=pm.id)
    draft = await mk(db_session, t, "GB", "Draft", primary_manager_user_id=pm.id)
    await mk(db_session, t, "GB", "Nothing")
    await login(client, pm)
    await signed(client, head, pm, str(excl.id), start_date="2026-01-01", expiry_date="2028-01-01", exclusivity="exclusive")
    await signed(client, head, pm, str(open_.id), start_date="2026-01-01", expiry_date="2028-01-01", exclusivity="non_exclusive")
    response = await client.post(f"/api/v1/partnership/universities/{draft.id}/agreements",
                                 json={"agreement_type": "mou", "start_date": "2026-01-01", "expiry_date": "2028-01-01", "exclusivity": "exclusive"})  # fmt: skip
    assert response.status_code == 201, response.text  # a draft is not in force
    assert await names(client, t, exclusivity="exclusive") == {"Excl"}
    assert await names(client, t, exclusivity="non_exclusive") == {"Open"}
    assert (await counts(client, t, exclusivity="exclusive"))["GB"]["total"] == 1
    await as_role(client, db_session, "overseas_admin", "overseas")  # not commercial data: every reader may filter by it
    assert await names(client, t, exclusivity="exclusive") == {"Excl"}


# --- AC6: readers, validation, commission ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "overseas"), ("bdm", "overseas"), ("overseas_student", "overseas"), ("overseas_admin", "it")])
async def test_other_roles_are_refused(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(MAP)).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_401(client):
    assert (await client.get(MAP)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["partnership_head", "super_admin", "overseas_admin", "partnership_manager"])
async def test_every_reader_gets_the_map(client, db_session, role):
    t = tag()
    await mk(db_session, t, "GB", "Seen")
    if role == "partnership_manager":
        await login(client, await make_pm(db_session, await make_head(db_session)))
    elif role == "partnership_head":
        await head_in(client, db_session)
    else:
        await as_role(client, db_session, role, "overseas" if role == "overseas_admin" else "global")
    assert (await counts(client, t))["GB"]["total"] == 1  # MP2: whoever owns it


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [{"iso2": "GBR"}, {"iso2": "G1"}, {"stage": "signed"}, {"priority": "D"}, {"activity": "dormant"}, {"exclusivity": "sole"},
     {"region": "Mars"}, {"partner_status": "partnered"}, {"manager": "someone"}, {"expected_from": "2027-05-01", "expected_to": "2027-04-01"}],
)  # fmt: skip
@pytest.mark.parametrize("url", [MAP, SEARCH])
async def test_bad_values_are_422(client, db_session, params, url):
    await head_in(client, db_session)
    response = await client.get(url, params=params)
    assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_map_ignores_commission_for_other_roles(client, db_session):
    from decimal import Decimal

    t = tag()
    await mk(db_session, t, "GB", "Paid", courses=[course("MBA", commission_percent=Decimal("12"))])
    await mk(db_session, t, "GB", "Unpaid")
    await login(client, await make_user(db_session, "super_admin", "global"))
    assert (await counts(client, t, commission_min="10"))["GB"]["total"] == 1
    await as_role(client, db_session, "overseas_admin", "overseas")
    assert (await counts(client, t, commission_min="100"))["GB"]["total"] == 2  # SR10: dropped, never filtered


# --- AC7: one grouped query --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_query_count_does_not_grow_with_universities(client, db_session):
    t = tag()
    await head_in(client, db_session)
    statements: list[str] = []
    listener = lambda *args: statements.append(args[2])  # noqa: E731 -- (conn, cursor, statement, ...)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        seen = []
        for iso2 in ("GB", "DE", "JP", "IN"):
            await mk(db_session, t, iso2, f"Q{iso2}")
            statements.clear()
            assert (await client.get(MAP, params={"q": t})).status_code == 200
            seen.append(len([s for s in statements if s.lstrip().upper().startswith("SELECT")]))
        assert len(set(seen)) == 1, seen
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
