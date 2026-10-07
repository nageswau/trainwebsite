"""AGN-023 (DEC-SCOPE-090 H11, spec §3.3): Agency / Counsellor filters on the overseas Students and Applications lists.

The Overseas Admin filters by agency and by counselor; a counselor by agency only. Filters only narrow the caller's existing scope and
are applied in SQL before the list's row cap. A filter value that is malformed, unknown, or not available to the caller is a 422 --
never silently ignored."""

from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentOrg, AgentOrgMember, OverseasApplication, User

FILTER_SECTIONS = frozenset({"students", "applications"})
NOT_AVAILABLE = "Filter not available"
UNKNOWN_VALUE = "Unknown filter value"


@dataclass(frozen=True)
class ApplicationFilters:
    agency: UUID | str | None = None  # an agency org id, "any" or "none"
    counselor: UUID | str | None = None  # an overseas counselor id or "none"


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(422, UNKNOWN_VALUE) from None


async def parse(db: AsyncSession, user: User, section: str, agency: str | None, counselor: str | None, repeated: frozenset[str] = frozenset()) -> ApplicationFilters:
    """`repeated` names the filter keys the request sent more than once."""
    if agency is None and counselor is None:
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
    return ApplicationFilters(parsed_agency, parsed_counselor)


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
    return stmt


async def row_labels(db: AsyncSession, apps: list[OverseasApplication]) -> tuple[dict, dict]:
    """({agent user id: agency name}, {counselor id: counselor name}) for the listed applications -- two bounded lookups."""
    agent_ids = {a.agent_id for a in apps if a.agent_id is not None}
    counselor_ids = {a.counselor_id for a in apps if a.counselor_id is not None}
    agencies = dict((await db.execute(select(AgentOrgMember.user_id, AgentOrg.name).join(AgentOrg, AgentOrg.id == AgentOrgMember.org_id).where(AgentOrgMember.user_id.in_(agent_ids)))).all()) if agent_ids else {}
    counselors = dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(counselor_ids)))).all()) if counselor_ids else {}
    return agencies, counselors


def _value(value: UUID | str | None) -> str | None:
    return None if value is None else str(value)


async def payload_part(db: AsyncSession, user: User, filters: ApplicationFilters) -> dict:
    """The applied values plus the dropdown options. A counselor's agency options are only the agencies on their own applications, so no
    agency outside their caseload is named; the Admin's counselor options include inactive counselors (past assignments name them)."""
    orgs = select(AgentOrg.id, AgentOrg.name).join(AgentOrgMember, AgentOrgMember.org_id == AgentOrg.id).join(OverseasApplication, OverseasApplication.agent_id == AgentOrgMember.user_id)
    if user.role == "counselor":
        orgs = orgs.where(OverseasApplication.counselor_id == user.id)
    part: dict = {
        "agency": _value(filters.agency),
        "counselor": _value(filters.counselor),
        "agencies": [{"value": str(i), "label": n} for i, n in (await db.execute(orgs.distinct().order_by(AgentOrg.name))).all()],
    }
    if user.role == "overseas_admin":
        rows = (await db.execute(select(User.id, User.full_name, User.active).where(User.role == "counselor", User.division == "overseas").order_by(User.full_name))).all()
        part["counselors"] = [{"value": str(i), "label": n if active else f"{n} (inactive)"} for i, n, active in rows]
    return part
