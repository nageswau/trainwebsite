"""SEC-002 -- GDPR self-service export/delete.

`consent capture at data-collection points` is already satisfied by STU-009's
`ConsentRecord` (the enrolment agreement) -- no other data-collection point is named
anywhere in evidence as requiring its own consent capture, so nothing new was built for
that half. The genuinely net-new half is `DataSubjectRequest` (DATA_MODEL.md #7.4,
API_CONTRACT.md #11): `POST /account/data-requests` (export|delete, idempotent on
`Idempotency-Key`), `GET /account/data-requests/{id}` (status polling), `GET
/account/data-requests/{id}/export` (signed download once fulfilled), and an Admin
fulfil/reject endpoint for deletion requests that pass the one concrete, evidence-backed
retention-hold rule (DATA_MODEL.md #8: never hard-delete a user with existing
Payment/ConsentRecord rows). Exact retention periods stay open (PRD_OPEN_ITEMS.md item 15)
and are not invented -- only presence of an existing hold is checked.
"""

import uuid

import pytest

from app.core.security import hash_password
from app.models import ConsentRecord, Payment, User


async def _create_user(db_session, *, role: str = "it_student", division: str = "it") -> User:
    user = User(
        email=f"sec002-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Privacy Tester",
        role=role,
        division=division,
        active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_export_request_is_fulfilled_immediately_and_downloadable(db_session, client):
    user = await _create_user(db_session)
    await _login(client, user.email)

    response = await client.post("/api/v1/account/data-requests", json={"type": "export"}, headers={"Idempotency-Key": uuid.uuid4().hex})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "fulfilled"

    download = await client.get(f"/api/v1/account/data-requests/{body['id']}/export")
    assert download.status_code == 200
    assert download.json()["url"]


@pytest.mark.asyncio
async def test_data_request_requires_idempotency_key(db_session, client):
    user = await _create_user(db_session)
    await _login(client, user.email)

    response = await client.post("/api/v1/account/data-requests", json={"type": "export"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_repeating_the_same_idempotency_key_returns_the_same_request_not_a_duplicate(db_session, client):
    user = await _create_user(db_session)
    await _login(client, user.email)
    key = uuid.uuid4().hex

    first = await client.post("/api/v1/account/data-requests", json={"type": "export"}, headers={"Idempotency-Key": key})
    second = await client.post("/api/v1/account/data-requests", json={"type": "export"}, headers={"Idempotency-Key": key})
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.asyncio
async def test_reusing_an_idempotency_key_for_a_different_type_is_a_conflict(db_session, client):
    user = await _create_user(db_session)
    await _login(client, user.email)
    key = uuid.uuid4().hex

    await client.post("/api/v1/account/data-requests", json={"type": "export"}, headers={"Idempotency-Key": key})
    response = await client.post("/api/v1/account/data-requests", json={"type": "delete"}, headers={"Idempotency-Key": key})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_delete_request_is_rejected_not_silently_dropped_when_a_payment_exists(db_session, client):
    user = await _create_user(db_session)
    db_session.add(Payment(user_id=user.id, division="it", reference_type="enrollment", amount=1000, status="paid"))
    await db_session.commit()
    await _login(client, user.email)

    response = await client.post("/api/v1/account/data-requests", json={"type": "delete"}, headers={"Idempotency-Key": uuid.uuid4().hex})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason"]


@pytest.mark.asyncio
async def test_delete_request_with_no_holds_is_queued_for_admin_review(db_session, client):
    user = await _create_user(db_session)
    await _login(client, user.email)

    response = await client.post("/api/v1/account/data-requests", json={"type": "delete"}, headers={"Idempotency-Key": uuid.uuid4().hex})
    assert response.status_code == 201
    assert response.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_admin_can_fulfil_a_queued_deletion_request(db_session, client):
    user = await _create_user(db_session)
    await _login(client, user.email)
    created = await client.post("/api/v1/account/data-requests", json={"type": "delete"}, headers={"Idempotency-Key": uuid.uuid4().hex})
    request_id = created.json()["id"]

    admin = await _create_user(db_session, role="it_admin")
    await _login(client, admin.email)
    response = await client.patch(f"/api/v1/admin/data-requests/{request_id}", json={"decision": "fulfil"})
    assert response.status_code == 200
    assert response.json()["status"] == "fulfilled"

    await db_session.refresh(user)
    assert user.active is False
    assert user.full_name == "Deleted user"


@pytest.mark.asyncio
async def test_a_request_only_ever_exposes_the_requesting_users_own_data(db_session, client):
    owner = await _create_user(db_session)
    other = await _create_user(db_session)
    await _login(client, owner.email)
    created = await client.post("/api/v1/account/data-requests", json={"type": "export"}, headers={"Idempotency-Key": uuid.uuid4().hex})
    request_id = created.json()["id"]

    await _login(client, other.email)
    response = await client.get(f"/api/v1/account/data-requests/{request_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_data_requests_endpoints_require_authentication(client):
    assert (await client.post("/api/v1/account/data-requests", json={"type": "export"}, headers={"Idempotency-Key": uuid.uuid4().hex})).status_code == 401
    assert (await client.get(f"/api/v1/account/data-requests/{uuid.uuid4()}")).status_code == 401


@pytest.mark.asyncio
async def test_non_admin_cannot_fulfil_a_deletion_request(db_session, client):
    user = await _create_user(db_session)
    await _login(client, user.email)
    created = await client.post("/api/v1/account/data-requests", json={"type": "delete"}, headers={"Idempotency-Key": uuid.uuid4().hex})
    request_id = created.json()["id"]

    response = await client.patch(f"/api/v1/admin/data-requests/{request_id}", json={"decision": "fulfil"})
    assert response.status_code == 403
