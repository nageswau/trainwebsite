"""AGN-020 -- the agency reports (DEC-SCOPE-067; docs/superpowers/specs/2026-10-03-agn-020-agency-reports-design.md §4-§5).

Read-only SQL over AGN-018's scope helpers, so a Master reads the agency and a staff member only their assigned students (G4) with
no new scope logic. Every report is `columns` + `items` (+ `totals` for the summaries): the JSON table and the CSV come from one
column list, so a CSV header cannot drift from the screen. Nothing here writes, locks or commits; the export route owns that."""

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement, and_, case, distinct, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.rbac import is_agent_staff
from app.models import AgentOrgMember, AgentStudent, Country, OverseasApplication, OverseasCourse, University, User, VisaCase
from app.services.agent_applications import OVERSEAS_APPLICATION_STAGES, WITHDRAWN, counts_as_offer, intake_end, stage_label, with_owner
from app.services.agent_dashboard import agency_applications, offer_clause
from app.services.agent_orgs import org_member_ids
from app.services.agent_students import student_scope

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
    intake_texts: list[str] | None = None  # the raw intake texts in scope that fold to the requested intake key
    status: str | None = None
    echo: dict[str, str] = field(default_factory=dict)  # the validated values as sent: audit metadata (§5.5) and nothing else


def intake_key(text: str | None) -> tuple[str, str]:
    """R4: `YYYY-MM` and its label ("Sep 2027") via the AGN-013 parser, else the one Unstructured group."""
    end = intake_end(text)
    return (f"{end.year:04d}-{end.month:02d}", end.strftime("%b %Y")) if end else UNSTRUCTURED


def _intake_order(keys) -> list[str]:
    """Months ascending, Unstructured last."""
    return sorted(keys, key=lambda key: (key == UNSTRUCTURED[0], key))


