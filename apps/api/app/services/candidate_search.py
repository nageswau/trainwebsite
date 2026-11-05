"""rec-013 (DEC-SCOPE-151, spec §3): Find Candidates -- skill AND / OR search over the whole pool (R11), expanded through aliases and
related skills (FS2), the S2-§18 filters (FS5), the F1-F3 facets (FS7) and the result cards (FS8).

Read only. Terms become skill ids before any candidate is read, and only ids and escaped patterns reach SQL as bound parameters (no
expression is ever parsed into SQL). Six queries whatever the pool or page size: terms, related, counts, locations, page, page skills.

rec-014 (DEC-SCOPE-154, FT1-FT6): an optional `text` matches the current resume's generated `search_vector` through
websearch_to_tsquery('english', :text) -- the text is a bound parameter, never SQL -- ranks by relevance and adds `ts_headline`
snippets. It adds two queries: the stop-word check and the page's snippets.

hrc-019 (DEC-SCOPE-399, S1-S14): the §8 filter groups (skills, education, experience, location, preferences, recruitment data, documents,
applications, package with the "unknown" option), a sort whitelist and a per-card "why matched" -- each filter one more WHERE condition
and each sort a fixed ORDER BY, so the query count does not change."""

import logging
import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Date, Numeric, and_, case, cast, exists, false, func, literal, literal_column, or_, select, union_all
from sqlalchemy.dialects.postgresql import JSONB, array
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.lookups import _pattern as like_pattern
from app.models import (
    CANDIDATE_SKILL_LEVELS,
    Candidate,
    CandidateDocument,
    CandidateEducation,
    CandidateEmployment,
    CandidateResume,
    CandidateSkill,
    CareerApplication,
    Interview,
    JobApplication,
    RecCandidateSource,
    RecruiterCall,
    RecruiterMessage,
    Skill,
    SkillAlias,
    SkillCategoryTag,
    SkillRelated,
    User,
)
from app.schemas import CandidateSearch
from app.services import candidate_engagement
from app.services.candidates import pool_filter

logger = logging.getLogger("app.candidate_search")

SUGGESTIONS = 5
TOP_LOCATIONS = 5
OTHER, NONE = "__other__", None
EXPERIENCE_BANDS = (("y0_1", 0, 11), ("y1_3", 12, 35), ("y3_5", 36, 59), ("y5_plus", 60, None))  # F1, months, inclusive
AVAILABILITY_BANDS = (("immediate", 0, 0), ("d15", 1, 15), ("d30", 16, 30), ("d31_59", 31, 59), ("d60_plus", 60, None))  # F3, days

# rec-014: the vector's configuration (models.RESUME_SEARCH_VECTOR); ts_headline marks hits with private-use characters, removed from the
# resume first, and the page receives [{text, hit}] segments -- never HTML (FT6).
ENGLISH = literal_column("'english'::regconfig")
START, STOP = "\ue000", "\ue001"
HEADLINE = f'StartSel={START}, StopSel={STOP}, MaxFragments=2, MaxWords=20, MinWords=8, FragmentDelimiter=" … "'
SNIPPET_CHARS = 300
STOP_WORDS_NOTICE = "Your resume search only has common words like “the” or “and”, so it matches nothing. Add a more specific word."


def _tsquery(text: str):
    return func.websearch_to_tsquery(ENGLISH, text)


def _current(resume):
    """The resume row is its candidate's highest version (rec-009: the current resume)."""
    newer = aliased(CandidateResume)
    return resume.version == select(func.max(newer.version)).where(newer.candidate_id == resume.candidate_id).scalar_subquery()


def _between(column, low: int, high: int | None):
    return column >= low if high is None else column.between(low, high)


