"""upc-013 -- a university's communication history (spec §1-§5; DEC-SCOPE-163 TL1-TL10): the §12 example chain newest first with
actor and summary (AC), every source kind, the tie order (edge), out of scope → 404 (negative) and the readers (TL2). The shared test
database is never truncated, so every assertion is scoped to universities made here."""

import uuid
from datetime import UTC, date, datetime

import pytest

from app.models import PartnershipTask, UniversityCall, UniversityStageHistory, User
from app.services import university_timeline
from tests.test_upc_009_meetings import _move, _started, act, schedule
from tests.test_upc_010_visits import plan
from tests.test_upc_012_comms import _setup, smtp_on  # noqa: F401 -- the fixture is used by name
from tests.test_upc_014_agreements import make as make_agreement
from tests.test_upc_020_tasks import add as add_task
from tests.test_upc_026_documents import add as add_document
from tests.upc003_helpers import as_role, login, url

CALLS = "/api/v1/partnership/calls"
MESSAGES = "/api/v1/partnership/messages"


def timeline_url(university_id) -> str:
    return url(university_id, "timeline")


async def timeline(client, university_id, expected: int = 200, **params) -> dict:
    response = await client.get(timeline_url(university_id), params=params)
    assert response.status_code == expected, response.text
    return response.json()


def summary(row: dict) -> tuple:
    return row["kind"], row["event"], row["to_value"] if row["kind"] == "stage" else row["subject"]


@pytest.mark.asyncio
async def test_the_section_12_example_reads_newest_first_with_actor_and_summary(client, db_session, smtp_on):  # noqa: F811
    """AC: Email sent → Call completed → Meeting scheduled → Meeting completed → Proposal sent → Follow-up → Commercial discussion."""
    _, pm, _, uni, person = await _setup(client, db_session)
    email = await client.post(MESSAGES, json={"contact_id": person["id"], "channel": "email", "subject": "Our proposal", "body": "Dear Priya"})
    assert email.status_code == 201, email.text
    call = await client.post(CALLS, json={"contact_id": person["id"], "outcome": "connected", "duration_seconds": 125, "notes": "Spoke to Priya"})
    assert call.status_code == 201, call.text
    meeting = await schedule(client, uni["id"])
    await _started(db_session, meeting["id"])
    await act(client, meeting["id"], "complete", notes="Met the dean")
    await _move(client, uni["id"], "proposal_sent")
    await add_task(client, uni["id"], title="Follow up on the proposal")
    await _move(client, uni["id"], "commercial_discussion")

    page = await timeline(client, uni["id"])
    chain = [summary(r) for r in page["items"]]
    expected = [
        ("stage", "move", "commercial_discussion"),
        ("task", "scheduled", "Follow up on the proposal"),
        ("stage", "move", "proposal_sent"),
        ("meeting", "completed", meeting["code"]),
        ("meeting", "scheduled", meeting["code"]),
        ("call", "outgoing", None),
        ("message", "email", "Our proposal"),
    ]
    positions = [chain.index(e) for e in expected]
    assert positions == sorted(positions), chain  # the §12 order, newest first (auto-tasks may sit between)
    assert page["total"] == len(page["items"])

    by = {summary(r): r for r in page["items"]}
    for key in expected:
        assert by[key]["actor"] == {"id": str(pm.id), "full_name": pm.full_name}
    stage = by[("stage", "move", "proposal_sent")]
    assert stage["to_label"] == "Proposal Sent" and stage["from_label"]
    call_row = by[("call", "outgoing", None)]
    assert (call_row["from_value"], call_row["from_label"], call_row["to_label"]) == ("connected", "Connected", person["name"])
    assert call_row["duration_seconds"] == 125 and call_row["reason"] == "Spoke to Priya"
    message = by[("message", "email", "Our proposal")]
    assert message["to_label"] == person["name"] and message["status"] and message["reason"] == "Dear Priya"
    assert by[("meeting", "scheduled", meeting["code"])]["from_value"] == "mou_discussion"
    assert by[("meeting", "scheduled", meeting["code"])]["scheduled_for"] is not None
    task = by[("task", "scheduled", "Follow up on the proposal")]
    assert task["from_value"] == "follow_up" and task["to_label"] == pm.full_name and task["status"] == "manual"


@pytest.mark.asyncio
async def test_visits_agreements_documents_and_task_outcomes_appear(client, db_session):
    head, pm, _, uni, _ = await _setup(client, db_session)
    visit = await plan(client, uni["id"])
    agreement = await make_agreement(client, uni["id"])
    document = await add_document(client, uni["id"], title=f"Fees {uuid.uuid4().hex[:6]}")
    done = await add_task(client, uni["id"], title="Send brochure")
    assert (await client.post(f"/api/v1/partnership/tasks/{done['id']}/complete", json={})).status_code == 200
    dropped = await add_task(client, uni["id"], title="Old idea")
    response = await client.post(f"/api/v1/partnership/tasks/{dropped['id']}/cancel", json={"reason": "No longer needed"})
    assert response.status_code == 200, response.text

    await login(client, head)  # every reader reads every university (TL3)
    rows = (await timeline(client, uni["id"]))["items"]
    keys = {summary(r) for r in rows}
    assert ("visit", "create", visit["code"]) in keys
    assert ("agreement", "create", agreement["mou_number"]) in keys
    assert ("document", "uploaded", document["title"]) in keys
    assert {("task", "done", "Send brochure"), ("task", "cancelled", "Old idea")} <= keys
    by = {summary(r): r for r in rows}
    assert by[("agreement", "create", agreement["mou_number"])]["status"] == "mou"
    assert by[("document", "uploaded", document["title"])]["from_value"] == "fee_structure"
    assert by[("task", "done", "Send brochure")]["actor"]["id"] == str(pm.id)  # the audit row names who completed it
    assert by[("task", "cancelled", "Old idea")]["reason"] == "No longer needed"


