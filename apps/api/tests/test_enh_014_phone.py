"""ENH-014 Task 2 -- E.164 normalisation, default country India (spec §6.3, D14). No I/O: plain unit tests."""

import pytest

from app.notifications.phone import normalise_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+91 98765 43210", "+919876543210"),
        ("+44 (20) 7946-0958", "+442079460958"),
        ("98765 43210", "+919876543210"),
        ("098765-43210", "+919876543210"),
        ("91 9876543210", "+919876543210"),
        ("919876543210", "+919876543210"),
        ("+1.415.555.2671", "+14155552671"),
    ],
)
def test_valid_numbers_normalise_to_e164(raw, expected):
    assert normalise_phone(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "12345", "5876543210", "+12", "+1234567890123456", "call me", "+91 98765 4321x", "++919876543210"])
def test_invalid_numbers_return_none(raw):
    assert normalise_phone(raw) is None


def test_non_ascii_digits_and_blank_are_invalid():
    # Review Focus 1: str.isdigit() accepts Devanagari digits; they must not pass as a number.
    assert normalise_phone("९८७६५४३२१०") is None
    assert normalise_phone("+९१९८७६५४३२१०") is None