async def _unknown(db: AsyncSession, term: str) -> HTTPException:
    """FS3: the 422 for a term that is no active skill's name or alias, with up to five skills whose name or alias contains it."""
    pattern = like_pattern(term)
    rows = await db.scalars(
        select(Skill.name).outerjoin(SkillAlias, SkillAlias.skill_id == Skill.id)
        .where(Skill.active.is_(True), or_(Skill.name.ilike(pattern, escape="\\"), SkillAlias.alias.ilike(pattern, escape="\\")))
        .group_by(Skill.name).order_by(func.lower(Skill.name)).limit(SUGGESTIONS)
    )
    suggestions = list(rows)
    hint = f" Did you mean {', '.join(suggestions)}?" if suggestions else " Pick a skill from the Skills Master."
    message = f"No skill is called “{term}”.{hint}"
    return HTTPException(422, {"message": message, "code": "unknown_skill", "term": term, "suggestions": suggestions})


async def resolve_terms(db: AsyncSession, body: CandidateSearch, *, strict: bool = True) -> dict[str, dict]:
    """Every distinct term (case-insensitive) → {skill, ids, also}. One query resolves all terms (a name wins over an alias, the
    services/skills.resolve rule); one reads the related pairs of every resolved skill. Not `strict` (a saved rec-015 pool rule), a term
    that is no longer an active skill resolves to {skill: None, ids: ∅}, which `filters` turns into "matches nobody" (P5)."""
    texts = {t.lower(): t for t in [*body.all, *(t for group in body.any for t in group), *body.preferred]}
    keys = list(texts)
    if not keys:
        return {}
    by_name = select(func.lower(Skill.name).label("term"), Skill.id, Skill.name, literal(0).label("rank")).where(
        func.lower(Skill.name).in_(keys), Skill.active.is_(True))
    by_alias = select(func.lower(SkillAlias.alias).label("term"), Skill.id, Skill.name, literal(1).label("rank")).join(
        Skill, Skill.id == SkillAlias.skill_id).where(func.lower(SkillAlias.alias).in_(keys), Skill.active.is_(True))
    found: dict[str, tuple] = {}
    for term, skill_id, name, _ in (await db.execute(union_all(by_name, by_alias).order_by("rank"))).all():
        found.setdefault(term, (skill_id, name))
    missing = [key for key in keys if key not in found]
    if missing and strict:
        raise await _unknown(db, texts[missing[0]])
    skill_ids = {skill_id for skill_id, _ in found.values()}
    related: dict[UUID, dict[UUID, str]] = {i: {} for i in skill_ids}
    other = Skill.__table__.alias("other")
    pairs = await db.execute(
        select(SkillRelated.skill_a_id, SkillRelated.skill_b_id, other.c.id, other.c.name)
        .join(other, or_(and_(SkillRelated.skill_a_id.in_(skill_ids), other.c.id == SkillRelated.skill_b_id),
                         and_(SkillRelated.skill_b_id.in_(skill_ids), other.c.id == SkillRelated.skill_a_id)))
    )
    for a, b, other_id, other_name in pairs.all():
        related[a if other_id == b else b][other_id] = other_name  # the joined side is the other skill; the pair's other end is ours
    out = {}
    for key, (skill_id, name) in found.items():
        also = sorted(related[skill_id].items(), key=lambda kv: kv[1].lower())
        out[key] = {"term": texts[key], "skill": {"id": skill_id, "name": name}, "ids": {skill_id, *related[skill_id]}, "also": [n for _, n in also]}
    for key in missing:
        out[key] = {"term": texts[key], "skill": None, "ids": set(), "also": []}
    return out


def _has(ids: set[UUID], verified_only: bool, min_level: str | None = None, min_months: int | None = None):
    """hrc-017 (T8): with `min_level`, only a holding at that level or above counts; hrc-019 (S3): with `min_months`, only one with at
    least that many months on the skill."""
    conditions = [CandidateSkill.candidate_id == Candidate.id, CandidateSkill.skill_id.in_(sorted(ids))]
    if verified_only:
        conditions.append(CandidateSkill.status != "claimed")
    if min_level:
        conditions.append(CandidateSkill.level.in_(CANDIDATE_SKILL_LEVELS[CANDIDATE_SKILL_LEVELS.index(min_level):]))
    if min_months is not None:
        conditions.append(CandidateSkill.experience_months >= min_months)
    return exists().where(*conditions)


