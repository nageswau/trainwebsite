"""ENH-023 (DEC-SCOPE-029) -- tier changes and grandfathered work against a real database."""

import logging
from datetime import date, timedelta
from uuid import UUID

import pytest
from enh005_helpers import login, mk_school, mk_staff
from sqlalchemy import func, select

from app.api.schools import TIER_DENIED, TIER_SERVICES, TIER_UPDATE
from app.models import AuditLog

SCHOOLS = "/api/v1/overseas-admin/schools"
PLATINUM = [k for k, _ in TIER_SERVICES["platinum"]]
EXPIRED_ON = date.today() - timedelta(days=2)
NO_TIER = "This school has no active partnership tier."


async def world(db, tier, staff_role=None, students=1) -> dict:
    w = await mk_school(db, label="T23", tier=tier, students=students)
    if staff_role:
        w["staff"] = await mk_staff(db, w["school"], w["admin"], role=staff_role)
    return w


async def change_tier(client, w, **body) -> dict:
    """PATCH the tier as the school's Overseas Admin (the only sanctioned tier change)."""
    await login(client, w["admin"].email)
    r = await client.patch(f"{SCHOOLS}/{w['school'].id}", json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def tier_rows(db, school_id) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.action == TIER_UPDATE, AuditLog.entity_id == str(school_id)).order_by(AuditLog.created_at)
    return list((await db.scalars(stmt)).all())


async def denials(db, school_id) -> int:
    return await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == TIER_DENIED, AuditLog.entity_id == str(school_id)))


# --- The transition record (AC-1..AC-4, AC-9) ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_downgrade_records_the_transition_and_returns_tier_change(client, db_session):
    w = await world(db_session, "platinum")
    body = await change_tier(client, w, tier="gold")
    assert body["tier"] == "gold"
    assert body["tier_change"]["direction"] == "downgrade"
    assert [s["key"] for s in body["tier_change"]["lost"]] == PLATINUM
    [row] = await tier_rows(db_session, w["school"].id)
    assert row.metadata_json == {
        "tier": "gold", "from_tier": "platinum", "to_tier": "gold", "direction": "downgrade",
        "gained": [], "lost": PLATINUM, "tier_valid_until": None, "previous_tier_valid_until": None,
    }


@pytest.mark.asyncio
async def test_upgrade_records_gained_services(client, db_session):
    w = await world(db_session, "gold")
    body = await change_tier(client, w, tier="platinum")
    assert body["tier_change"]["direction"] == "upgrade"
    [row] = await tier_rows(db_session, w["school"].id)
    assert (row.metadata_json["from_tier"], row.metadata_json["gained"], row.metadata_json["lost"]) == ("gold", PLATINUM, [])


@pytest.mark.asyncio
async def test_same_tier_and_valid_until_only_are_unchanged(client, db_session):
    w = await world(db_session, "gold")
    same = await change_tier(client, w, tier="gold")
    only_date = await change_tier(client, w, tier_valid_until="2027-03-31")
    assert same["tier_change"]["direction"] == only_date["tier_change"]["direction"] == "unchanged"
    rows = await tier_rows(db_session, w["school"].id)
    assert [r.metadata_json["direction"] for r in rows] == ["unchanged", "unchanged"]
    assert rows[1].metadata_json["tier_valid_until"] == "2027-03-31"
    assert rows[1].metadata_json["previous_tier_valid_until"] is None


@pytest.mark.asyncio
async def test_profile_only_patch_has_no_tier_change(client, db_session):
    w = await world(db_session, "gold")
    body = await change_tier(client, w, branch="North")
    assert body["tier_change"] is None
    assert body["branch"] == "North"
    assert await tier_rows(db_session, w["school"].id) == []


@pytest.mark.asyncio
async def test_down_then_up_keeps_both_transitions(client, db_session):
    w = await world(db_session, "platinum")
    await change_tier(client, w, tier="gold")
    await change_tier(client, w, tier="platinum")
    rows = await tier_rows(db_session, w["school"].id)
    assert [(r.metadata_json["from_tier"], r.metadata_json["to_tier"]) for r in rows] == [("platinum", "gold"), ("gold", "platinum")]


