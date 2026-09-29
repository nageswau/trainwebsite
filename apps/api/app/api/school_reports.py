"""ENH-015 -- downloadable PDF reports for the School domain (docs/superpowers/specs/2026-09-29-enh-015-reports-downloads-design.md,
DEC-SCOPE-037 provisional). Slice 1: the School Summary (coordinator/principal, own school) and the Student Progress Report.

A pure export layer: every figure comes from an existing read helper under the caller's existing scope, the PDF is
rendered in memory and streamed back, and nothing is stored -- so `/files/download` and `/local-files` can never reach
a report (spec §1). Rendering lives in `app.reporting.pdf`; this module only decides who may read what."""

from time import perf_counter
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.portfolio_certificates import HEADERS
from app.api.school_analytics import _roster, grade_table, student_indicators, students_in
from app.api.school_feedback import _require_school_reader
from app.api.schools import _own_school_id, _today_ist
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import AcademicYear, School, User
from app.reporting.pdf import render_school_summary

router = APIRouter(prefix="/school", tags=["school-reports"])
logger = get_logger("app.school_reports")

PDF = "application/pdf"
PDF_RESPONSES: dict[int | str, dict] = {200: {"content": {PDF: {}}, "description": "The report as a PDF attachment"}}
FAILED = "Could not generate the report; please try again"
# §30 management figures, in the source's own order, as (label, indicator key) -- the ENH-016 indicator sets, so the
# PDF agrees with the on-screen dashboards.
MANAGEMENT_FIGURES = (
    ("Career guidance", "guidance"),
    ("Psychometric assessment completed", "psych_completed"),
    ("Individual counselling", "counselling"),
    ("Skills programs", "skills_enrolled"),
    ("Global education aspirants", "global"),
)


def _grade_label(key: str) -> str:
    """The on-screen labels (SchoolGradePerformance.tsx), so a grade reads the same in the PDF."""
    return "Other grades" if key == "other" else "No grade" if key == "unspecified" else f"Grade {key}"


def _pdf_response(content: bytes, filename: str) -> Response:
    return Response(content=content, media_type=PDF, headers={**HEADERS, "Content-Disposition": f'attachment; filename="{filename}"'})


def _render(user: User, report: str, render, *args) -> bytes:
    """Render, or a generic 500. Only the exception *type* is logged: its message could quote student text (spec §9)."""
    try:
        return render(*args)
    except Exception as exc:
        logger.error("school_report_failed", extra={"extra_fields": {"actor_id": str(user.id), "report": report, "error_type": type(exc).__name__}})
        raise HTTPException(500, FAILED) from None


def _log_generated(user: User, report: str, started: float, content: bytes, **fields) -> None:
    logger.info(
        "school_report_generated",
        extra={
            "extra_fields": {
                "actor_id": str(user.id),
                "role": user.role,
                "report": report,
                **{k: str(v) for k, v in fields.items()},
                "bytes": len(content),
                "ms": round((perf_counter() - started) * 1000),
            }
        },
    )


async def school_summary_data(db: AsyncSession, school_id: UUID) -> dict:
    """Spec §5.1's figures for one school, in a fixed number of queries (AC09)."""
    school = await db.get(School, school_id)
    roster = await _roster(db, [school_id])
    indicators = await student_indicators(db, students_in([school_id]))
    table = grade_table(roster, indicators)
    year = await db.scalar(select(AcademicYear.label).where(AcademicYear.status == "active").order_by(AcademicYear.start_date.desc()).limit(1))
    return {
        "school_name": school.name if school else "",
        "as_of": _today_ist(),
        "academic_year": year,
        "total_students": len(roster),
        "kpis": [("Total students", len(roster)), *[(label, len(indicators[key])) for label, key in MANAGEMENT_FIGURES]],
        "grades": [_grade_label(g) for g in table.grades],
        "students": {_grade_label(g): n for g, n in table.students.items()},
        "metrics": [{"label": m.label, "is_proxy": m.is_proxy, "definition": m.definition, "cells": {_grade_label(g): c.model_dump() for g, c in m.cells.items()}} for m in table.metrics],
    }


@router.get("/reports/school-summary", response_class=Response, responses=PDF_RESPONSES)
async def school_summary_report(user: User = Depends(_require_school_reader), db: AsyncSession = Depends(get_db)):
    """Coordinator/Principal, own school only (D4). Aggregate counts only, so a log line and no AuditLog row (D9)."""
    started = perf_counter()
    school_id = _own_school_id(user)
    data = await school_summary_data(db, school_id)
    content = _render(user, "school_summary", render_school_summary, data)
    _log_generated(user, "school_summary", started, content, school_id=school_id, student_count=data["total_students"])
    return _pdf_response(content, "school-report.pdf")