IST = "Asia/Kolkata"  # S8: registration dates are business (IST) days
CGPA = r"^[0-9]{1,2}(\.[0-9]{1,2})?$"  # S4: only a plain number is compared as a CGPA


def _like(column, text: str | None):
    pattern = like_pattern(text)
    return column.ilike(pattern, escape="\\") if pattern else None


def _listed(column, text: str):
    """S6/S7: an entry of a JSON list of short texts contains `text`."""
    entry = func.json_array_elements_text(column).table_valued("value").render_derived()
    return select(literal(1)).select_from(entry).where(_like(entry.c.value, text)).exists()


def _overlaps(column, values: list[str]):
    """S6/S7: a JSON list of enum values holds any of `values`."""
    return cast(column, JSONB).op("?|")(array(values))


def _row(model, conditions: list):
    """S4/S5: one profile row satisfies every condition (same-row semantics); None when no condition applies."""
    conditions = [c for c in conditions if c is not None]
    return exists().where(model.candidate_id == Candidate.id, *conditions) if conditions else None


def _education(body: CandidateSearch):
    E = CandidateEducation
    out = [_like(E.degree, body.degree), _like(E.specialisation, body.specialisation), _like(E.institution, body.institution)]
    if body.passing_year_min is not None:
        out.append(E.year >= body.passing_year_min)
    if body.passing_year_max is not None:
        out.append(E.year <= body.passing_year_max)
    if body.cgpa_min is not None or body.cgpa_max is not None:
        grade = func.trim(E.grade)
        number = case((grade.op("~")(CGPA), cast(grade, Numeric)), else_=None)
        out.append(number.between(body.cgpa_min if body.cgpa_min is not None else 0, body.cgpa_max if body.cgpa_max is not None else 10))
    return _row(E, out)


def _employment(body: CandidateSearch):
    J = CandidateEmployment
    return _row(J, [_like(J.designation, body.designation), _like(J.industry, body.industry),
                    J.employment_type.in_(body.employment_types) if body.employment_types else None])  # fmt: skip


def _package(body: CandidateSearch) -> list:
    """S9: each applied range on the normalised annual INR; `package_unknown` keeps a candidate whose figure is not provided."""
    out = []
    for column, low, high in ((Candidate.expected_annual_inr, body.salary_min, body.salary_max), (Candidate.current_annual_inr, body.current_min, body.current_max),
                              (Candidate.minimum_annual_inr, body.minimum_min, body.minimum_max)):  # fmt: skip
        bounds = [c for c in (column >= low if low is not None else None, column <= high if high is not None else None) if c is not None]
        if bounds:
            out.append(or_(and_(*bounds), column.is_(None)) if body.package_unknown else and_(*bounds))
    return out


