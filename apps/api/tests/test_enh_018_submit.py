import asyncio
import logging
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from enh005_helpers import login, mk_school, mk_user
from enh018_helpers import FEEDBACK, URL, mk_activity
from httpx import ASGITransport
from sqlalchemy import func, select

from app.main import app
from app.models import AuditLog, SchoolActivityFeedback

# ENH-018 spec §5.1 / AC1-AC4: a coordinator submits feedback once per completed Edusphere activity of their own school.


async def _rows(db, activity):
    return (await db.scalars(select(SchoolActivityFeedback).where(SchoolActivityFeedback.activity_id == activity.id))).all()


@pytest.mark.asyncio
async def test_coordinator_submits_all_fields_for_a_past_typed_activity(client, db_session):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    await login(client, s["coordinator"].email)
    response = await client.post(URL.format(aid=activity.id), json=FEEDBACK)
    assert response.status_code == 201, response.text
    body = response.json()
    assert {k: body[k] for k in FEEDBACK} == FEEDBACK
    assert body["activity_id"] == str(activity.id) and body["submitted_by_name"] == s["coordinator"].full_name and body["submitted_at"]
    [row] = await _rows(db_session, activity)
    assert row.school_id == s["school"].id and row.submitted_by_user_id == s["coordinator"].id


@pytest.mark.asyncio
async def test_submission_writes_one_audit_row_with_ids_and_scores_only(client, db_session):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    await login(client, s["coordinator"].email)
    await client.post(URL.format(aid=activity.id), json=FEEDBACK)
    [audit] = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.activity_feedback_submit", AuditLog.entity_id == str(activity.id)))).all()
    assert audit.user_id == s["coordinator"].id and audit.entity_type == "school_activity"
    assert audit.metadata_json["rating"] == 4 and audit.metadata_json["satisfaction"] == 5 and audit.metadata_json["school_id"] == str(s["school"].id)
    flat = str(audit.metadata_json)
    for text in (FEEDBACK["feedback"], FEEDBACK["suggestions"], FEEDBACK["trainer_name"]):
        assert text not in flat


@pytest.mark.asyncio
async def test_another_schools_activity_and_an_unknown_id_are_the_same_404(client, db_session):
    a = await mk_school(db_session, label="A")
    b = await mk_school(db_session, label="B")
    theirs = await mk_activity(db_session, b["school"], b["coordinator"])
    await login(client, a["coordinator"].email)
    for aid in (theirs.id, uuid4()):
        response = await client.post(URL.format(aid=aid), json=FEEDBACK)
        assert (response.status_code, response.json()["detail"]) == (404, "Activity not found")
    assert await _rows(db_session, theirs) == []


@pytest.mark.asyncio
async def test_untyped_school_event_is_rejected(client, db_session):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"], activity_type=None)
    await login(client, s["coordinator"].email)
    response = await client.post(URL.format(aid=activity.id), json=FEEDBACK)
    assert (response.status_code, response.json()["detail"]) == (422, "Feedback is only collected for Edusphere activities")


@pytest.mark.asyncio
async def test_eligibility_boundary_one_minute_either_side_of_now(client, db_session):
    s = await mk_school(db_session, label="A")
    past = await mk_activity(db_session, s["school"], s["coordinator"], minutes=-1)
    future = await mk_activity(db_session, s["school"], s["coordinator"], minutes=1)
    await login(client, s["coordinator"].email)
    assert (await client.post(URL.format(aid=past.id), json=FEEDBACK)).status_code == 201
    response = await client.post(URL.format(aid=future.id), json=FEEDBACK)
    assert (response.status_code, response.json()["detail"]) == (422, "Feedback opens once the activity has taken place")


@pytest.mark.asyncio
async def test_second_submission_is_409_and_the_first_is_unchanged(client, db_session):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    await login(client, s["coordinator"].email)
    assert (await client.post(URL.format(aid=activity.id), json=FEEDBACK)).status_code == 201
    response = await client.post(URL.format(aid=activity.id), json={**FEEDBACK, "rating": 1})
    assert (response.status_code, response.json()["detail"]) == (409, "Feedback has already been submitted for this activity")
    [row] = await _rows(db_session, activity)
    assert row.rating == 4


@asynccontextmanager
async def _client_for(email: str):
    """A separate ASGI client with its own cookie jar, so requests are genuinely in flight at once (ENH-005 pattern)."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await login(c, email)
        yield c


@pytest.mark.asyncio
async def test_concurrent_submissions_store_exactly_one_row(db_session):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    async with _client_for(s["coordinator"].email) as one, _client_for(s["coordinator"].email) as two:
        results = await asyncio.gather(*(c.post(URL.format(aid=activity.id), json=FEEDBACK) for c in (one, two, one, two)))
    assert sorted(r.status_code for r in results) == [201, 409, 409, 409]
    assert len(await _rows(db_session, activity)) == 1
    audits = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.activity_feedback_submit", AuditLog.entity_id == str(activity.id)))
    assert audits == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_principal", "school_teacher", "school_parent", "overseas_admin", "super_admin", "career_counselor"])
async def test_only_a_coordinator_may_submit(client, db_session, role):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    other = await mk_user(db_session, role=role, name=f"{role} user", school_id=s["school"].id, assigned_by=s["admin"])
    await db_session.commit()
    await login(client, other.email)
    assert (await client.post(URL.format(aid=activity.id), json=FEEDBACK)).status_code == 403
    assert await _rows(db_session, activity) == []


@pytest.mark.asyncio
async def test_unlinked_coordinator_and_anonymous_caller_are_refused(client, db_session):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    client.cookies.clear()
    assert (await client.post(URL.format(aid=activity.id), json=FEEDBACK)).status_code == 401
    orphan = await mk_user(db_session, role="school_coordinator", name="Unlinked Coordinator", assigned_by=s["admin"])
    await db_session.commit()
    await login(client, orphan.email)
    assert (await client.post(URL.format(aid=activity.id), json=FEEDBACK)).status_code == 403


@pytest.mark.asyncio
async def test_invalid_body_is_422_and_stores_nothing(client, db_session):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    await login(client, s["coordinator"].email)
    for body in ({**FEEDBACK, "rating": 6}, {**FEEDBACK, "feedback": "   "}, {**FEEDBACK, "school_id": str(uuid4())}):
        assert (await client.post(URL.format(aid=activity.id), json=body)).status_code == 422
    assert await _rows(db_session, activity) == []


@pytest.mark.asyncio
async def test_logs_carry_ids_and_never_the_free_text(client, db_session, caplog):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    await login(client, s["coordinator"].email)
    # An in-process Alembic run earlier in the session (ENH-001's tests) disables existing loggers; see ENH-003's same guard.
    logging.getLogger("app.school.feedback").disabled = False
    with caplog.at_level(logging.INFO, logger="app.school.feedback"):
        await client.post(URL.format(aid=activity.id), json=FEEDBACK)
        await client.post(URL.format(aid=activity.id), json=FEEDBACK)
    records = [r for r in caplog.records if r.name == "app.school.feedback"]
    assert {"activity_feedback_submitted", "activity_feedback_duplicate"} <= {r.getMessage() for r in records}
    dumped = " ".join(str(getattr(r, "extra_fields", "")) for r in records)
    assert str(activity.id) in dumped
    for text in (FEEDBACK["feedback"], FEEDBACK["suggestions"], FEEDBACK["trainer_name"]):
        assert text not in dumped
