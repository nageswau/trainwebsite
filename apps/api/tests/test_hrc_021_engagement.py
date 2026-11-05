"""hrc-021 -- the derived candidate engagement status (DEC-SCOPE-397; design
docs/superpowers/specs/2026-11-05-hrc-021-candidate-engagement-status-design.md). AC1: each Appendix B definition (E2) holds on a fixture
candidate; AC2: the manual flags override the derived value. Rows are planted directly with controlled timestamps; names are unique per
test (the database is shared and never truncated)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import event, update

from app.core.database import engine
from app.models import ApplicationScreening, Candidate, CareerApplication, JobApplication, JobApplicationStatusHistory, RecruiterCall, RecruiterMessage
from app.services import candidate_engagement as engagement
from tests.test_rec_013_find_candidates import _world
from tests.test_rec_017_tracking import _candidate, _requirement, _team

CANDIDATES = "/api/v1/recruiter/candidates"


def _ago(days: float) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


async def _of(db, candidate) -> str:
    return (await engagement.of(db, [candidate.id]))[candidate.id]


async def _aged(db, candidate, days: float):
    """Registration `days` ago (inactive is measured from the newest activity of any kind, registration included)."""
    await db.execute(update(Candidate).where(Candidate.id == candidate.id).values(created_at=_ago(days), updated_at=_ago(days)))
    await db.commit()


async def _application(db, candidate, status, days: float = 0, history: tuple[str, ...] = ()) -> JobApplication:
    job = await _requirement(db)
    application = JobApplication(job_id=job.id, candidate_id=candidate.id, status=status)
    db.add(application)
    await db.flush()
    for step in history or (status,):
        db.add(JobApplicationStatusHistory(application_id=application.id, to_status=step, created_at=_ago(days)))
    await db.commit()
    await db.execute(update(JobApplication).where(JobApplication.id == application.id).values(updated_at=_ago(days), created_at=_ago(days)))
    await db.commit()
    return application


async def _call(db, candidate, caller, days: float = 0):
    db.add(RecruiterCall(candidate_id=candidate.id, caller_user_id=caller.id, occurred_at=_ago(days), direction="outgoing", outcome="connected"))
    await db.commit()


async def _message(db, candidate, sender, days: float = 0):
    db.add(RecruiterMessage(candidate_id=candidate.id, sender_user_id=sender.id, channel="whatsapp", body="Hi", sent_at=_ago(days)))
    await db.commit()


@pytest_asyncio.fixture
async def team(client, db_session):
    return await _team(client, db_session)


# --- AC1: each definition (E2) ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_new_is_registered_with_no_owner_and_no_contact(db_session, team):
    candidate = await _candidate(db_session, team[1])
    assert await _of(db_session, candidate) == "new"


@pytest.mark.asyncio
async def test_uncontacted_has_an_owner_but_no_call_or_message(db_session, team):
    candidate = await _candidate(db_session, team[1], owner_user_id=team[1].id)
    assert await _of(db_session, candidate) == "uncontacted"


@pytest.mark.asyncio
@pytest.mark.parametrize("touch", [_call, _message])
async def test_contacted_has_at_least_one_call_or_message(db_session, team, touch):
    candidate = await _candidate(db_session, team[1], owner_user_id=team[1].id)
    await touch(db_session, candidate, team[1], days=1)
    assert await _of(db_session, candidate) == "contacted"


@pytest.mark.asyncio
async def test_screened_has_a_screening_record(db_session, team):
    candidate = await _candidate(db_session, team[1])
    application = await _application(db_session, candidate, "rejected", days=40, history=("sourced", "rejected"))
    db_session.add(ApplicationScreening(application_id=application.id, result="hold", screened_by_user_id=team[1].id))
    await db_session.commit()
    assert await _of(db_session, candidate) == "screened"


@pytest.mark.asyncio
async def test_screened_also_counts_an_application_that_was_screened(db_session, team):
    candidate = await _candidate(db_session, team[1])
    await _application(db_session, candidate, "withdrawn", days=40, history=("sourced", "screened", "withdrawn"))
    assert await _of(db_session, candidate) == "screened"


@pytest.mark.asyncio
async def test_shortlisted_has_an_application_that_reached_shortlisted_or_beyond(db_session, team):
    candidate = await _candidate(db_session, team[1])
    await _call(db_session, candidate, team[1], days=40)
    await _application(db_session, candidate, "rejected", days=40, history=("sourced", "shortlisted", "interview", "rejected"))
    assert await _of(db_session, candidate) == "shortlisted"


@pytest.mark.asyncio
async def test_active_has_an_open_application_even_an_old_one(db_session, team):
    candidate = await _candidate(db_session, team[1])
    await _aged(db_session, candidate, 200)
    await _application(db_session, candidate, "sourced", days=200)
    assert await _of(db_session, candidate) == "active"


@pytest.mark.asyncio
async def test_active_has_an_application_change_in_the_last_30_days(db_session, team):
    candidate = await _candidate(db_session, team[1])
    await _application(db_session, candidate, "rejected", days=29, history=("sourced", "rejected"))
    assert await _of(db_session, candidate) == "active"
    stale = await _candidate(db_session, team[1])
    await _application(db_session, stale, "rejected", days=31, history=("sourced", "rejected"))
    assert await _of(db_session, stale) == "new"  # a closed, unscreened application older than 30 days adds nothing


@pytest.mark.asyncio
async def test_active_has_a_website_application_in_the_last_30_days(db_session, team):
    candidate = await _candidate(db_session, team[1])
    job = await _requirement(db_session)
    db_session.add(CareerApplication(job_id=job.id, full_name=candidate.name, email=candidate.email, resume_url="x", tracking_code=uuid.uuid4().hex,
                                     candidate_id=candidate.id))  # fmt: skip
    await db_session.commit()
    assert await _of(db_session, candidate) == "active"


@pytest.mark.asyncio
async def test_a_call_alone_never_makes_a_candidate_active(db_session, team):
    """E4: recruiter outreach is Contacted, not Active."""
    candidate = await _candidate(db_session, team[1])
    await _call(db_session, candidate, team[1], days=0)
    assert await _of(db_session, candidate) == "contacted"


@pytest.mark.asyncio
async def test_inactive_has_no_activity_of_any_kind_for_90_days(db_session, team):
    candidate = await _candidate(db_session, team[1], owner_user_id=team[1].id)
    await _aged(db_session, candidate, 120)
    await _call(db_session, candidate, team[1], days=91)
    await _application(db_session, candidate, "rejected", days=95, history=("sourced", "shortlisted", "rejected"))
    assert await _of(db_session, candidate) == "inactive"  # E6: inactive beats shortlisted
    recent = await _candidate(db_session, team[1], owner_user_id=team[1].id)
    await _aged(db_session, recent, 120)
    await _call(db_session, recent, team[1], days=89)
    assert await _of(db_session, recent) == "contacted"


@pytest.mark.asyncio
async def test_a_freshly_registered_candidate_is_not_inactive_but_an_old_untouched_one_is(db_session, team):
    candidate = await _candidate(db_session, team[1])
    await _aged(db_session, candidate, 91)
    assert await _of(db_session, candidate) == "inactive"


@pytest.mark.asyncio
async def test_placed_has_a_joined_application_and_beats_inactive(db_session, team):
    candidate = await _candidate(db_session, team[1])
    await _aged(db_session, candidate, 400)
    await _application(db_session, candidate, "joined", days=300, history=("sourced", "shortlisted", "selected", "joined"))
    assert await _of(db_session, candidate) == "placed"


@pytest.mark.asyncio
async def test_a_hand_set_placed_status_counts_as_placed(db_session, team):
    candidate = await _candidate(db_session, team[1], status="placed")
    assert await _of(db_session, candidate) == "placed"


@pytest.mark.asyncio
async def test_a_placed_candidate_with_a_new_open_application_is_active_again(db_session, team):
    """E5: the re-registration case -- the same person (Q-07) back in the pipeline."""
    candidate = await _candidate(db_session, team[1])
    await _application(db_session, candidate, "joined", days=300, history=("sourced", "joined"))
    await _application(db_session, candidate, "sourced", days=0)
    assert await _of(db_session, candidate) == "active"


# --- AC2: the manual flags override ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("stored", "expected"), [("do_not_contact", "do_not_contact"), ("not_looking", "not_interested")])
async def test_manual_flags_override_every_derived_value(db_session, team, stored, expected):
    candidate = await _candidate(db_session, team[1], status=stored)
    await _application(db_session, candidate, "joined", days=10, history=("sourced", "joined"))
    await _application(db_session, candidate, "interview", days=0)
    assert await _of(db_session, candidate) == expected


@pytest.mark.asyncio
async def test_available_and_interviewing_are_not_flags(db_session, team):
    for stored in ("available", "interviewing"):
        candidate = await _candidate(db_session, team[1], status=stored)
        assert await _of(db_session, candidate) == "new"


def test_labels_cover_every_key_in_order():
    assert list(engagement.ENGAGEMENTS) == [
        "new", "uncontacted", "contacted", "screened", "shortlisted", "active", "inactive", "placed", "not_interested", "do_not_contact",
    ]  # fmt: skip
    assert engagement.out("not_interested") == {"key": "not_interested", "label": "Not interested"}


# --- E7: the list, the detail and the search --------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_list_carries_and_filters_by_engagement(client, db_session, team):
    fresh = await _candidate(db_session, team[1])
    owned = await _candidate(db_session, team[1], owner_user_id=team[1].id, name=f"{fresh.name} B")
    items = (await client.get(CANDIDATES, params={"q": fresh.name})).json()["items"]
    assert {i["id"]: i["engagement"] for i in items} == {
        str(fresh.id): {"key": "new", "label": "New"}, str(owned.id): {"key": "uncontacted", "label": "Uncontacted"},
    }  # fmt: skip
    only = (await client.get(CANDIDATES, params={"q": fresh.name, "engagement": "uncontacted"})).json()
    assert [i["id"] for i in only["items"]] == [str(owned.id)] and only["total"] == 1


@pytest.mark.asyncio
async def test_an_unknown_engagement_filter_is_422(client, team):
    assert (await client.get(CANDIDATES, params={"engagement": "bogus"})).status_code == 422


@pytest.mark.asyncio
async def test_the_engagement_does_not_add_a_list_query(client, db_session, team):
    """The value is a column of the page query and the filter a WHERE term: same SELECT count with or without it. Both requests return the
    same one owned candidate (the owner lookup only runs when a row on the page has an owner)."""
    candidate = await _candidate(db_session, team[1], owner_user_id=team[1].id)
    statements: list[str] = []
    listener = lambda *args: statements.append(args[2])  # noqa: E731 -- (conn, cursor, statement, ...)
    counts = []
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        for params in ({"q": candidate.name}, {"q": candidate.name, "engagement": "uncontacted"}):
            statements.clear()
            response = await client.get(CANDIDATES, params=params)
            assert response.status_code == 200 and [i["id"] for i in response.json()["items"]] == [str(candidate.id)]
            counts.append(len([s for s in statements if s.lstrip().upper().startswith("SELECT")]))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
    assert counts[0] == counts[1]


@pytest.mark.asyncio
async def test_the_detail_carries_the_engagement(client, db_session, team):
    candidate = await _candidate(db_session, team[1], status="do_not_contact")
    body = (await client.get(f"{CANDIDATES}/{candidate.id}")).json()
    assert body["engagement"] == {"key": "do_not_contact", "label": "Do not contact"} and body["status"] == "do_not_contact"


@pytest.mark.asyncio
async def test_search_cards_carry_and_filter_by_engagement(client, db_session):
    world = await _world(client, db_session)
    skill = await world.skill("Engage")
    fresh = await world.candidate(skill)
    owned = await world.candidate(skill, owner_user_id=world.actor.id)
    body = {"all": [skill.name]}
    every = await client.post(f"{CANDIDATES}/search", json=body)
    assert every.status_code == 200, every.text
    assert {i["id"]: i["engagement"]["key"] for i in every.json()["items"]} == {str(fresh.id): "new", str(owned.id): "uncontacted"}
    narrowed = await client.post(f"{CANDIDATES}/search", json={**body, "engagement": "uncontacted"})
    assert [i["id"] for i in narrowed.json()["items"]] == [str(owned.id)] and narrowed.json()["total"] == 1
    assert (await client.post(f"{CANDIDATES}/search", json={**body, "engagement": "bogus"})).status_code == 422