def _more(body: CandidateSearch, terms: dict[str, dict], user_id: UUID | None) -> list:
    """hrc-019 (S3-S8): the §8 filter groups. A rec-015 pool rule (built with model_construct) has every default: nothing is added."""
    out = [_education(body), _employment(body)]
    if body.category_ids:
        tagged = exists().where(SkillCategoryTag.skill_id == Skill.id, SkillCategoryTag.category_id.in_(body.category_ids))
        out.append(select(CandidateSkill.id).join(Skill, Skill.id == CandidateSkill.skill_id)
                   .where(CandidateSkill.candidate_id == Candidate.id, or_(Skill.category_id.in_(body.category_ids), tagged)).exists())  # fmt: skip
    if body.preferred and not (body.all or body.any or body.text or body.category_ids):  # S3: preferred alone lists who holds one
        out.append(_has(set().union(*(terms[t.lower()]["ids"] for t in body.preferred)), body.verified_only))
    if body.fresher is not None:
        out.append(Candidate.experience_months == 0 if body.fresher else Candidate.experience_months > 0)
    if body.relevant_min_months is not None:
        out.append(Candidate.relevant_experience_months >= body.relevant_min_months)
    if body.relevant_max_months is not None:
        out.append(Candidate.relevant_experience_months <= body.relevant_max_months)
    out += [_like(Candidate.country, body.country), _like(Candidate.state, body.state), _like(Candidate.city, body.city)]
    if body.preferred_location:
        out.append(_listed(Candidate.preferred_locations, body.preferred_location))
    if body.willing_to_relocate is not None:
        out.append(Candidate.willing_to_relocate.is_(body.willing_to_relocate))
    if body.work_modes:
        out.append(_overlaps(Candidate.work_modes, body.work_modes))
    if body.preferred_role:
        out.append(or_(_like(Candidate.preferred_role, body.preferred_role), _listed(Candidate.preferred_roles, body.preferred_role)))
    if body.preferred_employment_types:
        out.append(_overlaps(Candidate.employment_types, body.preferred_employment_types))
    if body.owner == "me":
        out.append(Candidate.owner_user_id == user_id)
    elif body.owner == "unassigned":
        out.append(Candidate.owner_user_id.is_(None))
    registered = cast(func.timezone(IST, Candidate.created_at), Date)
    if body.registered_from is not None:
        out.append(registered >= body.registered_from)
    if body.registered_to is not None:
        out.append(registered <= body.registered_to)
    if body.has_resume is not None:
        resume = exists().where(CandidateResume.candidate_id == Candidate.id)
        out.append(resume if body.has_resume else ~resume)
    if body.document_types:
        out.append(exists().where(CandidateDocument.candidate_id == Candidate.id, CandidateDocument.document_type.in_(body.document_types)))
    if body.application_statuses:
        out.append(exists().where(JobApplication.candidate_id == Candidate.id, JobApplication.status.in_(body.application_statuses)))
    if body.interviewed is not None:
        held = select(Interview.id).join(JobApplication, JobApplication.id == Interview.application_id).where(JobApplication.candidate_id == Candidate.id).exists()
        out.append(held if body.interviewed else ~held)
    return [c for c in [*out, *_package(body)] if c is not None]


def filters(body: CandidateSearch, terms: dict[str, dict], user_id: UUID | None = None) -> list:
    """The pool (AC5), not archived, one EXISTS per AND term, one per OR group (hrc-019: at the minimum level and months), then the FS5
    filters and the hrc-019 groups -- all ANDed. `user_id` is the caller, for `owner=me` (S8)."""
    out = [*pool_filter(), Candidate.archived_at.is_(None)]
    level, months = body.min_level, body.skill_min_months
    out += [_has(terms[t.lower()]["ids"], body.verified_only, level, months) for t in dict.fromkeys(t.lower() for t in body.all)]
    out += [_has(set().union(*(terms[t.lower()]["ids"] for t in group)), body.verified_only, level, months) for group in body.any]
    if body.experience_min_months is not None:
        out.append(Candidate.experience_months >= body.experience_min_months)
    if body.experience_max_months is not None:
        out.append(Candidate.experience_months <= body.experience_max_months)
    for column, text in ((Candidate.location, body.location), (Candidate.qualification, body.qualification)):
        if pattern := like_pattern(text):
            out.append(column.ilike(pattern, escape="\\"))
    if body.availability:
        out.append(or_(*(_between(Candidate.notice_days, low, high) for key, low, high in AVAILABILITY_BANDS if key in body.availability)))
    if body.source_id:
        out.append(Candidate.source_id == body.source_id)
    if body.status:
        out.append(Candidate.status == body.status)
    if body.engagement:  # hrc-021 (DEC-SCOPE-397 E7)
        out.append(candidate_engagement.expression() == body.engagement)
    if body.text:  # FT1: the GIN index finds matching resumes; only a candidate's current one counts
        resume = aliased(CandidateResume)
        out.append(Candidate.id.in_(select(resume.candidate_id).where(resume.search_vector.op("@@")(_tsquery(body.text)), _current(resume))))
    return out + _more(body, terms, user_id)  # the expected-salary range is hrc-011 C6's normalised figure (now in `_package`)


