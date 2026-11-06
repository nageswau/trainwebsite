"""rec-016 (DEC-SCOPE-157) + hrc-018 (DEC-SCOPE-392 E1-E12, spec docs/superpowers/specs/2026-11-04-hrc-018-matching-engine-design.md):
requirement <-> candidate matching, the weighted score and its plain-language explanation.

`evaluate` is the pure rule, used both ways (job -> candidates for recruiters, candidate -> jobs for hrc-027): a job's spec and one
candidate's facts in, `None` (a hard filter failed) or the score, breakdown and explanation out. 100 points are shared by the factors
that apply to the job, in proportion to the admin weights, then the skills share by `job_skills.weight` -- whole numbers by largest
remainder, so a full match is exactly 100 and a breakdown always adds up to its score. SQL only narrows the pool to who holds the
required skills (else one preferred); Python decides everything else, so there is one copy of each rule."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CANDIDATE_SKILL_LEVELS,
    MATCH_DEFAULT_WEIGHTS,
    MATCH_FACTORS,
    Candidate,
    CandidateEducation,
    CandidateSkill,
    Job,
    JobApplication,
    JobSkill,
    MatchSetting,
    RecFxRate,
    SkillRelated,
    User,
)
from app.services import applications
from app.services.candidate_search import _has
from app.services.candidates import pool_filter
from app.services.compensation import INR, annual_inr

logger = logging.getLogger("app.matching")

NO_SKILLS = "no_skills"
PAGE_SIZE = 20
DEFAULT_WEIGHTS = dict(zip(MATCH_FACTORS, MATCH_DEFAULT_WEIGHTS, strict=True))
LABELS = {"skills": "Skills", "experience": "Experience", "qualification": "Qualification", "location": "Location", "role": "Role",
          "salary": "Salary & availability"}  # fmt: skip
HARD_FILTERS = ("experience", "qualification", "location", "salary")
HARD_FILTER_NEEDS = {"experience": "a minimum experience", "qualification": "a qualification", "location": "an on-site location",
                     "salary": "a maximum salary"}  # fmt: skip
DISCLAIMER = ("A match score is a guide based on the details recorded on the profile and the requirement. It is not a guarantee of "
              "suitability, an interview or an offer.")  # fmt: skip
RESTRICTED = "Salary details are restricted"


# --- the pure rules ------------------------------------------------------------------------------------------------------------------
def allocate(weights: list[int], total: int = 100) -> list[int]:
    """Whole-number shares of `total` in proportion to `weights`, the leftover by largest remainder (a tie goes to the earlier one).
    All zero when the weights sum to 0 (a skill outside the Skills Master has weight 0 and earns nothing)."""
    whole = sum(weights)
    if not whole:
        return [0] * len(weights)
    points = [total * w // whole for w in weights]
    for i in sorted(range(len(weights)), key=lambda i: (-(total * weights[i] % whole), i))[: total - sum(points)]:
        points[i] += 1
    return points


def factor_points(weights: dict[str, int], applies: set[str]) -> dict[str, int]:
    """E4: the 100 points over the factors that apply, in MATCH_FACTORS order."""
    keys = [f for f in MATCH_FACTORS if f in applies]
    return dict(zip(keys, allocate([weights[k] for k in keys]), strict=True))


def years(months: int) -> str:
    if months < 12:
        return f"{months} mo" if months == 1 else f"{months} mos"
    value = round(months / 12, 1)
    text = f"{value:g}"
    return f"{text} yr" if text == "1" else f"{text} yrs"


def rupees(amount: Decimal) -> str:
    if amount < 100000:
        return f"₹{int(amount):,}"
    return f"₹{float(amount / 100000):.1f}".rstrip("0").rstrip(".") + "L"


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


@dataclass
class Spec:
    """One job's matching inputs: the scored skills and the factor values, with the points already allocated."""

    job: Job
    criteria: dict
    skills: list[dict]  # resolved Skills-Master skills: {id, name, kind, points, accepted (skill ids), min_level}
    points: dict[str, int]
    experience: tuple[int | None, int | None] | None
    qualification: str | None
    location: str | None
    budget: Decimal | None
    joining: date | None
    hard: set[str] = field(default_factory=set)


