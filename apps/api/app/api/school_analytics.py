"""ENH-016 -- School & Edusphere analytics dashboards (docs/superpowers/specs/2026-09-28-enh-016-analytics-dashboards-design.md).

Read-only aggregations for `School CRM.md` §1/§27/§28/§29/§34 and Part B §14. Two routers, like `school_feedback.py`, so
`schools.py` and `admin.py` do not grow. Every query filters on a *student scope* -- a `select` of student ids or a plain id
list -- and groups in SQL, so an endpoint runs the same number of queries for one school or for all of them (spec §10).
Nothing here writes: no add, flush or commit."""

from collections import defaultdict
from collections.abc import Collection
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Select, func, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.school_feedback import _require_school_reader
from app.api.school_skills import _rollup
from app.api.schools import OFFER_ONWARD_STATUSES, _grade_level_from_label, _own_school_id, _stage_at_or_after
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import (
    OverseasApplication,
    PortfolioEntry,
    PortfolioProfile,
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
from app.schemas import GradeMetricRow, GradePerformanceOut, MetricCell

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
    career = select(SchoolCareerRecord.school_student_id, SchoolCareerRecord.record_type).where(SchoolCareerRecord.school_student_id.in_(scope)).distinct()
    for sid, record_type in (await db.execute(career)).tuples():
        ind["career_any"].add(sid)
        if record_type == "guidance_session":
            ind["guidance"].add(sid)
        elif record_type == "counselling_note":
            ind["counselling"].add(sid)
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