@pytest.mark.asyncio
async def test_equal_timestamps_read_in_causal_order_and_page_stably(client, db_session):
    """Edge (ties): one transaction's rows share `at`; newest first shows the auto-task above the stage move above its cause."""
    _, pm, _, uni, person = await _setup(client, db_session)
    when, uni_id = datetime(2026, 9, 14, 10, 0, tzinfo=UTC), uuid.UUID(uni["id"])
    db_session.add_all(
        [
            UniversityCall(university_id=uni_id, contact_id=uuid.UUID(person["id"]), caller_user_id=pm.id, occurred_at=when, direction="outgoing", outcome="connected"),
            UniversityStageHistory(university_id=uni_id, actor_user_id=pm.id, kind="move", from_stage="interested", to_stage="proposal_sent", created_at=when),
            PartnershipTask(
                university_id=uni_id,
                kind="task",
                title="Send partnership proposal",
                assignee_user_id=pm.id,
                created_by_user_id=pm.id,
                due_on=date(2026, 9, 16),
                source="stage",
                rule="stage:proposal_sent",
                created_at=when,
            ),
        ]
    )
    await db_session.commit()

    kinds = [r["kind"] for r in (await timeline(client, uni["id"]))["items"]]
    assert kinds == ["task", "stage", "call"]
    paged = [(await timeline(client, uni["id"], limit=1, offset=i))["items"][0]["kind"] for i in range(3)]
    assert paged == kinds
    assert (await timeline(client, uni["id"], limit=1, offset=3))["items"] == []


@pytest.mark.asyncio
async def test_free_text_is_an_excerpt_and_other_universities_never_show(client, db_session):
    _, _, _, uni, person = await _setup(client, db_session)
    long_notes = "x" * 500
    assert (await client.post(CALLS, json={"contact_id": person["id"], "outcome": "connected", "notes": long_notes})).status_code == 201
    _, _, _, other, _ = await _setup(client, db_session)

    assert len((await timeline(client, uni["id"]))["items"][0]["reason"]) == 200
    assert (await timeline(client, other["id"]))["total"] == 0  # only its own rows (none yet)
    empty = await timeline(client, other["id"])
    assert empty == {"items": [], "total": 0, "limit": 50, "offset": 0}


@pytest.mark.asyncio
async def test_unknown_or_malformed_ids_and_bad_paging(client, db_session):
    _, _, _, uni, _ = await _setup(client, db_session)
    await timeline(client, uuid.uuid4(), 404)
    assert (await client.get(url("not-a-uuid", "timeline"))).status_code == 422
    await timeline(client, uni["id"], 422, limit=0)
    await timeline(client, uni["id"], 422, limit=101)
    await timeline(client, uni["id"], 422, offset=-1)


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("overseas_admin", "overseas"), ("counselor", "overseas"), ("bdm", "it"), ("university_rep", "overseas")])
async def test_other_roles_are_refused(client, db_session, role, division):
    _, _, _, uni, _ = await _setup(client, db_session)
    await as_role(client, db_session, role, division)
    await timeline(client, uni["id"], 403)


@pytest.mark.asyncio
async def test_anonymous_is_401_and_super_admin_reads(client, db_session):
    _, _, _, uni, person = await _setup(client, db_session)
    assert (await client.post(CALLS, json={"contact_id": person["id"], "outcome": "connected"})).status_code == 201
    client.cookies.clear()
    await timeline(client, uni["id"], 401)
    await as_role(client, db_session, "super_admin", "global")
    assert (await timeline(client, uni["id"]))["total"] == 1


@pytest.mark.asyncio
async def test_commission_documents_are_hidden_from_a_non_commission_reader(client, db_session):
    """TL7: the service applies upc-026's document visibility (no TL2 reader is affected today)."""
    head, _, _, uni, _ = await _setup(client, db_session)
    title = f"Commission {uuid.uuid4().hex[:6]}"
    await add_document(client, uni["id"], kind="commission_agreement", title=title, shareable=False)
    outsider = User(id=uuid.uuid4(), role="overseas_admin", division="overseas", email="x@example.com", full_name="X")
    seen = await university_timeline.page(db_session, uuid.UUID(uni["id"]), head, 50, 0)
    hidden = await university_timeline.page(db_session, uuid.UUID(uni["id"]), outsider, 50, 0)
    assert [r["subject"] for r in seen["items"] if r["kind"] == "document"] == [title]
    assert [r for r in hidden["items"] if r["kind"] == "document"] == []