def _months(facts: dict) -> int | None:
    """E5: relevant experience when recorded, else total."""
    return facts["relevant_months"] if facts["relevant_months"] is not None else facts["experience_months"]


def _experience_text(facts: dict, low, high) -> tuple[bool, str]:
    if low is not None and high is not None:  # "2–5 yrs", "6 mos–2 yrs"
        need = f"{years(low).split()[0]}–{years(high)}" if years(low).split()[1:] == years(high).split()[1:] else f"{years(low)}–{years(high)}"
    elif low is not None:  # "2+ yrs"
        number, unit = years(low).split()
        need = f"{number}+ {unit}"
    else:
        need = f"up to {years(high)}"
    months = _months(facts)
    if months is None:
        return False, f"Experience not recorded (needs {need})"
    ok = (low is None or months >= low) and (high is None or months <= high)
    return ok, f"{years(months)} {'relevant' if facts['relevant_months'] is not None else 'experience'} (needs {need})"


def _qualification(facts: dict, wanted: str) -> str | None:
    """E5: the first of the candidate's degrees found in the job's qualification text."""
    return next((d for d in facts["degrees"] if _norm(d) and _norm(d) in wanted.lower()), None)


def _located(facts: dict, place: str) -> bool:
    return _norm(place) in {_norm(facts["location"]), *(_norm(p) for p in facts["preferred_locations"])}


def _role(facts: dict, title: str) -> str | None:
    t = _norm(title)
    return next((r.strip() for r in facts["roles"] if _norm(r) and (_norm(r) in t or t in _norm(r))), None)


def _salary(spec: Spec, facts: dict, today: date, amounts: bool) -> tuple[bool, str, bool | None]:
    """(matched, text, budget fit) for the salary & availability factor; budget fit is None when there is no budget."""
    parts, ok, fits = [], True, None
    if spec.budget is not None:
        expected = facts["expected_annual_inr"]
        fits = expected is not None and expected <= spec.budget
        ok &= fits
        if not amounts:
            parts.append(RESTRICTED)
        elif expected is None:
            parts.append("Expected salary not recorded")
        else:
            parts.append(f"Expected {rupees(expected)} {'within' if fits else 'above'} budget (up to {rupees(spec.budget)})")
    if spec.joining is not None:
        free = facts["available_from"] or (today + timedelta(days=facts["notice_days"]) if facts["notice_days"] is not None else None)
        on_time = free is not None and free <= spec.joining
        ok &= on_time
        when = spec.joining.strftime("%d %b %Y").lstrip("0")
        parts.append("Availability not recorded" if free is None else f"Available by {when}" if on_time else f"Not available by {when}")
    return ok, " · ".join(parts), fits


def skill_hits(spec: Spec, facts: dict) -> dict[UUID, bool]:
    """Each scored job skill: does the candidate hold it (or a related skill) at its hrc-017 minimum level?"""
    held = facts["skills"]

    def has(s: dict) -> bool:
        levels = CANDIDATE_SKILL_LEVELS[CANDIDATE_SKILL_LEVELS.index(s["min_level"]):] if s["min_level"] else CANDIDATE_SKILL_LEVELS
        return any(held.get(i) in levels for i in s["accepted"])

    return {s["id"]: has(s) for s in spec.skills}


def hard_filter_gaps(spec: Spec, facts: dict) -> list[str]:
    """E6: the job's switched-on hard filters the candidate does not meet, in HARD_FILTERS order; an unknown value fails. hrc-027 gates
    applying on these (J7); required skills only rank."""
    months = _months(facts)
    failed = {
        "experience": months is None or months < spec.experience[0] if spec.experience else False,
        "qualification": not _qualification(facts, spec.qualification) if spec.qualification else False,
        "location": not _located(facts, spec.location) if spec.location else False,
        "salary": not (facts["expected_annual_inr"] is not None and facts["expected_annual_inr"] <= spec.budget) if spec.budget is not None else False,
    }
    return [k for k in HARD_FILTERS if k in spec.hard and failed[k]]


