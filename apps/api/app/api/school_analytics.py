"""ENH-016 -- School & Edusphere analytics dashboards (docs/superpowers/specs/2026-09-28-enh-016-analytics-dashboards-design.md).

Read-only aggregations for `School CRM.md` §1/§27/§28/§29/§34 and Part B §14. Two routers, like `school_feedback.py`, so
`schools.py` and `admin.py` do not grow. Every query filters on a *student scope* -- a `select` of student ids or a plain id
list -- and groups in SQL, so an endpoint runs the same number of queries for one school or for all of them (spec §10).
Nothing here writes: no add, flush or commit."""

from collections import defaultdict
from collections.abc import Collection
from datetime import UTC, date, datetime, timedelta
from statistics import mean
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import Select, func, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.portfolio import portfolio_completion
from app.api.school_feedback import _require_school_reader
from app.api.school_skills import _rollup
from app.api.schools import (
    OFFER_ONWARD_STATUSES,
    TIER_TIMEZONE,
    _cumulative_services,
    _entitlement_denial,
    _grade_level_from_label,
    _own_school_id,
    _percentage,
    _school_account_counts,
    _stage_at_or_after,
    _today_ist,
    internship_progress,
    service_usage,
)
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import (
    OverseasApplication,
    PortfolioEntry,
    PortfolioProfile,
    School,
    SchoolAcademicResult,
    SchoolActivity,
    SchoolActivityAttendance,
    SchoolCareerRecord,
    SchoolLanguageRecord,
    SchoolPsychometricRecord,
    SchoolSkillBatch,
    SchoolSkillEnrollment,
    SchoolStudent,
    SchoolTestPrepRecord,
    User,
    VisaCase,
)
from app.schemas import (
    ActivityProgressRow,
    AverageRow,
    CrossSchoolSummaryOut,
    GradeMetricRow,
    GradePerformanceOut,
    Headcounts,
    MetricCell,
    PerformerList,
    PerformerRow,
    SchoolCounts,
    SchoolUtilizationPage,
    SchoolUtilizationRow,
    ScorecardArea,
    ScorecardOut,
    ScorecardPage,
    ServiceTotals,
    StudentCounts,
    StudentDevelopmentOut,
    TrackedValue,
    counts_as_completed,
)

school_router = APIRouter(prefix="/school", tags=["school-analytics"])
admin_router = APIRouter(prefix="/overseas-admin", tags=["school-analytics"])
logger = get_logger("app.school.analytics")

Scope = Select | Collection[UUID]
BLANKS = " \t\r\n\f\v"  # what Python's str.strip() removes for ASCII -- ENH-012 treats a whitespace-only statement as empty


def students_in(school_ids: Collection[UUID]) -> Select:
    return select(SchoolStudent.id).where(SchoolStudent.school_id.in_(list(school_ids)))


def _has_statement(scope: Scope) -> Select:
    return select(PortfolioProfile.school_student_id).where(
        PortfolioProfile.school_student_id.in_(scope), func.length(func.btrim(PortfolioProfile.personal_statement, BLANKS)) > 0
    )


async def portfolio_sections(db: AsyncSession, scope: Scope) -> dict[UUID, set[str]]:
    rows = await db.execute(select(PortfolioEntry.school_student_id, PortfolioEntry.section).where(PortfolioEntry.school_student_id.in_(scope)).distinct())
    out: dict[UUID, set[str]] = defaultdict(set)
    for student_id, section in rows.tuples():
        out[student_id].add(section)
    return out


async def statement_ids(db: AsyncSession, scope: Scope) -> set[UUID]:
    return set((await db.scalars(_has_statement(scope))).all())


async def portfolio_started_ids(db: AsyncSession, scope: Scope) -> set[UUID]:
    """D11: at least one portfolio entry, or a non-blank personal statement. Profile fields alone never count. One query."""
    entries = select(PortfolioEntry.school_student_id).where(PortfolioEntry.school_student_id.in_(scope))
    return set((await db.scalars(union(entries, _has_statement(scope)))).all())


