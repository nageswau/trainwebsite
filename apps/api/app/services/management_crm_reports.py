"""ccrm-034 (DEC-SCOPE-267, R1-R10; source PDF §13, AC 8): the management CRM reports -- application ageing, university performance,
visa outcomes, document readiness, lead conversion by intake and the forecast by intake. Every report counts applications and the students
behind them separately (R3) and carries its definitions. Each report is one grouped SELECT plus one for its total (students are distinct
people, so a total is never the sum of its rows). Read-only; only counts and organisation, place, intake and stage names leave."""

from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import ColumnElement, Date, Integer, Select, and_, case, cast, distinct, exists, func, literal, or_, select, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession

from app.application_checklists import COMPLETE
from app.application_outcome import TERMINAL
from app.application_sub_status import SUB_STATUSES
from app.application_sub_status import label as sub_status_label
from app.models import (
    ApplicationChecklist,
    ApplicationChecklistItem,
    ApplicationChecklistItemDocument,
    ApplicationOffer,
    Country,
    Enquiry,
    LeadQualification,
    OverseasApplication,
    StudentDocument,
    University,
    User,
    VisaCase,
)
from app.services import application_filters, management_metrics
from app.services.agent_applications import OVERSEAS_APPLICATION_STAGES, WITHDRAWN, stage_label

A = OverseasApplication
NOT_SET = "Not set"
NOT_RECORDED = "Not recorded"
# R3 (mgmt-003 MS4): one person per agency student, school student or user, in that order.
PERSON = func.coalesce(A.agent_student_id, A.school_student_id, A.student_id)
STUDENTS = func.count(distinct(PERSON))
# R4: neither withdrawn nor enrolled, and no terminal outcome (on hold and deferred stay open).
OPEN = and_(A.status.not_in((WITHDRAWN, "enrolled")), or_(A.outcome.is_(None), A.outcome.not_in(TERMINAL)))
CONFIRMED = A.enrollment_confirmed_at.is_not(None)  # ccrm-027 E4
OFFER = management_metrics.FUNNEL_COUNTS["offer"]  # mgmt-024 MF6, the funnel's own predicate
PRE_OFFER = OVERSEAS_APPLICATION_STAGES[: OVERSEAS_APPLICATION_STAGES.index("offer")]
POST_OFFER = OVERSEAS_APPLICATION_STAGES[OVERSEAS_APPLICATION_STAGES.index("offer") : OVERSEAS_APPLICATION_STAGES.index("enrolled")]
SUBMITTED_SUBS = ("submitted", "under_review")
VISA_PENDING = ("submitted", "additional_info_requested", "decision_pending")
VISA_SUBMITTED = (*VISA_PENDING, "approved", "refused")
# R5: (key, the band's last day); the last band is open-ended.
BANDS = (("d0_7", 7), ("d8_14", 14), ("d15_30", 30), ("d31_60", 60), ("d61_plus", None))

