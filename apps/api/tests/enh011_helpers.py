"""Shared builders for the ENH-011 database tests (docs/superpowers/plans/2026-09-22-enh-011-skills-tracker.md).

Reuses ENH-005's throwaway-school builders so every test gets its own schools, users and students."""

from enh005_helpers import login, mk_school, mk_staff

BATCHES = "/api/v1/school/career-counselor/skill-batches"
ENROLMENTS = "/api/v1/school/career-counselor/skill-enrollments"
SESSIONS = "/api/v1/school/career-counselor/skill-sessions"
ASSESSMENTS = "/api/v1/school/career-counselor/skill-assessments"


async def skills_world(db) -> dict:
    """School A (2 students; the parent is linked to the first; the teacher is assigned the first), school B (1 student),
    a Career Counselor with A in their portfolio, another with only B, and an Academic Team member at A."""
    a = await mk_school(db, label="A", students=2)
    b = await mk_school(db, admin=a["admin"], label="B", students=1)
    counselor = await mk_staff(db, a["school"], a["admin"], role="career_counselor")
    counselor_b = await mk_staff(db, b["school"], a["admin"], role="career_counselor")
    academic = await mk_staff(db, a["school"], a["admin"], role="academic_team")
    return {"a": a, "b": b, "counselor": counselor, "counselor_b": counselor_b, "academic": academic}


async def create_batch(client, school_id, **over) -> dict:
    body = {"school_id": str(school_id), "module_type": "soft_skills", "title": "Public speaking", "start_date": "2026-10-01", **over}
    response = await client.post(BATCHES, json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def enrol(client, batch_id, *students) -> list[dict]:
    response = await client.post(f"{BATCHES}/{batch_id}/enrollments", json={"school_student_ids": [str(s.id) for s in students]})
    assert response.status_code == 201, response.text
    return response.json()


__all__ = ["ASSESSMENTS", "BATCHES", "ENROLMENTS", "SESSIONS", "create_batch", "enrol", "login", "skills_world"]
