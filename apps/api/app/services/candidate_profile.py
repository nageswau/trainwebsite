"""hrc-010 (DEC-SCOPE-382, spec docs/superpowers/specs/2026-11-04-hrc-010-candidate-profile-design.md): the profile rows (education,
employment, certifications), the derived total experience (P4, Q-09), the legacy single fields as mirrors of the rows (P5) and the
Appendix B completeness (P10).

Functions only; nothing here commits -- the route owns the transaction, under the candidate's row lock."""

from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Candidate, CandidateCertification, CandidateEducation, CandidateEmployment, CandidateSkill

ROWS = {"education": CandidateEducation, "employment": CandidateEmployment, "certifications": CandidateCertification}
FIELDS = {
    "education": ("degree", "specialisation", "institution", "year", "grade"),
    "employment": ("employer", "designation", "industry", "employment_type", "start_date", "end_date"),
    "certifications": ("name", "issuer", "issued_on", "expires_on", "credential_id"),
}
# P5: the legacy fields a row kind sets (cleared with it), and every field `sync` may move -- the audit diff compares those too.
MIRRORS = {"education": ("qualification", "college", "passing_year"), "employment": ("experience_months", "current_company")}
DERIVED = (*MIRRORS["education"], *MIRRORS["employment"], "location", "preferred_role", "preferred_roles")
PLACE = ("city", "state", "country")
DAYS_PER_MONTH = Decimal("365.25") / 12


def experience_months(periods: list[tuple[date, date | None]], today: date) -> int | None:
    """P4 / AC2: the union of the periods (an open end is today), in whole months, half up; None without periods. Overlapping or touching
    periods join, so an overlap counts once."""
    if not periods:
        return None
    days, start, end = 0, None, None
    for begin, finish in sorted((b, f or today) for b, f in periods):
        if end is not None and begin.toordinal() <= end.toordinal() + 1:
            end = max(end, finish)
            continue
        if end is not None:
            days += (end - start).days + 1
        start, end = begin, finish
    days += (end - start).days + 1
    return min(600, int((Decimal(days) / DAYS_PER_MONTH).quantize(Decimal(1), rounding=ROUND_HALF_UP)))


async def rows(db: AsyncSession, candidate_id: UUID) -> dict[str, list[dict]]:
    """Every row kind in the recruiter's order, as plain dicts (one query per kind: the detail's fixed query count)."""
    out = {}
    for kind, model in ROWS.items():
        found = await db.scalars(select(model).where(model.candidate_id == candidate_id).order_by(model.position))
        out[kind] = [{field: getattr(row, field) for field in FIELDS[kind]} for row in found.all()]
    return out


async def replace(db: AsyncSession, candidate_id: UUID, kind: str, values: list[dict]) -> None:
    """P1: the sent list becomes the whole set, in its order."""
    model = ROWS[kind]
    await db.execute(delete(model).where(model.candidate_id == candidate_id))
    db.add_all(model(candidate_id=candidate_id, position=position, **row) for position, row in enumerate(values, start=1))


def _cleared(kind: str, stored_before: dict, stored: dict, sent: set) -> bool:
    """A row kind the request emptied: its mirrors clear too, unless the request sets them itself."""
    return kind in sent and stored_before[kind] and not stored[kind]


def sync(candidate: Candidate, stored: dict, sent: set, stored_before: dict | None = None) -> None:
    """P4/P5: the mirrors follow their rows. With no rows, a legacy key keeps the value the request (or an old client) set."""
    stored_before = stored_before or stored
    if first := next(iter(stored["education"]), None):
        candidate.qualification, candidate.college, candidate.passing_year = first["degree"], first["institution"], first["year"]
    elif _cleared("education", stored_before, stored, sent):
        for field in MIRRORS["education"]:
            if field not in sent:
                setattr(candidate, field, None)
    if jobs := stored["employment"]:
        candidate.experience_months = experience_months([(j["start_date"], j["end_date"]) for j in jobs], datetime.now(UTC).date())
        candidate.current_company = next((j["employer"] for j in jobs if j["end_date"] is None), None)
    elif _cleared("employment", stored_before, stored, sent):
        for field in MIRRORS["employment"]:
            if field not in sent:
                setattr(candidate, field, None)
    if any(getattr(candidate, part) for part in PLACE):
        candidate.location = ", ".join(getattr(candidate, part) for part in PLACE if getattr(candidate, part))
    if "preferred_roles" in sent:
        candidate.preferred_role = next(iter(candidate.preferred_roles or []), None)
    elif "preferred_role" in sent:  # an old client's single role replaces the first of the list
        role = candidate.preferred_role
        rest = [r for r in (candidate.preferred_roles or [])[1:] if r.lower() != (role or "").lower()]
        candidate.preferred_roles = [role, *rest] if role else rest
        candidate.preferred_role = next(iter(candidate.preferred_roles), None)


def _text(value) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


def audited(stored: dict, kinds) -> dict:
    """hrc-004: each row kind as text, one line per row ("B.Tech · Computer Science · JNTU · 2018"); None when empty."""
    return {kind: "\n".join(" · ".join(_text(v) for v in row.values() if v not in (None, "")) for row in stored[kind]) or None for kind in kinds}


# --- P10: Appendix B ---------------------------------------------------------------------------------------------------------------
COMPLETENESS = (
    ("contact_verified", "Contact verified", 10),
    ("education", "Education added", 15),
    ("skills", "At least 3 skills", 15),
    ("experience", "Experience or fresher recorded", 15),
    ("preferences", "Preferred role and location", 15),
    ("resume", "Resume uploaded", 20),
    ("compensation", "Expected salary provided", 10),
)


async def skill_count(db: AsyncSession, candidate_id: UUID) -> int:
    return await db.scalar(select(func.count()).select_from(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id)) or 0


def completeness(candidate: Candidate, stored: dict, skills: int, resumes: int) -> dict:
    met = {
        "contact_verified": candidate.email_verified_at is not None,
        "education": bool(stored["education"]),
        "skills": skills >= 3,
        "experience": candidate.experience_months is not None,
        "preferences": bool(candidate.preferred_roles) and bool(candidate.preferred_locations),
        "resume": resumes > 0,
        "compensation": candidate.expected_salary is not None,  # whether it is provided -- never the amount
    }
    items = [{"key": key, "label": label, "weight": weight, "met": met[key]} for key, label, weight in COMPLETENESS]
    return {"percent": sum(i["weight"] for i in items if i["met"]), "items": items}
