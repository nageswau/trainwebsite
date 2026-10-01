import pytest

from app.services.agent_orgs import MASTER_LIMIT, derive_prefix_base, member_code, pick_prefix


@pytest.mark.parametrize(("name", "expected"), [
    ("ABC Overseas Consultants", "ABC"),
    ("abc overseas", "ABC"),
    ("A1 Consultants", "ACO"),
    ("AB", "ABX"),
    ("A", "AXX"),
    ("12 34", "AGT"),
    ("शिक्षा", "AGT"),
    ("", "AGT"),
    (None, "AGT"),
    ("E2E Agent", "EEA"),
])
def test_prefix_base_follows_d5(name, expected):
    assert derive_prefix_base(name) == expected


def test_pick_prefix_uses_the_base_when_free():
    assert pick_prefix("ABC", set()) == "ABC"
    assert pick_prefix("ABC", {"ABD", "XYZ"}) == "ABC"


def test_pick_prefix_takes_the_lowest_free_suffix_from_2():
    assert pick_prefix("ABC", {"ABC"}) == "ABC2"
    assert pick_prefix("ABC", {"ABC", "ABC2", "ABC4"}) == "ABC3"


def test_member_code_is_zero_padded():
    assert member_code("ABC", 1) == "ABC-M001"
    assert member_code("ABC2", 12) == "ABC2-M012"
    assert member_code("ABC", 1000) == "ABC-M1000"


def test_the_master_limit_is_three():
    assert MASTER_LIMIT == 3
