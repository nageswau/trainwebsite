"""mgmt-015 -- partner capital accounts: `services/partner_capital.py` and /management/capital (spec CP1-CP15; AC1-AC4).

The test database is shared and never truncated, so every test reads its own partners' columns by id and never assumes the partner list.
Net profit comes from mgmt-009's `management_pnl.dashboard`; the profit-share tests replace it with fixed monthly figures."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import false, select

from app.models import AuditLog, PartnerShare
from app.services import partner_capital
from tests.bdm001_helpers import login, make_user

URL = "/api/v1/management/capital"
ENTRIES = f"{URL}/entries"
SHARES = f"{URL}/shares"


async def partner_client(client, db_session, name: str | None = None):
    partner = await make_user(db_session, "partner", "global", name=name)
    await login(client, partner)
    return partner


async def view(client, **params) -> dict:
    response = await client.get(URL, params=params)
    assert response.status_code == 200, response.text
    return response.json()


def account(data: dict, partner) -> dict:
    [found] = [a for a in data["accounts"] if a["partner"]["id"] == str(partner.id)]
    return found


async def add(client, partner, kind: str, amount: str, day: str = "2024-04-01", note: str | None = None) -> dict:
    response = await client.post(ENTRIES, json={"partner_id": str(partner.id), "entry_date": day, "kind": kind, "amount": amount, "note": note})
    assert response.status_code == 201, response.text
    return response.json()


async def set_shares(client, month: str, *rows) -> dict:
    payload = {"effective_from": month, "shares": [{"partner_id": str(p.id), "share_pct": pct, "commitment": commitment} for p, pct, commitment in rows]}
    response = await client.put(SHARES, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


async def audit_rows(db_session, entity_id: str) -> list[AuditLog]:
    return list((await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == entity_id).order_by(AuditLog.created_at))).all())


def monthly_profit(monkeypatch, by_month: dict[str, str]):
    """Each month's net profit (mgmt-009 total contribution); any other month made zero."""

    async def dashboard(db, user, month_start, period):
        assert period == "month"
        return {"total": {"contribution": Decimal(by_month.get(month_start.strftime("%Y-%m"), "0"))}}

    monkeypatch.setattr(partner_capital.management_pnl, "dashboard", dashboard)


# --- pure figures (CP8, CP9) ---------------------------------------------------------------------------------------------------
def test_ac2_capital_balance_is_invested_plus_additional_minus_withdrawals_and_returns_do_not_count():
    sums = {"initial": Decimal("500000"), "additional": Decimal("200000"), "withdrawal": Decimal("150000"), "profit_distribution": Decimal("90000")}
    out = partner_capital.figures(sums, share_pct=Decimal("50"), commitment=Decimal("1000000"), profit_share=None)
    assert (out["invested"], out["additional"], out["withdrawals"], out["returns"]) == (Decimal("500000.00"), Decimal("200000.00"), Decimal("150000.00"), Decimal("90000.00"))
    assert out["balance"] == Decimal("550000.00")
    assert out["outstanding"] == Decimal("300000.00")  # 10,00,000 - (5,00,000 + 2,00,000)


def test_outstanding_is_never_negative_and_unknown_without_a_commitment():
    sums = {"initial": Decimal("900")}
    assert partner_capital.figures(sums, share_pct=None, commitment=Decimal("500"), profit_share=None)["outstanding"] == Decimal("0.00")
    assert partner_capital.figures(sums, share_pct=None, commitment=None, profit_share=None)["outstanding"] is None
    assert partner_capital.figures({}, share_pct=None, commitment=None, profit_share=None)["balance"] == Decimal("0.00")


def test_ac3_profit_share_is_share_pct_times_net_profit():
    months = [(date(2026, 4, 1), Decimal("1000000"))]
    assert partner_capital.profit_share(months, [(date(2024, 4, 1), Decimal("50"))]) == Decimal("500000.00")


def test_profit_share_applies_a_mid_period_change_from_its_month_and_rounds_half_up():
    months = [(date(2026, 4, 1), Decimal("100")), (date(2026, 5, 1), Decimal("100")), (date(2026, 6, 1), Decimal("-10.01"))]
    history = [(date(2024, 4, 1), Decimal("50")), (date(2026, 5, 1), Decimal("40"))]
    assert partner_capital.profit_share(months, history) == Decimal("86.00")  # 50 + 40 - 4.004 = 85.996, rounded once
    assert partner_capital.profit_share(months[:1], [(date(2026, 5, 1), Decimal("40"))]) is None  # no share in force that month
    assert partner_capital.profit_share([(date(2026, 4, 1), Decimal("0.01"))], [(date(2026, 4, 1), Decimal("50"))]) == Decimal("0.01")


