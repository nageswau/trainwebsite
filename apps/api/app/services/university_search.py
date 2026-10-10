"""upc-024 (DEC-SCOPE-163, spec SR1-SR15): the Global University Database -- every active university, searched by the §25 fields and
narrowed by its 15 filters. Read only.

Every value reaches SQL as a bound parameter: substrings go through `lookups._pattern` (ILIKE, escaped) and the course term through
`_word_prefix` (a case-insensitive regex with every non-alphanumeric character escaped). The course filters hold for ONE active course
(a single EXISTS, SR7). A fixed number of queries whatever the page or the data: count, page, facet, page rankings, and the matching
course counts when a course filter is sent (SR15)."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Numeric, and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.lookups import _pattern as like_pattern
from app.models import Country, OverseasCourse, Scholarship, University, UniversityAgreement, UniversityCommissionTerm, UniversityRanking, User
from app.partnership_stages import GROUPS, STAGES
from app.schemas import UniversityFilterQuery, UniversitySearchQuery
from app.services import partnership_universities as svc
from app.services.bdm_travel import india_today
from app.services.partnership_access import can_see_commission
from app.services.university_agreements import IN_FORCE

PARTNER_STATUSES = ("partner", "in_progress", "target", "lost")  # SR14: the facet's keys, Appendix B G1, G2, G3 and the Lost flag
Primary, Backup = aliased(User), aliased(User)


def _word_prefix(term: str) -> str:
    """SR7: the term must start a word ("IT" matches "IT Management", not "Security"); spaces are collapsed."""
    text = " ".join(term.split())
    return r"\m" + "".join(c if c.isalnum() else "\\" + c for c in text)


def _lead_number(column):
    """SR6: a rank's leading number ("201-250" → 201), NULL when it has none. Numeric, so a long digit run cannot overflow."""
    return cast(func.substring(column, "^[0-9]+"), Numeric)


def _group(lost: bool, stage: str) -> str:
    return "lost" if lost else GROUPS.get(stage, "target")


def partner_status_of(uni: University) -> str:
    return _group(uni.lost_at is not None, uni.stage)


def _partner_status(value: str | None) -> list:
    """SR11: not_partnered = target + in progress; every value but `lost` leaves lost universities out."""
    if value is None:
        return []
    if value == "lost":
        return [University.lost_at.is_not(None)]
    groups = ("target", "in_progress") if value == "not_partnered" else (value,)
    return [University.lost_at.is_(None), University.stage.in_([key for key, group in GROUPS.items() if group in groups])]


def _activity(value: str) -> list:
    """upc-025 MP7: active only by default (SR2), as before."""
    return [] if value == "all" else [University.active.is_(value == "active")]


def _exclusivity(value: str):
    """upc-025 MP8 (Q-07): the current agreements are the in-force ones (signed/active) not past their expiry date (upc-014 AG4).
    `exclusive` = one of them is exclusive; `non_exclusive` = there is one and none is exclusive."""

    def current(*conditions):
        return (
            select(UniversityAgreement.id)
            .where(UniversityAgreement.university_id == University.id, UniversityAgreement.status.in_(IN_FORCE), UniversityAgreement.expiry_date >= india_today(), *conditions)
            .exists()
        )

    exclusive = current(UniversityAgreement.exclusivity == "exclusive")
    return exclusive if value == "exclusive" else and_(current(), ~exclusive)


def _course_conditions(query: UniversityFilterQuery) -> list:
    """SR7/SR8: the conditions one active course must meet (without the correlation to its university)."""
    conditions: list = [OverseasCourse.active.is_(True)]
    if term := (query.course or "").strip():
        pattern = _word_prefix(term)
        conditions.append(or_(OverseasCourse.title.op("~*")(pattern), OverseasCourse.category.op("~*")(pattern)))
    if query.level:
        conditions.append(OverseasCourse.level == query.level)
    if query.intake:
        conditions.append(cast(OverseasCourse.intakes, JSONB).contains([query.intake]))
    if query.tuition_currency:
        conditions.append(OverseasCourse.tuition_currency == query.tuition_currency)
    if query.tuition_min is not None:
        conditions.append(OverseasCourse.tuition_amount >= query.tuition_min)
    if query.tuition_max is not None:
        conditions.append(OverseasCourse.tuition_amount <= query.tuition_max)
    return conditions


