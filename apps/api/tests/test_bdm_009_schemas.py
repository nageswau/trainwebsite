"""bdm-009 -- request schemas (spec §5.1; AC1, AC2, V6)."""

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas import (
    ACTIVITY_DIRECTION_REFUSED,
    ACTIVITY_DIRECTION_REQUIRED,
    BdmActivityCreate,
    BdmActivityUpdate,
)

WHEN = datetime(2026, 10, 3, 5, 0, tzinfo=UTC)


def body(**over) -> dict:
    data = {"organization_id": str(uuid.uuid4()), "channel": "call", "direction": "outbound", "occurred_at": WHEN.isoformat()}
    data.update(over)
    return data


@pytest.mark.parametrize("channel", ["call", "whatsapp", "email"])
def test_directional_channels_need_a_direction(channel):
    assert BdmActivityCreate(**body(channel=channel)).direction == "outbound"
    with pytest.raises(ValidationError) as exc:
        BdmActivityCreate(**body(channel=channel, direction=None))
    assert ACTIVITY_DIRECTION_REQUIRED in str(exc.value)
    with pytest.raises(ValidationError):
        BdmActivityCreate(**{k: v for k, v in body(channel=channel).items() if k != "direction"})


@pytest.mark.parametrize("channel", ["visit", "meeting", "other"])
def test_other_channels_refuse_a_direction(channel):
    assert BdmActivityCreate(**body(channel=channel, direction=None)).direction is None
    with pytest.raises(ValidationError) as exc:
        BdmActivityCreate(**body(channel=channel, direction="inbound"))
    assert ACTIVITY_DIRECTION_REFUSED in str(exc.value)


def test_direction_error_sits_on_the_direction_field():
    with pytest.raises(ValidationError) as exc:
        BdmActivityCreate(**body(direction=None))
    assert exc.value.errors()[0]["loc"] == ("direction",)


def test_unknown_channel_and_naive_time_are_refused():
    with pytest.raises(ValidationError):
        BdmActivityCreate(**body(channel="fax"))
    with pytest.raises(ValidationError):
        BdmActivityCreate(**body(occurred_at="2026-10-03T10:00:00"))


def test_note_is_trimmed_capped_and_multiline():
    assert BdmActivityCreate(**body(note="  line one\nline two  ")).note == "line one\nline two"
    with pytest.raises(ValidationError):
        BdmActivityCreate(**body(note="x" * 501))
    with pytest.raises(ValidationError):
        BdmActivityCreate(**body(note="bad\x07bell"))


def test_blank_note_becomes_null():
    assert BdmActivityCreate(**body(note="   ")).note is None


@pytest.mark.parametrize("field", ["bdm_user_id", "contact_name", "id"])
def test_server_owned_fields_are_refused(field):
    with pytest.raises(ValidationError, match="extra"):
        BdmActivityCreate(**body(**{field: "x"}))


def test_update_has_no_organization_and_refuses_clearing_required_fields():
    with pytest.raises(ValidationError, match="extra"):
        BdmActivityUpdate(organization_id=str(uuid.uuid4()))
    with pytest.raises(ValidationError, match="Channel can't be empty"):
        BdmActivityUpdate(channel=None)
    with pytest.raises(ValidationError, match="When can't be empty"):
        BdmActivityUpdate(occurred_at=None)
    patch = BdmActivityUpdate(direction=None, contact_id=None, note=None)
    assert patch.model_fields_set == {"direction", "contact_id", "note"}
