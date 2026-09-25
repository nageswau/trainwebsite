"""ENH-023 (DEC-SCOPE-030) -- tier-change rules and grandfathering, without a database."""

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


from datetime import UTC, date, datetime  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from uuid import uuid4  # noqa: E402

from fastapi import HTTPException  # noqa: E402
from test_enh_022_tier_rules import USER, FakeDB  # noqa: E402

from app.api import schools  # noqa: E402
from app.api.schools import _grandfathers, require_school_entitlement  # noqa: E402

TODAY = date(2026, 9, 23)
SINCE = datetime(2026, 9, 1, tzinfo=UTC)
DOWNGRADE = {"direction": "downgrade", "from_tier": "platinum", "to_tier": "gold", "lost": ["visa_support", "internships"]}
REMOVAL = {"direction": "downgrade", "from_tier": "bronze", "to_tier": None, "lost": ["career_seminar"]}


def test_grandfathers_matches_only_a_lost_service_of_a_downgrade():
    assert _grandfathers(DOWNGRADE, "visa_support")
    assert not _grandfathers(DOWNGRADE, "ielts_coaching")
    assert not _grandfathers({"direction": "upgrade", "lost": ["visa_support"]}, "visa_support")
    assert not _grandfathers({"tier": "gold"}, "visa_support")  # a row written before ENH-023


def test_free_text_work_is_grandfathered_only_by_a_removal():
    assert _grandfathers(REMOVAL, None)
    assert not _grandfathers(DOWNGRADE, None)


@pytest.mark.asyncio
async def test_grandfathered_write_is_allowed_and_audited_uncommitted(monkeypatch):
    monkeypatch.setattr(schools, "_today_ist", lambda: TODAY)
    calls = []

    async def lost(db, school_id, key, since):
        calls.append((key, since))
        return True

    monkeypatch.setattr(schools, "_lost_since", lost)
    school_id = uuid4()
    db = FakeDB(SimpleNamespace(id=school_id, tier="gold", tier_valid_until=None))
    await require_school_entitlement(db, USER, school_id, "visa_support", grandfathered_since=SINCE)
    assert calls == [("visa_support", SINCE)]
    # D14: one grandfather row, left for the route's own commit; never a denial row, never a commit here.
    assert db.commits == 0 and len(db.added) == 1
    row = db.added[0]
    assert (row.action, row.entity_type, row.entity_id) == ("school.tier_grandfathered", "school", str(school_id))
    assert row.metadata_json == {"service_key": "visa_support", "reason": "not_included", "tier": "gold", "grandfathered_since": SINCE.isoformat()}


@pytest.mark.asyncio
async def test_without_an_anchor_the_lookup_never_runs(monkeypatch):
    monkeypatch.setattr(schools, "_today_ist", lambda: TODAY)

    async def lost(*_):
        raise AssertionError("must not be called")

    monkeypatch.setattr(schools, "_lost_since", lost)
    db = FakeDB(SimpleNamespace(id=uuid4(), tier="gold", tier_valid_until=None))
    with pytest.raises(HTTPException):
        await require_school_entitlement(db, USER, uuid4(), "visa_support")
    assert db.commits == 1


@pytest.mark.asyncio
async def test_expired_is_never_grandfathered(monkeypatch):
    monkeypatch.setattr(schools, "_today_ist", lambda: TODAY)

    async def lost(*_):
        return True

    monkeypatch.setattr(schools, "_lost_since", lost)
    expired = FakeDB(SimpleNamespace(id=uuid4(), tier="platinum", tier_valid_until=date(2026, 9, 1)))
    with pytest.raises(HTTPException) as exc:
        await require_school_entitlement(expired, USER, uuid4(), "visa_support", grandfathered_since=SINCE)
    assert exc.value.detail.startswith("This school's partnership expired on")
    removed_after_expiry = FakeDB(SimpleNamespace(id=uuid4(), tier=None, tier_valid_until=date(2026, 9, 1)))
    with pytest.raises(HTTPException):
        await require_school_entitlement(removed_after_expiry, USER, uuid4(), "visa_support", grandfathered_since=SINCE)


@pytest.mark.asyncio
async def test_not_lost_after_the_anchor_is_still_denied(monkeypatch):
    monkeypatch.setattr(schools, "_today_ist", lambda: TODAY)

    async def lost(*_):
        return False

    monkeypatch.setattr(schools, "_lost_since", lost)
    db = FakeDB(SimpleNamespace(id=uuid4(), tier="gold", tier_valid_until=None))
    with pytest.raises(HTTPException) as exc:
        await require_school_entitlement(db, USER, uuid4(), "visa_support", grandfathered_since=SINCE)
    assert exc.value.status_code == 403 and db.commits == 1
