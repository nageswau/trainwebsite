"""AGN-016 -- request validation at the API boundary (spec §3): lengths, aware due times, server-owned fields, status alone."""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas import AgentTaskCreate, AgentTaskUpdate

DUE = "2026-10-05T09:30:00+05:30"


def _create(**over):
    return AgentTaskCreate(**{"agent_student_id": str(uuid.uuid4()), "title": "Call the student", "due_at": DUE, **over})


def test_create_trims_title_and_blank_notes_become_null():
    task = _create(title="  Call back  ", notes="   ")
    assert (task.title, task.notes, task.application_id) == ("Call back", None, None)
    assert task.due_at.utcoffset() is not None


@pytest.mark.parametrize(
    "over",
    [
        {"title": "   "},
        {"title": "x" * 201},
        {"title": None},
        {"notes": "x" * 2001},
        {"title": "bad‮order"},
        {"title": 5},  # final review: a non-string title is a 422, never an AttributeError (500)
        {"title": ["Call"]},
        {"due_at": "2026-10-05T09:30:00"},  # no offset: refused, never silently read as UTC
        {"due_at": None},
        {"status": "done"},  # create never sets a status
        {"agent_id": str(uuid.uuid4())},
    ],
)
def test_create_rejects(over):
    with pytest.raises(ValidationError):
        _create(**over)


def test_update_empty_and_partial_are_valid():
    assert AgentTaskUpdate().model_fields_set == set()
    update = AgentTaskUpdate(notes=None)
    assert update.model_fields_set == {"notes"} and update.notes is None
    assert AgentTaskUpdate(status="cancelled").status == "cancelled"


@pytest.mark.parametrize(
    "body",
    [
        {"title": None},
        {"due_at": None},
        {"title": ""},
        {"due_at": "2026-10-05T09:30:00"},
        {"status": "open"},
        {"status": "archived"},
        {"status": "done", "title": "Also rename"},  # status changes travel alone
        {"status": "done", "notes": None},
        {"agent_student_id": str(uuid.uuid4())},  # the student is fixed after create
        {"closed_by_user_id": str(uuid.uuid4())},
    ],
)
def test_update_rejects(body):
    with pytest.raises(ValidationError):
        AgentTaskUpdate(**body)