def evaluate(spec: Spec, facts: dict, *, today: date, amounts: bool = True, audience: str = "staff") -> dict | None:
    """The pure rule (E4-E7, E9). `amounts=False` keeps salary figures out (E8); the candidate audience gets no salary line (E9)."""
    hits = skill_hits(spec, facts)
    required = [s for s in spec.skills if s["kind"] == "required"]
    preferred = [s for s in spec.skills if s["kind"] == "preferred"]
    if required and not all(hits[s["id"]] for s in required):
        return None
    if not required and not any(hits[s["id"]] for s in preferred):
        return None  # rec-016 M4: with no required skill, at least one preferred one
    breakdown = [{"key": f"skill:{s['id']}", "label": s["name"], "kind": s["kind"], "points": s["points"] if hits[s["id"]] else 0,
                  "max": s["points"], "matched": hits[s["id"]]} for s in spec.skills]  # fmt: skip
    names = {k: [s["name"] for s in group if hits[s["id"]] is v] for k, group, v in (
        ("required_matched", required, True), ("required_missing", required, False), ("preferred_matched", preferred, True),
        ("preferred_missing", preferred, False))}  # fmt: skip
    text = []
    if required:
        text.append(f"Matches {len(names['required_matched'])} of {len(required)} required skills")
    if preferred:
        tail = f" (missing {', '.join(names['preferred_missing'])})" if names["preferred_missing"] else ""
        text.append(f"{len(names['preferred_matched'])} of {len(preferred)} preferred{tail}" if required else
                    f"Matches {len(names['preferred_matched'])} of {len(preferred)} preferred skills{tail}")  # fmt: skip
    skill_points = sum(b["points"] for b in breakdown)
    explanation = [{"key": "skills", "label": LABELS["skills"], "text": " · ".join(text), "points": skill_points,
                    "max": spec.points.get("skills", 0), "matched": skill_points == spec.points.get("skills", 0)}]  # fmt: skip

    checks: dict[str, tuple[bool, str]] = {}
    if spec.experience:
        checks["experience"] = _experience_text(facts, *spec.experience)
    if spec.qualification:
        degree = _qualification(facts, spec.qualification)
        any_degree = any(_norm(d) for d in facts["degrees"])
        checks["qualification"] = (bool(degree), f"{degree.strip()} matches the qualification" if degree else
                                   "Qualification does not match" if any_degree else "Qualification not recorded")  # fmt: skip
    if spec.location:
        at = _located(facts, spec.location)
        checks["location"] = (at, f"{'In or prefers' if at else 'Not in or preferring'} {spec.location}")
    role = _role(facts, spec.job.title)
    known_role = any(_norm(r) for r in facts["roles"])
    checks["role"] = (bool(role), f"Wants a {role} role" if role else "Preferred role differs from the job title" if known_role else
                      "Preferred role not recorded")  # fmt: skip
    if "salary" in spec.points:
        ok, words, _fit = _salary(spec, facts, today, amounts)
        checks["salary"] = (ok, words)

    if hard_filter_gaps(spec, facts):  # E6: the optional hard filters; an unknown value fails
        return None

    for key in MATCH_FACTORS[1:]:
        if key not in checks or key not in spec.points:
            continue
        ok, words = checks[key]
        got = spec.points[key] if ok else 0
        breakdown.append({"key": key, "label": LABELS[key], "kind": key, "points": got, "max": spec.points[key], "matched": ok})
        if key == "salary" and audience == "candidate":
            continue
        explanation.append({"key": key, "label": LABELS[key], "text": words, "points": got, "max": spec.points[key], "matched": ok})
    result = {"score": sum(b["points"] for b in breakdown), "breakdown": breakdown, "explanation": explanation, "skills": names}
    if audience == "candidate":
        del result["breakdown"]  # E9: its salary item would still say whether the expected salary fits the unpublished budget
    return result