# --- entries (CP2-CP4, CP11, CP12) ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_entry_is_recorded_with_its_creator_and_audited_with_its_values(client, db_session):
    partner = await partner_client(client, db_session, name="Capital Partner")
    out = await add(client, partner, "initial", "500000", note="  Opening capital  ")
    assert (out["kind"], out["amount"], out["entry_date"], out["note"]) == ("initial", "500000.00", "2024-04-01", "Opening capital")
    assert out["partner"] == {"id": str(partner.id), "full_name": "Capital Partner"} and out["created_by"] == out["partner"]
    [row] = await audit_rows(db_session, out["id"])
    assert (row.user_id, row.action, row.entity_type) == (partner.id, "mgmt.capital.create", "mgmt.capital")
    assert row.metadata_json["values"]["amount"] == {"before": None, "after": "500000.00"}
    assert row.metadata_json["values"]["kind"]["after"] == "initial" and row.metadata_json["values"]["note"]["after"] == "Opening capital"


@pytest.mark.asyncio
async def test_a_partner_records_an_entry_for_the_other_partner(client, db_session):
    await partner_client(client, db_session)
    other = await make_user(db_session, "partner", "global")
    out = await add(client, other, "additional", "1000.50")
    assert out["partner"]["id"] == str(other.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"amount": "0"}, "more than ₹0"),
        ({"amount": "-5"}, "more than ₹0"),
        ({"amount": "1.005"}, "up to 2 decimals"),
        ({"amount": "abc"}, "up to 2 decimals"),
        ({"kind": "bonus"}, "kind"),
        ({"entry_date": "1999-12-31"}, "before 1 January 2000"),
        ({"entry_date": "2024-02-30"}, "valid entry date"),
        ({"entry_date": "2999-01-01"}, "can't be in the future"),
        ({"note": "x" * 501}, "500"),
        ({"note": "line\nbreak"}, "invalid characters"),
        ({"extra": 1}, "extra"),
    ],
)
async def test_an_entry_rejects_bad_input_with_a_worded_422(client, db_session, overrides, message):
    partner = await partner_client(client, db_session)
    payload = {"partner_id": str(partner.id), "entry_date": "2024-04-01", "kind": "initial", "amount": "10", **overrides}
    response = await client.post(ENTRIES, json=payload)
    assert response.status_code == 422 and message in response.text, response.text


@pytest.mark.asyncio
async def test_an_entry_needs_an_active_partner(client, db_session):
    await partner_client(client, db_session)
    for user in (await make_user(db_session, "accountant", "global"), await make_user(db_session, "partner", "global", active=False)):
        response = await client.post(ENTRIES, json={"partner_id": str(user.id), "entry_date": "2024-04-01", "kind": "initial", "amount": "10"})
        assert response.status_code == 422 and "Choose an active partner" in response.text


@pytest.mark.asyncio
async def test_a_withdrawal_over_the_balance_is_accepted_and_shows_a_negative_balance(client, db_session):
    partner = await partner_client(client, db_session)
    await add(client, partner, "initial", "1000")
    await add(client, partner, "withdrawal", "1500")
    await add(client, partner, "profit_distribution", "700")
    mine = account(await view(client), partner)
    assert (mine["invested"], mine["withdrawals"], mine["balance"], mine["returns"]) == ("1000.00", "1500.00", "-500.00", "700.00")


