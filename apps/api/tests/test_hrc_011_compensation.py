"""hrc-011 (DEC-SCOPE-372, spec docs/superpowers/specs/2026-11-04-hrc-011-candidate-compensation-design.md): each candidate amount keeps
its original amount, currency and pay period (C3) beside a normalised annual INR figure (C8) that search and pools filter on (C6). Non-INR
amounts use the placement manager's rate table (C1); a rate change recomputes (C5). The hrc-001 grant covers every new key (C7)."""

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import delete, select

from app.models import AuditLog, Candidate, CandidateSkill, RecFxRate, Skill, SkillCategory, UserPermissionOverride
from app.services import compensation
from tests.rec038_helpers import add, core, headers, tag

pytestmark = pytest.mark.asyncio
RATES = "/api/v1/recruiter/catalogue/exchange-rates"
NEW_KEYS = {
    "current_salary_currency", "current_salary_period", "expected_salary_currency", "expected_salary_period", "minimum_salary",
    "minimum_salary_currency", "minimum_salary_period", "salary_negotiable", "current_annual_inr", "expected_annual_inr", "minimum_annual_inr",
}  # fmt: skip


def _u(world, role):
    return headers(world["users"][role])


def _path(world):
    return f"/api/v1/recruiter/candidates/{world['candidate']}"


async def _rate(db, currency: str, value: str):
    """Tests share one DB: set the rate idempotently."""
    await db.execute(delete(RecFxRate).where(RecFxRate.currency == currency))
    await add(db, RecFxRate(currency=currency, inr_per_unit=Decimal(value)))
    await db.commit()


# --- the normaliser (C2, C8) ------------------------------------------------------------------------------------------------------------
async def test_annual_inr_rules():
    assert compensation.annual_inr(Decimal("50000"), "INR", "month", Decimal(1)) == Decimal("600000.00")  # AC1
    assert compensation.annual_inr(Decimal("4000"), "USD", "month", Decimal("83.25")) == Decimal("3996000.00")
    assert compensation.annual_inr(Decimal("1000.005"), "INR", "year", Decimal(1)) == Decimal("1000.01")  # half-up
    assert compensation.annual_inr(None, None, None, None) is None


# --- candidate writes -------------------------------------------------------------------------------------------------------------------
async def test_monthly_inr_is_kept_as_entered_and_normalised(client, db_session):
    world = await core(client, db_session)
    body = {"current_salary": "50000", "current_salary_period": "month", "expected_salary": "800000", "minimum_salary": "700000", "salary_negotiable": True}
    response = await client.patch(_path(world), json=body, headers=_u(world, "rec"))
    assert response.status_code == 200, response.text
    out = response.json()
    assert (Decimal(out["current_salary"]), out["current_salary_currency"], out["current_salary_period"]) == (Decimal("50000"), "INR", "month")  # AC3
    assert Decimal(out["current_annual_inr"]) == Decimal("600000")  # AC1
    assert (out["expected_salary_currency"], out["expected_salary_period"], Decimal(out["expected_annual_inr"])) == ("INR", "year", Decimal("800000"))
    assert Decimal(out["minimum_annual_inr"]) == Decimal("700000") and out["salary_negotiable"] is True


async def test_usd_uses_the_admin_rate(client, db_session):
    world = await core(client, db_session)
    await _rate(db_session, "USD", "83.2500")
    body = {"expected_salary": "4000", "expected_salary_currency": "usd", "expected_salary_period": "month"}
    out = (await client.patch(_path(world), json=body, headers=_u(world, "rec"))).json()
    assert out["expected_salary_currency"] == "USD" and Decimal(out["expected_salary"]) == Decimal("4000")  # AC3
    assert Decimal(out["expected_annual_inr"]) == Decimal("3996000")  # AC2


async def test_a_rate_change_recomputes_and_is_audited(client, db_session):
    world = await core(client, db_session)
    currency = "AED"
    await _rate(db_session, currency, "22.0000")
    await client.patch(_path(world), json={"current_salary": "10000", "current_salary_currency": currency, "current_salary_period": "month"}, headers=_u(world, "rec"))
    response = await client.put(f"{RATES}/{currency.lower()}", json={"inr_per_unit": "23.5"}, headers=_u(world, "mgr"))
    assert response.status_code == 200, response.text
    assert response.json()["currency"] == currency and Decimal(response.json()["inr_per_unit"]) == Decimal("23.5")
    out = (await client.get(_path(world), headers=_u(world, "rec"))).json()
    assert Decimal(out["current_annual_inr"]) == Decimal("2820000")  # 10,000 x 12 x 23.5
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter.fx_rate_set", AuditLog.entity_id == currency).order_by(AuditLog.created_at.desc()))
    assert row is not None and row.metadata_json["old"] == "22.0000" and row.metadata_json["new"] == "23.5000" and row.metadata_json["recomputed"] >= 1


async def test_clearing_an_amount_clears_its_currency_period_and_figure(client, db_session):
    world = await core(client, db_session)
    await client.patch(_path(world), json={"minimum_salary": "30000", "minimum_salary_period": "month"}, headers=_u(world, "rec"))
    out = (await client.patch(_path(world), json={"minimum_salary": None}, headers=_u(world, "rec"))).json()
    assert out["minimum_salary"] is None and out["minimum_salary_currency"] is None and out["minimum_salary_period"] is None and out["minimum_annual_inr"] is None