# --- reading a job and candidates ---------------------------------------------------------------------------------------------------
async def weights(db: AsyncSession) -> dict[str, int]:
    row = await db.get(MatchSetting, 1)
    return {f: getattr(row, f"{f}_weight") for f in MATCH_FACTORS} if row else dict(DEFAULT_WEIGHTS)


async def _related(db: AsyncSession, skill_ids: set[UUID]) -> dict[UUID, set[UUID]]:
    """Each skill with its related skills, both directions (rec-016 M3), in one query."""
    out = {i: {i} for i in skill_ids}
    pairs = await db.execute(select(SkillRelated.skill_a_id, SkillRelated.skill_b_id).where(or_(SkillRelated.skill_a_id.in_(skill_ids), SkillRelated.skill_b_id.in_(skill_ids))))
    for a, b in pairs.all():
        if a in out:
            out[a].add(b)
        if b in out:
            out[b].add(a)
    return out


def _place(job: Job) -> str:
    """M1/Q-14: the location matching scores -- none for a remote job."""
    return (job.location or "").strip() if job.work_mode != "remote" else ""


async def eligibility(db: AsyncSession, job: Job) -> tuple:
    """hrc-009 (DEC-SCOPE-390 R1): what decides who fits -- the required skills, the experience range, the qualification and the matched
    location, case-insensitive; a required skill counts with its hrc-017 minimum level. hrc-018 (E6): plus which optional hard filters are
    on, and the maximum salary while the salary filter is. Two equal snapshots = no eligibility change (preferred skills and weights only
    rank)."""
    required = await db.execute(select(JobSkill.name, JobSkill.min_level).where(JobSkill.job_id == job.id, JobSkill.kind == "required"))
    return (
        frozenset((name.strip().lower(), level) for name, level in required.all()),
        job.experience_min_months,
        job.experience_max_months,
        (job.qualification or "").strip().lower(),
        _place(job).lower(),
        frozenset(k for k in HARD_FILTERS if getattr(job, f"match_hard_{k}")),
        (job.salary_max, job.salary_currency, job.salary_period) if job.match_hard_salary else None,
    )


async def budget_of(db: AsyncSession, job: Job) -> Decimal | None:
    """The job's maximum salary in annual INR; None without one or without a rate for its currency (the factor then does not apply)."""
    if job.salary_max is None:
        return None
    currency = job.salary_currency or INR
    rate = Decimal(1) if currency == INR else await db.scalar(select(RecFxRate.inr_per_unit).where(RecFxRate.currency == currency))
    return annual_inr(job.salary_max, currency, job.salary_period or "year", rate) if rate is not None else None


def available_filters(job: Job, budget: Decimal | None) -> dict[str, bool]:
    """E6: a hard filter can be on only when the job has the value it compares with."""
    return {"experience": job.experience_min_months is not None, "qualification": bool(_norm(job.qualification)),
            "location": bool(_place(job)), "salary": budget is not None}  # fmt: skip