async def skill_statuses(db: AsyncSession, scope: Scope) -> dict[str, dict[UUID, list[str]]]:
    """Non-withdrawn ENH-011 enrolment statuses per module and student -- the input `school_skills._rollup` expects."""
    rows = await db.execute(
        select(SchoolSkillEnrollment.school_student_id, SchoolSkillBatch.module_type, SchoolSkillEnrollment.status)
        .join(SchoolSkillBatch, SchoolSkillBatch.id == SchoolSkillEnrollment.batch_id)
        .where(SchoolSkillEnrollment.school_student_id.in_(scope), SchoolSkillEnrollment.status != "withdrawn")
    )
    out: dict[str, dict[UUID, list[str]]] = {"soft_skills": defaultdict(list), "digital_skills": defaultdict(list)}
    for student_id, module, status in rows.tuples():
        out[module][student_id].append(status)
    return {module: dict(by_student) for module, by_student in out.items()}


# --- shared helpers --------------------------------------------------------------------------------------------------------

GRADE_COLUMNS = ["8", "9", "10", "11", "12"]
AWARENESS_ACTIVITY_TYPES = ("career_awareness_session", "career_seminar")


def grade_key(level: int | None, label: str | None) -> str:
    """`grade_level`, else the label fallback the dashboard already uses; a grade outside 8-12 is "other", none "unspecified"."""
    key = str(level) if level is not None else _grade_level_from_label(label)
    if key is None:
        return "unspecified"
    return key if key in GRADE_COLUMNS else "other"


def _ordered_grades(present: Collection[str]) -> list[str]:
    return [g for g in (*GRADE_COLUMNS, "other", "unspecified") if g in present]


def _pct(count: int, total: int) -> float | None:
    return round(count / total * 100, 1) if total else None


def _log_view(user: User, view: str, **fields) -> None:
    """One line per request -- ids and counts only, never names or marks (spec §12)."""
    logger.info("school_analytics_view", extra={"extra_fields": {"actor_id": str(user.id), "role": user.role, "view": view, **{k: str(v) for k, v in fields.items()}}})


async def _require_school_admin(user: User = Depends(get_current_user)) -> User:
    """D1: the existing cross-school pair only. Not `admin.ensure_admin`, which also admits `it_admin`."""
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    return user


