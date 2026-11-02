"""itc-008 (spec docs/superpowers/specs/2026-11-02-itc-008-lead-filters-telecaller-tiles-design.md): the telecaller lead list's source,
last-contact and next-follow-up filters (F1-F4). India-time days, inclusive; a reversed range is 422; every filter only narrows the
caller's scope. The shared database is never truncated, so every test narrows to rows it created (a unique `q`)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Enquiry, LeadCall, LeadFollowUp, LeadMessage
from app.services.bdm_activities import day_range
from app.services.bdm_appointments import db_now, today_ist
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager

pytestmark = pytest.mark.asyncio

TEL_LEADS = "/api/v1/telecaller/leads"
# 2026-10-20 23:59 and 2026-10-21 00:01 India time (UTC+05:30) -- the IST day boundary (E)
LATE = datetime(2026, 10, 20, 18, 29, tzinfo=UTC)
EARLY = datetime(2026, 10, 20, 18, 31, tzinfo=UTC)


def tag() -> str:
    return f"i08{uuid.uuid4().hex[:10]}"


async def add(db, *rows):
    db.add_all(rows)
    await db.commit()
    return rows[0] if len(rows) == 1 else rows


async def lead(db, name: str, **over) -> Enquiry:
    values = {
        "division": "it",
        "name": name,
        "email": f"{uuid.uuid4().hex[:8]}@example.local",
        "phone": "9876543210",
        "subject": "Python",
        "message": "Hello there",
        "source": "website",
        "status": "assigned",
    } | over
    return await add(db, Enquiry(**values))


def call(row, user, at) -> LeadCall:
    return LeadCall(lead_id=row.id, caller_user_id=user.id, occurred_at=at, duration_seconds=30, call_type="outgoing", outcome="interested")


def follow_up(row, user, due, **over) -> LeadFollowUp:
    return LeadFollowUp(**({"lead_id": row.id, "due_at": due, "reason": "fee_details", "created_by_user_id": user.id} | over))


async def names(client, t: str, **params) -> list[str]:
    response = await client.get(TEL_LEADS, params={"q": t, **params})
    assert response.status_code == 200, response.text
    return sorted(item["name"] for item in response.json()["items"])


async def caller(db):
    manager = await make_tl_manager(db)
    return manager, await make_telecaller(db, manager)


async def test_source_filter_narrows_inside_the_scope_and_refuses_an_unknown_source(client, db_session):
    t = tag()
    _, tel = await caller(db_session)
    await lead(db_session, f"Insta {t}", source="instagram", telecaller_user_id=tel.id)
    await lead(db_session, f"Web {t}", source="website", telecaller_user_id=tel.id)
    await lead(db_session, f"Stranger {t}", source="instagram")  # unassigned: never in a telecaller's own scope
    await as_user(client, tel)
    assert await names(client, t, source="instagram") == [f"Insta {t}"]
    assert await names(client, t) == [f"Insta {t}", f"Web {t}"]
    assert (await client.get(TEL_LEADS, params={"source": "carrier_pigeon"})).status_code == 422


async def test_last_contact_is_the_later_of_the_latest_call_and_message_by_india_day(client, db_session):
    t = tag()
    _, tel = await caller(db_session)
    both = await lead(db_session, f"Both {t}", telecaller_user_id=tel.id)
    called = await lead(db_session, f"Called {t}", telecaller_user_id=tel.id)
    await lead(db_session, f"Never {t}", telecaller_user_id=tel.id)
    await add(
        db_session,
        call(both, tel, LATE - timedelta(days=3)),
        LeadMessage(lead_id=both.id, sender_user_id=tel.id, channel="whatsapp", body="Hi", sent_at=EARLY),  # last contact: 21 Oct
        call(called, tel, LATE - timedelta(days=1)),
        call(called, tel, LATE),
    )  # last contact: 20 Oct 23:59 IST
    await as_user(client, tel)
    assert await names(client, t, last_contact_from="2026-10-20", last_contact_to="2026-10-20") == [f"Called {t}"]
    assert await names(client, t, last_contact_from="2026-10-21") == [f"Both {t}"]
    assert await names(client, t, last_contact_to="2026-10-20") == [f"Called {t}"]  # an earlier call never matches once a later one exists
    assert await names(client, t, last_contact_from="2026-10-01", last_contact_to="2026-10-31") == [f"Both {t}", f"Called {t}"]  # never contacted: no range
    reversed_range = await client.get(TEL_LEADS, params={"last_contact_from": "2026-10-21", "last_contact_to": "2026-10-20"})
    assert reversed_range.status_code == 422
    assert (await client.get(TEL_LEADS, params={"last_contact_from": "21-10-2026"})).status_code == 422


async def test_next_follow_up_is_the_earliest_open_one_and_takes_tomorrow(client, db_session):
    t = tag()
    _, tel = await caller(db_session)
    soon = await lead(db_session, f"Soon {t}", telecaller_user_id=tel.id)
    later = await lead(db_session, f"Later {t}", telecaller_user_id=tel.id)
    tomorrow_lead = await lead(db_session, f"Tomorrow {t}", telecaller_user_id=tel.id)
    await lead(db_session, f"None {t}", telecaller_user_id=tel.id)
    tomorrow = today_ist(await db_now(db_session)) + timedelta(days=1)
    await add(
        db_session,
        follow_up(soon, tel, EARLY),
        follow_up(soon, tel, EARLY + timedelta(days=4)),  # next: 21 Oct
        follow_up(later, tel, EARLY, status="cancelled", cancelled_at=LATE, cancel_reason="x"),  # not open: ignored
        follow_up(later, tel, EARLY + timedelta(days=1)),  # next: 22 Oct
        follow_up(tomorrow_lead, tel, day_range(tomorrow)[0] + timedelta(hours=6)),
    )
    await as_user(client, tel)
    assert await names(client, t, next_follow_up_from="2026-10-21", next_follow_up_to="2026-10-21") == [f"Soon {t}"]
    assert await names(client, t, next_follow_up_from="2026-10-22", next_follow_up_to="2026-10-31") == [f"Later {t}"]
    assert await names(client, t, next_follow_up_to="2026-10-20") == []  # 20 Oct 23:59 IST is before every due time (E)
    day = tomorrow.isoformat()
    assert await names(client, t, next_follow_up_from=day, next_follow_up_to=day) == [f"Tomorrow {t}"]  # "+": next follow-up = tomorrow
    reversed_range = await client.get(TEL_LEADS, params={"next_follow_up_from": "2026-10-22", "next_follow_up_to": "2026-10-21"})
    assert reversed_range.status_code == 422


async def test_the_managers_export_takes_and_audits_the_new_filters(client, db_session):
    t = tag()
    manager, tel = await caller(db_session)
    row = await lead(db_session, f"Export {t}", source="google", telecaller_user_id=tel.id)
    await lead(db_session, f"Other {t}", source="website", telecaller_user_id=tel.id)
    await add(db_session, call(row, tel, LATE))
    await as_user(client, manager)
    params = {"q": t, "source": "google", "last_contact_from": "2026-10-20", "last_contact_to": "2026-10-20"}
    assert sorted(item["name"] for item in (await client.get(TEL_LEADS, params=params)).json()["items"]) == [f"Export {t}"]
    response = await client.get(f"{TEL_LEADS}.xlsx", params=params)
    assert response.status_code == 200, response.text
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.user_id == manager.id, AuditLog.action == "crm.export"))
    assert audit.metadata_json["filters"] == {"q": True, "source": "google", "last_contact_from": "2026-10-20", "last_contact_to": "2026-10-20"}
    assert audit.metadata_json["rows"] == 1