# --- shares (CP5-CP7, CP12, CP14) ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_shares_are_set_from_a_month_and_audited_and_an_unchanged_save_writes_nothing(client, db_session):
    one = await partner_client(client, db_session)
    two = await make_user(db_session, "partner", "global")
    out = await set_shares(client, "2024-04", (one, "50", "1000000"), (two, "50", None))
    mine = [s for s in out["items"] if s["partner"]["id"] == str(one.id)]
    assert [(s["effective_from"], s["share_pct"], s["commitment"], s["in_force"]) for s in mine] == [("2024-04-01", "50.00", "1000000.00", True)]
    row = await db_session.scalar(select(PartnerShare).where(PartnerShare.partner_user_id == one.id))
    [created] = await audit_rows(db_session, str(row.id))
    assert created.action == "mgmt.capital.create" and created.metadata_json["values"]["share_pct"]["after"] == "50.00"

    await set_shares(client, "2024-04", (one, "50", "1000000"))
    assert len(await audit_rows(db_session, str(row.id))) == 1

    await set_shares(client, "2024-04", (one, "60", "1000000"))
    *_, updated = await audit_rows(db_session, str(row.id))
    assert updated.action == "mgmt.capital.update" and updated.metadata_json == {"fields": ["share_pct"], "values": {"share_pct": {"before": "50.00", "after": "60.00"}}}


@pytest.mark.asyncio
async def test_a_later_month_keeps_the_history_and_a_planned_change_is_not_yet_in_force(client, db_session):
    one = await partner_client(client, db_session)
    data = await view(client)
    this_month = date.fromisoformat(data["as_of"]).replace(day=1)
    next_month = date(this_month.year + this_month.month // 12, this_month.month % 12 + 1, 1)
    await set_shares(client, "2024-04", (one, "50", None))
    out = await set_shares(client, next_month.strftime("%Y-%m"), (one, "40", "2000"))
    mine = [(s["effective_from"], s["share_pct"], s["in_force"]) for s in out["items"] if s["partner"]["id"] == str(one.id)]
    assert mine == [(next_month.isoformat(), "40.00", False), ("2024-04-01", "50.00", True)]
    assert (account(await view(client), one)["share_pct"], account(await view(client), one)["commitment"]) == ("50.00", None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"effective_from": "1999-12", "shares": None}, "January 2000 to 12 months ahead"),
        ({"effective_from": "2999-01", "shares": None}, "January 2000 to 12 months ahead"),
        ({"effective_from": "2024-13", "shares": None}, "pattern"),
        ({"effective_from": "2024-04", "shares": []}, "at least 1"),
        ({"effective_from": "2024-04", "shares": "twice"}, "listed only once"),
        ({"effective_from": "2024-04", "shares": [{"share_pct": "100.01"}]}, "from 0 to 100"),
        ({"effective_from": "2024-04", "shares": [{"share_pct": "-1"}]}, "from 0 to 100"),
        ({"effective_from": "2024-04", "shares": [{"share_pct": "33.333"}]}, "from 0 to 100"),
        ({"effective_from": "2024-04", "shares": [{"commitment": "-1"}]}, "commitment can't be negative"),
    ],
)
async def test_shares_reject_bad_input_with_a_worded_422(client, db_session, payload, message):
    partner = await partner_client(client, db_session)
    row = {"partner_id": str(partner.id), "share_pct": "50", "commitment": None}
    shares = payload["shares"]
    if shares is None:
        shares = [row]
    elif shares == "twice":
        shares = [row, row]
    elif shares:
        shares = [{**row, **shares[0]}]
    response = await client.put(SHARES, json={"effective_from": payload["effective_from"], "shares": shares})
    assert response.status_code == 422 and message in response.text, response.text


@pytest.mark.asyncio
async def test_losing_the_first_insert_race_for_a_month_is_a_409_not_a_500(client, db_session, monkeypatch):
    """CP14: the other partner's first save of the same month commits between our locked read (which found nothing) and our insert."""
    partner = await partner_client(client, db_session)
    await set_shares(client, "2024-04", (partner, "50", None))
    real_select = partner_capital.select

    def blind_select(*entities):  # the locked read misses the row the other partner just committed
        query = real_select(*entities)
        return query.where(false()) if entities[0] is PartnerShare else query

    monkeypatch.setattr(partner_capital, "select", blind_select)
    response = await client.put(SHARES, json={"effective_from": "2024-04", "shares": [{"partner_id": str(partner.id), "share_pct": "60"}]})
    assert response.status_code == 409 and "changed at the same time" in response.text, response.text


@pytest.mark.asyncio
async def test_shares_need_active_partners(client, db_session):
    await partner_client(client, db_session)
    gone = await make_user(db_session, "partner", "global", active=False)
    response = await client.put(SHARES, json={"effective_from": "2024-04", "shares": [{"partner_id": str(gone.id), "share_pct": "50"}]})
    assert response.status_code == 422 and "Choose an active partner" in response.text


