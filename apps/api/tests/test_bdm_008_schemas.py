"""bdm-008 -- request schemas (spec §6.2, §6.3)."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas import BdmTaskCreate, BdmTaskUpdate

OK = {"kind": "task", "title": "Send brochure", "due_on": "2030-01-07"}


def _msgs(exc: ValidationError) -> list[str]:
    return [e["msg"] for e in exc.errors()]


def test_create_parses_and_trims():
    body = BdmTaskCreate.model_validate({**OK, "title": "  Send brochure  ", "notes": "line 1\nline 2"})
    assert (body.title, body.due_on, body.notes, body.organization_id) == ("Send brochure", date(2030, 1, 7), "line 1\nline 2", None)


@pytest.mark.parametrize(("over", "message"), [
    ({"title": "   "}, "Title is required"),
    ({"title": "a\nb"}, "Title contains invalid characters"),
    ({"title": "x" * 201}, "at most 200"),
    ({"notes": "bad\x07"}, "Notes contains invalid characters"),
    ({"notes": "x" * 2001}, "at most 2000"),
    ({"due_on": "22/09/2026"}, "Enter a valid due date"),
    ({"due_on": "202026-09-22"}, "Enter a valid due date"),
    ({"kind": "meeting"}, "follow_up"),
    ({"assignee_user_id": "00000000-0000-0000-0000-000000000000"}, "Extra inputs are not permitted"),
    ({"status": "done"}, "Extra inputs are not permitted"),
])
def test_create_refuses(over, message):
    with pytest.raises(ValidationError) as exc:
        BdmTaskCreate.model_validate({**OK, **over})
    assert any(message in m for m in _msgs(exc.value))


def test_blank_notes_become_null():
    assert BdmTaskCreate.model_validate({**OK, "notes": "  "}).notes is None


def test_update_is_partial_and_refuses_null_title_and_due():
    assert BdmTaskUpdate.model_validate({}).model_dump(exclude_unset=True) == {}
    assert BdmTaskUpdate.model_validate({"notes": None}).model_dump(exclude_unset=True) == {"notes": None}
    for field, message in (("title", "Title is required"), ("due_on", "Due date is required")):
        with pytest.raises(ValidationError) as exc:
            BdmTaskUpdate.model_validate({field: None})
        assert message in " ".join(_msgs(exc.value))
    with pytest.raises(ValidationError):
        BdmTaskUpdate.model_validate({"kind": "task"})  # kind and organization are fixed after create
