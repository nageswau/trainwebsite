"""bdm-025 -- request bodies (spec §5.2, §5.3, §5.6)."""

import uuid

import pytest
from pydantic import ValidationError

from app.schemas import BdmDeactivate, BdmHandover, BdmManagerDeactivate, BdmManagerOption, BdmManagerRow

TARGET = str(uuid.uuid4())


@pytest.mark.parametrize("body", [{"mode": "reassign", "reassign_to": TARGET}, {"mode": "leave"}, {"mode": "leave", "reassign_to": None}])
def test_deactivate_valid(body):
    parsed = BdmDeactivate.model_validate(body)
    assert parsed.mode == body["mode"]


@pytest.mark.parametrize(("body", "message"), [
    ({}, "Choose who takes over this BDM's open work"),
    ({"reassign_to": TARGET}, "Choose who takes over this BDM's open work"),
    ({"mode": None}, "Choose who takes over this BDM's open work"),
    ({"mode": "reassign"}, "Choose the BDM who takes over"),
    ({"mode": "reassign", "reassign_to": None}, "Choose the BDM who takes over"),
    ({"mode": "leave", "reassign_to": TARGET}, "Keeping the work with this BDM takes no target"),
    ({"mode": "delete"}, "Input should be 'reassign' or 'leave'"),
    ({"mode": "leave", "extra": 1}, "Extra inputs are not permitted"),
])
def test_deactivate_invalid(body, message):
    with pytest.raises(ValidationError) as exc:
        BdmDeactivate.model_validate(body)
    assert message in str(exc.value)


def test_handover_needs_a_target_and_nothing_else():
    assert str(BdmHandover.model_validate({"reassign_to": TARGET}).reassign_to) == TARGET
    for body in ({}, {"reassign_to": None}, {"reassign_to": TARGET, "mode": "leave"}):
        with pytest.raises(ValidationError):
            BdmHandover.model_validate(body)


def test_manager_deactivate_target_optional():
    assert BdmManagerDeactivate.model_validate({}).reassign_to is None
    assert str(BdmManagerDeactivate.model_validate({"reassign_to": TARGET}).reassign_to) == TARGET
    with pytest.raises(ValidationError):
        BdmManagerDeactivate.model_validate({"reassign_to": "x"})
    with pytest.raises(ValidationError):
        BdmManagerDeactivate.model_validate({"other": 1})


def test_bdm_count_only_on_the_bdm_manager_row():
    """The telecaller picker shares BdmManagerOption; its shape must not grow."""
    assert "bdm_count" not in BdmManagerOption.model_fields
    assert BdmManagerRow.model_validate({"id": TARGET, "full_name": "M", "email": "m@x", "bdm_count": 2}).bdm_count == 2
    with pytest.raises(ValidationError):
        BdmManagerRow.model_validate({"id": TARGET, "full_name": "M", "email": "m@x"})
