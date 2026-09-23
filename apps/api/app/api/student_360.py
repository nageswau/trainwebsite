"""ENH-013a -- Student 360° view / Career Passport (docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md).

A read aggregation over already-built modules. Every tab is built from the payload builders the existing endpoints already use
(`_overview_payload`, `portfolio_payload`, `_grade_history_rows`), then projected per role so no role sees anything here that it
cannot already read through an existing endpoint (spec §6.3, "no new exposure"). The loader runs before any query, and every
query below is keyed on the loaded `student`, never on the raw path id.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.portfolio import portfolio_payload
from app.api.schools import SCHOOL_ROLES, _grade_history_rows, _load_student_for_reader, _overview_payload
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import School, SchoolStudent, User
from app.schemas import TAB_360_KEYS, Student360Out

router = APIRouter(prefix="/school", tags=["school-360"])
logger = get_logger("app.student_360")

# Fixed server-side text (spec §6.4) -- never built from user input.
NOT_TRACKED = {
    "attendance": "Daily and period attendance is not tracked yet (ENH-030).",
    "personal_details": "Additional profile fields are not tracked yet (ENH-025).",
    "documents": "A student document registry is not tracked yet (ENH-013b).",
    "teacher_remarks": "A standalone teacher remarks log is not tracked yet (ENH-013b).",
    "parent_communication": "A parent communication log is not tracked yet (ENH-013b / ENH-014).",
}
ACTIVITY_SECTIONS = ("project", "internship", "sport", "leadership", "volunteering", "extracurricular")
ACHIEVEMENT_SECTIONS = ("award", "competition")


def _restricted() -> dict:
    return {"status": "restricted", "count": None, "not_tracked": [], "data": {}}


def _tab(key: str, data: dict, count: int | None, *, has_data: bool | None = None) -> dict:
    present = bool(count) if has_data is None else has_data
    return {"status": "has_data" if present else "empty", "count": count, "not_tracked": [NOT_TRACKED[key]] if key in NOT_TRACKED else [], "data": data}


def _language_status(records: list[dict]) -> str:
    statuses = {r["certification_status"] for r in records}
    return "certified" if "certified" in statuses else ("in_progress" if records else "not_started")


async def build_360(db: AsyncSession, user: User, student: SchoolStudent) -> dict:
    """The 16 tabs for one already scope-checked student, as `user`'s role may see them (spec §6.3)."""
    school_role = user.role in SCHOOL_ROLES
    academic = user.role == "academic_team"
    counselor = user.role == "career_counselor"
    psych = user.role == "psychometric_team"

    overview = await _overview_payload(db, student)
    portfolio = await portfolio_payload(db, user, student)
    history = await _grade_history_rows(db, student) if school_role else []
    school = await db.get(School, student.school_id)  # already in the identity map from _overview_payload: no extra query
    entries = portfolio["entries"]

    header = {"id": student.id, "full_name": student.full_name, "school_name": school.name if school else None,
              "student_code": None, "grade_or_class": None, "date_of_birth": None, "assigned_teacher_name": None}
    if school_role:  # service roles only ever see name + school today (/school/portfolio-students)
        o = overview["student"]
        header.update(student_code=o["student_code"], grade_or_class=o["grade_or_class"], date_of_birth=o["date_of_birth"], assigned_teacher_name=o["assigned_teacher_name"])

    results_full = overview["results"]  # published only, same rule as /overview (SCH-006-AC02)
    psych_status = {a["id"]: a["status"] for a in overview["psychometric"]["assessments"]}
    skills = overview["skills"]
    if counselor:  # a batch at the student's previous school is outside this counselor's portfolio
        skills = {m: {**v, "enrollments": [e for e in v["enrollments"] if not e["frozen"]]} for m, v in skills.items()}
    enrolments = [e for m in skills.values() for e in m["enrollments"]]
    languages = overview["foreign_language"]["records"] if (school_role or academic) else portfolio["languages"]
    attended = overview["activities"]["attended"]
    skill_sessions = [{"batch_title": e["batch_title"], **e["attendance"]} for e in enrolments if e["attendance"]["marked"]]
    activity_entries = {s: entries[s] for s in ACTIVITY_SECTIONS}
    achievements = [e for s in ACHIEVEMENT_SECTIONS for e in entries[s]]

    tabs: dict[str, dict] = {"personal_details": _tab("personal_details", dict(header), None, has_data=True)}
    tabs["academic_records"] = _tab("academic_records", {"grade_or_class": header["grade_or_class"], "grade_history": history}, len(history)) if school_role else _restricted()
    tabs["attendance"] = _tab("attendance", {"activities": attended, "skill_sessions": skill_sessions}, len(attended) + len(skill_sessions)) if school_role else _restricted()
    results = results_full if (school_role or academic) else portfolio["academic_achievements"]
    tabs["examination_results"] = _tab("examination_results", {"results": results}, len(results))
    tabs["career_guidance"] = _tab("career_guidance", {"records": portfolio["career_guidance"]}, len(portfolio["career_guidance"]))
    assessments = portfolio["psychometric_report"]
    if school_role or psych:
        assessments = [{**a, "status": psych_status.get(a["id"])} for a in assessments]
    tabs["psychometric_assessment"] = _tab("psychometric_assessment", {"assessments": assessments}, len(assessments))
    batches = skills if (school_role or counselor) else None
    tabs["skills"] = _tab("skills", {"batches": batches, "portfolio_entries": entries["skill"]}, (len(enrolments) if batches else 0) + len(entries["skill"]))
    tabs["foreign_languages"] = _tab("foreign_languages", {"records": languages}, len(languages))
    test_prep = overview["test_prep"]["records"]
    tabs["english_testing"] = _tab("english_testing", {"records": test_prep}, len(test_prep)) if (school_role or academic) else _restricted()
    tabs["activities"] = _tab(
        "activities",
        {"attended": attended if school_role else None, "upcoming": overview["activities"]["upcoming"] if school_role else None, "portfolio_entries": activity_entries},
        (len(attended) if school_role else 0) + sum(len(v) for v in activity_entries.values()),
    )
    tabs["certificates"] = _tab("certificates", {"entries": entries["certification"]}, len(entries["certification"]))
    reports = [{"assessment_type": a["assessment_type"], "report_url": a["report_url"], "created_at": a["created_at"]} for a in portfolio["psychometric_report"] if a["report_url"]]
    tabs["documents"] = _tab("documents", {"psychometric_reports": reports}, len(reports))
    remarks = [{"id": r["id"], "academic_year": r["academic_year"], "term": r["term"], "subject": r["subject"], "teacher_remarks": r["teacher_remarks"]} for r in results_full if r["teacher_remarks"]]
    tabs["teacher_remarks"] = _tab("teacher_remarks", {"remarks": remarks}, len(remarks)) if (school_role or academic) else _restricted()
    tabs["parent_communication"] = _tab("parent_communication", {}, 0)

    # Programmes the viewer can already see elsewhere (spec D6): skills, test prep, languages, and -- School roles only -- overseas.
    programmes = []
    if batches is not None:
        programmes += [{"key": module, "status": progress["status"]} for module, progress in skills.items()]
    if school_role or academic:
        programmes.append({"key": "test_prep", "status": overview["test_prep"]["status"]})
    programmes.append({"key": "foreign_language", "status": _language_status(languages)})
    if school_role:
        programmes.append({"key": "global_education", "status": overview["global_education"]["status"], "applications": overview["global_education"]["applications"]})
    tabs["edusphere_programs"] = _tab("edusphere_programs", {"programmes": programmes}, sum(1 for p in programmes if p["status"] != "not_started"))

    tabs["overview"] = _tab("overview", {"achievements": achievements, "portfolio_completion_percentage": portfolio["completion_percentage"]},
                            len(achievements), has_data=bool(student.career_goal or achievements))
    return {"student": header, "career_goal": student.career_goal, "can_edit_career_goal": counselor, "tabs": {key: tabs[key] for key in TAB_360_KEYS}}


@router.get("/students/{student_id}/360-view", response_model=None, responses={200: {"model": Student360Out}})
async def student_360_view(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The envelope is validated against `Student360Out` (a broken shape fails loudly), but the dict itself is returned so its
    timestamps serialize exactly as /overview's and /portfolio's do for the same rows -- a `response_model` would re-encode the
    nested tab data (`...Z` instead of `...+00:00`), giving one record two formats depending on the endpoint."""
    student = await _load_student_for_reader(db, user, student_id)
    body = await build_360(db, user, student)
    Student360Out.model_validate(body)
    logger.info("student_360_view", extra={"extra_fields": {"actor_id": str(user.id), "role": user.role, "student_id": str(student.id)}})
    return body
