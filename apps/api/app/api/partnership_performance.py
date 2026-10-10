"""upc-018 (DEC-SCOPE-153, spec §4): the §17 student opportunity funnel and the §18 university performance ranking (EVID-020).

Read-only and computed live by `services.partnership_metrics` (Appendix B F1-F9); nothing is stored or audited. The readers are the
University Master's (PF5). The ranking covers the caller's scope (PF6: manager = primary/backup, head = team + unowned, super_admin and
overseas_admin = all); one university's funnel follows the master's read rule (every reader reads every university). A constant query
count: the scope, one grouped query per step and the clock."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Country, University, User
from app.partnership_stages import GROUPS, label_of
from app.schemas import UniversityPerformance, UniversityPerformancePage
from app.services import partnership_universities as universities
from app.services import university_commission as commission
from app.services.bdm_activities import india_date
from app.services.bdm_appointments import db_now
from app.services.partnership_access import can_see_commission
from app.services.partnership_metrics import FUNNEL, STEPS, funnel_counts, period
from app.services.partnership_metrics import scope_filter as _scope  # PF6, shared with upc-022's dashboard

router = APIRouter(prefix="/partnership", tags=["partnership-performance"])
DAY = r"^\d{4}-\d{2}-\d{2}$"
FROM = Query(None, alias="from", pattern=DAY, description="First IST day, YYYY-MM-DD (default the 1st of this month)")
TO = Query(None, alias="to", pattern=DAY, description="Last IST day, YYYY-MM-DD (default today)")
LIMIT = Query(25, ge=1, le=100)
OFFSET = Query(0, ge=0)
PARTNER_STAGES = frozenset(key for key, group in GROUPS.items() if group == "partner")  # Appendix B G1
STEPS_OUT = [step._asdict() for step in STEPS]


async def request_period(db: AsyncSession, first: str | None, last: str | None) -> tuple[date, date]:
    """PF1: the default is this IST month to date."""
    today = india_date(await db_now(db))
    try:
        return period(date.fromisoformat(first) if first else today.replace(day=1), date.fromisoformat(last) if last else today)
    except ValueError as e:  # a well-formed but impossible day, e.g. 2025-02-30
        raise HTTPException(422, "Use a real date (YYYY-MM-DD)") from e


def _partner(uni: University) -> bool:
    return uni.stage in PARTNER_STAGES and uni.lost_at is None


def _university(uni: University, country: str) -> dict:
    return {
        "id": uni.id, "university_code": uni.university_code, "name": uni.name, "country": country, "stage": uni.stage,
        "stage_label": label_of(uni.stage), "partner": _partner(uni),
    }  # fmt: skip


def step_counts(found: dict[str, int] | None) -> dict:
    return {step.key: (found or {}).get(step.key, 0) if step.tracked else None for step in STEPS}


def _amounts(sums: dict[str, Decimal]) -> list[dict]:
    return [{"currency": c, "amount": commission.money_str(v)} for c, v in sorted(sums.items())]


def _add(total: dict[str, Decimal], part: dict[str, Decimal]) -> None:
    for currency, value in part.items():
        total[currency] = total.get(currency, Decimal(0)) + value


async def commission_by_university(db: AsyncSession, user: User, university_ids: list[UUID], first: date, last: date) -> dict[UUID, dict] | None:
    """upc-019 CL13 (F10/F11) per university for the period -- computed only for the commission roles (U2); None for everyone else."""
    if not can_see_commission(user):
        return None
    rows, received = await commission.expected_rows(db, university_ids), await commission.received_sums(db, university_ids, first, last)
    return {u: {"expected": commission.currency_sums(rows.get(u, []), first, last), "received": received.get(u, {})} for u in university_ids}


def _commission_out(sums: dict) -> dict:
    return {"expected": _amounts(sums["expected"]), "received": _amounts(sums["received"])}


def commission_totals(money: dict[UUID, dict]) -> dict:
    """F10/F11 summed over the universities, per currency."""
    overall: dict[str, dict[str, Decimal]] = {"expected": {}, "received": {}}
    for sums in money.values():
        _add(overall["expected"], sums["expected"])
        _add(overall["received"], sums["received"])
    return _commission_out(overall)


async def ranking(db: AsyncSession, user: User, team: frozenset[UUID], first: date, last: date) -> tuple[list, dict[str, int], dict[UUID, dict] | None]:
    """PF7/PF8: the ranked rows (active universities in scope that are partners or have any step in the period, by enrolled then
    applications), the funnel totals over all of them and their commission (None outside U2). upc-029's global dashboard shares it."""
    rows = (await db.execute(select(University, Country.name).join(Country, Country.id == University.country_id).where(University.active.is_(True), *_scope(user, team)))).all()
    found = await funnel_counts(db, [uni.id for uni, _ in rows], first, last)
    ranked = [(uni, country, found.get(uni.id, {})) for uni, country in rows if uni.id in found or _partner(uni)]
    ranked.sort(key=lambda r: (-r[2].get("enrolled", 0), -r[2].get("applications", 0), r[0].name.casefold(), str(r[0].id)))
    totals = {key: sum(counts.get(key, 0) for *_, counts in ranked) for key in FUNNEL}
    return ranked, totals, await commission_by_university(db, user, [uni.id for uni, *_ in ranked], first, last)


@router.get("/performance", response_model=UniversityPerformancePage, response_model_exclude_unset=True)
async def performance(first: str | None = FROM, last: str | None = TO, limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """PF7: the ranking, paged; `totals` is over every ranked row (PF8), not the page."""
    await universities.require_reader(db, user)
    first_day, last_day = await request_period(db, first, last)
    ranked, totals, money = await ranking(db, user, await universities.team_of(db, user), first_day, last_day)
    items = [{"rank": offset + i + 1, "university": _university(uni, country), "counts": step_counts(counts)} for i, (uni, country, counts) in enumerate(ranked[offset : offset + limit])]
    page = {"from": first_day, "to": last_day, "steps": STEPS_OUT, "totals": step_counts(totals), "items": items, "total": len(ranked), "limit": limit, "offset": offset}
    if money is not None:
        for item, (uni, *_) in zip(items, ranked[offset : offset + limit], strict=True):
            item["commission"] = _commission_out(money[uni.id])
        page["commission"] = commission_totals(money)
    return page


@router.get("/universities/{university_id}/performance", response_model=UniversityPerformance, response_model_exclude_unset=True)
async def university_performance(university_id: UUID, first: str | None = FROM, last: str | None = TO, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """One university's funnel (§17), active or not; an unknown id is a 404."""
    await universities.require_reader(db, user)
    first_day, last_day = await request_period(db, first, last)
    row = (await db.execute(select(University, Country.name).join(Country, Country.id == University.country_id).where(University.id == university_id))).one_or_none()
    if row is None:
        raise HTTPException(404, universities.NOT_FOUND)
    uni, country = row
    found = await funnel_counts(db, [uni.id], first_day, last_day)
    out = {"from": first_day, "to": last_day, "steps": STEPS_OUT, "university": _university(uni, country), "counts": step_counts(found.get(uni.id))}
    money = await commission_by_university(db, user, [uni.id], first_day, last_day)
    if money is not None:
        out["commission"] = _commission_out(money[uni.id])
    return out
