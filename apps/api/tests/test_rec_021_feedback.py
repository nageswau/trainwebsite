"""rec-021 -- interview feedback (spec §2-§3; AC1, AC2; DEC-SCOPE-175 FB1-FB8). The shared test database is never truncated, so every
value is unique per test; a completed interview is made by moving its time back in the database, then marking it Completed."""

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, InterviewEvent
from app.services import interviews as svc
from tests.rec001_helpers import as_role, login, make_recruiter
from tests.test_rec_020_interviews import INTERVIEWS, _app_status, _interview, _move, _setup, _to_past

FULL = {
    "technical_rating": 4,
    "communication_rating": 3,
    "overall_rating": 4,
    "strengths": "Solid Java fundamentals",
    "weaknesses": "Little cloud exposure",
    "recruiter_comments": "Recommend the manager round",
    "company_feedback": "Client liked the problem solving",
    "next_round": "manager_round",
    "final_decision": "selected",
}


def _url(interview_id) -> str:
    return f"{INTERVIEWS}/{interview_id}/feedback"


async def _completed(client, db, round_="hr_round", **setup) -> tuple[dict, dict]:
    s = await _setup(client, db, **setup)
    item = await _interview(client, s["application"]["id"], round=round_)
    await _to_past(db, item["id"])
    assert (await _move(client, item["id"], "completed")).status_code == 200
    return s, item


async def _save(client, interview_id, **over):
    return await client.put(_url(interview_id), json=FULL | over)


# --- AC1 / FB2: only a Completed interview ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_feedback_is_refused_before_the_interview_is_completed(client, db_session):
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"])
    assert item["feedback"] is None and item["can_feedback"] is False
    response = await _save(client, item["id"])
    assert response.status_code == 409 and "Completed" in response.json()["detail"]
    await _to_past(db_session, item["id"])
    assert (await _move(client, item["id"], "no_show")).status_code == 200
    assert (await _save(client, item["id"])).status_code == 409  # a No Show was never held


@pytest.mark.asyncio
async def test_ac1_a_completed_interview_takes_feedback_and_ac2_suggests_the_next_round(client, db_session):
    s, item = await _completed(client, db_session)
    assert (await client.get(f"{INTERVIEWS}/{item['id']}")).json()["can_feedback"] is True
    response = await _save(client, item["id"])
    assert response.status_code == 200, response.text
    saved = response.json()["interview"]
    fb = saved["feedback"]
    assert {k: fb[k] for k in FULL} == FULL
    assert (fb["next_round_label"], fb["final_decision_label"]) == ("Manager Round", "Selected")
    assert fb["recorded_by"]["id"] == str(s["recruiter"].id) and fb["updated_at"]
    # FB4: the decision set the status, through rec-020's move with its history; an HR round's Selected keeps the application (IV8)
    assert saved["status"] == "selected" and saved["can_feedback"] is True
    assert (saved["history"][-1]["from_status"], saved["history"][-1]["to_status"], saved["history"][-1]["note"]) == ("completed", "selected", "Feedback")
    assert await _app_status(db_session, s["application"]["id"]) == "interview"


# --- FB3: validation ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "over, field",
    [
        ({"overall_rating": 6}, "overall_rating"),
        ({"technical_rating": 0}, "technical_rating"),
        ({"communication_rating": 6}, "communication_rating"),
        ({"overall_rating": None}, "overall_rating"),
        ({"next_round": "lunch_round"}, "next_round"),
        ({"final_decision": "maybe"}, "final_decision"),
        ({"final_decision": "rejected", "next_round": "manager_round"}, "next_round"),
        ({"strengths": "x" * 2001}, "strengths"),
        ({"status": "selected"}, "status"),
    ],
)
async def test_invalid_feedback_is_422_on_its_field(client, db_session, over, field):
    _s, item = await _completed(client, db_session)
    response = await _save(client, item["id"], **over)
    assert response.status_code == 422
    assert field in [e["loc"][-1] for e in response.json()["detail"]]


@pytest.mark.asyncio
async def test_only_the_overall_rating_is_required(client, db_session):
    _s, item = await _completed(client, db_session)
    response = await client.put(_url(item["id"]), json={"overall_rating": 3})
    assert response.status_code == 200, response.text
    saved = response.json()["interview"]
    assert saved["status"] == "completed"  # no decision moves nothing
    assert saved["feedback"]["overall_rating"] == 3 and saved["feedback"]["strengths"] is None and saved["feedback"]["final_decision"] is None