@pytest.mark.asyncio
async def test_invalid_tier_is_still_422_and_records_nothing(client, db_session):
    w = await world(db_session, "gold")
    await login(client, w["admin"].email)
    r = await client.patch(f"{SCHOOLS}/{w['school'].id}", json={"tier": "diamond"})
    assert (r.status_code, r.json()["detail"]) == (422, "tier must be one of bronze, silver, gold, platinum")
    assert await tier_rows(db_session, w["school"].id) == []


# --- Precondition, empty string, typed contract (D12, D13, AC-15..AC-17) ----------------------------------------------


@pytest.mark.asyncio
async def test_stale_expected_tier_is_409_and_writes_nothing(client, db_session):
    w = await world(db_session, "platinum")
    await login(client, w["admin"].email)
    r = await client.patch(f"{SCHOOLS}/{w['school'].id}", json={"tier": "gold", "expected_tier": "bronze"})
    assert r.status_code == 409
    assert r.json()["detail"] == "This school's tier changed to Platinum since you looked it up. Look it up again before changing the tier."
    await db_session.refresh(w["school"])
    assert w["school"].tier == "platinum"
    assert await tier_rows(db_session, w["school"].id) == []


@pytest.mark.asyncio
async def test_matching_expected_tier_saves_and_is_not_a_profile_field(client, db_session):
    w = await world(db_session, "platinum")
    body = await change_tier(client, w, tier="gold", expected_tier="platinum")
    assert body["tier_change"]["direction"] == "downgrade"
    profile_rows = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.profile_update", AuditLog.entity_id == str(w["school"].id)))
    assert profile_rows == 0


@pytest.mark.asyncio
async def test_expected_tier_empty_string_means_tierless(client, db_session):
    w = await world(db_session, None)
    body = await change_tier(client, w, tier="bronze", expected_tier="")
    assert body["tier_change"]["direction"] == "upgrade"
    await login(client, w["admin"].email)
    bad = await client.patch(f"{SCHOOLS}/{w['school'].id}", json={"tier": "gold", "expected_tier": "diamond"})
    assert (bad.status_code, bad.json()["detail"]) == (422, "tier must be one of bronze, silver, gold, platinum")


@pytest.mark.asyncio
async def test_empty_string_tier_is_stored_as_a_removal(client, db_session):
    w = await world(db_session, "gold")
    body = await change_tier(client, w, tier="")
    assert body["tier"] is None
    assert body["tier_change"]["to_tier"] is None
    [row] = await tier_rows(db_session, w["school"].id)
    assert (row.metadata_json["to_tier"], row.metadata_json["tier"], row.metadata_json["direction"]) == (None, None, "downgrade")


@pytest.mark.asyncio
async def test_openapi_documents_the_typed_tier_change(client):
    spec = (await client.get("/openapi.json")).json()
    patch = spec["paths"]["/api/v1/overseas-admin/schools/{school_id}"]["patch"]
    assert patch["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/SchoolUpdateOut")
    direction = spec["components"]["schemas"]["TierChangeOut"]["properties"]["direction"]
    assert set(direction["enum"]) == {"upgrade", "downgrade", "unchanged"}


# --- Preview (AC-5) ----------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_reports_a_downgrade_and_writes_nothing(client, db_session):
    w = await world(db_session, "platinum")
    await login(client, w["admin"].email)
    r = await client.get(f"{SCHOOLS}/{w['school'].id}/tier-change-preview", params={"tier": "gold"})
    assert r.status_code == 200
    assert r.json()["direction"] == "downgrade"
    assert [s["key"] for s in r.json()["lost"]] == PLATINUM
    assert await tier_rows(db_session, w["school"].id) == []
    await db_session.refresh(w["school"])
    assert w["school"].tier == "platinum"


@pytest.mark.asyncio
async def test_preview_empty_tier_means_removal(client, db_session):
    w = await world(db_session, "silver")
    await login(client, w["admin"].email)
    r = await client.get(f"{SCHOOLS}/{w['school'].id}/tier-change-preview", params={"tier": ""})
    assert (r.json()["direction"], r.json()["to_tier"]) == ("downgrade", None)
    assert len(r.json()["lost"]) == 7


