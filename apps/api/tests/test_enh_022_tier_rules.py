"""ENH-022 (DEC-SCOPE-027) -- tier rules and the enforcement helper, without a database."""

import datetime as real_datetime
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from app.api import schools
from app.api.schools import TIER_DENIED, _entitlement_denial, _minimum_tier, require_school_entitlement

TODAY = date(2026, 9, 23)
NO_TIER = "This school has no active partnership tier."


def test_minimum_tier_is_the_first_tier_that_lists_the_key():
    assert _minimum_tier("psychometric_test") == "bronze"
    assert _minimum_tier("web_designing") == "silver"
    assert _minimum_tier("ielts_coaching") == "gold"
    assert _minimum_tier("visa_support") == "platinum"


def test_unknown_service_key_is_a_programming_error():
    with pytest.raises(ValueError):
        _minimum_tier("ielts")
    with pytest.raises(ValueError):
        _entitlement_denial("platinum", None, "not_a_service", TODAY)


@pytest.mark.parametrize("tier", [None, "", "diamond"])
def test_no_or_unknown_tier_is_denied(tier):
    assert _entitlement_denial(tier, None, "psychometric_test", TODAY) == ("no_tier", NO_TIER)
    assert _entitlement_denial(tier, None, None, TODAY) == ("no_tier", NO_TIER)


def test_minimum_tier_allows_and_one_below_denies_with_exact_message():
    assert _entitlement_denial("gold", None, "ielts_coaching", TODAY) is None
    assert _entitlement_denial("silver", None, "ielts_coaching", TODAY) == (
        "not_included",
        "This school's Silver partnership does not include IELTS coaching (requires Gold or higher).",
    )


def test_tiers_are_cumulative():
    assert _entitlement_denial("platinum", None, "career_seminar", TODAY) is None
    assert _entitlement_denial("silver", None, "soft_skills", TODAY) is None


def test_expiry_is_inclusive_and_null_never_expires():
    assert _entitlement_denial("platinum", TODAY, "visa_support", TODAY) is None
    assert _entitlement_denial("platinum", None, "visa_support", TODAY) is None
    assert _entitlement_denial("platinum", date(2026, 9, 22), "visa_support", TODAY) == (
        "expired",
        "This school's partnership expired on 22 Sep 2026.",
    )


def test_any_valid_tier_check():
    assert _entitlement_denial("bronze", None, None, TODAY) is None
    assert _entitlement_denial("bronze", date(2026, 1, 1), None, TODAY)[0] == "expired"


def test_today_is_the_india_date(monkeypatch):
    class FakeDateTime(real_datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            # 18:31 UTC on 22 Sep is 00:01 IST on 23 Sep.
            return real_datetime.datetime(2026, 9, 22, 18, 31, tzinfo=real_datetime.UTC).astimezone(tz)

    monkeypatch.setattr(schools, "datetime", FakeDateTime)
    assert schools._today_ist() == date(2026, 9, 23)


class FakeDB:
    """Just enough of AsyncSession for the helper: get / add / commit / rollback."""

    def __init__(self, school, fail_commit=False):
        self.school, self.fail_commit = school, fail_commit
        self.added, self.commits, self.rollbacks = [], 0, 0

    async def get(self, model, key):
        return self.school

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        if self.fail_commit:
            raise OperationalError("COMMIT", {}, Exception("connection lost"))
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


USER = SimpleNamespace(id=uuid4(), role="school_coordinator")


@pytest.mark.asyncio
async def test_allowed_request_writes_nothing(monkeypatch):
    monkeypatch.setattr(schools, "_today_ist", lambda: TODAY)
    db = FakeDB(SimpleNamespace(tier="gold", tier_valid_until=None))
    await require_school_entitlement(db, USER, uuid4(), "ielts_coaching")
    assert db.added == [] and db.commits == 0


@pytest.mark.asyncio
async def test_denial_commits_one_audit_row_then_raises_403(monkeypatch):
    monkeypatch.setattr(schools, "_today_ist", lambda: TODAY)
    school_id = uuid4()
    db = FakeDB(SimpleNamespace(tier="bronze", tier_valid_until=None))
    with pytest.raises(HTTPException) as exc:
        await require_school_entitlement(db, USER, school_id, "monthly_campus_visits")
    assert exc.value.status_code == 403
    assert exc.value.detail == "This school's Bronze partnership does not include Monthly campus visits (requires Platinum or higher)."
    assert db.commits == 1 and len(db.added) == 1
    audit = db.added[0]
    assert (audit.action, audit.entity_type, audit.entity_id, audit.outcome) == (TIER_DENIED, "school", str(school_id), "denied")
    assert audit.metadata_json == {"service_key": "monthly_campus_visits", "reason": "not_included", "tier": "bronze"}


@pytest.mark.asyncio
async def test_missing_school_is_denied_not_a_500(monkeypatch):
    monkeypatch.setattr(schools, "_today_ist", lambda: TODAY)
    db = FakeDB(None)
    with pytest.raises(HTTPException) as exc:
        await require_school_entitlement(db, USER, uuid4(), None)
    assert (exc.value.status_code, exc.value.detail) == (403, NO_TIER)


@pytest.mark.asyncio
async def test_a_failed_audit_commit_still_denies(monkeypatch):
    monkeypatch.setattr(schools, "_today_ist", lambda: TODAY)
    db = FakeDB(SimpleNamespace(tier=None, tier_valid_until=None), fail_commit=True)
    with pytest.raises(HTTPException) as exc:
        await require_school_entitlement(db, USER, uuid4(), "career_seminar")
    assert exc.value.status_code == 403
    assert db.rollbacks == 1