def _has_course(*conditions):
    return select(OverseasCourse.id).where(OverseasCourse.university_id == University.id, *conditions).exists()


def _scholarship():
    """SR9: an active scholarship of the university, or an active course with a linked scholarship."""
    own = select(Scholarship.id).where(Scholarship.university_id == University.id, Scholarship.active.is_(True)).exists()
    linked = _has_course(OverseasCourse.active.is_(True), func.jsonb_array_length(cast(OverseasCourse.scholarship_ids, JSONB)) > 0)
    return or_(own, linked)


def _commission(minimum: Decimal):
    """SR10: an active course's percent, or a term of an in-force agreement, at or above the minimum. Fixed amounts are not compared."""
    by_course = _has_course(OverseasCourse.active.is_(True), OverseasCourse.commission_percent >= minimum)
    by_term = (
        select(UniversityCommissionTerm.id)
        .join(UniversityAgreement, UniversityAgreement.id == UniversityCommissionTerm.agreement_id)
        .where(UniversityAgreement.university_id == University.id, UniversityAgreement.status.in_(IN_FORCE), UniversityCommissionTerm.commission_percent >= minimum)
        .exists()
    )
    return or_(by_course, by_term)


def _ranking(query: UniversityFilterQuery):
    conditions = [UniversityRanking.university_id == University.id, _lead_number(UniversityRanking.rank) <= query.ranking_max]
    if query.ranking_system:
        conditions.append(UniversityRanking.system == query.ranking_system)
    return select(UniversityRanking.id).where(*conditions).exists()


def filters(user: User, query: UniversityFilterQuery) -> list:
    """Every filter except partner status (the facet is counted without it, SR14). Active universities unless `activity` says otherwise."""
    out = [*_activity(query.activity), *svc.manager_filter(user, query.manager)]
    if pattern := like_pattern(query.q):
        out.append(or_(*(c.ilike(pattern, escape="\\") for c in (University.name, University.university_code, University.city, Country.name))))
    if country := (query.country or "").strip():
        out.append(or_(Country.name.ilike(like_pattern(country), escape="\\"), Country.iso2 == country.upper()))
    if pattern := like_pattern(query.city):
        out.append(University.city.ilike(pattern, escape="\\"))
    for column, value in (
        (Country.iso2, query.iso2 and query.iso2.upper()),  # upc-025 MP4: one exact country, the map's click target
        (Country.region, query.region),
        (University.institution_type, query.institution_type),
        (University.ownership_type, query.ownership_type),
        (University.stage, query.stage),
        (University.priority, query.priority),
    ):
        if value is not None:
            out.append(column == value)
    if query.ranking_max is not None:
        out.append(_ranking(query))
    if query.course_filtered:
        out.append(_has_course(*_course_conditions(query)))
    if query.scholarship:
        out.append(_scholarship())
    if query.commission_min is not None:
        out.append(_commission(query.commission_min))
    if query.exclusivity:
        out.append(_exclusivity(query.exclusivity))
    if query.expected_from:
        out.append(University.target_partnership_date >= query.expected_from)
    if query.expected_to:
        out.append(University.target_partnership_date <= query.expected_to)
    return out


def _ranking_text(r: UniversityRanking) -> str:
    return f"{r.other_name if r.system == 'Other' else r.system} {r.year}: {r.rank}"


async def _best_rankings(db: AsyncSession, ids: list[UUID]) -> dict[UUID, str]:
    """SR6: per university, the lowest leading number, then the latest year (a rank without a number comes last)."""
    rows = (await db.execute(select(UniversityRanking, _lead_number(UniversityRanking.rank)).where(UniversityRanking.university_id.in_(ids)))).all()
    best: dict[UUID, tuple] = {}
    for r, lead in rows:
        key = (lead is None, lead or 0, -r.year)
        if r.university_id not in best or key < best[r.university_id][0]:
            best[r.university_id] = (key, _ranking_text(r))
    return {uid: text for uid, (_, text) in best.items()}