APPLICATIONS = ("applications", "Applications", "Applications created in the period that match the filters.")
STUDENTS_DEF = ("students", "Students", "The distinct students behind those applications — one person may have several applications.")
DEFINITIONS: dict[str, tuple[tuple[str, str, str], ...]] = {
    "ageing": (
        ("applications", "Applications", "Open applications: not withdrawn, not enrolled and with no closing outcome. On hold and deferred are open."),
        STUDENTS_DEF,
        ("days", "Days since last update", "Today (India time) minus the date the application was last changed."),
        ("oldest_days", "Oldest", "The most days any application in the row has gone without an update."),
    ),
    "universities": (
        APPLICATIONS, STUDENTS_DEF,
        ("offers", "Offers", "Applications that reached the Offer stage or have an offer recorded — the applications funnel's Offer."),
        ("offer_rate", "Offer rate", "Offers as a share of applications."),
        ("rejections", "Rejections", "Applications with the Rejected outcome."),
        ("acceptances", "Acceptances", "Applications with an offer the student accepted."),
        ("enrollments", "Enrolments", "Applications with the enrolment confirmed."),
    ),
    "visa": (
        ("applications", "Visa cases", "Applications in the period that have a visa case, by destination country."),
        STUDENTS_DEF,
        ("submitted", "Submitted", "Visa cases that reached Submitted: pending, approved or refused."),
        ("pending", "Pending", "Submitted, additional information requested or decision pending."),
        ("approved", "Approved", "Visa approved."),
        ("refused", "Refused", "Visa refused."),
        ("enrolled", "Enrolled", "Visa approved and the enrolment confirmed."),
    ),
    "readiness": (
        ("applications", "Applications", "Open applications not yet submitted: before the Offer stage, no submitted date, not Submitted or Under review."),
        STUDENTS_DEF,
        ("ready", "Ready", "A checklist with every required document complete (verified, approved or not required)."),
        ("blocked", "Blocked", "Required documents incomplete and the checklist blocks Ready for Submission."),
        ("needs_override", "Needs override", "Required documents incomplete; the counselor can continue only with a recorded reason."),
        ("no_checklist", "No checklist", "No document checklist has been made for the application yet."),
    ),
    "leads": (
        ("leads", "Leads", "Overseas leads created in the period, by the intake on their qualification. University and course filters do not apply."),
        ("converted", "Converted", "Of those leads, the ones converted to a student now."),
        ("conversion_pct", "Conversion %", "Converted as a share of leads."),
        ("students", "Students", "The distinct students those leads became."),
        ("applications", "Applications", "Every application of those students, any intake."),
    ),
    "forecast": (
        APPLICATIONS, STUDENTS_DEF,
        ("confirmed", "Confirmed", "Applications with the enrolment confirmed."),
        ("expected", "Expected", "Open applications with the visa approved, not yet enrolled."),
        ("possible", "Possible", "Open applications at the Offer stage or later without a visa approval."),
        ("lost", "Lost", "Withdrawn applications and applications with a closing outcome."),
        ("forecast", "Forecast", "Confirmed plus expected. A rule, not a prediction: nothing is weighted by probability."),
    ),
}  # fmt: skip


@dataclass(frozen=True)
class ReportFilters:
    """R2: every filter optional, ANDed. `counselor` is an id or "none"."""

    date_from: date | None = None
    date_to: date | None = None
    counselor: UUID | str | None = None
    country: UUID | None = None
    university: UUID | None = None
    course: UUID | None = None
    intake: str | None = None


def _scoped(stmt: Select, f: ReportFilters) -> Select:
    narrowed = application_filters.ApplicationFilters(counselor=f.counselor, country=f.country, university=f.university, intake=f.intake)
    stmt = application_filters.apply(stmt, narrowed).where(*_created(A.created_at, f))
    return stmt.where(A.course_id == f.course) if f.course else stmt


def _created(column, f: ReportFilters) -> list:
    """R2: the inclusive IST dates, as the applications funnel reads them (mgmt-024)."""
    clauses = [column >= management_metrics._ist_start(f.date_from)] if f.date_from else []
    return clauses + ([column < management_metrics._ist_start(f.date_to + timedelta(days=1))] if f.date_to else [])


async def _report(db: AsyncSession, f: ReportFilters, keys: list, measures: dict[str, ColumnElement], *where, joins=()) -> tuple[list[dict], dict]:
    """The grouped rows and the total row of `measures` over the filtered applications (with `joins`), one SELECT each."""

    def stmt(*cols) -> Select:
        s = select(*cols, *(m.label(k) for k, m in measures.items())).select_from(A)
        for target, on, outer in joins:
            s = s.join(target, on, isouter=outer)
        return _scoped(s.where(*where), f)

    rows = [dict(r._mapping) for r in await db.execute(stmt(*keys).group_by(*keys))]
    return rows, dict((await db.execute(stmt())).one()._mapping)


def _days(today: date) -> ColumnElement:
    return type_coerce(literal(today, Date) - cast(func.timezone("Asia/Kolkata", A.updated_at), Date), Integer)


def _sub_order(stage: str, sub_status: str | None) -> int:
    subs = SUB_STATUSES.get(stage, ())
    return -1 if sub_status is None else subs.index(sub_status) if sub_status in subs else len(subs)


def _stage_order(stage: str) -> int:
    return OVERSEAS_APPLICATION_STAGES.index(stage) if stage in OVERSEAS_APPLICATION_STAGES else len(OVERSEAS_APPLICATION_STAGES)


