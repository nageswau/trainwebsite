"""ENH-009 / DEC-SCOPE-025 -- SchoolCreate/SchoolUpdate/SchoolOut schema behavior."""

from datetime import date

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


def test_school_create_accepts_local_domain_email():
    """ENH-009 fix: .local addresses (used throughout the test suite and demo data)
    must be accepted for the School.email field, not rejected by EmailStr."""
    school = SchoolCreate(
        name="X",
        coordinator_full_name="Y",
        coordinator_email="y@example.local",
        email="school@example.local",
    )
    assert school.email == "school@example.local"


def test_school_create_email_max_length_matches_its_column():
    """ENH-009 final review: `max_length` was 320 while `schools.email` is VARCHAR(255), so a
    256-360 character address passed validation and only failed at the database layer with a
    raw StringDataRightTruncation -- the exact QA-001 anti-pattern `_fit()` exists to prevent.
    A syntactically valid address of 256 characters must now be a ValidationError."""
    too_long = "a" * 256 + "@example.local"
    assert len(too_long) < 320
    with pytest.raises(ValidationError):
        SchoolCreate(
            name="X", coordinator_full_name="Y", coordinator_email="y@example.local",
            email=too_long,
        )
    with pytest.raises(ValidationError):
        SchoolUpdate(email=too_long)


def test_school_create_accepts_tier_valid_until():
    """ENH-009 final review: restored so POST stays additive-compatible with the pre-ENH-009
    dict-bodied create_school(), which parsed `tier_valid_until` via date.fromisoformat."""
    school = SchoolCreate(
        name="X", coordinator_full_name="Y", coordinator_email="y@example.local",
        tier="gold", tier_valid_until="2027-06-30",
    )
    assert school.tier_valid_until == date(2027, 6, 30)
    assert SchoolCreate(name="X", coordinator_full_name="Y", coordinator_email="y@example.local").tier_valid_until is None