async def _intake_texts(db: AsyncSession, user: User) -> list[str]:
    """The distinct raw intake texts of the caller's applications (few per agency)."""
    return list(await db.scalars(select(distinct(OverseasApplication.intake)).where(*agency_applications(user))))


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
    given: dict[str, str] = {param: value for param, value in raw.items() if value}
    for param, value in given.items():
        if param not in offered or (param == "member" and is_agent_staff(user)):
            raise ReportInputError(param, "This filter is not available for this report")
        if len(value) > MAX_VALUE:
            raise ReportInputError(param, f"{param} is too long (at most {MAX_VALUE} characters)")

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
        f.intake_texts = [text for text in await _intake_texts(db, user) if intake_key(text)[0] == intake]

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
ZERO_COUNTS = {column.key: 0 for column in STAGE_COLUMNS}


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
    assignee of the agency's record for that login. The current assignee, as AGN-018 (spec §4.3). The record table is aliased: the
    list queries outer-join `agent_students` themselves (`with_owner`), and an unaliased subquery would be correlated away."""
    record = aliased(AgentStudent)
    by_record = select(record.assigned_member_id).where(record.id == OverseasApplication.agent_student_id).scalar_subquery()
    by_login = (
        select(record.assigned_member_id)
        .where(record.student_id == OverseasApplication.student_id, record.agent_id.in_(org_member_ids(user)))
        .order_by(record.created_at)
        .limit(1)
        .scalar_subquery()
    )
    return case((OverseasApplication.agent_student_id.is_not(None), by_record), else_=by_login)


def _member_is(expression, f: Filters) -> list[ColumnElement[bool]]:
    if f.member is None:
        return []
    return [expression.is_(None) if f.member == "unassigned" else expression == f.member]


def _application_where(user: User, f: Filters, *, dated: bool = True) -> list[ColumnElement[bool]]:
    """The caller's applications (scope + School-bridged rows out, A12) narrowed by the shared filters. Needs University joined.
    `dated=False`: the caller applies its own date basis (enrollments, R6)."""
    where = [*agency_applications(user), *_member_is(_assignee(user), f)]
    if dated:
        where += _created_between(OverseasApplication.created_at, f)
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


async def _universities(db: AsyncSession, user: User, f: Filters) -> tuple[tuple[Column, ...], list[dict]]:
    stmt = _summary_stmt(user, f, University.name, Country.name.label("country")).group_by(University.id, University.name, Country.name)
    items = [{"university": row.name, "country": row.country, **_counted(row)} for row in (await db.execute(stmt)).all()]
    items.sort(key=lambda item: (-item["applications"], item["university"], item["country"]))
    return (Column("university", "University"), Column("country", "Country"), *STAGE_COLUMNS), items


async def _intakes(db: AsyncSession, user: User, f: Filters) -> tuple[tuple[Column, ...], list[dict]]:
    """R4: SQL counts per raw intake text; Python folds the texts into months (the distinct texts per agency are few)."""
    stmt = _summary_stmt(user, f, OverseasApplication.intake).group_by(OverseasApplication.intake)
    folded: dict[str, dict] = {}
    for row in (await db.execute(stmt)).all():
        key, label = intake_key(row.intake)
        group = folded.setdefault(key, {"intake": label, **ZERO_COUNTS})
        for name, value in _counted(row).items():
            group[name] += value
    return (Column("intake", "Intake"), *STAGE_COLUMNS), [folded[key] for key in _intake_order(folded)]


async def _staff(db: AsyncSession, user: User, f: Filters) -> tuple[tuple[Column, ...], list[dict]]:
    """Master only. Per member: active students assigned (created in range) and the stage counts of the applications counting for
    them (`_assignee`), plus Unassigned. Active staff are always listed; anyone else only with something to show (spec §4.3)."""
    assignee = _assignee(user).label("member_id")
    counted = {row.member_id: _counted(row) for row in (await db.execute(_summary_stmt(user, f, assignee).group_by(assignee))).all()}
    students_stmt = (
        select(AgentStudent.assigned_member_id, func.count())
        .where(*student_scope(user), AgentStudent.status == "active", *_created_between(AgentStudent.created_at, f))
        .group_by(AgentStudent.assigned_member_id)
    )
    students = dict((await db.execute(students_stmt)).all())
    members = await db.execute(
        select(AgentOrgMember, User.full_name)
        .join(User, User.id == AgentOrgMember.user_id)
        .where(AgentOrgMember.org_id == user.agent_membership.org_id)
        .order_by(AgentOrgMember.role.desc(), AgentOrgMember.seq)  # staff first, then any Master holding students
    )
    items = []
    for member, name in members.all():
        row = {"students": students.get(member.id, 0), **counted.get(member.id, ZERO_COUNTS)}
        listed = member.role == "staff" and member.status == "active"
        if listed or any(row.values()):
            label = f"{member.code} {name}" + ("" if member.status == "active" else " (deactivated)")
            items.append({"member": label, **row})
    unassigned = {"students": students.get(None, 0), **counted.get(None, ZERO_COUNTS)}
    if items or any(unassigned.values()):  # QA20-04: an agency with no staff and nothing unassigned has no rows (the empty state)
        items.append({"member": "Unassigned", **unassigned})
    return (Column("member", "Staff member"), Column("students", "Students", True), *STAGE_COLUMNS), items


SUMMARIES = {"countries": _countries, "universities": _universities, "intakes": _intakes, "staff": _staff}


# --- List reports (spec §4.2): one row per record, a page at a time ---

VISA_LABELS = {None: "None", 1: "In progress", 2: "Withdrawn", 3: "Refused", 4: "Approved"}  # the furthest outcome of any case


def _day_of(value: datetime | None) -> str | None:
    return value.astimezone(UTC).date().isoformat() if value else None


async def _page(db: AsyncSession, stmt, limit: int, offset: int) -> tuple[list, int]:
    """The page and its total from ONE statement (`count(*) OVER ()`), so they cannot disagree. Only a page past the end, which has
    no row to carry the total, costs a second count."""
    rows = list((await db.execute(stmt.add_columns(func.count().over()).limit(limit).offset(offset))).all())
    if rows:
        return rows, int(rows[0][-1])
    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) if offset else 0
    return [], int(total or 0)


STUDENT_COLUMNS = (
    Column("name", "Name"), Column("assigned_staff", "Assigned staff"), Column("preferred_country", "Preferred country"),
    Column("preferred_intake", "Preferred intake"), Column("status", "Status"), Column("created", "Created"),
    Column("applications", "Applications", True),
)


async def _students(db: AsyncSession, user: User, f: Filters, limit: int, offset: int) -> tuple[tuple[Column, ...], list[dict], int]:
    staff_user = aliased(User)
    applications = (
        select(func.count())
        .select_from(OverseasApplication)
        .where(
            or_(
                OverseasApplication.agent_student_id == AgentStudent.id,
                and_(OverseasApplication.agent_student_id.is_(None), AgentStudent.student_id.is_not(None), OverseasApplication.student_id == AgentStudent.student_id),
            ),
            OverseasApplication.agent_id.in_(org_member_ids(user)),
            OverseasApplication.school_student_id.is_(None),
            OverseasApplication.status != WITHDRAWN,
        )
        .correlate(AgentStudent)
        .scalar_subquery()
    )
    stmt = (
        select(AgentStudent, func.coalesce(User.full_name, AgentStudent.full_name), AgentOrgMember.code, staff_user.full_name, applications)
        .outerjoin(User, User.id == AgentStudent.student_id)
        .outerjoin(AgentOrgMember, AgentOrgMember.id == AgentStudent.assigned_member_id)
        .outerjoin(staff_user, staff_user.id == AgentOrgMember.user_id)
        .where(*student_scope(user), *_created_between(AgentStudent.created_at, f), *_member_is(AgentStudent.assigned_member_id, f))
        .order_by(AgentStudent.created_at.desc(), AgentStudent.id.desc())
    )
    if f.status != "all":
        stmt = stmt.where(AgentStudent.status == (f.status or "active"))
    if f.student_country:
        stmt = stmt.where(func.lower(func.trim(AgentStudent.preferred_country)) == f.student_country)  # equality, never LIKE
    rows, total = await _page(db, stmt, limit, offset)
    items = [
        {
            "name": name or "—", "assigned_staff": f"{code} {staff_name}" if code else "Unassigned", "preferred_country": record.preferred_country,
            "preferred_intake": record.preferred_intake, "status": record.status.capitalize(), "created": _day_of(record.created_at), "applications": int(count),
        }
        for record, name, code, staff_name, count, _ in rows
    ]
    return STUDENT_COLUMNS, items, total


def _application_stmt(user: User, f: Filters, *where, dated: bool = True):
    """Applications with their place, course and owner. `with_owner` (AGN-008) adds the owner as outer joins -- a student with no
    login is listed -- and keeps School-bridged rows out; its two columns come last before the window total."""
    visa = (
        select(func.max(case((VisaCase.decision == "approved", 4), (VisaCase.decision == "refused", 3), (VisaCase.decision == "withdrawn", 2), else_=1)))
        .where(VisaCase.application_id == OverseasApplication.id)
        .scalar_subquery()
    )
    stmt = (
        select(OverseasApplication, University.name, Country.name, OverseasCourse.title, visa)
        .join(University, University.id == OverseasApplication.university_id)
        .join(Country, Country.id == University.country_id)
        .outerjoin(OverseasCourse, OverseasCourse.id == OverseasApplication.course_id)
        .where(*_application_where(user, f, dated=dated), *where)
    )
    return with_owner(stmt)


APPLICATION_COLUMNS = (
    Column("student", "Student"), Column("university", "University"), Column("country", "Country"), Column("course", "Course"),
    Column("intake", "Intake"), Column("application_ref", "Application ref"), Column("stage", "Stage"), Column("submitted", "Submitted"),
    Column("offer", "Offer"), Column("visa", "Visa"), Column("created", "Created"),
)


async def _applications(db: AsyncSession, user: User, f: Filters, limit: int, offset: int) -> tuple[tuple[Column, ...], list[dict], int]:
    stmt = _application_stmt(user, f).order_by(OverseasApplication.created_at.desc(), OverseasApplication.id.desc())
    rows, total = await _page(db, stmt, limit, offset)
    items = [
        {
            "student": name or "—", "university": university, "country": country, "course": course, "intake": app.intake,
            "application_ref": app.application_reference, "stage": stage_label(app.status),
            "submitted": app.submitted_on.isoformat() if app.submitted_on else None, "offer": "Yes" if counts_as_offer(app) else "No",
            "visa": VISA_LABELS[visa], "created": _day_of(app.created_at),
        }
        for app, university, country, course, visa, _account, name, _ in rows
    ]
    return APPLICATION_COLUMNS, items, total


ENROLLMENT_COLUMNS = (
    Column("student", "Student"), Column("university", "University"), Column("country", "Country"), Column("course", "Course"),
    Column("intake", "Intake"), Column("enrollment_date", "Enrollment date"), Column("university_student_id", "University student ID"),
)


async def _enrollments(db: AsyncSession, user: User, f: Filters, limit: int, offset: int) -> tuple[tuple[Column, ...], list[dict], int]:
    """R6: dated by `enrollment_date` (a calendar date, inclusive both ends); an undated legacy enrollment shows only undated."""
    dates = [OverseasApplication.enrollment_date >= f.start] if f.start else []
    dates += [OverseasApplication.enrollment_date <= f.end] if f.end else []
    stmt = _application_stmt(user, f, OverseasApplication.status == "enrolled", *dates, dated=False)
    stmt = stmt.order_by(OverseasApplication.enrollment_date.desc().nulls_last(), OverseasApplication.id.desc())
    rows, total = await _page(db, stmt, limit, offset)
    items = [
        {
            "student": name or "—", "university": university, "country": country, "course": course, "intake": app.intake,
            "enrollment_date": app.enrollment_date.isoformat() if app.enrollment_date else None, "university_student_id": app.university_student_id,
        }
        for app, university, country, course, _visa, _account, name, _ in rows
    ]
    return ENROLLMENT_COLUMNS, items, total


LISTS = {"students": _students, "applications": _applications, "enrollments": _enrollments}


# --- Filter options (spec §5.2, §7.1): built from the caller's own scope, so they reveal nothing outside it ---


async def _options(db: AsyncSession, user: User, kind: str) -> dict[str, list[dict[str, str]]]:
    offered, options = REPORT_KINDS[kind].filters, {}
    if "member" in offered and not is_agent_staff(user):
        staff = await db.execute(
            select(AgentOrgMember.code, User.full_name)
            .join(User, User.id == AgentOrgMember.user_id)
            .where(AgentOrgMember.org_id == user.agent_membership.org_id, AgentOrgMember.role == "staff")
            .order_by(AgentOrgMember.seq)
        )
        options["members"] = [{"value": code, "label": f"{code} {name}"} for code, name in staff.all()] + [{"value": "unassigned", "label": "Unassigned"}]
    if "country" in offered and kind == "students":
        text = func.trim(AgentStudent.preferred_country)
        texts: list[str] = list(await db.scalars(select(distinct(text)).where(*student_scope(user), AgentStudent.preferred_country.is_not(None), text != "").order_by(text)))
        options["countries"] = [{"value": value, "label": value} for value in texts]
    universities_in_scope = select(OverseasApplication.university_id).where(*agency_applications(user))
    if "country" in offered and kind != "students":
        countries = await db.execute(
            select(Country.slug, Country.name)
            .where(Country.id.in_(select(University.country_id).where(University.id.in_(universities_in_scope))))
            .order_by(Country.name, Country.slug)
        )
        options["countries"] = [{"value": slug, "label": name} for slug, name in countries.all()]
    if "university" in offered:
        universities = await db.execute(
            select(University.slug, University.name).where(University.id.in_(universities_in_scope)).order_by(University.name, University.slug)
        )
        options["universities"] = [{"value": slug, "label": name} for slug, name in universities.all()]
    if "intake" in offered:
        labels = dict(intake_key(text) for text in await _intake_texts(db, user))
        options["intakes"] = [{"value": key, "label": labels[key]} for key in _intake_order(labels)]
    if "status" in offered:
        statuses = STUDENT_STATUSES if kind == "students" else APPLICATION_STATUSES
        options["statuses"] = [{"value": status, "label": stage_label(status)} for status in statuses]
    return options


async def report(db: AsyncSession, user: User, kind: str, f: Filters, *, limit: int, offset: int) -> dict:
    """The `AgentReportOut` payload (spec §5.3). A summary is every group plus a Total row; a list is one page."""
    if REPORT_KINDS[kind].summary:
        columns, items = await SUMMARIES[kind](db, user, f)
        totals, total, limit, offset = _totals(columns, items), len(items), len(items), 0
    else:
        columns, items, total = await LISTS[kind](db, user, f, limit, offset)
        totals = None
    return {
        "kind": kind,
        "title": REPORT_KINDS[kind].title,
        "scope": "own" if is_agent_staff(user) else "agency",
        "columns": [vars(column) for column in columns],
        "items": items,
        "totals": totals,
        "total": total,
        "limit": limit,
        "offset": offset,
        "options": await _options(db, user, kind),
        "as_of": datetime.now(UTC),
    }
