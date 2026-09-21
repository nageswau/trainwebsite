import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.schemas import (
    AcceptedOut,
    IncomingTransferCreate,
    TransferRejectRequest,
    TransferRequestCreate,
    TransferRequestOut,
    TransferRequestPage,
)

# ENH-005: the typed request boundary (docs/superpowers/specs/2026-09-21-enh-005-student-school-transfer-design.md §5.2, §6.1 S7).


def test_student_code_is_normalised_and_ascii_hex_only():
    assert IncomingTransferCreate(student_code=" a3f9c21b ").student_code == "A3F9C21B"
    # too short, too long, non-hex letter, empty, Arabic-Indic digits, full-width letters
    for bad in ("A3F9C21", "A3F9C21BX", "G3F9C21B", "", "٣٣٣٣٣٣٣٣", "ＡＡＡＡＡＡＡＡ"):
        with pytest.raises(ValidationError):
            IncomingTransferCreate(student_code=bad)


@pytest.mark.parametrize(
    "model,kwargs",
    [
        (TransferRequestCreate, {"to_school_id": uuid.uuid4()}),
        (IncomingTransferCreate, {"student_code": "A3F9C21B"}),
        (TransferRejectRequest, {}),
    ],
)
@pytest.mark.parametrize("extra", ["school_id", "from_school_id", "filed_by_school_id", "status", "student_id"])
def test_a_client_supplied_server_field_is_rejected(model, kwargs, extra):
    with pytest.raises(ValidationError):
        model(**kwargs, **{extra: "x"})


def test_a_malformed_school_id_is_a_validation_error_not_a_crash():
    with pytest.raises(ValidationError):
        TransferRequestCreate(to_school_id="not-a-uuid")


def test_free_text_accepts_line_breaks_and_indic_joiners():
    ok = TransferRequestCreate(to_school_id=uuid.uuid4(), reason="line one\nline two\tक्‍ष")
    assert "‍" in ok.reason and "\n" in ok.reason


@pytest.mark.parametrize("bad", ["a\x00b", "a‮b", "a⁦b", "a\x1bb", "x" * 501])
def test_free_text_rejects_control_bidi_and_overlong_input(bad):
    with pytest.raises(ValidationError):
        TransferRequestCreate(to_school_id=uuid.uuid4(), reason=bad)


def test_blank_free_text_becomes_none_and_the_reject_note_is_checked_too():
    assert TransferRejectRequest(note="   ").note is None
    assert TransferRequestCreate(to_school_id=uuid.uuid4()).reason is None
    with pytest.raises(ValidationError):
        TransferRejectRequest(note="a‮b")


def test_a_redacted_request_row_has_the_same_schema_as_a_full_one():
    base = dict(id=uuid.uuid4(), direction="incoming", status="pending", student_code="A3F9C21B", reason=None, decision_note=None, created_at=datetime.now(UTC), decided_at=None, to_school={"id": uuid.uuid4(), "name": "B"})
    redacted = TransferRequestOut(**base, student_id=None, student_name=None, from_school=None)
    full = TransferRequestOut(**base, student_id=uuid.uuid4(), student_name="Aarav", from_school={"id": uuid.uuid4(), "name": "A"})
    assert redacted.model_dump().keys() == full.model_dump().keys()
    assert redacted.student_name is None and redacted.from_school is None


def test_page_envelope_and_accepted_body():
    page = TransferRequestPage(items=[], total=0, limit=25, offset=0)
    assert page.model_dump() == {"items": [], "total": 0, "limit": 25, "offset": 0}
    assert AcceptedOut(accepted=True).model_dump() == {"accepted": True}
