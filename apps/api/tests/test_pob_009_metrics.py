"""pob-009 T2/T8 -- the PO figures (backlog Appendix B), each credited to the person who did the work, and the contacts drill-down whose
replied ÷ rows equals the response rate (AC1). The shared test database is never truncated, so every figure is asserted on fresh POs."""

from datetime import datetime, time, timedelta

import pytest

from app.models import CompanyVendorStatusHistory, RecruiterCall, RecruiterMessage
from app.services import recruiter_metrics as metrics
from app.services.bdm_appointments import IST, today_ist
from tests.rec001_helpers import make_pm, make_recruiter
from tests.test_rec_034_by_recruiter import _application, _company, _contact, _job, _joined, _meeting, _now


def _period():
    today = today_ist(_now())
    return today.replace(day=1), today


def _before():
    return datetime.combine(today_ist(_now()).replace(day=1), time.min, tzinfo=IST) - timedelta(hours=1)


def _msg(db, contact, sender, channel="whatsapp", at=None, replied=None, **extra):
    fields = {"subject": "Hi", "delivery_status": "sent"} if channel == "email" else {"linkedin_action": "message"} if channel == "linkedin" else {}
    db.add(RecruiterMessage(company_id=contact.company_id, contact_id=contact.id, sender_user_id=sender.id, channel=channel, body="Hello",
                            sent_at=at or _now(), replied_at=replied, **fields, **extra))


def _call(db, contact, caller, direction="outgoing", at=None):
    db.add(RecruiterCall(company_id=contact.company_id, contact_id=contact.id, caller_user_id=caller.id, occurred_at=at or _now(), direction=direction, outcome="connected"))


async def _pos(db, size=2):
    manager = await make_pm(db)
    return [await make_recruiter(db, manager) for _ in range(size)]


@pytest.mark.asyncio
async def test_outreach_and_response_rate_follow_appendix_b(db_session):
    db = db_session
    me, peer = await _pos(db)
    company = await _company(db, me)
    a, b, c, d = [await _contact(db, company) for _ in range(4)]
    _msg(db, a, me, "email", replied=_now())  # reached + replied
    _msg(db, a, me, "linkedin")  # second outreach to the same contact
    _call(db, b, me)  # reached by an outgoing call, no reply
    _call(db, c, me, direction="incoming")  # an incoming call is not outreach
    _msg(db, c, peer, replied=_now())  # peer's outreach and reply are peer's
    _msg(db, d, me, at=_before(), replied=_now())  # reached only last month: its reply is outside this period's reach
    await db.flush()

    first, last = _period()
    counts = await metrics.po_counts(db, [me.id, peer.id], first, last)
    assert counts[me.id]["outreach"] == 3
    assert counts[me.id]["contacts_reached"] == 2
    assert counts[me.id]["responses"] == 1
    assert counts[me.id]["response_rate"] == 50
    assert (counts[peer.id]["outreach"], counts[peer.id]["responses"], counts[peer.id]["response_rate"]) == (1, 1, 100)

    drill = await metrics.po_contacts(db, me.id, first, last, limit=50, offset=0)
    assert drill["total"] == 2 and drill["responses"] == 1
    assert sum(row["replied"] for row in drill["items"]) * 100 // len(drill["items"]) == counts[me.id]["response_rate"]
    assert {row["contact"]["id"]: row["outreach"] for row in drill["items"]} == {a.id: 2, b.id: 1}


@pytest.mark.asyncio
async def test_no_contact_reached_has_no_rate(db_session):
    (me,) = await _pos(db_session, size=1)
    first, last = _period()
    counts = await metrics.po_counts(db_session, [me.id], first, last)
    assert counts[me.id] == {key: 0 for key in metrics.PO_KPIS} | {"contacts_reached": 0, "response_rate": None}


@pytest.mark.asyncio
async def test_meetings_requirements_vendors_accounts_and_placements(db_session):
    db = db_session
    me, peer = await _pos(db)
    client = await _company(db, me, client_status="active_client")
    _meeting(db, client, peer, completed_by=me)  # credited to who completed it
    _meeting(db, client, me, completed_by=me, at=_before())  # last month
    job = await _job(db, client, me, creator=me)  # a requirement + an open requirement for the active account
    await _company(db, me, client_status="repeat_business")  # no open requirement: not active
    closed = await _company(db, me, client_status="active_client")
    await _job(db, closed, me, creator=peer, status="closed")
    vendor = await _company(db, me, partner_type="vendor", vendor_status="approved")
    db.add(CompanyVendorStatusHistory(company_id=vendor.id, from_status="registration_submitted", to_status="approved", actor_user_id=me.id))
    db.add(CompanyVendorStatusHistory(company_id=vendor.id, from_status="prospect", to_status="registration_submitted", actor_user_id=me.id))
    await _joined(db, await _application(db, job, peer), me)
    await db.flush()

    first, last = _period()
    counts = await metrics.po_counts(db, [me.id, peer.id], first, last)
    mine = {key: counts[me.id][key] for key in ("meetings", "requirements", "vendor_registrations", "active_accounts", "placements")}
    assert mine == {"meetings": 1, "requirements": 1, "vendor_registrations": 1, "active_accounts": 1, "placements": 1}
    assert counts[peer.id]["requirements"] == 1 and counts[peer.id]["placements"] == 0
