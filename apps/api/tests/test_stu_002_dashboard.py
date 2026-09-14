"""STU-002 -- Student dashboard.

Covers: the dashboard aggregates enrolment/attendance/payments/applied-jobs/assignments
in one view, and that a failed data source for one widget does not block the rest
(STU-002-AC02) -- verified by making a real query raise and confirming both (a) the
response still succeeds with the other widgets intact, and (b) the failure doesn't
poison the session for whatever runs after it.
"""

import uuid
from unittest.mock import patch

import pytest

from app.core.security import hash_password
from app.models import User
from app.services import portal as portal_service


async def _create_student(db_session) -> User:
    student = User(
        email=f"dash-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Dashboard Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.commit()
    return student


async def _login(client, email: str):
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "it"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_dashboard_aggregates_required_widgets(client, db_session):
    student = await _create_student(db_session)
    await _login(client, student.email)

    response = await client.get("/api/v1/portal/it/student/dashboard")
    assert response.status_code == 200
    labels = {m["label"] for m in response.json()["metrics"]}
    assert {"Course progress", "Attendance", "Pending fee", "Applied jobs", "Enrollments"} <= labels


@pytest.mark.asyncio
async def test_dashboard_survives_a_failed_widget_query(client, db_session):
    """STU-002-AC02, exercised for real: force the payments-due query to raise and
    confirm the dashboard still returns 200 with every other widget intact, the failed
    one marked "Unavailable" (not silently zero), and the session isn't left unusable."""
    student = await _create_student(db_session)
    await _login(client, student.email)

    real_safe = portal_service._safe
    call_count = {"n": 0}

    async def flaky_safe(db, fn, default):
        call_count["n"] += 1
        if call_count["n"] == 3:  # the "Pending fee" (due) computation, by call order
            async def failing():
                raise RuntimeError("simulated payments-table outage")

            return await real_safe(db, failing, default)
        return await real_safe(db, fn, default)

    with patch.object(portal_service, "_safe", side_effect=flaky_safe):
        response = await client.get("/api/v1/portal/it/student/dashboard")

    assert response.status_code == 200
    metrics = {m["label"]: m["value"] for m in response.json()["metrics"]}
    assert metrics["Pending fee"] == "Unavailable"
    # Every other widget, computed via calls before/after the forced failure, is intact.
    assert metrics["Course progress"].endswith("%")
    assert metrics["Applied jobs"] != "Unavailable"
    assert metrics["Enrollments"] == 0


@pytest.mark.asyncio
async def test_safe_helper_does_not_poison_the_session_for_later_queries(db_session):
    """Direct unit coverage of the resilience mechanism itself: a failure inside
    `_safe` must not leave the outer transaction unusable for whatever query follows
    it in the same request -- this is the actual risk `_safe`'s SAVEPOINT exists to
    avoid (a plain, unguarded exception mid-transaction would poison it under Postgres)."""
    from sqlalchemy import select

    from app.models import User as UserModel

    async def boom():
        raise RuntimeError("simulated failure")

    result = await portal_service._safe(db_session, boom, "fallback")
    assert result == "fallback"

    # The session must still be usable for a completely unrelated query afterward.
    follow_up = await db_session.scalar(select(UserModel).limit(1))
    assert follow_up is None or follow_up.id is not None


@pytest.mark.asyncio
async def test_dashboard_requires_authentication(client):
    assert (await client.get("/api/v1/portal/it/student/dashboard")).status_code == 401


@pytest.mark.asyncio
async def test_dashboard_with_no_data_yet_shows_sane_defaults_not_errors(client, db_session):
    student = await _create_student(db_session)
    await _login(client, student.email)
    response = await client.get("/api/v1/portal/it/student/dashboard")
    assert response.status_code == 200
    metrics = {m["label"]: m["value"] for m in response.json()["metrics"]}
    assert metrics["Enrollments"] == 0
    assert metrics["Attendance"] == "0%"
    assert response.json()["rows"] == []