async def facets(db: AsyncSession, where: list) -> tuple[int, dict]:
    """FS7: the total, F1 and F3 in one row of FILTERed counts; F2's five most common locations (grouped case-insensitively) in one
    grouped query. Every facet's counts add up to the total (AC4)."""
    def bands(column, spec):
        counts = [func.count().filter(_between(column, low, high)).label(key) for key, low, high in spec]
        return [*counts, func.count().filter(column.is_(None)).label(f"none_{column.key}")]

    place = func.lower(func.trim(Candidate.location))
    unplaced = or_(place.is_(None), place == "")
    row = (await db.execute(
        select(
            func.count().label("total"), func.count().filter(unplaced).label("no_location"),
            *bands(Candidate.experience_months, EXPERIENCE_BANDS), *bands(Candidate.notice_days, AVAILABILITY_BANDS),
        ).where(*where)
    )).one()._mapping
    top = (await db.execute(
        select(func.min(func.trim(Candidate.location)), func.count()).where(*where, ~unplaced)
        .group_by(place).order_by(func.count().desc(), place).limit(TOP_LOCATIONS)
    )).all()
    location = [{"value": name, "count": count} for name, count in top]
    other = row["total"] - row["no_location"] - sum(count for _, count in top)
    location += [{"value": value, "count": count} for value, count in ((OTHER, other), (NONE, row["no_location"])) if count]
    return row["total"], {
        "experience": [*({"key": key, "count": row[key]} for key, _, _ in EXPERIENCE_BANDS), {"key": "none", "count": row["none_experience_months"]}],
        "availability": [*({"key": key, "count": row[key]} for key, _, _ in AVAILABILITY_BANDS), {"key": "none", "count": row["none_notice_days"]}],
        "location": location,
    }


def completeness():
    """S10: hrc-010's Appendix B completeness percent (services/candidate_profile.COMPLETENESS) as one SQL expression, for sorting."""
    def points(condition, weight: int):
        return case((condition, weight), else_=0)

    skills = select(func.count()).select_from(CandidateSkill).where(CandidateSkill.candidate_id == Candidate.id).scalar_subquery()
    preferences = and_(func.json_array_length(Candidate.preferred_roles) > 0, func.json_array_length(Candidate.preferred_locations) > 0)
    return (points(Candidate.email_verified_at.is_not(None), 10) + points(exists().where(CandidateEducation.candidate_id == Candidate.id), 15)
            + points(skills >= 3, 15) + points(Candidate.experience_months.is_not(None), 15) + points(preferences, 15)
            + points(exists().where(CandidateResume.candidate_id == Candidate.id), 20) + points(Candidate.expected_salary.is_not(None), 10))  # fmt: skip


def last_activity():
    """S10: the latest of the profile update, an application change, a website application, a call and a message (GREATEST skips NULLs)."""
    def latest(column, owner):
        return select(func.max(column)).where(owner == Candidate.id).scalar_subquery()

    return func.greatest(Candidate.updated_at, latest(JobApplication.updated_at, JobApplication.candidate_id),
                         latest(CareerApplication.created_at, CareerApplication.candidate_id), latest(RecruiterCall.occurred_at, RecruiterCall.candidate_id),
                         latest(RecruiterMessage.sent_at, RecruiterMessage.candidate_id))  # fmt: skip


def _distinct(values) -> list[str]:
    return list(dict.fromkeys(v.lower() for v in values))


def _sort(body: CandidateSearch | None, terms: dict[str, dict], text: str | None) -> list:
    """S10: a whitelist of fixed orders, each ending newest first (FS11); `relevance` is rec-013/014's order."""
    order = [Candidate.created_at.desc(), Candidate.id.desc()]
    key = body.sort if body is not None else "relevance"
    if key == "match":
        searched = _distinct([*body.all, *(t for g in body.any for t in g), *body.preferred])
        held = [case((_has(terms[t]["ids"], body.verified_only), 1), else_=0) for t in searched if terms[t]["ids"]]
        return [sum(held, literal(0)).desc(), *order]
    first = {"experience": Candidate.experience_months.desc().nulls_last(), "package": Candidate.expected_annual_inr.asc().nulls_last(),
             "activity": last_activity().desc(), "completeness": completeness().desc()}.get(key)  # fmt: skip
    if first is not None:
        return [first, *order]
    if key == "relevance" and text:
        resume = aliased(CandidateResume)
        rank = select(func.ts_rank_cd(resume.search_vector, _tsquery(text))).where(resume.candidate_id == Candidate.id, _current(resume))
        return [rank.scalar_subquery().desc(), *order]
    return order