def test_ac1_shares_not_totalling_100_are_flagged_by_the_total():
    accounts = [partner_capital.figures({}, share_pct=Decimal("50"), commitment=None, profit_share=None), partner_capital.figures({}, share_pct=Decimal("40"), commitment=None, profit_share=None)]
    assert partner_capital.totals(accounts)["share_pct"] == Decimal("90.00")
    assert partner_capital.totals([partner_capital.figures({}, share_pct=None, commitment=None, profit_share=None)])["share_pct"] == Decimal("0.00")


# --- the view (CP1, CP8-CP10, CP15) --------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac3_the_view_gives_each_partner_share_pct_of_net_profit_over_the_period(client, db_session, monkeypatch):
    one = await partner_client(client, db_session)
    two = await make_user(db_session, "partner", "global")
    await set_shares(client, "2024-04", (one, "50", "1000000"), (two, "50", "1000000"))
    await add(client, one, "initial", "500000")
    monthly_profit(monkeypatch, {"2026-04": "600000", "2026-05": "400000"})
    data = await view(client, month="2026-05", period="year")
    assert (data["period"], data["month"], data["net_profit"]) == ("year", "2026-05", "1000000.00")
    assert data["label"] == "Financial year 2026-27 to date"
    mine = account(data, one)
    assert (mine["share_pct"], mine["profit_share"], mine["outstanding"], mine["balance"]) == ("50.00", "500000.00", "500000.00", "500000.00")
    assert account(data, two)["profit_share"] == "500000.00" and account(data, two)["partner"]["active"] is True

    month_only = await view(client, month="2026-05", period="month")
    assert (month_only["net_profit"], account(month_only, one)["profit_share"]) == ("400000.00", "200000.00")


@pytest.mark.asyncio
async def test_the_view_rejects_a_future_month_or_unknown_period(client, db_session):
    await partner_client(client, db_session)
    assert (await client.get(URL, params={"month": "2999-01"})).status_code == 422
    assert (await client.get(URL, params={"period": "week"})).status_code == 422


@pytest.mark.asyncio
async def test_entries_are_newest_first_and_paged(client, db_session):
    partner = await partner_client(client, db_session)
    for day in ("2024-04-01", "2024-06-01", "2024-05-01"):
        await add(client, partner, "additional", "1", day=day)
    data = await view(client)
    assert data["entries"]["limit"] == 25 and data["entries"]["total"] >= 3
    dates = [e["entry_date"] for e in data["entries"]["items"]]
    assert dates == sorted(dates, reverse=True)
    second = await view(client, offset=1)
    assert second["entries"]["offset"] == 1 and second["entries"]["items"][0] == data["entries"]["items"][1]


@pytest.mark.asyncio
async def test_a_former_partner_with_records_stays_listed_and_partner_choices_are_active_only(client, db_session):
    me = await partner_client(client, db_session)
    gone = await make_user(db_session, "partner", "global")
    await add(client, gone, "initial", "100")
    gone.active = False
    await db_session.commit()
    data = await view(client)
    assert account(data, gone)["partner"]["active"] is False and account(data, gone)["invested"] == "100.00"
    choices = {p["id"] for p in data["partners"]}
    assert str(me.id) in choices and str(gone.id) not in choices


# --- access (CP13, M13, AC4) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "division", "message"),
    [
        ("accountant", "global", "Only partners"),
        ("super_admin", "global", "Only partners"),
        ("bdm_manager", "global", "Management access required"),
        ("it_admin", "it", "Management access required"),
    ],
)
async def test_ac4_everyone_but_a_partner_is_refused(client, db_session, role, division, message):
    partner = await make_user(db_session, "partner", "global")
    await login(client, await make_user(db_session, role, division))
    for response in (
        await client.get(URL),
        await client.post(ENTRIES, json={"partner_id": str(partner.id), "entry_date": "2024-04-01", "kind": "initial", "amount": "10"}),
        await client.put(SHARES, json={"effective_from": "2024-04", "shares": [{"partner_id": str(partner.id), "share_pct": "50"}]}),
    ):
        assert response.status_code == 403 and message in response.text, response.text


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(URL)).status_code == 401
    assert (await client.post(ENTRIES, json={})).status_code == 401
    assert (await client.put(SHARES, json={})).status_code == 401
