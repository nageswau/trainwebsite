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


from app.api.admin import _tier_notices  # noqa: E402 -- grouped with the notice tests


def test_upgrade_notice_lists_what_became_available():
    (title, body), (admin_title, admin_body) = _tier_notices("Oak School", tier_change_payload("gold", "platinum"))
    assert title == "Your partnership is now Platinum"
    assert body.startswith("Oak School has moved from Gold to Platinum. Newly available: Dedicated EduSphere counselor, Monthly campus visits")
    assert admin_title == "Tier change recorded: Oak School, Gold → Platinum"
    assert admin_body.startswith("Newly available: Dedicated EduSphere counselor")


def test_downgrade_and_removal_notices_promise_completion():
    (title, body), (admin_title, _) = _tier_notices("Oak School", tier_change_payload("platinum", "gold"))
    assert title == "Your partnership changed from Platinum to Gold"
    assert body.startswith("These services are no longer available for new work: Dedicated EduSphere counselor")
    assert body.endswith("Work already started for them can still be completed.")
    (removed, _), _ = _tier_notices("Oak School", tier_change_payload("bronze", None))
    assert removed == "Your partnership changed from Bronze to no partnership tier"


def test_long_school_name_is_cut_to_the_title_limit():
    (_, _), (admin_title, _) = _tier_notices("S" * 200, tier_change_payload("gold", "platinum"))
    assert len(admin_title) == 180