async def spec(db: AsyncSession, job: Job) -> Spec:
    """The criteria (what the page shows) and the scored items. No Skills-Master skill = no scored skills (`no_skills`)."""
    rows = (await db.scalars(select(JobSkill).where(JobSkill.job_id == job.id).order_by(JobSkill.kind.desc(), JobSkill.position))).all()
    budget = await budget_of(db, job)
    has_experience = job.experience_min_months is not None or job.experience_max_months is not None
    place = _place(job)
    available = available_filters(job, budget)
    applies = {"role"} | {k for k, on in (("skills", any(r.skill_id for r in rows)), ("experience", has_experience),
                                          ("qualification", available["qualification"]), ("location", available["location"]),
                                          ("salary", budget is not None or job.expected_joining_date is not None)) if on}  # fmt: skip
    admin = await weights(db)
    points = factor_points(admin, applies)
    skill_points = allocate([r.weight if r.skill_id else 0 for r in rows], points.get("skills", 0))
    related = await _related(db, {r.skill_id for r in rows if r.skill_id}) if any(r.skill_id for r in rows) else {}
    skills = [{"id": r.id, "name": r.name, "kind": r.kind, "points": p, "accepted": related[r.skill_id], "min_level": r.min_level}
              for r, p in zip(rows, skill_points, strict=True) if r.skill_id]  # fmt: skip
    applied = {k for k in HARD_FILTERS if getattr(job, f"match_hard_{k}") and available[k]}
    criteria = {
        "skills": [{"id": r.id, "name": r.name, "kind": r.kind, "weight": r.weight, "points": p, "in_master": r.skill_id is not None,
                    "min_level": r.min_level} for r, p in zip(rows, skill_points, strict=True)],  # fmt: skip
        "experience": {"min_months": job.experience_min_months, "max_months": job.experience_max_months, "points": points["experience"]} if "experience" in points else None,
        "location": {"value": place, "points": points["location"]} if "location" in points else None,
        "factors": [{"key": f, "label": LABELS[f], "weight": w, "applies": f in points, "points": points.get(f, 0)} for f, w in admin.items()],
        "hard_filters": {k: {"on": bool(getattr(job, f"match_hard_{k}")), "available": available[k]} for k in HARD_FILTERS},
    }
    return Spec(job=job, criteria=criteria, skills=skills, points=points,
                experience=(job.experience_min_months, job.experience_max_months) if has_experience else None,
                qualification=job.qualification if available["qualification"] else None, location=place if available["location"] else None,
                budget=budget, joining=job.expected_joining_date, hard=applied)  # fmt: skip


async def facts(db: AsyncSession, candidates: list[Candidate] | object, sp: Spec) -> dict[UUID, dict]:
    """Each candidate's matching facts: three reads whatever the count. `candidates` is a list or an id subquery."""
    ids = [c.id for c in candidates] if isinstance(candidates, list) else candidates
    rows = candidates if isinstance(candidates, list) else (await db.scalars(select(Candidate).where(Candidate.id.in_(ids)))).all()
    out = {c.id: {"skills": {}, "degrees": [c.qualification] if c.qualification else [], "experience_months": c.experience_months,
                  "relevant_months": c.relevant_experience_months, "location": c.location, "preferred_locations": c.preferred_locations or [],
                  "roles": [r for r in (c.preferred_role, *(c.preferred_roles or [])) if r], "expected_annual_inr": c.expected_annual_inr,
                  "available_from": c.available_from, "notice_days": c.notice_days, "candidate": c} for c in rows}  # fmt: skip
    wanted = set().union(*(item["accepted"] for item in sp.skills))
    if wanted:
        held = await db.execute(select(CandidateSkill.candidate_id, CandidateSkill.skill_id, CandidateSkill.level)
                                .where(CandidateSkill.candidate_id.in_(ids), CandidateSkill.skill_id.in_(sorted(wanted))))  # fmt: skip
        for candidate_id, skill_id, level in held.all():
            out[candidate_id]["skills"][skill_id] = level
    if sp.qualification:
        degrees = await db.execute(select(CandidateEducation.candidate_id, CandidateEducation.degree)
                                   .where(CandidateEducation.candidate_id.in_(ids), CandidateEducation.degree.is_not(None)))  # fmt: skip
        for candidate_id, degree in degrees.all():
            out[candidate_id]["degrees"].append(degree)
    return out


def _today() -> date:
    return datetime.now(UTC).date()


