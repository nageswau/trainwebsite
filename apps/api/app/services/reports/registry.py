"""nehn-009 (DEC-SCOPE-303): the report registry and the standard filter model.

A report is declared once -- id, title, the catalogue resource whose `view`/`download` grants gate it (nehn-005), its columns with their
sensitivity class (nehn-008), the standard filters it supports, a `query` that returns its rows already scoped to the caller, filtered and
in its default order, and `options` (the filter pickers, within the same scope). `api/reports.py` serves every registered report the
same way, so the JSON, the CSV and the xlsx of one filter hold the same rows and columns.

Filters are plain strings validated here, after authorization. A parameter the report does not declare -- a standard filter it does not
support or any other name -- is refused (422), as is a repeated one; an empty value counts as not given (a GET form sends empty fields).
Dates are calendar days and both ends are inclusive; the stored columns are `date`s, so there is no time-zone arithmetic."""

import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rbac
from app.models import User

STANDARD = ("from", "to", "course_id", "batch_id", "trainer_id", "recruiter_id", "student", "status", "latest", "completion_from", "completion_to", "attendance_below")
PAGING = ("page", "page_size")
LABELS = {
    "from": "From", "to": "To", "course_id": "Course", "batch_id": "Batch", "trainer_id": "Trainer", "recruiter_id": "Recruiter",
    "student": "Student", "status": "Status", "latest": "Latest", "completion_from": "Completion from", "completion_to": "Completion to",
    "attendance_below": "Attendance below %", "page": "Page", "page_size": "Rows per page",
}
DATES = {"from": "date_from", "to": "date_to", "completion_from": "completion_from", "completion_to": "completion_to"}
IDS = ("course_id", "batch_id", "trainer_id", "recruiter_id")
ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
MAX_LATEST = 1000
PAGE_SIZE, MAX_PAGE_SIZE = 50, 200
EXPORT_CAP = 10_000  # a download over this is refused, never cut short (builder's default, NEEDS_CONFIRMATION)
MAX_STUDENT, MAX_STATUS = 100, 30


class ReportInputError(Exception):
    """A refused input; the message names the form's field, as the page shows it (the 422 detail)."""


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    cls: str | None = None  # nehn-008 sensitivity class; a tagged column needs `field.<cls>.view`


@dataclass(frozen=True)
class Filters:
    date_from: date | None = None
    date_to: date | None = None
    course_id: UUID | None = None
    batch_id: UUID | None = None
    trainer_id: UUID | None = None
    recruiter_id: UUID | None = None
    student: str | None = None
    status: str | None = None
    latest: int | None = None
    completion_from: date | None = None
    completion_to: date | None = None
    attendance_below: int | None = None  # nehn-011 (DEC-SCOPE-311): seats on the course whose attendance % is below it
    given: dict[str, str] = field(default_factory=dict)  # the filters the caller set, as sent (the audit row records them)


@dataclass(frozen=True)
class Report:
    id: str
    title: str
    description: str
    resource: str
    columns: tuple[Column, ...]
    filters: tuple[str, ...]
    query: Callable[[User, Filters], Select]
    options: Callable[[AsyncSession, User], Awaitable[dict]]

    @property
    def classes(self) -> dict[str, str]:
        return {c.key: c.cls for c in self.columns if c.cls}


REPORTS: dict[str, Report] = {}


def register(report: Report) -> Report:
    """Add a report. A duplicate id, a filter outside the standard set or a resource without view+download fails at import."""
    if report.id in REPORTS:
        raise ValueError(f"Report already registered: {report.id}")
    if unknown := set(report.filters) - set(STANDARD):
        raise ValueError(f"Unknown filters for {report.id}: {sorted(unknown)}")
    if not {"view", "download"} <= set(rbac.CATALOGUE.get(report.resource, {}).get("actions", ())):
        raise ValueError(f"Unknown resource for {report.id}: {report.resource}")
    REPORTS[report.id] = report
    return report


def _date(name: str, value: str) -> date:
    try:
        if ISO_DAY.fullmatch(value):
            return date.fromisoformat(value)
    except ValueError:
        pass
    raise ReportInputError(f"Enter {LABELS[name]} as a date (YYYY-MM-DD)")


def _whole(name: str, value: str, low: int, high: int | None) -> int:
    number = int(value) if value.isdigit() else 0
    if number < low or (high is not None and number > high):
        span = f"from {low}" + (f" to {high:,}" if high is not None else "")
        raise ReportInputError(f"{LABELS[name]} must be a whole number {span}")
    return number


def parse(report: Report, params: Iterable[tuple[str, str]]) -> tuple[Filters, int, int]:
    """(filters, page, page_size) from the query string's (name, value) pairs. Paging is accepted (and ignored) on downloads too."""
    allowed = set(report.filters) | set(PAGING)
    raw: dict[str, str] = {}
    seen: set[str] = set()
    for name, value in params:
        if name not in allowed:
            raise ReportInputError(f"This report can't be filtered by {LABELS.get(name, name[:40])}")
        if name in seen:
            raise ReportInputError(f"Give {LABELS[name]} once")
        seen.add(name)
        if value.strip():
            raw[name] = value.strip()
    values: dict = {}
    for name, value in raw.items():
        if name in DATES:
            values[DATES[name]] = _date(name, value)
        elif name in IDS:
            try:
                values[name] = UUID(value)
            except ValueError:
                raise ReportInputError(f"Choose a {LABELS[name].lower()} from the list") from None
        elif name == "student":
            if len(value) > MAX_STUDENT:
                raise ReportInputError(f"Search for a student with at most {MAX_STUDENT} characters")
            values[name] = value
        elif name == "status":
            if len(value) > MAX_STATUS:
                raise ReportInputError("Choose a status from the list")
            values[name] = value
        elif name == "latest":
            values[name] = _whole(name, value, 1, MAX_LATEST)
        elif name == "attendance_below":
            values[name] = _whole(name, value, 1, 100)
    for start, end in (("date_from", "date_to"), ("completion_from", "completion_to")):
        if values.get(start) and values.get(end) and values[start] > values[end]:
            first, last = (LABELS[k] for k, v in DATES.items() if v in (start, end))
            raise ReportInputError(f"'{first}' must be on or before '{last}'")
    page = _whole("page", raw["page"], 1, None) if "page" in raw else 1
    size = _whole("page_size", raw["page_size"], 1, MAX_PAGE_SIZE) if "page_size" in raw else PAGE_SIZE
    given = {name: value for name, value in raw.items() if name not in PAGING}
    return Filters(**values, given=given), page, size
