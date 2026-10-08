"""rec-017 test builders: since migration 0119 every job application belongs to a candidate (R6), so a test that writes a student's
application directly goes through the student's candidate, as the student-apply and employer routes do."""

from app.models import JobApplication, User
from app.services.applications import candidate_for_student


async def student_application(db, job_id, student: User, status: str = "sourced", **extra) -> JobApplication:
    """Added to the session and flushed (the caller commits). `status` is a rec-017 key (A1: applied -> sourced, hired -> joined)."""
    candidate = await candidate_for_student(db, student)
    application = JobApplication(job_id=job_id, student_id=student.id, candidate_id=candidate.id, status=status, **extra)
    db.add(application)
    await db.flush()
    return application