def page_statement(body: CandidateSearch | None, where: list, terms: dict[str, dict], limit: int, offset: int, text: str | None = None):
    text = body.text if body is not None else text
    return (select(Candidate, RecCandidateSource, candidate_engagement.expression()).join(RecCandidateSource, RecCandidateSource.id == Candidate.source_id)
            .where(*where).order_by(*_sort(body, terms, text)).limit(limit).offset(offset))  # fmt: skip


def _match(body: CandidateSearch, terms: dict[str, dict], held: set[UUID]) -> dict:
    """S11: each searched term and whether the candidate holds it (or an alias / related skill) -- from the rows already read."""
    def line(key: str) -> dict:
        t = terms[key]
        return {"term": t["term"], "skill": t["skill"]["name"] if t["skill"] else None, "held": bool(t["ids"] & held)}

    return {"required": [line(k) for k in _distinct([*body.all, *(t for g in body.any for t in g)])], "preferred": [line(k) for k in _distinct(body.preferred)]}


async def page(db: AsyncSession, where: list, terms: dict[str, dict], limit: int, offset: int, text: str | None = None,
               body: CandidateSearch | None = None) -> list[dict]:  # fmt: skip
    """The page's cards, newest first (FS11) -- with text, the most relevant current resume first (FT5); hrc-019: in `body.sort`'s order,
    with `match` (S11) when a search `body` is given: one query for the candidates with their source, one for all their skills."""
    rows = (await db.execute(page_statement(body, where, terms, limit, offset, text))).all()
    matched = set().union(*(t["ids"] for t in terms.values()))
    skills: dict[UUID, list] = {c.id: [] for c, _, _ in rows}
    holds: dict[UUID, set] = {c.id: set() for c, _, _ in rows}
    if skills:
        held = await db.execute(
            select(CandidateSkill.candidate_id, CandidateSkill.skill_id, Skill.name, CandidateSkill.level, CandidateSkill.status)
            .join(Skill, Skill.id == CandidateSkill.skill_id).where(CandidateSkill.candidate_id.in_(list(skills)))
        )
        for candidate_id, skill_id, name, level, status in held.all():
            skills[candidate_id].append({"name": name, "level": level, "status": status, "matched": skill_id in matched})
            holds[candidate_id].add(skill_id)
        for items in skills.values():
            items.sort(key=lambda s: (not s["matched"], s["name"].lower()))
    cards = [
        {
            "id": c.id, "candidate_code": c.candidate_code, "name": c.name, "preferred_role": c.preferred_role, "current_company": c.current_company,
            "experience_months": c.experience_months, "location": c.location, "notice_days": c.notice_days, "expected_salary": c.expected_salary,
            "expected_salary_currency": c.expected_salary_currency, "expected_salary_period": c.expected_salary_period, "expected_annual_inr": c.expected_annual_inr,
            "source": {"id": s.id, "name": s.name, "active": s.active}, "source_detail": c.source_detail, "status": c.status, "skills": skills[c.id],
            "snippet": None, "engagement": candidate_engagement.out(e),
        }
        for c, s, e in rows
    ]
    if body is not None:
        for card in cards:
            card["match"] = _match(body, terms, holds[card["id"]])
    return cards


def _segments(headline: str) -> list[dict]:
    """ts_headline's output as alternating plain / hit segments (the markers alternate), whitespace collapsed, capped at SNIPPET_CHARS."""
    out, room = [], SNIPPET_CHARS
    for n, part in enumerate(re.split(f"[{START}{STOP}]", headline)):
        part = re.sub(r"\s+", " ", part)
        if not part:
            continue
        if len(part) > room:
            if room > 0:
                out.append({"text": part[:room], "hit": n % 2 == 1})
            out.append({"text": "…", "hit": False})
            break
        out.append({"text": part, "hit": n % 2 == 1})
        room -= len(part)
    return out