async def matches(db: AsyncSession, job: Job, *, limit: int, offset: int, amounts: bool = True) -> dict:
    """Job -> candidates (rec-016 M8): the pool, not archived, narrowed in SQL by the required skills; ranked by score, newest first."""
    s = await spec(db, job)
    base = {"criteria": s.criteria, "limit": limit, "offset": offset, "disclaimer": DISCLAIMER}
    if not s.skills:
        return {**base, "reason": NO_SKILLS, "items": [], "total": 0}
    required = [_has(x["accepted"], False, x["min_level"]) for x in s.skills if x["kind"] == "required"]
    narrowed = select(Candidate.id).where(*pool_filter(), Candidate.archived_at.is_(None),
                                          *(required or [or_(*(_has(x["accepted"], False, x["min_level"]) for x in s.skills))]))  # fmt: skip
    found = await facts(db, narrowed, s)
    today = _today()
    scored = [(f["candidate"], r) for f in found.values() if (r := evaluate(s, f, today=today, amounts=amounts))]
    scored.sort(key=lambda cr: (cr[1]["score"], cr[0].created_at, cr[0].id), reverse=True)
    page = scored[offset: offset + limit]
    on_job = {}
    if page:
        rows = await db.scalars(select(JobApplication).where(JobApplication.job_id == job.id, JobApplication.candidate_id.in_([c.id for c, _ in page])))
        on_job = {a.candidate_id: a for a in rows.all()}
    items = []
    for candidate, result in page:
        application = on_job.get(candidate.id)
        items.append({
            "id": candidate.id, "candidate_code": candidate.candidate_code, "name": candidate.name, "preferred_role": candidate.preferred_role,
            "current_company": candidate.current_company, "experience_months": candidate.experience_months, "location": candidate.location,
            "notice_days": candidate.notice_days, "status": candidate.status, **result,
            "application": {"id": application.id, "status": application.status, "status_label": applications.label(application.status)} if application else None,
        })
    logger.info("requirement_matches_scored", extra={"extra_fields": {"job_id": str(job.id), "narrowed": len(found), "scored": len(scored)}})
    return {**base, "reason": None, "items": items, "total": len(scored)}


async def portal_matches(db: AsyncSession, job: Job, *, min_score: int, limit: int) -> list[Candidate]:
    """hrc-032 (N7): the opted-in portal candidates who fit this job and have not applied -- best first, failed hard filters out. Narrowed in SQL
    as `matches` is, and scored for the candidate audience."""
    s = await spec(db, job)
    if not s.skills:
        return []
    required = [_has(x["accepted"], False, x["min_level"]) for x in s.skills if x["kind"] == "required"]
    applied = select(JobApplication.candidate_id).where(JobApplication.job_id == job.id)
    narrowed = select(Candidate.id).where(*pool_filter(), Candidate.archived_at.is_(None), Candidate.user_id.is_not(None), Candidate.merged_into_id.is_(None), Candidate.id.not_in(applied),
                                          *(required or [or_(*(_has(x["accepted"], False, x["min_level"]) for x in s.skills))]))  # fmt: skip
    found = await facts(db, narrowed, s)
    today = _today()
    scored = [(r["score"], f["candidate"]) for f in found.values() if (r := evaluate(s, f, today=today, audience="candidate")) and r["score"] >= min_score]
    scored.sort(key=lambda sc: (sc[0], sc[1].id), reverse=True)
    return [candidate for _, candidate in scored[:limit]]


async def jobs_for_candidate(db: AsyncSession, candidate: Candidate, jobs: list[Job], *, audience: str = "candidate") -> list[dict]:
    """Candidate -> jobs (E12, for hrc-027): the same `evaluate` over the jobs the caller chose; failed hard filters drop out. The
    candidate audience never sees a salary line (E9)."""
    out, today = [], _today()
    for job in jobs:
        s = await spec(db, job)
        if not s.skills:
            continue
        result = evaluate(s, (await facts(db, [candidate], s))[candidate.id], today=today, audience=audience)
        if result:
            out.append({"job_id": job.id, **result})
    return sorted(out, key=lambda m: m["score"], reverse=True)


def log(user: User, job: Job, total: int) -> None:
    """Ids and counts only -- never a candidate."""
    logger.info("requirement_matches", extra={"extra_fields": {"actor_id": str(user.id), "job_id": str(job.id), "total": total}})
