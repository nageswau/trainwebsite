"""upc-031 (DEC-SCOPE-173, spec docs/superpowers/specs/2026-10-10-upc-031-partnership-reports-design.md): the §32 partnership reports.

Five read-only tables, each built from the code behind the figure it repeats, so a report always reconciles with its page (AC): pipeline
by country = the dashboard overview (upc-022 D1-D5), expected = upc-023's rows, performance = upc-018's ranking, agreements expiring =
upc-014's AG4 effective status, targets = upc-021's team comparison. Scope is upc-018 PF6 (targets: upc-021's own). Commission columns
only for the U2 roles (RP12). Counts, names and dates only -- no student is identified. Nothing here writes or commits."""

import re
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.partnership_expected import READERS, chosen_rows, expected_rows
from app.api.partnership_performance import _add, ranking
from app.models import Country, University, UniversityAgreement, User
from app.partnership_stages import effective_probability, label_of
from app.partnership_target_kpis import KPIS
from app.services import partnership_targets, partnership_universities
from app.services.bdm_activities import india_date
from app.services.bdm_appointments import db_now
from app.services.partnership import partnership_context
from app.services.partnership_metrics import STEPS, _in_group, period, scope_filter, weighted
from app.services.university_agreements import STATUS_LABELS, TYPE_LABELS, effective_status_sql

ROLE_REQUIRED = "Partnership reports are for partnership managers and heads"
SCREEN_ROWS = 500  # RP11: the page shows the first rows; the CSV has them all
CSV_ROWS = 5_000  # a larger export is refused, never cut short
TITLES = {
    "pipeline": "Pipeline by Country", "expected": "Expected Partnerships", "performance": "University Performance",
    "agreements": "Agreements Expiring", "targets": "Targets vs Actual",
}  # fmt: skip
FILTERS = {"pipeline": (), "expected": ("window",), "performance": ("from", "to"), "agreements": (), "targets": ("month",)}
WINDOWS = ("all", "this_month", "next_month", "this_quarter", "undated")  # upc-023 EX9
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class ReportInputError(Exception):
    """A refused input; the message names the form's field (the 422 detail)."""


async def require_reader(db: AsyncSession, user: User) -> None:
    if user.role not in READERS:  # RP2: the dashboard's readers (DB15)
        raise HTTPException(403, ROLE_REQUIRED)
    if user.role == "partnership_manager":
        await partnership_context(db, user)  # a manager without a profile is a 403 (upc-001)


def given(kind: str, raw: dict[str, str | None]) -> list[str]:
    """The kind's filters the caller set (names only: what is logged and audited)."""
    return [name for name in FILTERS[kind] if raw.get(name)]


def _col(key: str, label: str, numeric: bool = False) -> dict:
    return {"key": key, "label": label, "numeric": numeric}


def _day(raw: str | None, field: str, default: date) -> date:
    if not raw:
        return default
    try:
        if not DAY.match(raw):
            raise ValueError
        return date.fromisoformat(raw)
    except ValueError:
        raise ReportInputError(f"{field}: use a real date (YYYY-MM-DD)") from None


def _money(sums: dict[str, Decimal]) -> str:
    """Per-currency amounts as text ("GBP 1200.00; USD 50.00"): currencies never add up."""
    return "; ".join(f"{currency} {value:.2f}" for currency, value in sorted(sums.items()) if value)


async def _pipeline(db: AsyncSession, user: User, today: date, raw: dict) -> dict:
    """RP5: the dashboard overview (D1-D5 + lost) per country of the active universities in scope."""
    team = await partnership_universities.team_of(db, user)
    counts = (
        func.count(), func.count().filter(_in_group("partner")), func.count().filter(_in_group("in_progress")), func.count().filter(_in_group("target")),
        func.count().filter(University.lost_at.is_not(None)), func.count().filter(University.relationship_strength == "at_risk"),
    )  # fmt: skip
    rows = await db.execute(
        select(Country.name, *counts).join(Country, Country.id == University.country_id)
        .where(University.active.is_(True), *scope_filter(user, team)).group_by(Country.name).order_by(func.count().desc(), Country.name)
    )  # fmt: skip
    keys = ("total", "partners", "in_progress", "targets", "lost", "at_risk")
    items = [{"country": country, **dict(zip(keys, values, strict=True))} for country, *values in rows.all()]
    columns = [_col("country", "Country"), *(_col(k, label, True) for k, label in zip(keys, ("Total", "Partners", "In progress", "Targets", "Lost", "At risk"), strict=True))]
    return {"columns": columns, "items": items, "totals": {"country": "Total", **{k: sum(i[k] for i in items) for k in keys}}, "filters": {}}


async def _expected(db: AsyncSession, user: User, today: date, raw: dict) -> dict:
    """RP6: upc-023's rows for one window, ordered as the Expected page (EX12); the Total row's Weighted is E4."""
    window = raw.get("window") or "all"
    if window not in WINDOWS:
        raise ReportInputError("Expected date window: choose one of the listed windows")
    rows = await expected_rows(db, user, await partnership_universities.team_of(db, user))
    items = []
    for uni, country, owner in chosen_rows(rows, window, today):
        probability = effective_probability(uni.stage, uni.probability_override)
        items.append({
            "university": uni.name, "code": uni.university_code, "country": country, "stage": label_of(uni.stage),
            "expected_date": uni.expected_agreement_date.isoformat() if uni.expected_agreement_date else None,
            "owner": owner.full_name if owner else None, "probability": probability, "weighted": probability / 100,
        })  # fmt: skip
    columns = [
        _col("university", "University"), _col("code", "Code"), _col("country", "Country"), _col("stage", "Stage"), _col("expected_date", "Expected date"),
        _col("owner", "Owner"), _col("probability", "Probability (%)", True), _col("weighted", "Weighted", True),
    ]  # fmt: skip
    totals = dict.fromkeys(c["key"] for c in columns) | {"university": "Total", "weighted": weighted([i["probability"] for i in items])}
    return {"columns": columns, "items": items, "totals": totals, "filters": {"window": window}}