async def _ageing(db: AsyncSession, f: ReportFilters, today: date) -> dict:
    days = _days(today)
    bands, low = {}, None
    for key, high in BANDS:
        bands[key] = func.count().filter(days > low if high is None else days <= high if low is None else and_(days > low, days <= high))
        low = high
    measures = {"applications": func.count(), "students": STUDENTS, **bands, "oldest_days": func.max(days)}
    rows, total = await _report(db, f, [A.status.label("stage"), A.sub_status.label("sub_status")], measures, OPEN)

    def shape(r: dict) -> dict:
        return {"applications": r["applications"], "students": r["students"], "bands": {k: r[k] for k, _ in BANDS}, "oldest_days": r["oldest_days"]}

    rows.sort(key=lambda r: (_stage_order(r["stage"]), r["stage"], _sub_order(r["stage"], r["sub_status"])))
    out = [{"stage": r["stage"], "stage_label": stage_label(r["stage"]), "sub_status": r["sub_status"], "sub_status_label": sub_status_label(r["sub_status"]) or NOT_SET, **shape(r)} for r in rows]
    return {"rows": out, "total": shape(total)}


def _rate(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


async def _universities(db: AsyncSession, f: ReportFilters) -> dict:
    accepted = exists().where(ApplicationOffer.application_id == A.id, ApplicationOffer.decision == "accepted")
    measures = {
        "applications": func.count(), "students": STUDENTS, "offers": func.count().filter(OFFER), "rejections": func.count().filter(A.outcome == "rejected"),
        "acceptances": func.count().filter(accepted), "enrollments": func.count().filter(CONFIRMED),
    }  # fmt: skip
    keys = [University.id.label("university_id"), University.name.label("label")]
    rows, total = await _report(db, f, keys, measures, joins=[(University, University.id == A.university_id, False)])
    for r in (*rows, total):
        r["offer_rate"] = _rate(r["offers"], r["applications"])
    rows.sort(key=lambda r: (-r["applications"], r["label"].lower(), str(r["university_id"])))
    return {"rows": rows, "total": total}


async def _visa(db: AsyncSession, f: ReportFilters) -> dict:
    status = VisaCase.visa_status
    measures = {
        "applications": func.count(), "students": STUDENTS, "submitted": func.count().filter(status.in_(VISA_SUBMITTED)),
        "pending": func.count().filter(status.in_(VISA_PENDING)), "approved": func.count().filter(status == "approved"),
        "refused": func.count().filter(status == "refused"), "enrolled": func.count().filter(status == "approved", CONFIRMED),
    }  # fmt: skip
    joins = [(VisaCase, VisaCase.application_id == A.id, False), (University, University.id == A.university_id, False), (Country, Country.id == University.country_id, False)]
    rows, total = await _report(db, f, [Country.id.label("country_id"), Country.name.label("label")], measures, joins=joins)
    rows.sort(key=lambda r: (-r["applications"], r["label"].lower(), str(r["country_id"])))
    return {"rows": rows, "total": total}


def _incomplete_required() -> ColumnElement:
    """ccrm-019 AC1 in SQL: a required item is complete when marked Not required, or unmarked with a current linked document that is
    verified or approved (`application_checklists.item_status` + `COMPLETE`)."""
    item, link = ApplicationChecklistItem, ApplicationChecklistItemDocument
    complete_document = exists().where(link.item_id == item.id, StudentDocument.id == link.document_id, StudentDocument.archived_at.is_(None), StudentDocument.verification_status.in_(COMPLETE))
    # Written without negating a nullable comparison: NOT (NULL) is NULL, which would drop an unmarked item.
    marked_incomplete = and_(item.mark.is_not(None), item.mark.not_in(COMPLETE))
    unmarked_incomplete = and_(item.mark.is_(None), ~complete_document)
    return exists().where(item.application_id == A.id, item.required.is_(True), or_(marked_incomplete, unmarked_incomplete))


async def _readiness(db: AsyncSession, f: ReportFilters) -> dict:
    checklist, incomplete = ApplicationChecklist, _incomplete_required()
    has = checklist.application_id.is_not(None)
    measures = {
        "applications": func.count(), "students": STUDENTS, "ready": func.count().filter(has, ~incomplete),
        "blocked": func.count().filter(checklist.gate_mode == "block", incomplete), "needs_override": func.count().filter(checklist.gate_mode == "warn", incomplete),
        "no_checklist": func.count().filter(~has),
    }  # fmt: skip
    pre_submission = (OPEN, A.status.in_(PRE_OFFER), A.submitted_on.is_(None), or_(A.sub_status.is_(None), A.sub_status.not_in(SUBMITTED_SUBS)))
    joins = [(checklist, checklist.application_id == A.id, True)]
    rows, total = await _report(db, f, [A.status.label("stage")], measures, *pre_submission, joins=joins)
    rows.sort(key=lambda r: _stage_order(r["stage"]))
    return {"rows": [{**r, "stage_label": stage_label(r["stage"])} for r in rows], "total": total}


def _intake_label(r: dict) -> dict:
    return {**r, "label": r["intake"] or NOT_RECORDED}


def _by_intake(rows: list[dict]) -> list[dict]:
    return sorted((_intake_label(r) for r in rows), key=lambda r: (r["intake"] is None, (r["intake"] or "").lower()))


async def _forecast(db: AsyncSession, f: ReportFilters) -> dict:
    approved = or_(A.sub_status.is_not_distinct_from("visa_approved"), exists().where(VisaCase.application_id == A.id, VisaCase.visa_status == "approved"))
    expected = and_(OPEN, ~CONFIRMED, approved)
    measures = {
        "applications": func.count(), "students": STUDENTS, "confirmed": func.count().filter(CONFIRMED), "expected": func.count().filter(expected),
        "possible": func.count().filter(OPEN, A.status.in_(POST_OFFER), ~approved), "lost": func.count().filter(or_(A.status == WITHDRAWN, A.outcome.in_(TERMINAL))),
    }  # fmt: skip
    rows, total = await _report(db, f, [func.nullif(func.trim(A.intake), "").label("intake")], measures)
    for r in (*rows, total):
        r["forecast"] = r["confirmed"] + r["expected"]
    return {"rows": _by_intake(rows), "total": total}


async def _leads(db: AsyncSession, f: ReportFilters) -> dict:
    """R9: overseas leads by their qualification intake. The counselor is the lead's owner; destination its preferred country."""
    converted = Enquiry.status == "converted"
    their_applications = select(func.count()).where(A.student_id == Enquiry.converted_user_id).correlate(Enquiry).scalar_subquery()
    measures = {
        "leads": func.count(), "converted": func.count().filter(converted), "students": func.count(distinct(Enquiry.converted_user_id)).filter(converted),
        "applications": func.coalesce(func.sum(case((converted, their_applications), else_=0)), 0),
    }  # fmt: skip
    where = [Enquiry.division == "overseas", *_created(Enquiry.created_at, f)]
    if f.counselor == "none":
        where.append(~exists().where(User.id == Enquiry.owner_id, User.role == "counselor"))
    elif f.counselor is not None:
        where.append(Enquiry.owner_id == f.counselor)
    if f.country:
        where.append(LeadQualification.preferred_country_id == f.country)
    if f.intake:
        where.append(LeadQualification.intake == f.intake)
    intake = func.nullif(func.trim(LeadQualification.intake), "").label("intake")

    def stmt(*cols) -> Select:
        s = select(*cols, *(m.label(k) for k, m in measures.items())).select_from(Enquiry)
        return s.outerjoin(LeadQualification, LeadQualification.lead_id == Enquiry.id).where(*where)

    rows = [dict(r._mapping) for r in await db.execute(stmt(intake).group_by(intake))]
    total = dict((await db.execute(stmt())).one()._mapping)
    for r in (*rows, total):
        r["applications"] = int(r["applications"])
        r["conversion_pct"] = _rate(r["converted"], r["leads"])
    return {"rows": _by_intake(rows), "total": total}


async def _options(db: AsyncSession) -> dict[str, list[dict]]:
    """The funnel's own choices (mgmt-024 MF14) for the filters these reports take; intakes also those recorded on leads."""
    options = await management_metrics.application_options(db)
    lead_intakes = (await db.scalars(select(LeadQualification.intake).where(func.trim(LeadQualification.intake) != "").distinct())).all()
    # Browser QA-02: a blank intake is "Not recorded" in the reports, never a choice (it would read as "All").
    intakes = sorted({v for v in [o["value"] for o in options["intakes"]] + list(lead_intakes) if v.strip()}, key=str.lower)
    return {**{k: options[k] for k in ("counselors", "countries", "universities", "courses")}, "intakes": [{"value": i, "label": i} for i in intakes]}


async def reports(db: AsyncSession, f: ReportFilters, today: date) -> dict:
    """The six reports for the filters; `today` is the IST date the ageing counts from."""
    built = {
        "ageing": await _ageing(db, f, today), "universities": await _universities(db, f), "visa": await _visa(db, f),
        "readiness": await _readiness(db, f), "leads": await _leads(db, f), "forecast": await _forecast(db, f),
    }  # fmt: skip
    for key, report in built.items():
        report["definitions"] = [{"key": k, "label": label, "definition": text} for k, label, text in DEFINITIONS[key]]
    return {**built, "options": await _options(db)}
