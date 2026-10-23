"""AGN-023 (DEC-SCOPE-090 H11, spec §3.3): Agency / Counsellor filters on the overseas Students and Applications lists.

The Overseas Admin filters by agency and by counselor; a counselor by agency only. Filters only narrow the caller's existing scope and
are applied in SQL before the list's row cap. A filter value that is malformed, unknown, or not available to the caller is a 422 --
never silently ignored.

ccrm-012 (DEC-SCOPE-246 QS6): both roles also filter by destination country, university, intake, stage, sub-status and the application's
created date (from / to, inclusive), under the same rules. The options name only what the caller's own applications use."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application_sub_status import STAGE_OF
from app.application_sub_status import label as sub_status_label
from app.models import AgentOrg, AgentOrgMember, Country, OverseasApplication, University, User
from app.services.agent_applications import OVERSEAS_APPLICATION_STAGES

FILTER_SECTIONS = frozenset({"students", "applications"})
FILTER_KEYS = ("agency", "counselor", "country", "university", "intake", "stage", "sub_status", "from", "to")
NOT_AVAILABLE = "Filter not available"
UNKNOWN_VALUE = "Unknown filter value"
SUB_STATUS_MISMATCH = "Sub-status does not belong to that stage"
DATE_ORDER = "The start date must be on or before the end date"
STAGES = (*OVERSEAS_APPLICATION_STAGES, "withdrawn")
INTAKE_MAX = 80  # OverseasApplication.intake's width


@dataclass(frozen=True)
class ApplicationFilters:
    agency: UUID | str | None = None  # an agency org id, "any" or "none"
    counselor: UUID | str | None = None  # an overseas counselor id or "none"
    country: UUID | None = None
    university: UUID | None = None
    intake: str | None = None
    stage: str | None = None
    sub_status: str | None = None
    created_from: date | None = None
    created_to: date | None = None


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(422, UNKNOWN_VALUE) from None


def _date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, UNKNOWN_VALUE) from None


def date_range(created_from: str | None, created_to: str | None) -> tuple[date | None, date | None]:
    """ccrm-012: an inclusive from / to pair of ISO dates; a malformed date or a reversed pair is 422."""
    start, end = _date(created_from), _date(created_to)
    if start and end and start > end:
        raise HTTPException(422, DATE_ORDER)
    return start, end


def created_between(column, start: date | None, end: date | None) -> list:
    """WHERE clauses for an inclusive range of UTC days on a timestamp column."""
    clauses = []
    if start:
        clauses.append(column >= datetime.combine(start, time.min, UTC))
    if end:
        clauses.append(column < datetime.combine(end + timedelta(days=1), time.min, UTC))
    return clauses


async def parse(db: AsyncSession, user: User, section: str, agency: str | None, counselor: str | None, repeated: frozenset[str] = frozenset(), *,
                country: str | None = None, university: str | None = None, intake: str | None = None, stage: str | None = None,
                sub_status: str | None = None, created_from: str | None = None, created_to: str | None = None) -> ApplicationFilters:
    """`repeated` names the filter keys the request sent more than once."""
    if all(v is None for v in (agency, counselor, country, university, intake, stage, sub_status, created_from, created_to)):
        return ApplicationFilters()
    available = user.division == "overseas" and user.role in {"overseas_admin", "counselor"} and section in FILTER_SECTIONS
    if not available or (counselor is not None and user.role != "overseas_admin"):
        raise HTTPException(422, NOT_AVAILABLE)
    if repeated:  # B7: a repeated key is ambiguous -- refused only after availability, so a filter that is not available says so
        raise HTTPException(422, UNKNOWN_VALUE)
    parsed_agency: UUID | str | None = None
    if agency is not None:
        if agency in {"any", "none"}:
            parsed_agency = agency
        else:
            parsed_agency = _uuid(agency)
            if await db.get(AgentOrg, parsed_agency) is None:
                raise HTTPException(422, UNKNOWN_VALUE)
    parsed_counselor: UUID | str | None = None
    if counselor is not None:
        if counselor == "none":
            parsed_counselor = counselor
        else:
            parsed_counselor = _uuid(counselor)
            target = await db.get(User, parsed_counselor)
            if target is None or target.role != "counselor" or target.division != "overseas":
                raise HTTPException(422, UNKNOWN_VALUE)
    parsed_country = _uuid(country) if country is not None else None
    parsed_university = _uuid(university) if university is not None else None
    if (parsed_country and await db.get(Country, parsed_country) is None) or (parsed_university and await db.get(University, parsed_university) is None):
        raise HTTPException(422, UNKNOWN_VALUE)
    if intake is not None and not 0 < len(intake) <= INTAKE_MAX:
        raise HTTPException(422, UNKNOWN_VALUE)
    if (stage is not None and stage not in STAGES) or (sub_status is not None and sub_status not in STAGE_OF):
        raise HTTPException(422, UNKNOWN_VALUE)
    if stage and sub_status and STAGE_OF[sub_status] != stage:
        raise HTTPException(422, SUB_STATUS_MISMATCH)
    start, end = date_range(created_from, created_to)
    return ApplicationFilters(parsed_agency, parsed_counselor, parsed_country, parsed_university, intake, stage, sub_status, start, end)


def apply(stmt: Select, filters: ApplicationFilters) -> Select:
    if filters.agency == "any":
        stmt = stmt.where(OverseasApplication.agent_id.is_not(None))
    elif filters.agency == "none":
        stmt = stmt.where(OverseasApplication.agent_id.is_(None))
    elif filters.agency is not None:
        stmt = stmt.where(OverseasApplication.agent_id.in_(select(AgentOrgMember.user_id).where(AgentOrgMember.org_id == filters.agency)))
    if filters.counselor == "none":
        stmt = stmt.where(OverseasApplication.counselor_id.is_(None))
    elif filters.counselor is not None:
        stmt = stmt.where(OverseasApplication.counselor_id == filters.counselor)
    if filters.country is not None:  # ccrm-012: a subquery, so a statement without a University join filters too (management_metrics)
        stmt = stmt.where(OverseasApplication.university_id.in_(select(University.id).where(University.country_id == filters.country)))
    if filters.university is not None:
        stmt = stmt.where(OverseasApplication.university_id == filters.university)
    if filters.intake is not None:
        stmt = stmt.where(OverseasApplication.intake == filters.intake)
    if filters.stage is not None:
        stmt = stmt.where(OverseasApplication.status == filters.stage)
    if filters.sub_status is not None:
        stmt = stmt.where(OverseasApplication.sub_status == filters.sub_status)
    return stmt.where(*created_between(OverseasApplication.created_at, filters.created_from, filters.created_to))


async def row_labels(db: AsyncSession, apps: list[OverseasApplication]) -> tuple[dict, dict]:
    """({agent user id: agency name}, {counselor id: counselor name}) for the listed applications -- two bounded lookups."""
    agent_ids = {a.agent_id for a in apps if a.agent_id is not None}
    counselor_ids = {a.counselor_id for a in apps if a.counselor_id is not None}
    agencies = dict((await db.execute(select(AgentOrgMember.user_id, AgentOrg.name).join(AgentOrg, AgentOrg.id == AgentOrgMember.org_id).where(AgentOrgMember.user_id.in_(agent_ids)))).all()) if agent_ids else {}
    counselors = dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(counselor_ids)))).all()) if counselor_ids else {}
    return agencies, counselors


def _value(value: UUID | str | date | None) -> str | None:
    return None if value is None else str(value)


async def payload_part(db: AsyncSession, user: User, filters: ApplicationFilters) -> dict:
    """The applied values plus the dropdown options. A counselor's agency options are only the agencies on their own applications, so no
    agency outside their caseload is named; the Admin's counselor options include inactive counselors (past assignments name them).
    ccrm-012: the university, country and intake options follow the agency rule."""
    orgs = select(AgentOrg.id, AgentOrg.name).join(AgentOrgMember, AgentOrgMember.org_id == AgentOrg.id).join(OverseasApplication, OverseasApplication.agent_id == AgentOrgMember.user_id)
    universities = (
        select(University.id, University.name, Country.id, Country.name)
        .join(Country, Country.id == University.country_id)
        .join(OverseasApplication, OverseasApplication.university_id == University.id)
    )
    intakes = select(OverseasApplication.intake)
    if user.role == "counselor":
        orgs, universities, intakes = (stmt.where(OverseasApplication.counselor_id == user.id) for stmt in (orgs, universities, intakes))
    used = (await db.execute(universities.distinct().order_by(University.name))).all()
    countries = sorted({(str(i), n) for _, _, i, n in used}, key=lambda c: c[1])
    part: dict = {
        "agency": _value(filters.agency),
        "counselor": _value(filters.counselor),
        "country": _value(filters.country),
        "university": _value(filters.university),
        "intake": filters.intake,
        "stage": filters.stage,
        "sub_status": filters.sub_status,
        "from": _value(filters.created_from),
        "to": _value(filters.created_to),
        "agencies": [{"value": str(i), "label": n} for i, n in (await db.execute(orgs.distinct().order_by(AgentOrg.name))).all()],
        "countries": [{"value": i, "label": n} for i, n in countries],
        "universities": [{"value": str(i), "label": n} for i, n, _, _ in used],
        "intakes": [{"value": i, "label": i} for i in (await db.scalars(intakes.distinct().order_by(OverseasApplication.intake))).all()],
        "stages": [{"value": s, "label": s.replace("_", " ").capitalize()} for s in STAGES],
        "sub_statuses": [{"value": s, "label": sub_status_label(s), "stage": stage} for s, stage in STAGE_OF.items()],
    }
    if user.role == "overseas_admin":
        rows = (await db.execute(select(User.id, User.full_name, User.active).where(User.role == "counselor", User.division == "overseas").order_by(User.full_name))).all()
        part["counselors"] = [{"value": str(i), "label": n if active else f"{n} (inactive)"} for i, n, active in rows]
    return part
