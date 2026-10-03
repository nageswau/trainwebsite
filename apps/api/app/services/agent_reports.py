"""AGN-020 -- the agency reports (DEC-SCOPE-063; docs/superpowers/specs/2026-10-03-agn-020-agency-reports-design.md §4-§5).

Read-only SQL over AGN-018's scope helpers, so a Master reads the agency and a staff member only their assigned students (G4) with
no new scope logic. Every report is `columns` + `items` (+ `totals` for the summaries): the JSON table and the CSV come from one
column list, so a CSV header cannot drift from the screen. Nothing here writes, locks or commits; the export route owns that."""

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement, case, distinct, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import is_agent_staff
from app.models import AgentOrgMember, AgentStudent, Country, OverseasApplication, University, User, VisaCase
from app.services.agent_applications import OVERSEAS_APPLICATION_STAGES, WITHDRAWN, intake_end
from app.services.agent_dashboard import agency_applications, offer_clause
from app.services.agent_orgs import org_member_ids

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


# --- Report building (spec §4) ---


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    numeric: bool = False


# Spec §4.1/§4.3: the six stage counts every summary shows -- AGN-018's G3 definitions on the milestone base (D1: offers, visa and
# submitted count a withdrawn application; "Applications" does not).
STAGE_COLUMNS = (
    Column("applications", "Applications", True),
    Column("submitted", "Submitted", True),
    Column("offers", "Offers", True),
    Column("visa_applications", "Visa apps", True),
    Column("visa_approvals", "Visa approved", True),
    Column("enrollments", "Enrolled", True),
)


def _created_between(column, f: Filters) -> list[ColumnElement[bool]]:
    """Inclusive UTC calendar days on a timestamp (DEC-SCOPE-051 R7 semantics): [start 00:00, end + 1 day 00:00)."""
    clauses = []
    if f.start:
        clauses.append(column >= datetime.combine(f.start, time.min, tzinfo=UTC))
    if f.end:
        clauses.append(column < datetime.combine(f.end + timedelta(days=1), time.min, tzinfo=UTC))
    return clauses


def _assignee(user: User):
    """The staff member an application counts for: its agency record's assignee; for a row made before AGN-008 (login only), the
    assignee of the agency's record for that login. The current assignee, as AGN-018 (spec §4.3)."""
    by_record = select(AgentStudent.assigned_member_id).where(AgentStudent.id == OverseasApplication.agent_student_id).scalar_subquery()
    by_login = (
        select(AgentStudent.assigned_member_id)
        .where(AgentStudent.student_id == OverseasApplication.student_id, AgentStudent.agent_id.in_(org_member_ids(user)))
        .order_by(AgentStudent.created_at)
        .limit(1)
        .scalar_subquery()
    )
    return case((OverseasApplication.agent_student_id.is_not(None), by_record), else_=by_login)


def _member_is(expression, f: Filters) -> list[ColumnElement[bool]]:
    if f.member is None:
        return []
    return [expression.is_(None) if f.member == "unassigned" else expression == f.member]


def _application_where(user: User, f: Filters) -> list[ColumnElement[bool]]:
    """The caller's applications (scope + School-bridged rows out, A12) narrowed by the shared filters. Needs University joined."""
    where = [*agency_applications(user), *_created_between(OverseasApplication.created_at, f), *_member_is(_assignee(user), f)]
    if f.country_id:
        where.append(University.country_id == f.country_id)
    if f.university_id:
        where.append(OverseasApplication.university_id == f.university_id)
    if f.intake_texts is not None:
        where.append(OverseasApplication.intake.in_(f.intake_texts))
    if f.status:
        where.append(OverseasApplication.status == f.status)
    return where


def _stage_counts() -> list:
    """One FILTER aggregate per stage column, so a whole summary is one statement (one snapshot)."""
    has_visa = exists().where(VisaCase.application_id == OverseasApplication.id)
    approved = exists().where(VisaCase.application_id == OverseasApplication.id, VisaCase.decision == "approved")
    conditions = (
        OverseasApplication.status != WITHDRAWN,
        OverseasApplication.submitted_on.is_not(None),
        offer_clause(),
        has_visa,
        approved,
        OverseasApplication.status == "enrolled",
    )
    return [func.count().filter(condition).label(column.key) for column, condition in zip(STAGE_COLUMNS, conditions, strict=True)]


def _counted(row) -> dict[str, int]:
    return {column.key: int(getattr(row, column.key)) for column in STAGE_COLUMNS}


def _totals(columns: tuple[Column, ...], items: list[dict]) -> dict:
    """The Total row: the groups are disjoint (each application is in exactly one), so the sum is exact."""
    totals: dict[str, str | int | None] = {column.key: (sum(item[column.key] for item in items) if column.numeric else "") for column in columns}
    totals[columns[0].key] = "Total"
    return totals


def _summary_stmt(user: User, f: Filters, *group):
    return (
        select(*group, *_stage_counts())
        .select_from(OverseasApplication)
        .join(University, University.id == OverseasApplication.university_id)
        .join(Country, Country.id == University.country_id)
        .where(*_application_where(user, f))
    )


async def _countries(db: AsyncSession, user: User, f: Filters) -> tuple[tuple[Column, ...], list[dict]]:
    stmt = _summary_stmt(user, f, Country.name).group_by(Country.id, Country.name)
    items = [{"country": row.name, **_counted(row)} for row in (await db.execute(stmt)).all()]
    items.sort(key=lambda item: (-item["applications"], item["country"]))
    return (Column("country", "Country"), *STAGE_COLUMNS), items


SUMMARIES = {"countries": _countries}


async def report(db: AsyncSession, user: User, kind: str, f: Filters, *, limit: int, offset: int) -> dict:
    """The `AgentReportOut` payload (spec §5.3)."""
    columns, items = await SUMMARIES[kind](db, user, f)
    return {
        "kind": kind,
        "title": REPORT_KINDS[kind].title,
        "scope": "own" if is_agent_staff(user) else "agency",
        "columns": [vars(column) for column in columns],
        "items": items,
        "totals": _totals(columns, items),
        "total": len(items),
        "limit": len(items),
        "offset": 0,
        "options": {},
        "as_of": datetime.now(UTC),
    }