async def _matching_courses(db: AsyncSession, query: UniversitySearchQuery, ids: list[UUID]) -> dict[UUID, int]:
    stmt = select(OverseasCourse.university_id, func.count()).where(OverseasCourse.university_id.in_(ids), *_course_conditions(query)).group_by(OverseasCourse.university_id)
    return dict((await db.execute(stmt)).all())


def _drop_hidden_commission(user: User, query):
    """SR10 (U2): commission is dropped before any SQL for other roles, so neither the list nor the map depends on commission data."""
    return query if can_see_commission(user) else query.model_copy(update={"commission_min": None})


def _grouped(*columns):
    """Counts by the given columns plus partner status: the lost flag and the stage (one GROUP BY)."""
    lost = University.lost_at.is_not(None)
    return select(*columns, lost, University.stage, func.count()).join(Country, Country.id == University.country_id).group_by(*columns, lost, University.stage)


async def search(db: AsyncSession, user: User, query: UniversitySearchQuery) -> dict:
    query = _drop_hidden_commission(user, query)
    base = filters(user, query)
    where = [*base, *_partner_status(query.partner_status)]
    total = await db.scalar(select(func.count()).select_from(University).join(Country, Country.id == University.country_id).where(*where))
    stmt = (
        select(University, Country, Primary, Backup)
        .join(Country, Country.id == University.country_id)
        .outerjoin(Primary, Primary.id == University.primary_manager_user_id)
        .outerjoin(Backup, Backup.id == University.backup_manager_user_id)
        .where(*where)
        .order_by(University.name, University.id)
        .limit(query.limit)
        .offset(query.offset)
    )
    rows = (await db.execute(stmt)).all()
    facet = {status: 0 for status in PARTNER_STATUSES}
    for lost, stage, count in (await db.execute(_grouped().where(*base))).all():
        facet[_group(lost, stage)] += count
    ids = [uni.id for uni, *_ in rows]
    rankings = await _best_rankings(db, ids) if ids else {}
    matching = await _matching_courses(db, query, ids) if ids and query.course_filtered else {}
    team = await svc.team_of(db, user)
    items = [
        {
            **svc.row_out(user, uni, country, primary, backup, team),
            "ownership_type": uni.ownership_type,
            "partner_status": partner_status_of(uni),
            "target_partnership_date": uni.target_partnership_date,
            "ranking": rankings.get(uni.id),
            "matching_courses": matching.get(uni.id, 0) if query.course_filtered else None,
        }
        for uni, country, primary, backup in rows
    ]
    return {"items": items, "total": total or 0, "limit": query.limit, "offset": query.offset, "facets": {"partner_status": facet}}


async def country_counts(db: AsyncSession, user: User, query: UniversityFilterQuery) -> dict:
    """upc-025 (MP2, MP3, MP10): the partner-status counts per country of exactly what the search would list for the same filters (the
    partner-status filter included), in one grouped query. Only countries with a matching university, ordered by name."""
    query = _drop_hidden_commission(user, query)
    where = [*filters(user, query), *_partner_status(query.partner_status)]
    rows: dict[UUID, dict] = {}
    for country_id, iso2, name, region, lost, stage, count in (await db.execute(_grouped(Country.id, Country.iso2, Country.name, Country.region).where(*where))).all():
        row = rows.setdefault(country_id, {"iso2": iso2, "name": name, "region": region, **dict.fromkeys(PARTNER_STATUSES, 0), "total": 0})
        row[_group(lost, stage)] += count
        row["total"] += count
    countries = sorted(rows.values(), key=lambda r: (r["name"], r["iso2"] or ""))
    totals = {key: sum(r[key] for r in countries) for key in (*PARTNER_STATUSES, "total")}
    return {"countries": countries, "totals": totals, "stages": [{"key": s.key, "label": s.label} for s in STAGES]}