# --- FB4: the decision and the application (IV8) ------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rejected_rejects_the_application(client, db_session):
    s, item = await _completed(client, db_session)
    response = await _save(client, item["id"], final_decision="rejected", next_round=None)
    assert response.json()["interview"]["status"] == "rejected"
    assert await _app_status(db_session, s["application"]["id"]) == "rejected"


@pytest.mark.asyncio
async def test_selected_on_a_final_round_selects_the_application(client, db_session):
    s, item = await _completed(client, db_session, round_="final_round")
    assert (await _save(client, item["id"], next_round=None)).json()["interview"]["status"] == "selected"
    assert await _app_status(db_session, s["application"]["id"]) == "selected"


@pytest.mark.asyncio
async def test_on_hold_then_a_decision_but_a_decided_interview_keeps_its_decision(client, db_session):
    _s, item = await _completed(client, db_session)
    assert (await _save(client, item["id"], final_decision="on_hold")).json()["interview"]["status"] == "on_hold"
    assert (await _save(client, item["id"], final_decision="selected")).json()["interview"]["status"] == "selected"
    response = await _save(client, item["id"], final_decision="rejected", next_round=None)
    assert response.status_code == 409
    assert (await client.get(f"{INTERVIEWS}/{item['id']}")).json()["feedback"]["final_decision"] == "selected"  # nothing saved
    edited = await _save(client, item["id"], strengths="Strong SQL too")  # the same decision: the text can still be edited
    assert edited.status_code == 200 and edited.json()["interview"]["feedback"]["strengths"] == "Strong SQL too"


@pytest.mark.asyncio
async def test_an_on_hold_interview_that_was_never_completed_takes_no_feedback(client, db_session):
    s = await _setup(client, db_session)
    item = await _interview(client, s["application"]["id"])
    assert (await _move(client, item["id"], "on_hold")).status_code == 200
    assert (await _save(client, item["id"], final_decision=None)).status_code == 409


# --- FB1: one current row, audit names only -------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_feedback_is_overwritten_and_audited_by_field_name_only(client, db_session):
    _s, item = await _completed(client, db_session)
    await _save(client, item["id"], final_decision=None)
    await _save(client, item["id"], final_decision=None, weaknesses="None noted")
    await _save(client, item["id"], final_decision=None, weaknesses="None noted")  # unchanged: no audit row
    audits = (
        (await db_session.execute(select(AuditLog.metadata_json).where(AuditLog.action == "recruiter_interview.feedback", AuditLog.entity_id == item["id"]).order_by(AuditLog.created_at)))
        .scalars()
        .all()
    )
    assert len(audits) == 2
    assert audits[1]["fields"] == ["weaknesses"]
    assert "None noted" not in str(audits) and "Java" not in str(audits)
    events = await db_session.scalar(select(func.count()).select_from(InterviewEvent).where(InterviewEvent.interview_id == item["id"]))
    assert events == 2  # scheduled + completed: feedback without a decision adds no history


# --- FB8: who -----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_reads_feedback_but_cannot_write_and_another_recruiter_gets_404(client, db_session):
    s, item = await _completed(client, db_session)
    await _save(client, item["id"], final_decision=None)
    await login(client, s["manager"])
    read = (await client.get(f"{INTERVIEWS}/{item['id']}")).json()
    assert read["feedback"]["overall_rating"] == 4 and read["can_feedback"] is False
    assert (await _save(client, item["id"])).status_code == 403
    stranger = await make_recruiter(db_session, s["manager"])
    await login(client, stranger)
    assert (await _save(client, item["id"])).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("role, division", [("hr_team", "it"), ("it_admin", "it"), ("employer", "it"), ("it_student", "it")])
async def test_other_roles_are_refused(client, db_session, role, division):
    _s, item = await _completed(client, db_session)
    await as_role(client, db_session, role, division)
    assert (await _save(client, item["id"])).status_code == 403


@pytest.mark.asyncio
async def test_unknown_interview_is_404(client, db_session):
    await _setup(client, db_session)
    assert (await _save(client, "00000000-0000-0000-0000-000000000000")).status_code == 404


def test_labels_cover_the_catalogue():
    from app.models import FEEDBACK_DECISIONS

    assert svc.FEEDBACK_EDITABLE == ("completed", *FEEDBACK_DECISIONS)
    assert all(svc.STATUS_LABELS[d] for d in FEEDBACK_DECISIONS)
