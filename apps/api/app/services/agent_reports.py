"""AGN-020 -- the agency reports (DEC-SCOPE-063; docs/superpowers/specs/2026-10-03-agn-020-agency-reports-design.md §4-§5).

Read-only SQL over AGN-018's scope helpers, so a Master reads the agency and a staff member only their assigned students (G4) with
no new scope logic. Every report is `columns` + `items` (+ `totals` for the summaries): the JSON table and the CSV come from one
column list, so a CSV header cannot drift from the screen. Nothing here writes, locks or commits; the export route owns that."""

import re
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import is_agent_staff
from app.models import AgentOrgMember, Country, OverseasApplication, University, User
from app.services.agent_applications import OVERSEAS_APPLICATION_STAGES, WITHDRAWN, intake_end
from app.services.agent_dashboard import agency_applications

PAGE_SIZE = 50  # R7: the on-screen lists
MAX_LIMIT = 100
CSV_ROW_CAP = 10_000  # R7: a larger export is refused, never cut short
MAX_OFFSET = CSV_ROW_CAP - PAGE_SIZE  # paging stops where an export would
MAX_VALUE = 120  # every filter value is length-capped before use (spec §5.1)

DATES = frozenset({"date_from", "date_to"})


@dataclass(frozen=True)
class ReportKind:
    title: str
    summary: bool
    filters: frozenset[str]
    master_only: bool = False


# Spec §4.2/§4.3: the filters each report offers. `member` is further limited to Masters (§5.1 step 6).
REPORT_KINDS: dict[str, ReportKind] = {
    "students": ReportKind("Students", False, DATES | {"member", "country", "status"}),
    "applications": ReportKind("Applications", False, DATES | {"member", "country", "university", "intake", "status"}),
    "enrollments": ReportKind("Enrollments", False, DATES | {"member", "country", "university"}),
    "universities": ReportKind("Applications by university", True, DATES | {"member", "country"}),
    "countries": ReportKind("Applications by country", True, DATES | {"member"}),
    "intakes": ReportKind("Applications by intake", True, DATES | {"member", "country"}),
    "staff": ReportKind("Staff performance", True, DATES, master_only=True),
}
STUDENT_STATUSES = ("active", "archived", "all")
APPLICATION_STATUSES = (*OVERSEAS_APPLICATION_STAGES, WITHDRAWN)
UNSTRUCTURED = ("unstructured", "Unstructured")  # R4: an intake the parser cannot read
_YYYY_MM_DD = re.compile(r"\d{4}-\d{2}-\d{2}")
_YYYY_MM = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


class ReportInputError(Exception):
    """A query parameter the report cannot use. The route turns it into FastAPI's 422 list shape, `loc` naming `param`."""

    def __init__(self, param: str, message: str):
        super().__init__(f"{param}: {message}")
        self.param, self.message = param, message


@dataclass
class Filters:
    start: date | None = None
    end: date | None = None
    member: UUID | str | None = None  # a member id, or "unassigned"
    country_id: UUID | None = None
    student_country: str | None = None  # students: the free-text preferred country, trimmed and lower-cased
    university_id: UUID | None = None
    intake: str | None = None
    intake_texts: list[str] | None = None  # the raw intake texts in scope that fold to `intake`
    status: str | None = None
    echo: dict[str, str] = field(default_factory=dict)  # the validated values as sent: audit metadata (§5.5) and nothing else


def intake_key(text: str | None) -> tuple[str, str]:
    """R4: `YYYY-MM` and its label ("Sep 2027") via the AGN-013 parser, else the one Unstructured group."""
    end = intake_end(text)
    return (f"{end.year:04d}-{end.month:02d}", end.strftime("%b %Y")) if end else UNSTRUCTURED


def parse_page(limit: str | None, offset: str | None) -> tuple[int, int]:
    """The codebase's `Page` convention (limit/offset), parsed after authorization so a refused caller never sees 422."""

    def number(param: str, value: str | None, default: int, low: int, high: int) -> int:
        if not value:
            return default
        if not value.isdigit() or not low <= int(value) <= high:
            raise ReportInputError(param, f"{param} must be a whole number from {low} to {high}")
        return int(value)

    return number("limit", limit, PAGE_SIZE, 1, MAX_LIMIT), number("offset", offset, 0, 0, MAX_OFFSET)


def _day(param: str, value: str) -> date:
    # AGN-014's rule and wording: fullmatch first (`fromisoformat` also takes "20260930"), then a real calendar day.
    if _YYYY_MM_DD.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ReportInputError(param, f"{param} must be a date (YYYY-MM-DD)")


async def parse_filters(db: AsyncSession, user: User, kind: str, raw: dict[str, str | None]) -> Filters:
    """Spec §5.1 step 6. `kind` is already known to be valid. Member codes resolve inside the caller's own organisation only, so
    another agency's real code gets the same answer as a made-up one (no cross-tenant oracle)."""
    offered = REPORT_KINDS[kind].filters
    given = {param: value for param, value in raw.items() if value not in (None, "")}
    for param, value in given.items():
        if param not in offered or (param == "member" and is_agent_staff(user)):
            raise ReportInputError(param, "This filter is not available for this report")
        if len(value) > MAX_VALUE:
            raise ReportInputError(param, "Too long")

    f = Filters(echo=dict(given))
    if "date_from" in given:
        f.start = _day("date_from", given["date_from"])
    if "date_to" in given:
        f.end = _day("date_to", given["date_to"])
        if f.start and f.end < f.start:
            raise ReportInputError("date_to", "date_to must be on or after date_from")
        if f.end == date.max:  # the exclusive bound is the next day, which does not exist
            raise ReportInputError("date_to", "date_to must be before 9999-12-31")

    if member := given.get("member"):
        if member == "unassigned":
            f.member = member
        else:
            f.member = await db.scalar(select(AgentOrgMember.id).where(AgentOrgMember.org_id == user.agent_membership.org_id, AgentOrgMember.code == member))
            if f.member is None:
                raise ReportInputError("member", "Unknown staff member")

    if country := given.get("country"):
        if kind == "students":
            f.student_country = country.strip().lower()
        else:
            f.country_id = await db.scalar(select(Country.id).where(Country.slug == country))
            if f.country_id is None:
                raise ReportInputError("country", "Unknown country")

    if university := given.get("university"):
        f.university_id = await db.scalar(select(University.id).where(University.slug == university))
        if f.university_id is None:
            raise ReportInputError("university", "Unknown university")

    if intake := given.get("intake"):
        if intake != UNSTRUCTURED[0] and not _YYYY_MM.fullmatch(intake):
            raise ReportInputError("intake", "Intake must be YYYY-MM or unstructured")
        texts = await db.scalars(select(distinct(OverseasApplication.intake)).where(*agency_applications(user)))
        f.intake, f.intake_texts = intake, [text for text in texts if intake_key(text)[0] == intake]

    if status := given.get("status"):
        if status not in (STUDENT_STATUSES if kind == "students" else APPLICATION_STATUSES):
            raise ReportInputError("status", "Unknown status")
        f.status = status
    return f
