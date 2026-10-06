"""bdm-008 -- pure rules (spec §5): IST buckets, overdue and permissions."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.services.bdm_appointments import today_ist
from app.services.bdm_tasks import is_overdue, permissions


def test_overdue_uses_the_ist_date():
    """AC2: at 18:31 UTC on 22 Sep it is already 23 Sep in India -- a task due 23 Sep is today, one due 22 Sep is overdue."""
    today = today_ist(datetime(2026, 9, 22, 18, 31, tzinfo=UTC))
    assert today == date(2026, 9, 23)
    assert not is_overdue("open", date(2026, 9, 23), today)
    assert is_overdue("open", date(2026, 9, 22), today)
    assert today_ist(datetime(2026, 9, 22, 18, 29, tzinfo=UTC)) == date(2026, 9, 22)


def test_done_and_cancelled_are_never_overdue():
    assert not is_overdue("done", date(2020, 1, 1), date(2026, 9, 23))
    assert not is_overdue("cancelled", date(2020, 1, 1), date(2026, 9, 23))


def _task(**over):
    base = {"assignee_user_id": uuid4(), "status": "open", "source": "manual"}
    return SimpleNamespace(**{**base, **over})


def test_permissions_follow_owner_state_and_source():
    owner = SimpleNamespace(id=uuid4(), role="bdm")
    manual = _task(assignee_user_id=owner.id)
    assert permissions(owner, manual) == {"can_edit": True, "can_complete": True, "can_cancel": True}
    outcome = _task(assignee_user_id=owner.id, source="appointment_outcome")
    assert permissions(owner, outcome) == {"can_edit": False, "can_complete": True, "can_cancel": False}
    assert permissions(owner, _task(assignee_user_id=owner.id, status="done")) == {"can_edit": False, "can_complete": False, "can_cancel": False}
    manager = SimpleNamespace(id=uuid4(), role="bdm_manager")
    assert not any(permissions(manager, manual).values())
    other = SimpleNamespace(id=uuid4(), role="bdm")
    assert not any(permissions(other, manual).values())