async def test_a_period_change_alone_renormalises(client, db_session):
    world = await core(client, db_session)
    await client.patch(_path(world), json={"expected_salary": "60000"}, headers=_u(world, "rec"))
    out = (await client.patch(_path(world), json={"expected_salary_period": "month"}, headers=_u(world, "rec"))).json()
    assert Decimal(out["expected_annual_inr"]) == Decimal("720000")


@pytest.mark.parametrize(
    "body, message",
    [
        ({"expected_salary": "-1"}, "Expected salary"),
        ({"expected_salary": "1", "expected_salary_currency": "ZZQ"}, "exchange rate"),
        ({"expected_salary": "1", "expected_salary_currency": "US"}, "currency"),
        ({"expected_salary": "1", "expected_salary_period": "hour"}, "period"),
        ({"minimum_salary": "-5"}, "Minimum salary"),
        ({"salary_negotiable": "maybe"}, "Negotiable"),
    ],
)
async def test_invalid_compensation_is_422(client, db_session, body, message):
    world = await core(client, db_session)
    response = await client.patch(_path(world), json=body, headers=_u(world, "rec"))
    assert response.status_code == 422 and message.lower() in response.text.lower(), response.text


async def test_create_defaults_to_inr_per_year(client, db_session):
    world = await core(client, db_session)
    source = (await db_session.get(Candidate, UUID(world["candidate"]))).source_id
    body = {"name": "Meera Iyer", "email": f"{tag('hrc11-')}@example.com", "source_id": str(source), "expected_salary": "900000"}
    out = (await client.post("/api/v1/recruiter/candidates", json=body, headers=_u(world, "rec"))).json()
    assert (out["expected_salary_currency"], out["expected_salary_period"], Decimal(out["expected_annual_inr"])) == ("INR", "year", Decimal("900000"))
    assert out["current_salary"] is None and out["current_annual_inr"] is None and out["salary_negotiable"] is None  # unknown stays null


# --- the grant (AC4, C7) ----------------------------------------------------------------------------------------------------------------
async def test_no_compensation_key_without_the_grant(client, db_session):
    world = await core(client, db_session)
    await client.patch(_path(world), json={"expected_salary": "800000", "minimum_salary": "700000", "salary_negotiable": False}, headers=_u(world, "rec"))
    hidden = (await client.get(_path(world), headers=_u(world, "hr"))).json()
    assert not (NEW_KEYS | {"current_salary", "expected_salary"}) & set(hidden)
    await add(db_session, UserPermissionOverride(user_id=world["users"]["rec"].id, resource="candidates.compensation", action="view", effect="deny", reason="hrc-011 test"))
    await db_session.commit()
    for key, value in (("minimum_salary", "1"), ("salary_negotiable", True), ("expected_salary_currency", "INR"), ("current_salary_period", "month")):
        assert (await client.patch(_path(world), json={key: value}, headers=_u(world, "rec"))).status_code == 403, key


# --- search and pools (C6) --------------------------------------------------------------------------------------------------------------
async def test_search_range_uses_the_annual_inr_and_cards_carry_it(client, db_session):
    world = await core(client, db_session)
    await client.patch(_path(world), json={"expected_salary": "70000", "expected_salary_period": "month"}, headers=_u(world, "rec"))  # 8.4 LPA
    category = await db_session.scalar(select(SkillCategory.id).where(SkillCategory.name == "Programming"))
    skill = await add(db_session, Skill(name=f"Elixir {tag()}", category_id=category))
    await add(db_session, CandidateSkill(candidate_id=UUID(world["candidate"]), skill_id=skill.id, level="advanced", added_by_user_id=world["users"]["rec"].id, status="claimed"))
    await db_session.commit()
    search = "/api/v1/recruiter/candidates/search"
    hit = await client.post(search, json={"all": [skill.name], "salary_min": 800000, "salary_max": 900000}, headers=_u(world, "rec"))
    assert hit.status_code == 200 and len(hit.json()["items"]) == 1, hit.text
    assert Decimal(str(hit.json()["items"][0]["expected_annual_inr"])) == Decimal("840000")
    miss = await client.post(search, json={"all": [skill.name], "salary_max": 100000}, headers=_u(world, "rec"))
    assert miss.json()["items"] == []  # the monthly 70,000 is not compared as a yearly figure
    hidden = await client.post(search, json={"all": [skill.name]}, headers=_u(world, "hr"))
    assert "expected_annual_inr" not in hidden.json()["items"][0]


# --- the rate table (C1) ----------------------------------------------------------------------------------------------------------------
async def test_rate_routes_roles_and_rules(client, db_session):
    world = await core(client, db_session)
    await _rate(db_session, "SGD", "62.0000")
    listed = await client.get(RATES, headers=_u(world, "hr"))
    assert listed.status_code == 200 and any(r["currency"] == "SGD" for r in listed.json()["items"])
    assert (await client.put(f"{RATES}/SGD", json={"inr_per_unit": "63"}, headers=_u(world, "rec"))).status_code == 403
    assert (await client.get(RATES, headers=_u(world, "bdm"))).status_code == 403
    for currency, body in (("INR", {"inr_per_unit": "1"}), ("SG", {"inr_per_unit": "1"}), ("SGD", {"inr_per_unit": "0"}), ("SGD", {"inr_per_unit": "10001"}), ("SGD", {})):
        assert (await client.put(f"{RATES}/{currency}", json=body, headers=_u(world, "mgr"))).status_code == 422, (currency, body)
    assert (await client.put(f"{RATES}/SGD", json={"inr_per_unit": "61.5"}, headers=_u(world, "super"))).status_code == 200