async def student_indicators(db: AsyncSession, scope: Scope) -> dict[str, set[UUID]]:
    """Every spec §6.1 indicator as a set of student ids, in a fixed number of queries (one per source table). Statuses follow
    `_overview_payload` (SCH-007) and `school_skills._rollup` (ENH-011), so a student reads the same here as on their own page."""
    ind: dict[str, set[UUID]] = defaultdict(set)
    career = select(SchoolCareerRecord.school_student_id, SchoolCareerRecord.record_type, SchoolCareerRecord.status).where(SchoolCareerRecord.school_student_id.in_(scope)).distinct()
    for sid, record_type, status in (await db.execute(career)).tuples():
        ind["career_any"].add(sid)  # ENH-012's completion input counts any career record
        if not counts_as_completed(status):  # ENH-026 C5: a scheduled/not-started session is not delivered yet
            continue
        if record_type == "guidance_session":
            ind["guidance"].add(sid)
        elif record_type == "counselling_note":
            ind["counselling"].add(sid)
    internships = select(PortfolioEntry.school_student_id, PortfolioEntry.completion_status).where(PortfolioEntry.school_student_id.in_(scope), PortfolioEntry.section == "internship")
    internship_statuses: dict[UUID, list[str | None]] = defaultdict(list)
    for sid, status in (await db.execute(internships)).tuples():
        internship_statuses[sid].append(status)
    for sid, statuses in internship_statuses.items():
        ind["internship_any"].add(sid)  # ENH-021 I7: the dashboard KPI's definition
        progress = internship_progress(statuses)  # ENH-021 I8: best progress wins
        if progress == "completed":
            ind["internship_completed"].add(sid)
        elif progress == "in_progress":
            ind["internship_in_progress"].add(sid)
    psych = select(SchoolPsychometricRecord.school_student_id, SchoolPsychometricRecord.status).where(SchoolPsychometricRecord.school_student_id.in_(scope)).distinct()
    for sid, status in (await db.execute(psych)).tuples():
        ind["psych_started"].add(sid)
        if status == "completed":
            ind["psych_completed"].add(sid)
    prep_statuses: dict[UUID, set[str]] = defaultdict(set)
    prep = select(SchoolTestPrepRecord.school_student_id, SchoolTestPrepRecord.test_type, SchoolTestPrepRecord.status).where(SchoolTestPrepRecord.school_student_id.in_(scope)).distinct()
    for sid, test_type, status in (await db.execute(prep)).tuples():
        ind["test_prep_started"].add(sid)
        ind[test_type].add(sid)  # "ielts" / "sat"
        prep_statuses[sid].add(status)
    ind["test_prep_completed"] = {sid for sid, statuses in prep_statuses.items() if statuses == {"completed"}}
    language = select(SchoolLanguageRecord.school_student_id, SchoolLanguageRecord.certification_status).where(SchoolLanguageRecord.school_student_id.in_(scope)).distinct()
    for sid, status in (await db.execute(language)).tuples():
        ind["language_started"].add(sid)
        if status == "certified":
            ind["language_certified"].add(sid)
    for module, by_student in (await skill_statuses(db, scope)).items():
        for sid, statuses in by_student.items():
            ind["skills_enrolled"].add(sid)
            state = _rollup(statuses)
            if state in {"completed", "certified"}:
                ind[f"{module}_completed"].add(sid)
            elif state == "in_progress":
                ind[f"{module}_in_progress"].add(sid)
    ind["portfolio_started"] = await portfolio_started_ids(db, scope)
    published = select(SchoolAcademicResult.school_student_id).where(SchoolAcademicResult.school_student_id.in_(scope), SchoolAcademicResult.status == "published").distinct()
    ind["published_results"] = set((await db.scalars(published)).all())
    applications = select(OverseasApplication.school_student_id, OverseasApplication.status, OverseasApplication.offer_letter_url).where(OverseasApplication.school_student_id.in_(scope))
    for sid, status, offer_url in (await db.execute(applications)).tuples():
        ind["global"].add(sid)
        if _stage_at_or_after(status, "university_selection"):
            ind["shortlisted"].add(sid)
        if status not in {"withdrawn", "rejected"}:
            ind["applied_active"].add(sid)
        if status in OFFER_ONWARD_STATUSES or offer_url:
            ind["offer"].add(sid)
        if status == "enrolled":
            ind["admitted"].add(sid)
    visas = select(OverseasApplication.school_student_id).join(VisaCase, VisaCase.application_id == OverseasApplication.id).where(OverseasApplication.school_student_id.in_(scope)).distinct()
    ind["visa_started"] = set((await db.scalars(visas)).all())
    attended = (
        select(SchoolActivityAttendance.school_student_id)
        .join(SchoolActivity, SchoolActivity.id == SchoolActivityAttendance.activity_id)
        .where(SchoolActivityAttendance.school_student_id.in_(scope), SchoolActivityAttendance.present.is_(True), SchoolActivity.activity_type.in_(AWARENESS_ACTIVITY_TYPES))
        .distinct()
    )
    ind["awareness_attended"] = set((await db.scalars(attended)).all())
    return ind


async def _roster(db: AsyncSession, school_ids: Collection[UUID]) -> list:
    """(id, school_id, grade_level, grade_or_class) for every student of these schools."""
    stmt = select(SchoolStudent.id, SchoolStudent.school_id, SchoolStudent.grade_level, SchoolStudent.grade_or_class).where(SchoolStudent.school_id.in_(list(school_ids)))
    return (await db.execute(stmt)).all()


# --- §29 grade-wise comparison --------------------------------------------------------------------------------------------

