"""ENH-009 / DEC-SCOPE-023 -- SchoolCreate/SchoolUpdate/SchoolOut schema behavior."""

import pytest
from pydantic import ValidationError

from app.schemas import SchoolCreate, SchoolUpdate


def test_school_create_rejects_an_unexpected_field():
    with pytest.raises(ValidationError):
        SchoolCreate(
            name="X", coordinator_full_name="Y", coordinator_email="y@example.local",
            role="super_admin",  # smuggled field -- must be a loud rejection, not silently dropped
        )


def test_school_create_rejects_an_invalid_board_value():
    with pytest.raises(ValidationError):
        SchoolCreate(
            name="X", coordinator_full_name="Y", coordinator_email="y@example.local",
            board="Cambridge",
        )


def test_school_create_accepts_a_valid_board_value():
    school = SchoolCreate(
        name="X", coordinator_full_name="Y", coordinator_email="y@example.local", board="IB",
    )
    assert school.board == "IB"


def test_school_update_allows_every_field_to_be_omitted():
    update = SchoolUpdate()
    assert update.model_dump(exclude_unset=True) == {}


def test_school_create_validates_the_new_contact_email_format():
    with pytest.raises(ValidationError):
        SchoolCreate(
            name="X", coordinator_full_name="Y", coordinator_email="y@example.local",
            email="not-an-email",
        )
