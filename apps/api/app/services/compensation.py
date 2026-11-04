"""hrc-011 (DEC-SCOPE-372, spec docs/superpowers/specs/2026-11-04-hrc-011-candidate-compensation-design.md): each candidate amount is
kept as entered (amount, currency, pay period) beside its annual INR figure, which search and pools compare (C6).

Functions only; nothing here commits -- the route owns the transaction."""

from decimal import ROUND_HALF_UP, Decimal

from fastapi import HTTPException
from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SALARY_PERIODS, Candidate, RecFxRate

INR = "INR"
AMOUNTS = ("current", "expected", "minimum")
CENT = Decimal("0.01")


def annual_inr(amount: Decimal | None, currency: str | None, period: str | None, rate: Decimal | None) -> Decimal | None:
    """C8: amount x periods a year x rupees per unit, half-up to the paisa; None when the amount is unknown."""
    if amount is None:
        return None
    return (amount * SALARY_PERIODS[period] * rate).quantize(CENT, rounding=ROUND_HALF_UP)


async def rate_of(db: AsyncSession, currency: str) -> Decimal:
    """INR is 1. FOR SHARE (C5): a concurrent rate change waits for this save, so neither leaves a stale figure."""
    if currency == INR:
        return Decimal(1)
    rate = await db.scalar(select(RecFxRate.inr_per_unit).where(RecFxRate.currency == currency).with_for_update(read=True))
    if rate is None:
        raise HTTPException(422, f"There is no exchange rate for {currency}. A placement manager adds it under Catalogues → Exchange rates.")
    return rate


async def normalise(db: AsyncSession, candidate: Candidate) -> None:
    """C4: a cleared amount clears its currency, period and figure; a set one keeps its currency and period, else INR per year."""
    for amount in AMOUNTS:
        value = getattr(candidate, f"{amount}_salary")
        if value is None:
            currency = period = None
        else:
            currency = getattr(candidate, f"{amount}_salary_currency") or INR
            period = getattr(candidate, f"{amount}_salary_period") or "year"
        setattr(candidate, f"{amount}_salary_currency", currency)
        setattr(candidate, f"{amount}_salary_period", period)
        setattr(candidate, f"{amount}_annual_inr", annual_inr(value, currency, period, await rate_of(db, currency) if currency else None))


async def recompute(db: AsyncSession, currency: str, rate: Decimal) -> int:
    """C5: every amount in this currency takes the new rate. `updated_at` is kept: a rate is not an edit of the candidate, so an open
    form is not made stale (hrc-003). Returns the number of amounts recomputed."""
    touched = 0
    for amount in AMOUNTS:
        value, period = getattr(Candidate, f"{amount}_salary"), getattr(Candidate, f"{amount}_salary_period")
        periods = case(*((period == key, n) for key, n in SALARY_PERIODS.items()), else_=1)
        result = await db.execute(
            update(Candidate)
            .where(getattr(Candidate, f"{amount}_salary_currency") == currency, value.is_not(None))
            .values({f"{amount}_annual_inr": func.round(value * periods * rate, 2), "updated_at": Candidate.updated_at})
            .execution_options(synchronize_session=False)
        )
        touched += result.rowcount or 0
    return touched