# (key, label, rule over the indicators, definition when the metric is a D5 estimate)
GRADE_METRICS = [
    ("career_readiness", "Career readiness", lambda i: i["guidance"] & i["psych_completed"], "Students with a career guidance session and a completed psychometric test"),
    ("assessment_completion", "Assessment completion", lambda i: i["psych_completed"], None),
    ("counselling_completion", "Counselling completion", lambda i: i["counselling"], None),
    ("skills_development", "Skills development", lambda i: i["skills_enrolled"], "Students enrolled in a soft-skills or digital-skills batch"),
    ("global_education_interest", "Global education interest", lambda i: i["global"], "Students with any overseas application"),
    ("application_readiness", "Application readiness", lambda i: i["shortlisted"], "Students whose application has reached university selection or later"),
    ("university_applications", "University applications", lambda i: i["applied_active"], None),
    ("admissions", "Admissions", lambda i: i["admitted"], None),
]


@school_router.get("/analytics/grade-performance", response_model=GradePerformanceOut)
async def grade_performance(user: User = Depends(_require_school_reader), db: AsyncSession = Depends(get_db)):
    """§29: the same metrics side by side for Grade 8 -> 12, own school only. D5 estimates are flagged with their definition."""
    school_id = _own_school_id(user)
    by_grade: dict[str, set[UUID]] = defaultdict(set)
    for sid, _school, level, label in await _roster(db, [school_id]):
        by_grade[grade_key(level, label)].add(sid)
    indicators = await student_indicators(db, students_in([school_id]))
    grades = _ordered_grades(by_grade)
    metrics = []
    for key, label, rule, definition in GRADE_METRICS:
        chosen = rule(indicators)
        cells = {g: MetricCell(count=len(by_grade[g] & chosen), pct=_pct(len(by_grade[g] & chosen), len(by_grade[g]))) for g in grades}
        metrics.append(GradeMetricRow(key=key, label=label, is_proxy=definition is not None, definition=definition, cells=cells))
    _log_view(user, "grade_performance", school_id=school_id)
    return GradePerformanceOut(grades=grades, students={g: len(by_grade[g]) for g in grades}, metrics=metrics)


# --- Part B §14 student development -----------------------------------------------------------------------------------------

THRESHOLD_ORDER = "at_risk_below must be less than top_from"
PERFORMER_CAP = 50  # named lists are about minors; the full count is still returned (spec §12)
DEVELOPMENT_ROWS = [  # D2: pending = total students - completed
    ("career_guidance", "Career Guidance", lambda i: i["guidance"]),
    ("psychometric_test", "Psychometric Test", lambda i: i["psych_completed"]),
    ("foreign_language", "Foreign Language", lambda i: i["language_certified"]),
    ("english_testing", "English Testing", lambda i: i["ielts"] & i["test_prep_completed"]),
    ("university_guidance", "University Guidance", lambda i: i["shortlisted"]),
]


def _averages(groups: dict[str, list[float]], order: list[str]) -> list[AverageRow]:
    return [AverageRow(key=k, label=k, average_pct=round(mean(groups[k]), 1) if groups[k] else None, count=len(groups[k])) for k in order]


