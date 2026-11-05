"""hrc-025 -- the New Website Registrations workspace (DEC-SCOPE-402; design
docs/superpowers/specs/2026-11-05-hrc-025-website-registrations-workspace-design.md). AC1: a website registration is listed on the next
request; AC2: the filters; AC3: the first contact is the first call or message. Rows are planted directly with controlled timestamps; the
database is shared and never truncated, so each test looks for its own (newest) rows."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import update

from app.models import Candidate, CandidateDuplicate, CandidateSkill, CandidateTask, JobApplication, RecruiterCall, RecruiterMessage, Skill, SkillCategory
from app.services import candidates as candidates_svc
from app.services import website_intake
from tests.rec001_helpers import login, make_pm, make_recruiter, make_user
from tests.test_rec_017_tracking import _candidate, _requirement

URL = "/api/v1/recruiter/candidates/website-registrations"


def _ago(hours: float) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)


def _tag() -> str:
    return uuid.uuid4().hex[:8]


async def _website(db, *, hours: float = 1, **extra) -> Candidate:
    """A candidate the website created (hrc-023/022 give it the Website source), registered `hours` ago."""
    fields = {"name": f"Web {_tag()}", "email": f"web-{_tag()}@example.com", "preferred_locations": [], **extra}
    candidate = Candidate(candidate_code=await candidates_svc.next_code(db), source_id=await website_intake.source_id(db), **fields)
    db.add(candidate)
    await db.commit()
    await db.execute(update(Candidate).where(Candidate.id == candidate.id).values(created_at=_ago(hours)))
    await db.commit()
    return candidate


async def _rows(client, **params) -> dict:
    response = await client.get(URL, params={"limit": 100, **params})
    assert response.status_code == 200, response.text
    return response.json()


async def _row(client, candidate, **params) -> dict | None:
    return next((r for r in (await _rows(client, **params))["items"] if r["id"] == str(candidate.id)), None)


@pytest_asyncio.fixture
async def manager(client, db_session):
    pm = await make_pm(db_session)
    await login(client, pm)
    return pm


# --- AC1: who is listed -----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_website_registration_is_listed_with_its_facts(client, db_session, manager):
    recruiter = await make_recruiter(db_session, manager)
    candidate = await _website(db_session, city="Pune", location="Pune, MH", owner_user_id=recruiter.id)
    row = await _row(client, candidate)
    assert row is not None
    assert row["name"] == candidate.name and row["candidate_code"] == candidate.candidate_code
    assert row["location"] == "Pune"
    assert row["owner"]["id"] == str(recruiter.id)
    assert row["engagement"]["key"] == "uncontacted"
    assert row["conversion"] == "registered"
    assert row["first_contact_at"] is None and row["next_follow_up_at"] is None
    assert row["can_open"] is True and row["duplicate_review"] is False
    assert isinstance(row["completeness"], int)
    assert "email" not in row and "mobile" not in row  # N2: no contact details


@pytest.mark.asyncio
async def test_other_sources_are_not_listed(client, db_session, manager):
    imported = await _candidate(db_session, manager)  # a Referral candidate (an import or recruiter add carries its own source)
    assert await _row(client, imported) is None


@pytest.mark.asyncio
async def test_archived_and_anonymised_registrations_are_not_listed(client, db_session, manager):
    archived = await _website(db_session, archived_at=datetime.now(UTC))
    anonymised = await _website(db_session, anonymised_at=datetime.now(UTC), anonymised_reason="request")
    rows = {r["id"] for r in (await _rows(client))["items"]}
    assert str(archived.id) not in rows and str(anonymised.id) not in rows


@pytest.mark.asyncio
async def test_newest_registration_first_and_the_sla_target_is_returned(client, db_session, manager):
    older = await _website(db_session, hours=0.2)
    newer = await _website(db_session, hours=0.1)
    page = await _rows(client)
    ids = [r["id"] for r in page["items"]]
    assert ids.index(str(newer.id)) < ids.index(str(older.id))
    assert page["sla_hours"] == 24 and page["total"] >= 2


@pytest.mark.asyncio
async def test_skills_show_three_names_primary_first_and_the_count(client, db_session, manager):
    candidate = await _website(db_session)
    category = SkillCategory(name=f"Web Cat {_tag()}")
    db_session.add(category)
    await db_session.flush()
    names = [f"A{_tag()}", f"B{_tag()}", f"C{_tag()}", f"D{_tag()}"]
    skills = [Skill(name=n, category_id=category.id) for n in names]
    db_session.add_all(skills)
    await db_session.flush()
    for i, skill in enumerate(skills):
        db_session.add(CandidateSkill(candidate_id=candidate.id, skill_id=skill.id, level="beginner", is_primary=(i == 3), added_by_user_id=manager.id))
    await db_session.commit()
    row = await _row(client, candidate)
    assert row["skill_count"] == 4
    assert row["skills"][0] == names[3] and len(row["skills"]) == 3


# --- AC3: first contact, follow-up, conversion, SLA ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_first_contact_is_the_earliest_call_or_message(client, db_session, manager):
    candidate = await _website(db_session, hours=10)
    first, later = _ago(5), _ago(2)
    db_session.add(RecruiterMessage(candidate_id=candidate.id, sender_user_id=manager.id, channel="whatsapp", body="Hi", sent_at=first))
    db_session.add(RecruiterCall(candidate_id=candidate.id, caller_user_id=manager.id, occurred_at=later, direction="outgoing", outcome="connected"))
    await db_session.commit()
    row = await _row(client, candidate)
    assert datetime.fromisoformat(row["first_contact_at"]) == first
    assert row["contact_sla"] == "met"


@pytest.mark.asyncio
async def test_a_first_call_sets_the_first_contact(client, db_session, manager):
    candidate = await _website(db_session, hours=1)
    assert (await _row(client, candidate))["first_contact_at"] is None
    at = _ago(0.5)
    db_session.add(RecruiterCall(candidate_id=candidate.id, caller_user_id=manager.id, occurred_at=at, direction="outgoing", outcome="connected"))
    await db_session.commit()
    assert datetime.fromisoformat((await _row(client, candidate))["first_contact_at"]) == at


@pytest.mark.asyncio
@pytest.mark.parametrize(("registered", "contacted", "expected"), [(2, None, "pending"), (30, None, "breached"), (30, 1, "breached"), (30, 20, "met")])
async def test_contact_sla(client, db_session, manager, registered, contacted, expected):
    candidate = await _website(db_session, hours=registered)
    if contacted is not None:
        db_session.add(RecruiterCall(candidate_id=candidate.id, caller_user_id=manager.id, occurred_at=_ago(contacted), direction="outgoing", outcome="connected"))
        await db_session.commit()
    assert (await _row(client, candidate))["contact_sla"] == expected


@pytest.mark.asyncio
async def test_next_follow_up_is_the_earliest_open_task(client, db_session, manager):
    candidate = await _website(db_session)
    soon, later = datetime.now(UTC) + timedelta(days=1), datetime.now(UTC) + timedelta(days=3)
    for due, status in ((later, "open"), (soon, "open"), (datetime.now(UTC) + timedelta(hours=1), "done")):
        db_session.add(CandidateTask(candidate_id=candidate.id, task_type="follow_up", title="Call back", due_at=due, assignee_user_id=manager.id,
                                     created_by_user_id=manager.id, status=status,
                                     completed_at=datetime.now(UTC) if status == "done" else None,
                                     completed_by_user_id=manager.id if status == "done" else None))  # fmt: skip
    await db_session.commit()
    assert datetime.fromisoformat((await _row(client, candidate))["next_follow_up_at"]) == soon


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "expected"), [("sourced", "applied"), ("joined", "placed")])
async def test_conversion(client, db_session, manager, status, expected):
    candidate = await _website(db_session)
    job = await _requirement(db_session)
    db_session.add(JobApplication(job_id=job.id, candidate_id=candidate.id, status=status))
    await db_session.commit()
    assert (await _row(client, candidate))["conversion"] == expected


# --- AC2: filters -----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unassigned_filter(client, db_session, manager):
    recruiter = await make_recruiter(db_session, manager)
    queued = await _website(db_session)
    owned = await _website(db_session, owner_user_id=recruiter.id)
    ids = {r["id"] for r in (await _rows(client, view="unassigned"))["items"]}
    assert str(queued.id) in ids and str(owned.id) not in ids


@pytest.mark.asyncio
async def test_engagement_filters(client, db_session, manager):
    recruiter = await make_recruiter(db_session, manager)
    new = await _website(db_session)
    contacted = await _website(db_session, owner_user_id=recruiter.id)
    db_session.add(RecruiterCall(candidate_id=contacted.id, caller_user_id=recruiter.id, occurred_at=_ago(0.1), direction="outgoing", outcome="connected"))
    await db_session.commit()
    news = {r["id"] for r in (await _rows(client, view="new"))["items"]}
    contacts = {r["id"] for r in (await _rows(client, view="contacted"))["items"]}
    assert str(new.id) in news and str(contacted.id) not in news
    assert str(contacted.id) in contacts and str(new.id) not in contacts


@pytest.mark.asyncio
async def test_duplicate_review_filter(client, db_session, manager):
    one, two = await _website(db_session), await _website(db_session)
    clean = await _website(db_session)
    low, high = sorted([one.id, two.id], key=str)
    db_session.add(CandidateDuplicate(candidate_id=low, other_id=high, signals=["phone_variant"]))
    await db_session.commit()
    rows = {r["id"]: r for r in (await _rows(client, view="duplicate_review"))["items"]}
    assert str(one.id) in rows and str(two.id) in rows and str(clean.id) not in rows
    assert rows[str(one.id)]["duplicate_review"] is True


@pytest.mark.asyncio
async def test_an_unknown_view_is_422(client, db_session, manager):
    assert (await client.get(URL, params={"view": "placed"})).status_code == 422


# --- N2: who reads what -----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_recruiter_sees_their_own_and_the_queue_only(client, db_session):
    pm = await make_pm(db_session)
    me, other = await make_recruiter(db_session, pm), await make_recruiter(db_session, pm)
    mine, queued, theirs = await _website(db_session, owner_user_id=me.id), await _website(db_session), await _website(db_session, owner_user_id=other.id)
    await login(client, me)
    ids = {r["id"] for r in (await _rows(client))["items"]}
    assert str(mine.id) in ids and str(queued.id) in ids and str(theirs.id) not in ids


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("hr_manager", "it"), ("hr_team", "it")])
async def test_hr_roles_read_all(client, db_session, role, division):
    pm = await make_pm(db_session)
    owned = await _website(db_session, owner_user_id=(await make_recruiter(db_session, pm)).id)
    await login(client, await make_user(db_session, role, division))
    row = await _row(client, owned)
    assert row is not None
    assert row["can_open"] is (role == "hr_team")  # the HR Manager has no candidate screen


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("student", "it"), ("it_admin", "it"), ("counselor", "it")])
async def test_other_roles_are_refused(client, db_session, role, division):
    await login(client, await make_user(db_session, role, division))
    assert (await client.get(URL)).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    client.cookies.clear()
    assert (await client.get(URL)).status_code == 401
