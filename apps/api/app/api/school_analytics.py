"""ENH-016 -- School & Edusphere analytics dashboards (docs/superpowers/specs/2026-09-28-enh-016-analytics-dashboards-design.md).

Read-only aggregations for `School CRM.md` §1/§27/§28/§29/§34 and Part B §14. Two routers, like `school_feedback.py`, so
`schools.py` and `admin.py` do not grow. Every query filters on a *student scope* -- a `select` of student ids or a plain id
list -- and groups in SQL, so an endpoint runs the same number of queries for one school or for all of them (spec §10).
Nothing here writes: no add, flush or commit."""

from collections import defaultdict
from collections.abc import Collection
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import Select, func, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import PortfolioEntry, PortfolioProfile, SchoolSkillBatch, SchoolSkillEnrollment, SchoolStudent

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
