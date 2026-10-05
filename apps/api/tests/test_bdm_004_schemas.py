"""bdm-004 -- request schemas (spec §6.1): stage-key shape, note / reason rules, unknown fields."""

import pytest
from pydantic import ValidationError

from app.schemas import BdmLostIn, BdmReviveIn, BdmStageMove


def _move(**over) -> BdmStageMove:
    return BdmStageMove(**{"from_stage": "prospect", "to_stage": "contacted", **over})


def test_note_is_optional_trimmed_and_line_breaks_normalized():
    assert _move().note is None
    assert _move(note="  first\r\nsecond\rthird  ").note == "first\nsecond\nthird"


def test_blank_note_is_none():
    assert _move(note="   ").note is None


def test_crlf_counts_as_one_character():
    assert len(_move(note="a" * 498 + "\r\n" + "b").note) == 500
    with pytest.raises(ValidationError):
        _move(note="a" * 501)


def test_control_characters_are_refused_but_tabs_allowed():
    assert _move(note="a\tb").note == "a\tb"
    with pytest.raises(ValidationError, match="Note contains invalid characters"):
        _move(note="a\x07b")


@pytest.mark.parametrize("key", ["Contacted", "x" * 41, "", "prospect;drop", "pro spect", "<script>"])
def test_stage_keys_are_lower_snake_case(key):
    with pytest.raises(ValidationError):
        _move(to_stage=key)
    with pytest.raises(ValidationError):
        _move(from_stage=key)


def test_unknown_fields_are_refused():
    with pytest.raises(ValidationError):
        _move(stage="contacted")
    with pytest.raises(ValidationError):
        BdmLostIn(reason="x", lost_at="2026-01-01")


def test_reason_is_required_trimmed_and_normalized():
    for model in (BdmLostIn, BdmReviveIn):
        assert model(reason=" No budget\r\nthis year ").reason == "No budget\nthis year"
        with pytest.raises(ValidationError, match="Reason is required"):
            model(reason="   ")
        with pytest.raises(ValidationError):
            model()
        with pytest.raises(ValidationError):
            model(reason="r" * 501)
