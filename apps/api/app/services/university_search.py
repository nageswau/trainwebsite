"""upc-024 (DEC-SCOPE-163, spec SR1-SR15): the Global University Database -- every active university, searched by the §25 fields and
narrowed by its 15 filters. Read only.

Every value reaches SQL as a bound parameter: substrings go through `lookups._pattern` (ILIKE, escaped) and the course term through
`_word_prefix` (a case-insensitive regex with every non-alphanumeric character escaped). The course filters hold for ONE active course
(a single EXISTS, SR7). A fixed number of queries whatever the page or the data: count, page, facet, page rankings, and the matching
course counts when a course filter is sent (SR15)."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Numeric, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.lookups import _pattern as like_pattern
from app.models import Country, OverseasCourse, Scholarship, University, UniversityAgreement, UniversityCommissionTerm, UniversityRanking, User
from app.partnership_stages import GROUPS
from app.schemas import UniversitySearchQuery
from app.services import partnership_universities as svc
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


def partner_status_of(uni: University) -> str:
    return "lost" if uni.lost_at is not None else GROUPS.get(uni.stage, "target")


def _partner_status(value: str | None) -> list:
    """SR11: not_partnered = target + in progress; every value but `lost` leaves lost universities out."""
    if value is None:
        return []
    if value == "lost":
        return [University.lost_at.is_not(None)]
    groups = ("target", "in_progress") if value == "not_partnered" else (value,)
    return [University.lost_at.is_(None), University.stage.in_([key for key, group in GROUPS.items() if group in groups])]


def _course_conditions(query: UniversitySearchQuery) -> list:
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


def _ranking(query: UniversitySearchQuery):
    conditions = [UniversityRanking.university_id == University.id, _lead_number(UniversityRanking.rank) <= query.ranking_max]
    if query.ranking_system:
        conditions.append(UniversityRanking.system == query.ranking_system)
    return select(UniversityRanking.id).where(*conditions).exists()


def filters(user: User, query: UniversitySearchQuery) -> list:
    """Every filter except partner status (the facet is counted without it, SR14). Active universities only (SR2)."""
    out = [University.active.is_(True), *svc.manager_filter(user, query.manager)]
    if pattern := like_pattern(query.q):
        out.append(or_(*(c.ilike(pattern, escape="\\") for c in (University.name, University.university_code, University.city, Country.name))))
    if country := (query.country or "").strip():
        out.append(or_(Country.name.ilike(like_pattern(country), escape="\\"), Country.iso2 == country.upper()))
    if pattern := like_pattern(query.city):
        out.append(University.city.ilike(pattern, escape="\\"))
    for column, value in (
        (Country.region, query.region),
        (University.institution_type, query.institution_type),
        (University.ownership_type, query.ownership_type),
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


async def search(db: AsyncSession, user: User, query: UniversitySearchQuery) -> dict:
    if not can_see_commission(user):  # SR10 (U2): dropped before any SQL, so results never depend on commission data
        query = query.model_copy(update={"commission_min": None})
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
    grouped = select(University.lost_at.is_not(None), University.stage, func.count()).join(Country, Country.id == University.country_id).where(*base)
    for lost, stage, count in (await db.execute(grouped.group_by(University.lost_at.is_not(None), University.stage))).all():
        facet["lost" if lost else GROUPS.get(stage, "target")] += count
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
