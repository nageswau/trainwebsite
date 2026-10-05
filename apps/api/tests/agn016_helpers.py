"""AGN-016 test helpers: tasks built directly (the API under test builds them in the feature tests). The tests' world is AGN-008's
`agency_world` (Master, two staff, a student with no login and a linked one, both assigned to `staff`; another agency)."""

from datetime import UTC, datetime, timedelta

from app.models import AgentTask

TASKS = "/api/v1/workflows/overseas/agent/crm/tasks"
TASK_KEYS = {"id", "title", "notes", "due_at", "status", "overdue", "student", "application", "assigned_to", "created_by", "closed_by", "closed_at", "created_at", "updated_at"}


def due(**delta) -> datetime:
    """A due time relative to now (default: a day ahead)."""
    return datetime.now(UTC) + (timedelta(**delta) if delta else timedelta(days=1))


async def mk_task(db, *, record, author, title: str = "Follow up", due_at: datetime | None = None, status: str = "open", application=None, notes: str | None = None) -> AgentTask:
    closed = status != "open"
    row = AgentTask(
        agent_student_id=record.id,
        application_id=application.id if application else None,
        title=title,
        notes=notes,
        due_at=due_at or due(),
        status=status,
        closed_at=datetime.now(UTC) if closed else None,
        closed_by_user_id=author.id if closed else None,
        created_by_user_id=author.id,
        updated_by_user_id=author.id,
    )
    db.add(row)
    await db.commit()
    return row
