"""bdm-008 test builders (on bdm-006's). Unique per call: the shared test database is never truncated, so every test uses fresh BDMs."""

from datetime import date, datetime, timedelta

from sqlalchemy import func

from app.models import BdmTask
from app.services.bdm_appointments import IST

TASKS = "/api/v1/bdm/tasks"


def ist_day(n: int = 0) -> date:
    return (datetime.now(IST) + timedelta(days=n)).date()


def task_body(**over) -> dict:
    return {"kind": "task", "title": "Send brochure", "due_on": ist_day().isoformat(), **over}


async def create_task(client, **over) -> dict:
    response = await client.post(TASKS, json=task_body(**over))
    assert response.status_code == 201, response.text
    return response.json()


async def insert_task(db, assignee_id, *, due_on: date | None = None, org_id=None, kind="follow_up", status="open", source="manual",
                      title="Seeded") -> BdmTask:
    """A row the API can't create (a past due date, a done / cancelled state, an `mou` source)."""
    task = BdmTask(
        kind=kind, title=title, due_on=due_on or ist_day(), organization_id=org_id, source=source, assignee_user_id=assignee_id, status=status,
        completed_at=func.now() if status == "done" else None,
        cancelled_at=func.now() if status == "cancelled" else None, cancel_reason="Seeded" if status == "cancelled" else None,
    )
    db.add(task)
    await db.commit()
    return task


async def listed(client, **params) -> dict:
    response = await client.get(TASKS, params=params)
    assert response.status_code == 200, response.text
    return response.json()