@school_router.get("/analytics/student-development", response_model=StudentDevelopmentOut)
async def student_development(
    user: User = Depends(_require_school_reader),
    at_risk_below: int = Query(40, ge=0, le=100),
    top_from: int = Query(85, ge=0, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Part B §14: headcounts, Completed/Pending per activity, and academic performance from PUBLISHED results only
    (SCH-006-AC02). At-risk / top-performer thresholds are D4's configurable defaults."""
    if at_risk_below >= top_from:
        raise HTTPException(422, THRESHOLD_ORDER)
    school_id = _own_school_id(user)
    students = {
        row.id: row
        for row in (await db.execute(select(SchoolStudent.id, SchoolStudent.full_name, SchoolStudent.grade_level, SchoolStudent.grade_or_class).where(SchoolStudent.school_id == school_id))).all()
    }
    total = len(students)
    indicators = await student_indicators(db, students_in([school_id]))
    accounts = await _school_account_counts(db, school_id)
    results = (
        await db.execute(
            select(SchoolAcademicResult.school_student_id, SchoolAcademicResult.academic_year, SchoolAcademicResult.term, SchoolAcademicResult.subject, SchoolAcademicResult.max_marks, SchoolAcademicResult.marks_obtained)
            .join(SchoolStudent, SchoolStudent.id == SchoolAcademicResult.school_student_id)
            .where(SchoolStudent.school_id == school_id, SchoolAcademicResult.status == "published")
        )
    ).all()

    per_student: dict[UUID, list[float]] = defaultdict(list)
    per_subject: dict[str, list[float]] = defaultdict(list)
    per_term: dict[str, list[float]] = defaultdict(list)
    for sid, year, term, subject, max_marks, obtained in results:
        pct = _percentage(float(max_marks), float(obtained))
        if pct is None:
            continue
        per_student[sid].append(pct)
        per_subject[subject].append(pct)
        per_term[f"{year} · {term}"].append(pct)
    averages = {sid: round(mean(values), 1) for sid, values in per_student.items()}
    per_grade: dict[str, list[float]] = defaultdict(list)
    for sid, average in averages.items():
        per_grade[grade_key(students[sid].grade_level, students[sid].grade_or_class)].append(average)

    def _performers(chosen: list[UUID]) -> PerformerList:
        rows = [
            PerformerRow(school_student_id=sid, full_name=students[sid].full_name, grade=grade_key(students[sid].grade_level, students[sid].grade_or_class), average_pct=averages[sid], result_count=len(per_student[sid]))
            for sid in chosen
        ]
        return PerformerList(items=rows[:PERFORMER_CAP], total=len(rows))

    at_risk = sorted((sid for sid, a in averages.items() if a < at_risk_below), key=lambda sid: (averages[sid], students[sid].full_name, str(sid)))
    top = sorted((sid for sid, a in averages.items() if a >= top_from), key=lambda sid: (-averages[sid], students[sid].full_name, str(sid)))
    _log_view(user, "student_development", school_id=school_id)
    return StudentDevelopmentOut(
        headcounts=Headcounts(students=total, teachers=accounts["teachers"], parents=accounts["parents"]),
        activities=[ActivityProgressRow(key=k, label=label, completed=len(rule(indicators)), pending=total - len(rule(indicators))) for k, label, rule in DEVELOPMENT_ROWS],
        by_grade=_averages(per_grade, _ordered_grades(per_grade)),
        by_subject=_averages(per_subject, sorted(per_subject)),
        by_term=_averages(per_term, sorted(per_term)),
        at_risk=_performers(at_risk),
        top_performers=_performers(top),
        at_risk_below=at_risk_below,
        top_from=top_from,
    )


# --- §28 Student Progress Scorecard -----------------------------------------------------------------------------------------

STUDENT_NOT_FOUND = "Student not found"
MAX_OFFSET = 10_000  # bounds a URL-supplied offset: past PostgreSQL's bigint it was a 500, not a 422
_NONE: frozenset[UUID] = frozenset()
# (key, label, plan service keys or None when no module exists, completed rule, in-progress rule). Rules take (indicators,
# ids whose ENH-012 portfolio is 100% complete). Spec §6.3 / D3 / D12.
SCORECARD_AREAS = [
    ("career_awareness", "Career Awareness", ("career_awareness_session",), lambda i, p: i["awareness_attended"] | i["guidance"], lambda i, p: _NONE),
    ("psychometric", "Psychometric", ("psychometric_test",), lambda i, p: i["psych_completed"], lambda i, p: i["psych_started"]),
    ("career_counselling", "Career Counselling", ("individual_counselling",), lambda i, p: i["counselling"], lambda i, p: _NONE),
    ("soft_skills", "Soft Skills", ("soft_skills",), lambda i, p: i["soft_skills_completed"], lambda i, p: i["soft_skills_in_progress"]),
    ("foreign_language", "Foreign Language", ("foreign_language_classes",), lambda i, p: i["language_certified"], lambda i, p: i["language_started"]),
    ("digital_portfolio", "Digital Portfolio", ("digital_portfolio_creation",), lambda i, p: p, lambda i, p: i["portfolio_started"]),
    ("ielts_sat", "IELTS/SAT", ("ielts_coaching", "sat_coaching"), lambda i, p: i["test_prep_completed"], lambda i, p: i["test_prep_started"]),
    ("university_shortlisting", "University Shortlisting", ("application_support",), lambda i, p: i["shortlisted"], lambda i, p: i["global"]),
    ("scholarship", "Scholarship", None, None, None),  # no school-student scholarship link yet (ENH-017)
    ("application", "Application", ("application_support",), lambda i, p: i["offer"], lambda i, p: i["applied_active"]),
    # NEEDS_CONFIRMATION: visa_cases.status is free text with no terminal value, so "completed" is taken as admitted.
    ("visa", "Visa", ("visa_support",), lambda i, p: i["admitted"], lambda i, p: i["visa_started"]),
    # ENH-021 (merged after the spec): internships are portfolio entries; progress follows its own I8 rule.
    ("internship", "Internship", ("internships",), lambda i, p: i["internship_completed"], lambda i, p: i["internship_in_progress"]),
]
SCORECARD_COLUMNS = (SchoolStudent.id, SchoolStudent.full_name, SchoolStudent.grade_level, SchoolStudent.grade_or_class, SchoolStudent.date_of_birth)


def _area_state(sid: UUID, plan: set[str], keys: tuple[str, ...], done: Collection[UUID], started: Collection[UUID]) -> str:
    if sid in done:
        return "completed"
    if sid in started:
        return "in_progress"
    return "not_started" if plan.intersection(keys) else "not_in_plan"


async def build_scorecards(db: AsyncSession, school_tier: str | None, students: list) -> list[ScorecardOut]:
    """Scorecards for already scope-checked rows of SCORECARD_COLUMNS, in a fixed number of queries. "In plan" uses the same
    inclusion rule as /school/entitlements (the tier's cumulative services; expiry is not applied there either)."""
    ids = [s.id for s in students]
    if not ids:
        return []
    indicators = await student_indicators(db, ids)
    sections = await portfolio_sections(db, ids)
    statements = await statement_ids(db, ids)
    plan = {key for key, _ in _cumulative_services(school_tier)}
    completion = {
        s.id: portfolio_completion(
            profile_complete=s.date_of_birth is not None and s.grade_or_class is not None,
            has_academic=s.id in indicators["published_results"],
            has_psychometric=s.id in indicators["psych_started"],
            has_career=s.id in indicators["career_any"],
            has_language=s.id in indicators["language_started"],
            sections=sections.get(s.id, set()),
            has_statement=s.id in statements,
        )
        for s in students
    }
    complete = {sid for sid, pct in completion.items() if pct == 100}
    cards = []
    for s in students:
        areas = [
            ScorecardArea(key=key, label=label, state="not_tracked" if keys is None else _area_state(s.id, plan, keys, done(indicators, complete), started(indicators, complete)))
            for key, label, keys, done, started in SCORECARD_AREAS
        ]
        cards.append(ScorecardOut(school_student_id=s.id, full_name=s.full_name, grade=grade_key(s.grade_level, s.grade_or_class), portfolio_completion_pct=completion[s.id], areas=areas))
    return cards


@school_router.get("/analytics/scorecards", response_model=ScorecardPage)
async def scorecard_grid(
    user: User = Depends(_require_school_reader),
    grade: int | None = Query(None, ge=8, le=12),  # an int range, not Literal: query strings never coerce into Literal[int]
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=MAX_OFFSET),
    db: AsyncSession = Depends(get_db),
):
    """§28 school-wide grid (D10), own school only, ordered by name then id so pages are stable. `grade` uses the same
    `grade_key` as §29 and the KPI board (the ENH-001 label fallback included), so a grade means the same students on every
    figure; the filter therefore runs over the school's light roster columns in Python, still one query."""
    school_id = _own_school_id(user)
    roster = (await db.execute(select(*SCORECARD_COLUMNS).where(SchoolStudent.school_id == school_id).order_by(SchoolStudent.full_name, SchoolStudent.id))).all()
    if grade is not None:
        roster = [s for s in roster if grade_key(s.grade_level, s.grade_or_class) == str(grade)]
    students = roster[offset : offset + limit]
    tier = await db.scalar(select(School.tier).where(School.id == school_id))
    _log_view(user, "scorecard_grid", school_id=school_id, count=len(students))
    return ScorecardPage(items=await build_scorecards(db, tier, students), total=len(roster), limit=limit, offset=offset)


@school_router.get("/students/{student_id}/scorecard", response_model=ScorecardOut)
async def student_scorecard(student_id: UUID, user: User = Depends(_require_school_reader), db: AsyncSession = Depends(get_db)):
    """§28 card for one student (D9). The school is part of the lookup, so another school's student is the same 404 as a
    missing one -- no existence oracle."""
    school_id = _own_school_id(user)
    student = (await db.execute(select(*SCORECARD_COLUMNS).where(SchoolStudent.id == student_id, SchoolStudent.school_id == school_id))).first()
    if student is None:
        raise HTTPException(404, STUDENT_NOT_FOUND)
    tier = await db.scalar(select(School.tier).where(School.id == school_id))
    _log_view(user, "student_scorecard", school_id=school_id, student_id=student_id)
    return (await build_scorecards(db, tier, [student]))[0]


# --- §34 Edusphere cross-school dashboard and §27 school-wise utilization ---------------------------------------------------

NEW_SCHOOL_DAYS = 90  # D6
RENEWAL_DUE_DAYS = 60  # D6
PARTICIPATION_KEYS = ("career_any", "psych_started", "test_prep_started", "language_started", "skills_enrolled", "portfolio_started", "global", "awareness_attended", "internship_any")
UNTRACKED_OUTCOMES = {
    "scholarships": "No school-student scholarship link exists yet (ENH-017).",
}


def utilization(tier: str | None, usage: dict) -> dict:
    """§27 for one school over the services its tier includes: delivered (used > 0 or True), pending (0 or False), not tracked
    (no usage key -- no module yet). The percentage is over the tracked services only, `None` when there are none."""
    values = [usage.get(key) for key, _ in _cumulative_services(tier)]
    not_tracked = sum(1 for v in values if v is None)
    delivered = sum(1 for v in values if v is not None and v is not False and v != 0)
    pending = len(values) - not_tracked - delivered
    return {"services_included": len(values), "delivered": delivered, "pending": pending, "not_tracked": not_tracked, "utilization_pct": _pct(delivered, len(values) - not_tracked)}


def _is_new(school: School, today: date) -> bool:
    start = school.partnership_date or school.created_at.astimezone(TIER_TIMEZONE).date()
    return (today - start).days <= NEW_SCHOOL_DAYS


def _is_active(school: School, today: date) -> bool:
    """D6 (revised 2026-09-28): an active partnership is ENH-022's own rule -- a tier that is set and not past its end date."""
    return _entitlement_denial(school.tier, school.tier_valid_until, None, today) is None


def _renewal_due(school: School, today: date) -> bool:
    """An already expired partnership is due too (D6)."""
    return school.tier_valid_until is not None and school.tier_valid_until <= today + timedelta(days=RENEWAL_DUE_DAYS)


@admin_router.get("/analytics/summary", response_model=CrossSchoolSummaryOut)
async def cross_school_summary(user: User = Depends(_require_school_admin), db: AsyncSession = Depends(get_db)):
    """§34: every partner school at once, for Edusphere's Overseas and Super Admins (D1). Aggregates only (spec §12)."""
    today = _today_ist()
    schools = (await db.scalars(select(School))).all()
    ids = [s.id for s in schools]
    roster = await _roster(db, ids)
    indicators = await student_indicators(db, select(SchoolStudent.id))
    usage = await service_usage(db, ids)
    per_school = [utilization(s.tier, usage.get(s.id, {})) for s in schools]
    totals = {k: sum(p[k] for p in per_school) for k in ("services_included", "delivered", "pending", "not_tracked")}
    by_grade: dict[str, int] = defaultdict(int)
    for _sid, _school, level, label in roster:
        by_grade[grade_key(level, label)] += 1
    from_schools = OverseasApplication.school_student_id.is_not(None)
    active_apps = await db.scalar(select(func.count()).select_from(OverseasApplication).where(from_schools, OverseasApplication.status.not_in(("withdrawn", "rejected")))) or 0
    offer_condition = OverseasApplication.status.in_(list(OFFER_ONWARD_STATUSES)) | OverseasApplication.offer_letter_url.is_not(None)
    offers = await db.scalar(select(func.count()).select_from(OverseasApplication).where(from_schools, offer_condition)) or 0
    _log_view(user, "cross_school_summary", school_count=len(ids))
    return CrossSchoolSummaryOut(
        schools=SchoolCounts(
            total=len(schools), active=sum(1 for s in schools if _is_active(s, today)), new=sum(1 for s in schools if _is_new(s, today)), renewal_due=sum(1 for s in schools if _renewal_due(s, today))
        ),
        students=StudentCounts(
            total=len(roster), by_grade={g: by_grade[g] for g in _ordered_grades(by_grade)}, career_guidance=len(indicators["guidance"]),
            psychometric=len(indicators["psych_completed"]), counselling=len(indicators["counselling"]), global_education=len(indicators["global"]),
        ),
        services=ServiceTotals(**totals, utilization_pct=_pct(totals["delivered"], totals["services_included"] - totals["not_tracked"])),
        outcomes={
            "applications": TrackedValue(value=active_apps, tracked=True),
            "offers": TrackedValue(value=offers, tracked=True),
            "visas": TrackedValue(value=len(indicators["visa_started"]), tracked=True),
            "admissions": TrackedValue(value=len(indicators["admitted"]), tracked=True),
            "internships": TrackedValue(value=len(indicators["internship_any"]), tracked=True),  # ENH-021 I7
            **{key: TrackedValue(value=None, tracked=False, note=note) for key, note in UNTRACKED_OUTCOMES.items()},
        },
    )


@admin_router.get("/analytics/schools", response_model=SchoolUtilizationPage)
async def cross_school_rows(
    user: User = Depends(_require_school_admin),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=MAX_OFFSET),
    db: AsyncSession = Depends(get_db),
):
    """§27 "school-wise": one row per partner school, ordered by name then id. Every figure is a count."""
    today = _today_ist()
    total = await db.scalar(select(func.count()).select_from(School)) or 0
    schools = (await db.scalars(select(School).order_by(School.name, School.id).limit(limit).offset(offset))).all()
    ids = [s.id for s in schools]
    students_by_school: dict[UUID, set[UUID]] = defaultdict(set)
    for sid, school_id, _level, _label in await _roster(db, ids):
        students_by_school[school_id].add(sid)
    indicators = await student_indicators(db, students_in(ids))
    participating = set().union(*(indicators[k] for k in PARTICIPATION_KEYS))
    usage = await service_usage(db, ids)
    upcoming_stmt = select(SchoolActivity.school_id, func.count()).where(SchoolActivity.school_id.in_(ids), SchoolActivity.scheduled_at >= datetime.now(UTC)).group_by(SchoolActivity.school_id)
    upcoming = dict((await db.execute(upcoming_stmt)).tuples().all())
    items = [
        SchoolUtilizationRow(
            school_id=s.id, name=s.name, tier=s.tier, tier_valid_until=s.tier_valid_until, is_active=_is_active(s, today), is_new=_is_new(s, today), renewal_due=_renewal_due(s, today),
            students=len(students_by_school[s.id]), student_participation=len(students_by_school[s.id] & participating), pending_activities=upcoming.get(s.id, 0),
            **utilization(s.tier, usage.get(s.id, {})),
        )
        for s in schools
    ]
    _log_view(user, "cross_school_rows", school_count=len(ids))
    return SchoolUtilizationPage(items=items, total=total, limit=limit, offset=offset)
