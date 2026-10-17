"""AGN-024 final review: /auth/register refuses non-JSON/non-form bodies (login CSRF via text/plain, I1) and throttles agent signups to
5 per client IP per rolling hour (K11, DEC-SCOPE-224)."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select, update
from starlette.requests import Request

from app.core.client_ip import client_ip
from app.models import AuditLog, User
from app.services.storage import storage
from tests.agn001_helpers import PASSWORD, uniq
from tests.agn024_helpers import REGISTER, agent_form, ip_headers, kyc_files

THROTTLED_IP = "203.0.113.7"


async def _users_with(db, email: str) -> int:
    return await db.scalar(select(func.count()).select_from(User).where(User.email == email.lower()))


def _student(**overrides) -> dict:
    return {"email": f"{uniq('guard')}@example.local", "password": PASSWORD, "full_name": "Guard Student", "division": "overseas", **overrides}


def _ip_rows(ip: str):
    return (AuditLog.action == "auth.register", AuditLog.metadata_json["ip"].as_string() == ip)


@pytest.mark.asyncio
async def test_text_plain_json_body_is_415_and_creates_nothing(client, db_session):
    body = _student()
    response = await client.post(REGISTER, content=json.dumps(body), headers={"Content-Type": "text/plain"})
    assert response.status_code == 415 and response.json()["detail"] == "Unsupported content type"
    assert await _users_with(db_session, body["email"]) == 0
    assert "edusphere_access" not in response.cookies


@pytest.mark.asyncio
async def test_missing_content_type_is_415(client, db_session):
    body = _student()
    response = await client.post(REGISTER, content=json.dumps(body).encode())
    assert "content-type" not in response.request.headers
    assert response.status_code == 415 and await _users_with(db_session, body["email"]) == 0


@pytest.mark.asyncio
async def test_json_student_signup_is_unchanged(client, db_session):
    plain = await client.post(REGISTER, json=_student())
    assert plain.status_code == 201 and plain.json()["user"]["role"] == "overseas_student"
    body = _student()
    charset = await client.post(REGISTER, content=json.dumps(body), headers={"Content-Type": "application/json; charset=utf-8"})
    assert charset.status_code == 201 and await _users_with(db_session, body["email"]) == 1


@pytest.mark.asyncio
async def test_sixth_agent_signup_from_one_ip_in_an_hour_is_429(client, db_session, monkeypatch):
    await db_session.execute(delete(AuditLog).where(*_ip_rows(THROTTLED_IP)))  # the test DB outlives a run; start this IP clean
    await db_session.commit()
    headers = {"X-Forwarded-For": f"{THROTTLED_IP}, 10.0.0.2"}  # leftmost entry is the client (Caddy -> Next -> API)
    for _ in range(5):
        ok = await client.post(REGISTER, data=agent_form(), files=kyc_files(), headers=headers)
        assert ok.status_code == 201, ok.text
    rows = (await db_session.scalars(select(AuditLog).where(*_ip_rows(THROTTLED_IP)))).all()
    assert len(rows) == 5 and all(r.metadata_json["role"] == "agent" and "ABCDE1234F" not in str(r.metadata_json) for r in rows)

    written: list[str] = []
    real_write = storage.write_bytes
    monkeypatch.setattr(storage, "write_bytes", lambda key, data, ct: written.append(key))
    form = agent_form()
    blocked = await client.post(REGISTER, data=form, files=kyc_files(), headers=headers)
    assert blocked.status_code == 429 and blocked.json()["detail"] == "Too many registrations from this network -- try again later"
    assert 0 < int(blocked.headers["Retry-After"]) <= 3600
    assert written == [] and await _users_with(db_session, form["email"]) == 0
    monkeypatch.setattr(storage, "write_bytes", real_write)

    other = await client.post(REGISTER, data=agent_form(), files=kyc_files(), headers=ip_headers())
    assert other.status_code == 201
    student = await client.post(REGISTER, json=_student(), headers=headers)  # students are never throttled
    assert student.status_code == 201

    await db_session.execute(update(AuditLog).where(*_ip_rows(THROTTLED_IP)).values(created_at=datetime.now(UTC) - timedelta(minutes=61)))
    await db_session.commit()
    again = await client.post(REGISTER, data=agent_form(), files=kyc_files(), headers=headers)  # the window rolled past them
    assert again.status_code == 201


@pytest.mark.asyncio
async def test_student_signups_do_not_record_an_ip(client, db_session):
    response = await client.post(REGISTER, json=_student(), headers=ip_headers())
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "auth.register", AuditLog.entity_id == response.json()["user"]["id"]))
    assert "ip" not in audit.metadata_json


def _request(xff: str | None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff is not None else []
    return Request({"type": "http", "method": "POST", "path": "/", "headers": headers, "client": ("172.18.0.7", 40000)})


@pytest.mark.parametrize(
    "xff,expected",
    [
        ("203.0.113.7", "203.0.113.7"),
        ("203.0.113.7, 172.18.0.1", "203.0.113.7"),
        (" 2001:DB8::1 ", "2001:db8::1"),
        ("not-an-ip, 203.0.113.7", "172.18.0.7"),
        ("", "172.18.0.7"),
        (None, "172.18.0.7"),
    ],
)
def test_client_ip_is_the_leftmost_valid_forwarded_entry_else_the_peer(xff, expected):
    assert client_ip(_request(xff)) == expected
