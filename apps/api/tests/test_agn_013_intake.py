"""AGN-013 (DEC-SCOPE-052 E2) -- the best-effort intake parser and the enrollment date check; pure functions."""

from datetime import date
from types import SimpleNamespace

import pytest

from app.services.agent_applications import enrollment_check, intake_end


@pytest.mark.parametrize(
    ("text", "end"),
    [
        ("Sep 2027", date(2027, 9, 30)),
        ("Sept. 2027", date(2027, 9, 30)),
        ("September 2027", date(2027, 9, 30)),
        ("february 2028", date(2028, 2, 29)),
        ("09/2027", date(2027, 9, 30)),
        ("9-2027", date(2027, 9, 30)),
        ("2027-09", date(2027, 9, 30)),
        ("2027/1", date(2027, 1, 31)),
        ("Intake: Jan 2028 (main)", date(2028, 1, 31)),
    ],
)
def test_intake_end_recognises_month_and_year(text, end):
    assert intake_end(text) == end


@pytest.mark.parametrize("text", [None, "", "Next intake", "Fall 2027", "Spring", "13/2027", "2027", "Sep 1999", "Mayday 2027"])
def test_intake_end_returns_none_when_unrecognised(text):
    assert intake_end(text) is None


TODAY = date(2026, 10, 2)


@pytest.mark.parametrize(
    ("enrolled", "intake", "expected"),
    [
        (None, "Sep 2027", None),
        (date(2027, 9, 15), "Sep 2027", None),
        (date(2027, 10, 1), "Sep 2027", "after_intake"),
        (date(2026, 9, 1), "Jan 2026", None),  # after the intake, but not in the future
        (date(2027, 10, 1), "Next intake", "intake_unrecognised"),
    ],
)
def test_enrollment_check(enrolled, intake, expected):
    assert enrollment_check(SimpleNamespace(enrollment_date=enrolled, intake=intake), TODAY) == expected
