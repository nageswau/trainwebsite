"""upc-023 (DEC-SCOPE-161, spec §4): the §23 Expected University Partnerships list, the §24 probability override and the weighted forecast
(Appendix B E1-E4).

The list is read-only and computed live: one scoped query (upc-018 PF6: manager = primary/backup, head = team + unowned, super_admin = all)
and the clock; the windows are folded in Python over those rows, so the figures never depend on the page (EX10, EX12). The override is a
write like upc-007's stage move: the university row lock, the stage rule (`can_move_stage`: 403 logged; inactive 409), change, an audit row
only when something changed, one commit here, then the structured log (ids and values only; the reason is never logged)."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.partnership_universities import _locked
from app.core.database import get_db
from app.models import Country, University, User
from app.partnership_stages import PROBABILITY, STAGE_KEYS, effective_probability, label_of
from app.schemas import ExpectedPage, ExpectedWindowKey, UniversityEnvelope, UniversityProbabilityPut
from app.services import partnership_universities as universities
from app.services.bdm_activities import india_date
from app.services.bdm_appointments import db_now
from app.services.partnership import partnership_context
from app.services.partnership_metrics import forecast_windows, scope_filter, weighted
from app.services.telecaller import person_ref

router = APIRouter(prefix="/partnership", tags=["partnership-expected"])
READERS = frozenset({"partnership_manager", "partnership_head", "super_admin"})  # EX5
NOT_SIGNED = STAGE_KEYS[: STAGE_KEYS.index("agreement_signed")]  # EX7


async def _require_reader(db: AsyncSession, user: User) -> None:
    if user.role == "partnership_manager":
        await partnership_context(db, user)  # a manager without a profile is a 403 (upc-001)
    elif user.role not in READERS:
        raise HTTPException(403, "Expected partnerships are for partnership managers and heads")


def _row(uni: University, country: str, owner: User | None) -> dict:
    return {
        "university": {"id": uni.id, "university_code": uni.university_code, "name": uni.name}, "country": country, "stage": uni.stage,
        "stage_label": label_of(uni.stage), "expected_agreement_date": uni.expected_agreement_date, "owner": person_ref(owner) if owner else None,
        "probability": effective_probability(uni.stage, uni.probability_override), "stage_probability": PROBABILITY[uni.stage],
        "override_reason": uni.probability_override_reason,
    }  # fmt: skip


def _in(day: date | None, first: date, last: date) -> bool:
    return day is not None and first <= day <= last


async def expected_rows(db: AsyncSession, user: User, team: frozenset[UUID]) -> list:
    """EX6/EX7: the caller's active, not-lost universities before Agreement Signed, with their country and owner (one query)."""
    stmt = (
        select(University, Country.name, User)
        .join(Country, Country.id == University.country_id)
        .outerjoin(User, User.id == University.primary_manager_user_id)
        .where(University.active.is_(True), University.lost_at.is_(None), University.stage.in_(NOT_SIGNED), *scope_filter(user, team))
    )
    return list((await db.execute(stmt)).all())


def window_figures(rows: list, today: date) -> list[dict]:
    """E1-E3 with E4: per window its raw count and weighted forecast (upc-022's D13 reads `this_month`)."""
    figures = []
    for w in forecast_windows(today):
        inside = [effective_probability(uni.stage, uni.probability_override) for uni, *_ in rows if _in(uni.expected_agreement_date, w.first, w.last)]
        figures.append({**w._asdict(), "count": len(inside), "weighted": weighted(inside)})
    return figures


def chosen_rows(rows: list, window: str, today: date) -> list:
    """EX9/EX12: `all` = every dated row (overdue included), a window = its IST days, `undated` = no expected date; by expected date, then
    name (upc-031's expected report lists the same rows)."""
    if window == "undated":
        chosen = [r for r in rows if r[0].expected_agreement_date is None]
    elif window == "all":
        chosen = [r for r in rows if r[0].expected_agreement_date is not None]
    else:
        w = next(w for w in forecast_windows(today) if w.key == window)
        chosen = [r for r in rows if _in(r[0].expected_agreement_date, w.first, w.last)]
    return sorted(chosen, key=lambda r: (r[0].expected_agreement_date or date.max, r[0].name.casefold(), str(r[0].id)))


@router.get("/expected", response_model=ExpectedPage)
async def expected(
    window: ExpectedWindowKey = "all",
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """EX9: `all` = every dated row (overdue included), a window = its IST days, `undated` = no expected date (never in a window).
    Ordered by expected date, then name (EX12); every figure covers the whole scope, not the page."""
    await _require_reader(db, user)
    today = india_date(await db_now(db))
    rows = await expected_rows(db, user, await universities.team_of(db, user))
    figures = window_figures(rows, today)
    chosen = chosen_rows(rows, window, today)
    return {
        "today": today, "window": window, "windows": figures, "undated_count": sum(1 for uni, *_ in rows if uni.expected_agreement_date is None),
        "total": len(chosen), "limit": limit, "offset": offset, "items": [_row(*r) for r in chosen[offset : offset + limit]],
    }  # fmt: skip


@router.put("/universities/{university_id}/probability", response_model=UniversityEnvelope)
async def set_probability(university_id: UUID, payload: UniversityProbabilityPut, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """EX2-EX4: set (0-100, with a reason) or clear (null) the manual override; the stage probability is unchanged."""
    uni, team = await _locked(db, user, university_id, "can_move_stage", "probability")
    before = (uni.probability_override, uni.probability_override_reason)
    if before != (payload.probability, payload.reason):
        uni.probability_override, uni.probability_override_reason = payload.probability, payload.reason
        universities.audit(db, user, "probability_overridden", uni.id, {"from": before[0], "to": payload.probability, "reason": payload.reason is not None})
        await db.commit()
        universities.log("university_probability_overridden", user, uni.id, from_value=before[0], to_value=payload.probability)
    return {"university": await universities.detail_out(db, user, uni, team)}
