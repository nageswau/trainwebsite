import json
import logging
import re

import pytest
from enh005_helpers import login, mk_school
from sqlalchemy import select

from app.api import school_transfers
from app.models import Notification, SchoolStudentTransferRequest

# ENH-005 security review S8 (logs), S9 (CSRF: no state-changing GET) and the safe-link rule for notifications (AC-30, AC-31, AC-32).

SAFE_URL = re.compile(r"^/school/[a-z-]+(/[a-z-]+)*(/[0-9a-f-]{36})?$")


@pytest.fixture(autouse=True)
def _app_loggers_enabled():
    """Alembic's env.py calls `logging.config.fileConfig`, which DISABLES loggers that already exist; an earlier test that migrates
    in-process would silence `app.*` and `caplog` would see nothing (the order-dependence ENH-004's tests found)."""
    for name in ("app.school", "app.school.transfers", "app.auth"):
        logging.getLogger(name).disabled = False
    yield


def _transfer_routes():
    # The two routers' own route objects: on this FastAPI version `app.routes` does not flatten included routers, and the HTTP tests in
    # the other ENH-005 files already prove both routers are registered.
    return [*school_transfers.coordinator_router.routes, *school_transfers.admin_router.routes]


def test_every_mutating_transfer_route_is_a_post_and_no_get_changes_state():
    """Cookies are SameSite=Lax, which sends them on top-level cross-site GET navigations: so a state change must never be a GET (S9)."""
    routes = _transfer_routes()
    assert len(routes) == 10
    by_name = {r.endpoint.__name__: set(r.methods) for r in routes}
    reads = {"transfer_destinations", "list_my_transfer_requests", "student_transfer_history", "admin_list_transfer_requests", "admin_student_transfer_history"}
    writes = {"file_outgoing_request", "file_incoming_request", "cancel_transfer_request", "approve_transfer_request", "reject_transfer_request"}
    assert set(by_name) == reads | writes
    assert all(by_name[n] == {"GET"} for n in reads)
    assert all(by_name[n] == {"POST"} for n in writes)


def _flatten(record) -> str:
    return record.getMessage() + " " + json.dumps(getattr(record, "extra_fields", {}), default=str)


@pytest.mark.asyncio
async def test_no_log_record_or_notification_link_leaks_a_code_reason_note_name_or_email(client, db_session, caplog, monkeypatch):
    a = await mk_school(db_session, label="A", students=2)
    b = await mk_school(db_session, label="B", students=0)
    kid, sibling = a["students"]
    secrets = ["SECRET-REASON-ONE", "SECRET-REASON-TWO", "SECRET-NOTE", kid.student_code, sibling.student_code, kid.full_name, sibling.full_name]
    secrets += [a["coordinator"].email, b["coordinator"].email, a["parent"].email, a["admin"].email, a["parent"].full_name]
    caplog.set_level(logging.DEBUG)

    await login(client, a["coordinator"].email)
    outgoing = await client.post(f"/api/v1/school/students/{kid.id}/transfer-requests", json={"to_school_id": str(b["school"].id), "reason": "SECRET-REASON-ONE"})
    assert outgoing.status_code == 201, outgoing.text
    await login(client, b["coordinator"].email)
    assert (await client.post("/api/v1/school/transfer-requests/incoming", json={"student_code": sibling.student_code, "reason": "SECRET-REASON-TWO"})).status_code == 202
    assert (await client.post("/api/v1/school/transfer-requests/incoming", json={"student_code": "00000000"})).status_code == 202
    incoming = await db_session.scalar(select(SchoolStudentTransferRequest).where(SchoolStudentTransferRequest.school_student_id == sibling.id))
    assert (await client.post(f"/api/v1/school/transfer-requests/{incoming.id}/cancel")).status_code == 200
    await login(client, a["admin"].email)
    assert (await client.post(f"/api/v1/overseas-admin/school-transfer-requests/{outgoing.json()['id']}/approve")).status_code == 200
    again = await client.post("/api/v1/school/transfer-requests/incoming", json={"student_code": "00000001"})  # (an admin is not a coordinator)
    assert again.status_code == 403
    await login(client, b["coordinator"].email)  # the throttle warning
    monkeypatch.setattr(school_transfers, "TRANSFER_FILINGS_PER_HOUR", 1)
    assert (await client.post("/api/v1/school/transfer-requests/incoming", json={"student_code": "00000002"})).status_code == 429
    # a rejection with a note, on a fresh request
    await login(client, a["coordinator"].email)
    monkeypatch.setattr(school_transfers, "TRANSFER_FILINGS_PER_HOUR", 30)
    extra = await client.post(f"/api/v1/school/students/{sibling.id}/transfer-requests", json={"to_school_id": str(b["school"].id)})
    await login(client, a["admin"].email)
    assert (await client.post(f"/api/v1/overseas-admin/school-transfer-requests/{extra.json()['id']}/reject", json={"note": "SECRET-NOTE"})).status_code == 200

    records = [r for r in caplog.records if r.name.startswith("app.school")]
    assert {r.getMessage() for r in records} >= {"transfer_request_filed", "transfer_incoming_attempt", "transfer_request_cancelled", "student_transfer_approved", "transfer_request_rejected", "transfer_filing_throttled"}
    text = " ".join(_flatten(r) for r in records)
    for secret in secrets:
        assert secret not in text, secret
    notification_urls = [n.action_url for n in (await db_session.scalars(select(Notification))).all() if n.title and ("transfer" in n.title.lower() or kid.full_name in n.title)]
    assert notification_urls and all(u is None or SAFE_URL.match(u) for u in notification_urls), notification_urls