async def snippets(db: AsyncSession, candidate_ids: list[UUID], text: str) -> dict[UUID, list[dict]]:
    """FT6: one query -- the page's current resumes around their hits."""
    resume = aliased(CandidateResume)
    source = func.translate(resume.extracted_text, START + STOP, "")
    rows = await db.execute(
        select(resume.candidate_id, func.ts_headline(ENGLISH, source, _tsquery(text), HEADLINE))
        .where(resume.candidate_id.in_(candidate_ids), _current(resume))
    )
    return {candidate_id: _segments(headline) for candidate_id, headline in rows.all()}


async def conditions_for(db: AsyncSession, body: CandidateSearch, user_id: UUID | None) -> tuple[dict[str, dict], list, str | None]:
    """The resolved terms, the WHERE terms and the stop-words notice -- shared by the search and its export (hrc-020)."""
    terms = await resolve_terms(db, body)
    conditions = filters(body, terms, user_id)
    notice = None
    if body.text and not await db.scalar(select(func.numnode(_tsquery(body.text)))):
        conditions.append(false())  # FT3: only stop words -- the same shape, nothing in it
        notice = STOP_WORDS_NOTICE
    return terms, conditions, notice


async def search(db: AsyncSession, body: CandidateSearch, *, limit: int, offset: int, user_id: UUID | None = None) -> dict:
    terms, where, notice = await conditions_for(db, body, user_id)
    total, facet_counts = await facets(db, where)
    items = await page(db, where, terms, limit, offset, body=body)
    if body.text and items:
        found = await snippets(db, [item["id"] for item in items], body.text)
        for item in items:
            item["snippet"] = found.get(item["id"])
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "facets": facet_counts,
        "terms": [{"term": t["term"], "skill": t["skill"], "also": t["also"]} for t in terms.values()],
        "notice": notice,
    }


def log(user: User, body: CandidateSearch, total: int) -> None:
    """Counts only -- never the search or resume text (it can name a person's skills) or a candidate."""
    logger.info(
        "candidate_search",
        extra={"user_id": str(user.id), "terms": len(body.all) + sum(len(g) for g in body.any), "groups": len(body.any), "text": body.text is not None, "total": total},
    )


# hrc-020 (DEC-SCOPE-401 X10): the export's columns -- the card's facts, never contact details; the salary only with the grant.
EXPORT_COLUMNS = (
    ("candidate_code", "Candidate ID"), ("name", "Name"), ("preferred_role", "Preferred role"), ("current_company", "Current company"),
    ("experience", "Experience (years)"), ("location", "Location"), ("notice_days", "Notice (days)"), ("skills", "Skills"), ("source", "Source"),
    ("status", "Status"), ("engagement", "Engagement"),
)  # fmt: skip
SALARY_COLUMN = ("expected_annual_inr", "Expected salary (₹ a year)")


def _export_row(card: dict) -> dict:
    months, salary = card["experience_months"], card["expected_annual_inr"]
    return {
        **{key: card[key] for key in ("candidate_code", "name", "preferred_role", "current_company", "location", "notice_days")},
        "experience": None if months is None else f"{round(months / 12, 1):g}", "skills": ", ".join(s["name"] for s in card["skills"]),
        "source": card["source"]["name"], "status": card["status"].replace("_", " ").capitalize(),
        "engagement": card["engagement"]["label"] if card["engagement"] else None, "expected_annual_inr": None if salary is None else int(salary),
    }  # fmt: skip


async def export_table(db: AsyncSession, body: CandidateSearch, *, user_id: UUID, cap: int, salary: bool) -> dict:
    """X8-X10: up to `cap` + 1 rows (the caller refuses more than `cap`) in the search's own order, as a `tabular` table."""
    terms, where, _ = await conditions_for(db, body, user_id)
    cards = await page(db, where, terms, cap + 1, 0, body=body)
    columns = EXPORT_COLUMNS + ((SALARY_COLUMN,) if salary else ())
    return {"columns": [{"key": k, "label": label} for k, label in columns], "items": [_export_row(card) for card in cards], "totals": None}
