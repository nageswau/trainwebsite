"""rec-013 (DEC-SCOPE-151, spec §3): Find Candidates -- skill AND / OR search over the whole pool (R11), expanded through aliases and
related skills (FS2), the S2-§18 filters (FS5), the F1-F3 facets (FS7) and the result cards (FS8).

Read only. Terms become skill ids before any candidate is read, and only ids and escaped patterns reach SQL as bound parameters (no
expression is ever parsed into SQL). Six queries whatever the pool or page size: terms, related, counts, locations, page, page skills.

rec-014 (DEC-SCOPE-154, FT1-FT6): an optional `text` matches the current resume's generated `search_vector` through
websearch_to_tsquery('english', :text) -- the text is a bound parameter, never SQL -- ranks by relevance and adds `ts_headline`
snippets. It adds two queries: the stop-word check and the page's snippets."""

import logging
import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, exists, false, func, literal, literal_column, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.lookups import _pattern as like_pattern
from app.models import Candidate, CandidateResume, CandidateSkill, RecCandidateSource, Skill, SkillAlias, SkillRelated, User
from app.schemas import CandidateSearch
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
    texts = {t.lower(): t for t in [*body.all, *(t for group in body.any for t in group)]}
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


def _has(ids: set[UUID], verified_only: bool):
    conditions = [CandidateSkill.candidate_id == Candidate.id, CandidateSkill.skill_id.in_(sorted(ids))]
    if verified_only:
        conditions.append(CandidateSkill.status != "claimed")
    return exists().where(*conditions)


def filters(body: CandidateSearch, terms: dict[str, dict]) -> list:
    """The pool (AC5), not archived, one EXISTS per AND term, one per OR group, then the FS5 filters -- all ANDed."""
    out = [*pool_filter(), Candidate.archived_at.is_(None)]
    out += [_has(terms[t.lower()]["ids"], body.verified_only) for t in dict.fromkeys(t.lower() for t in body.all)]
    out += [_has(set().union(*(terms[t.lower()]["ids"] for t in group)), body.verified_only) for group in body.any]
    if body.experience_min_months is not None:
        out.append(Candidate.experience_months >= body.experience_min_months)
    if body.experience_max_months is not None:
        out.append(Candidate.experience_months <= body.experience_max_months)
    for column, text in ((Candidate.location, body.location), (Candidate.qualification, body.qualification)):
        if pattern := like_pattern(text):
            out.append(column.ilike(pattern, escape="\\"))
    if body.availability:
        out.append(or_(*(_between(Candidate.notice_days, low, high) for key, low, high in AVAILABILITY_BANDS if key in body.availability)))
    if body.salary_min is not None:
        out.append(Candidate.expected_salary >= body.salary_min)
    if body.salary_max is not None:
        out.append(Candidate.expected_salary <= body.salary_max)
    if body.source_id:
        out.append(Candidate.source_id == body.source_id)
    if body.status:
        out.append(Candidate.status == body.status)
    if body.text:  # FT1: the GIN index finds matching resumes; only a candidate's current one counts
        resume = aliased(CandidateResume)
        out.append(Candidate.id.in_(select(resume.candidate_id).where(resume.search_vector.op("@@")(_tsquery(body.text)), _current(resume))))
    return out


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


async def page(db: AsyncSession, where: list, terms: dict[str, dict], limit: int, offset: int, text: str | None = None) -> list[dict]:
    """The page's cards, newest first (FS11) -- with text, the most relevant current resume first (FT5): one query for the candidates
    with their source, one for all their skills."""
    order = [Candidate.created_at.desc(), Candidate.id.desc()]
    if text:
        resume = aliased(CandidateResume)
        rank = select(func.ts_rank_cd(resume.search_vector, _tsquery(text))).where(resume.candidate_id == Candidate.id, _current(resume))
        order.insert(0, rank.scalar_subquery().desc())
    rows = (await db.execute(
        select(Candidate, RecCandidateSource).join(RecCandidateSource, RecCandidateSource.id == Candidate.source_id).where(*where)
        .order_by(*order).limit(limit).offset(offset)
    )).all()
    matched = set().union(*(t["ids"] for t in terms.values()))
    skills: dict[UUID, list] = {c.id: [] for c, _ in rows}
    if skills:
        held = await db.execute(
            select(CandidateSkill.candidate_id, CandidateSkill.skill_id, Skill.name, CandidateSkill.level, CandidateSkill.status)
            .join(Skill, Skill.id == CandidateSkill.skill_id).where(CandidateSkill.candidate_id.in_(list(skills)))
        )
        for candidate_id, skill_id, name, level, status in held.all():
            skills[candidate_id].append({"name": name, "level": level, "status": status, "matched": skill_id in matched})
        for items in skills.values():
            items.sort(key=lambda s: (not s["matched"], s["name"].lower()))
    return [
        {
            "id": c.id, "candidate_code": c.candidate_code, "name": c.name, "preferred_role": c.preferred_role, "current_company": c.current_company,
            "experience_months": c.experience_months, "location": c.location, "notice_days": c.notice_days, "expected_salary": c.expected_salary,
            "source": {"id": s.id, "name": s.name, "active": s.active}, "source_detail": c.source_detail, "status": c.status, "skills": skills[c.id],
            "snippet": None,
        }
        for c, s in rows
    ]


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


async def search(db: AsyncSession, body: CandidateSearch, *, limit: int, offset: int) -> dict:
    terms = await resolve_terms(db, body)
    where = filters(body, terms)
    notice = None
    if body.text and not await db.scalar(select(func.numnode(_tsquery(body.text)))):
        where.append(false())  # FT3: only stop words -- the same shape, nothing in it
        notice = STOP_WORDS_NOTICE
    total, facet_counts = await facets(db, where)
    items = await page(db, where, terms, limit, offset, body.text)
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