@pytest.mark.asyncio
async def test_preview_errors(client, db_session):
    w = await world(db_session, "gold")
    await login(client, w["coordinator"].email)
    assert (await client.get(f"{SCHOOLS}/{w['school'].id}/tier-change-preview", params={"tier": "gold"})).status_code == 403
    await login(client, w["admin"].email)
    missing = await client.get(f"{SCHOOLS}/00000000-0000-0000-0000-000000000000/tier-change-preview", params={"tier": "gold"})
    assert missing.status_code == 404
    bad = await client.get(f"{SCHOOLS}/{w['school'].id}/tier-change-preview", params={"tier": "diamond"})
    assert (bad.status_code, bad.json()["detail"]) == (422, "tier must be one of bronze, silver, gold, platinum")


from app.api import schools  # noqa: E402
from app.models import Notification, NotificationDelivery  # noqa: E402


async def notices_for(db, user_id) -> list[Notification]:
    return list((await db.scalars(select(Notification).where(Notification.user_id == user_id))).all())


# --- Notifications (AC-1..AC-3, AC-11) ---------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upgrade_notifies_coordinator_principal_and_admin_only(client, db_session):
    w = await world(db_session, "gold")
    await change_tier(client, w, tier="platinum")
    [coord] = await notices_for(db_session, w["coordinator"].id)
    [principal] = await notices_for(db_session, w["principal"].id)
    [admin] = await notices_for(db_session, w["admin"].id)
    assert coord.title == principal.title == "Your partnership is now Platinum"
    assert "Visa support" in coord.body
    assert (coord.action_url, principal.action_url) == ("/school/coordinator/entitlements", "/school/principal/entitlements")
    assert admin.title.startswith("Tier change recorded: ") and admin.action_url is None
    assert await notices_for(db_session, w["teacher"].id) == [] and await notices_for(db_session, w["parent"].id) == []
    delivered = await db_session.scalar(select(func.count()).select_from(NotificationDelivery).where(NotificationDelivery.notification_id == coord.id, NotificationDelivery.channel == "email"))
    assert delivered == 1


@pytest.mark.asyncio
async def test_downgrade_notice_lists_lost_services(client, db_session):
    w = await world(db_session, "platinum")
    await change_tier(client, w, tier=None)
    [coord] = await notices_for(db_session, w["coordinator"].id)
    assert coord.title == "Your partnership changed from Platinum to no partnership tier"
    assert "Work already started for them can still be completed." in coord.body


@pytest.mark.asyncio
async def test_unchanged_tier_notifies_nobody(client, db_session):
    w = await world(db_session, "gold")
    await change_tier(client, w, tier="gold")
    await change_tier(client, w, tier_valid_until="2027-03-31")
    assert await notices_for(db_session, w["coordinator"].id) == []
    assert await notices_for(db_session, w["admin"].id) == []


@pytest.mark.asyncio
async def test_failing_email_never_fails_or_undoes_the_tier_change(client, db_session, monkeypatch, caplog):
    async def boom(**kwargs):
        raise RuntimeError(f"recipient refused: <{kwargs['to_email']}>")  # what real SMTP errors look like

    monkeypatch.setattr(schools, "send_parent_notification_email", boom)
    w = await world(db_session, "gold")
    with caplog.at_level(logging.WARNING, logger="app.admin"):
        body = await change_tier(client, w, tier="platinum")
    assert body["tier"] == "platinum"
    await db_session.refresh(w["school"])
    assert w["school"].tier == "platinum"
    assert len(await tier_rows(db_session, w["school"].id)) == 1
    # S1 / AC-18: ids and the error type only -- never the address the exception carried, never a traceback.
    failures = [r for r in caplog.records if r.getMessage() == "tier_change_notification_failed"]
    assert len(failures) == 3  # coordinator, principal, acting admin
    for record in failures:
        assert set(record.extra_fields) == {"school_id", "recipient_id", "error_type"}
        assert record.extra_fields["error_type"] == "RuntimeError"
        assert record.exc_info is None
        assert "@" not in str(record.extra_fields)
