"""ENH-023 (DEC-SCOPE-029) -- tier-change rules and grandfathering, without a database."""

import pytest

from app.api.schools import TIER_SERVICES, TIER_UPDATE, _tier_name, _tier_transition, tier_change_payload

BRONZE = [k for k, _ in TIER_SERVICES["bronze"]]
SILVER = [k for k, _ in TIER_SERVICES["silver"]]
GOLD = [k for k, _ in TIER_SERVICES["gold"]]
PLATINUM = [k for k, _ in TIER_SERVICES["platinum"]]


def test_action_name_is_the_existing_tier_update_action():
    assert TIER_UPDATE == "school.tier_update"


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (None, "bronze", ("upgrade", BRONZE, [])),
        ("gold", "platinum", ("upgrade", PLATINUM, [])),
        (None, "gold", ("upgrade", BRONZE + SILVER + GOLD, [])),
        ("platinum", "gold", ("downgrade", [], PLATINUM)),
        ("silver", None, ("downgrade", [], BRONZE + SILVER)),
        ("platinum", "bronze", ("downgrade", [], SILVER + GOLD + PLATINUM)),
        ("gold", "gold", ("unchanged", [], [])),
        (None, None, ("unchanged", [], [])),
        ("diamond", "bronze", ("upgrade", BRONZE, [])),
    ],
)
def test_tier_transition_truth_table(old, new, expected):
    assert _tier_transition(old, new) == expected


def test_tier_name_capitalises_and_names_the_absence_of_a_tier():
    assert _tier_name("gold") == "Gold"
    assert _tier_name(None) == "no partnership tier"
    assert _tier_name("diamond") == "no partnership tier"


def test_tier_change_payload_carries_labels_in_tier_services_order():
    payload = tier_change_payload("platinum", "gold")
    assert payload["direction"] == "downgrade"
    assert (payload["from_tier"], payload["to_tier"]) == ("platinum", "gold")
    assert payload["gained"] == []
    assert payload["lost"][0] == {"key": "dedicated_counselor", "label": "Dedicated EduSphere counselor"}
    assert [s["key"] for s in payload["lost"]] == PLATINUM
