"""bdm-007 -- report schemas (spec §5.1, §5.2)."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas import BDM_REPORT_TEXT_FIELDS, BdmMeetingReportCreate, BdmMeetingReportUpdate

VALID = {"outcome": "interested", "discussion": "Principal keen on IT training."}


def _messages(exc: ValidationError) -> dict[str, str]:
    return {str(e["loc"][-1]): e["msg"] for e in exc.errors()}


def test_minimal_report_and_blanks_become_null():
    r = BdmMeetingReportCreate.model_validate({**VALID, "requirements": "  ", "responsible_person": "", "next_action": "Send proposal"})
    assert (r.requirements, r.responsible_person, r.next_action, r.next_follow_up_on) == (None, None, "Send proposal", None)
    assert BDM_REPORT_TEXT_FIELDS == ("discussion", "requirements", "opportunity", "next_action", "responsible_person")


def test_blank_discussion_is_required():
    with pytest.raises(ValidationError) as missing:
        BdmMeetingReportCreate.model_validate({"outcome": "interested"})
    assert "discussion" in _messages(missing.value)
    with pytest.raises(ValidationError) as blank:
        BdmMeetingReportCreate.model_validate({**VALID, "discussion": "   \n "})
    assert _messages(blank.value)["discussion"] == "Value error, Discussion is required"


def test_multiline_allowed_but_control_characters_and_lengths_refused():
    assert BdmMeetingReportCreate.model_validate({**VALID, "discussion": "Line 1\nLine 2\tend"}).discussion == "Line 1\nLine 2\tend"
    with pytest.raises(ValidationError) as bad:
        BdmMeetingReportCreate.model_validate({**VALID, "opportunity": "a\x07b", "responsible_person": "Mrs\nRao"})
    assert _messages(bad.value) == {
        "opportunity": "Value error, Opportunity contains invalid characters",
        "responsible_person": "Value error, Responsible person contains invalid characters",
    }
    for field, limit in (("discussion", 4000), ("requirements", 2000), ("opportunity", 2000), ("next_action", 1000), ("responsible_person", 200)):
        BdmMeetingReportCreate.model_validate({**VALID, field: "x" * limit})
        with pytest.raises(ValidationError):
            BdmMeetingReportCreate.model_validate({**VALID, field: "x" * (limit + 1)})


def test_server_owned_fields_and_bad_values_are_refused():
    for extra in ({"legacy": True}, {"author_user_id": "00000000-0000-0000-0000-000000000000"}, {"status": "completed"}):
        with pytest.raises(ValidationError):
            BdmMeetingReportCreate.model_validate({**VALID, **extra})
    with pytest.raises(ValidationError):
        BdmMeetingReportCreate.model_validate({**VALID, "outcome": "great"})
    with pytest.raises(ValidationError) as bad_date:
        BdmMeetingReportCreate.model_validate({**VALID, "next_follow_up_on": "22-09-2026"})
    assert _messages(bad_date.value)["next_follow_up_on"] == "Enter a valid follow-up date"
    assert BdmMeetingReportCreate.model_validate({**VALID, "next_follow_up_on": "2030-01-10"}).next_follow_up_on == date(2030, 1, 10)


def test_update_is_partial_and_refuses_null_for_required_fields():
    u = BdmMeetingReportUpdate.model_validate({"next_action": "Call back", "next_follow_up_on": None})
    assert u.model_dump(exclude_unset=True) == {"next_action": "Call back", "next_follow_up_on": None}
    for field in ("outcome", "discussion"):
        with pytest.raises(ValidationError):
            BdmMeetingReportUpdate.model_validate({field: None})
    with pytest.raises(ValidationError):
        BdmMeetingReportUpdate.model_validate({"discussion": "  "})
    with pytest.raises(ValidationError):
        BdmMeetingReportUpdate.model_validate({"legacy": False})