async def _performance(db: AsyncSession, user: User, today: date, raw: dict) -> dict:
    """RP7: upc-018's ranking over the period (PF1: default this IST month to date), every ranked row, F3 + F5-F9."""
    first, last = period(_day(raw.get("from"), "From", today.replace(day=1)), _day(raw.get("to"), "To", today))
    ranked, totals, money = await ranking(db, user, await partnership_universities.team_of(db, user), first, last)  # money: None outside U2 (RP12)
    steps = [s for s in STEPS if s.tracked]
    columns = [_col("rank", "Rank", True), _col("university", "University"), _col("code", "Code"), _col("country", "Country"), _col("stage", "Stage"),
               *(_col(s.key, s.label, True) for s in steps)]  # fmt: skip
    items = [
        {"rank": i, "university": uni.name, "code": uni.university_code, "country": country, "stage": label_of(uni.stage), **{s.key: counts.get(s.key, 0) for s in steps}}
        for i, (uni, country, counts) in enumerate(ranked, start=1)
    ]  # fmt: skip
    out_totals: dict = {"rank": None, "university": "Total", "code": None, "country": None, "stage": None, **totals}
    if money is not None:
        columns += [_col("commission_expected", "Commission expected"), _col("commission_received", "Commission received")]
        overall: dict[str, dict[str, Decimal]] = {"expected": {}, "received": {}}
        for item, (uni, *_) in zip(items, ranked, strict=True):
            item |= {"commission_expected": _money(money[uni.id]["expected"]), "commission_received": _money(money[uni.id]["received"])}
            _add(overall["expected"], money[uni.id]["expected"])
            _add(overall["received"], money[uni.id]["received"])
        out_totals |= {"commission_expected": _money(overall["expected"]), "commission_received": _money(overall["received"])}
    return {"columns": columns, "items": items, "totals": out_totals, "filters": {"from": first.isoformat(), "to": last.isoformat()},
            "notes": ["Leads, Counselling and Eligible are not tracked, so they are not listed."]}  # fmt: skip


async def _agreements(db: AsyncSession, user: User, today: date, raw: dict) -> dict:
    """RP8: agreements whose AG4 effective status is Expiring today, on universities in scope, soonest expiry first."""
    team = await partnership_universities.team_of(db, user)
    rows = await db.execute(
        select(UniversityAgreement, University, Country.name, User)
        .join(University, University.id == UniversityAgreement.university_id)
        .join(Country, Country.id == University.country_id)
        .outerjoin(User, User.id == University.primary_manager_user_id)
        .where(effective_status_sql(today) == "expiring", *scope_filter(user, team))
        .order_by(UniversityAgreement.expiry_date, UniversityAgreement.mou_number)
    )
    items = [
        {
            "mou_number": a.mou_number, "university": uni.name, "code": uni.university_code, "country": country, "type": TYPE_LABELS[a.agreement_type],
            "status": STATUS_LABELS[a.status], "expiry_date": a.expiry_date.isoformat(), "days_left": (a.expiry_date - today).days,
            "owner": owner.full_name if owner else None,
        }
        for a, uni, country, owner in rows.all()
    ]  # fmt: skip
    columns = [
        _col("mou_number", "MoU number"), _col("university", "University"), _col("code", "Code"), _col("country", "Country"), _col("type", "Type"),
        _col("status", "Status"), _col("expiry_date", "Expiry date"), _col("days_left", "Days left", True), _col("owner", "Owner"),
    ]  # fmt: skip
    return {"columns": columns, "items": items, "totals": None, "filters": {}}


async def _targets(db: AsyncSession, user: User, today: date, raw: dict) -> dict:
    """RP9: upc-021's team comparison for the month; the Total row is the team row. Blank achieved = not tracked or a future month."""
    text = raw.get("month")
    if text and not MONTH.match(text):
        raise ReportInputError("Month: use YYYY-MM")
    current = today.replace(day=1)
    month = date(int(text[:4]), int(text[5:]), 1) if text else current
    sheet = await partnership_targets.team(db, user, month, current)

    def figures(kpis: list[dict]) -> dict:
        return {f"{k['key']}_{part}": k[part] for k in kpis for part in ("target", "achieved")}

    columns = [_col("manager", "Manager"), _col("status", "Status"),
               *(_col(f"{k.key}_{part}", f"{k.label} {part}", True) for k in KPIS for part in ("target", "achieved"))]  # fmt: skip
    items = [{"manager": r["manager"]["full_name"], "status": "Active" if r["active"] else "Inactive", **figures(r["kpis"])} for r in sheet["managers"]]
    return {"columns": columns, "items": items, "totals": {"manager": "Team total", "status": None, **figures(sheet["team"])},
            "filters": {"month": sheet["month"]}, "notes": ["A blank achieved figure is not tracked, or the month has not started."]}  # fmt: skip


BUILDERS = {"pipeline": _pipeline, "expected": _expected, "performance": _performance, "agreements": _agreements, "targets": _targets}


async def build(db: AsyncSession, user: User, kind: str, raw: dict[str, str | None]) -> dict:
    """Every row of one report (the caller has passed `require_reader` and the kind exists); the screen and the CSV cap are the route's."""
    today = india_date(await db_now(db))
    report = await BUILDERS[kind](db, user, today, raw)
    return {"kind": kind, "title": f"{TITLES[kind]} Report", "as_of": today.isoformat(), "notes": [], **report, "total": len(report["items"])}
