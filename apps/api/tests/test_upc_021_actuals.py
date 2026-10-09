"""upc-021 -- the monthly actuals T1-T7 (spec TG8-TG11; AC1, AC2, AC7). Events are made through the API, then dated into a past month by
rewriting their (append-only) timestamps, so every test reads a month nobody else writes to for its own fresh managers."""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import update

from app.models import University, UniversityAgreement, UniversityAgreementEvent, UniversityAssignmentHistory, UniversityStageHistory
from app.services.partnership_metrics import target_actuals
from tests.upc003_helpers import catalogue_country, create, login, make_head, make_pm, url
from tests.upc007_helpers import move_ok

MARCH = date(2025, 3, 1)
IN_MARCH = datetime(2025, 3, 15, 6, tzinfo=UTC)
FEB = datetime(2025, 2, 10, 6, tzinfo=UTC)
APRIL = datetime(2025, 4, 10, 6, tzinfo=UTC)
ZERO = {"new_universities": 0, "contacted": 0, "proposals": 0, "negotiations": 0, "mous": 0, "new_active": 0}


async def _university(client, db, head) -> dict:
    await login(client, head)
    return await create(client, (await catalogue_country(db)).id)


async def _assign(client, head, university_id, manager) -> None:
    await login(client, head)
    response = await client.post(url(university_id, "assign"), json={"primary_manager_user_id": str(manager.id) if manager else None})
    assert response.status_code == 200, response.text


async def _date_assignments(db, university_id, when: datetime) -> None:
    """Dates every assignment row of the university not yet dated (newest rows are still 'now')."""
    await db.execute(
        update(UniversityAssignmentHistory)
        .where(UniversityAssignmentHistory.university_id == uuid.UUID(str(university_id)), UniversityAssignmentHistory.created_at > datetime(2026, 1, 1, tzinfo=UTC))
        .values(created_at=when)
    )
    await db.commit()


async def _date_moves(db, university_id, when: datetime) -> None:
    await db.execute(
        update(UniversityStageHistory)
        .where(UniversityStageHistory.university_id == uuid.UUID(str(university_id)), UniversityStageHistory.created_at > datetime(2026, 1, 1, tzinfo=UTC))
        .values(created_at=when)
    )
    await db.commit()


async def _owned(client, db, head, pm, when: datetime = FEB) -> dict:
    """A university first assigned to `pm` at `when` (before March by default); the client ends signed in as `pm`."""
    uni = await _university(client, db, head)
    await _assign(client, head, uni["id"], pm)
    await _date_assignments(db, uni["id"], when)
    await login(client, pm)
    return uni


async def _actuals(db, *managers, month: date = MARCH) -> list[dict]:
    result = await target_actuals(db, [m.id for m in managers], month)
    return [result[m.id] for m in managers]


async def _signed_agreement(db, university_id, head, to_status: str, when: datetime) -> None:
    a = UniversityAgreement(
        mou_number=f"T-{uuid.uuid4().hex[:10]}", university_id=uuid.UUID(str(university_id)), agreement_type="mou", start_date=date(2025, 1, 1),
        expiry_date=date(2027, 1, 1), exclusivity="exclusive", created_by_user_id=head.id,
    )  # fmt: skip
    db.add(a)
    await db.flush()
    db.add(UniversityAgreementEvent(agreement_id=a.id, kind="status", from_status="approved", to_status=to_status, actor_user_id=head.id, created_at=when))
    await db.commit()


@pytest.mark.asyncio
async def test_a_manager_with_no_activity_has_zero_for_every_tracked_kpi(client, db_session):
    pm = await make_pm(db_session, await make_head(db_session))
    assert await _actuals(db_session, pm) == [ZERO]


@pytest.mark.asyncio
async def test_new_universities_counts_first_primary_assignments_in_the_month(client, db_session):
    """T1 (TG10): first-ever primary assignment in the month, credited to the assignee. A reassignment is not a new university."""
    head = await make_head(db_session)
    pm, other = await make_pm(db_session, head), await make_pm(db_session, head)
    await _owned(client, db_session, head, pm, IN_MARCH)
    moved = await _owned(client, db_session, head, other, FEB)
    await _assign(client, head, moved["id"], pm)
    await _date_assignments(db_session, moved["id"], IN_MARCH)
    await _owned(client, db_session, head, pm, APRIL)
    mine, theirs = await _actuals(db_session, pm, other)
    assert mine["new_universities"] == 1 and theirs["new_universities"] == 0


@pytest.mark.asyncio
async def test_stage_entries_count_once_per_university_per_month(client, db_session):
    """T2/T4/T5/T7 (TG10): a university bounced back and re-entering Partner Activated counts once; a skipped stage is not entered."""
    head = await make_head(db_session)
    pm = await make_pm(db_session, head)
    uni = await _owned(client, db_session, head, pm)
    await move_ok(client, uni["id"], "target_university", "initial_contact")
    await move_ok(client, uni["id"], "initial_contact", "proposal_sent")
    await move_ok(client, uni["id"], "proposal_sent", "commercial_discussion")
    await move_ok(client, uni["id"], "commercial_discussion", "partner_activated")
    await move_ok(client, uni["id"], "partner_activated", "agreement_signed", note="Activation paused")
    await move_ok(client, uni["id"], "agreement_signed", "partner_activated")
    skipped = await _owned(client, db_session, head, pm)
    await move_ok(client, skipped["id"], "target_university", "commercial_discussion")
    for u in (uni, skipped):
        await _date_moves(db_session, u["id"], IN_MARCH)
    [mine] = await _actuals(db_session, pm)
    assert mine == ZERO | {"contacted": 2, "proposals": 1, "negotiations": 2, "new_active": 1}


@pytest.mark.asyncio
async def test_contacted_counts_only_the_first_entry_into_contact_or_later(client, db_session):
    """T2 = D6: contacted in February, then Interested in March -> not a new contact in March."""
    head = await make_head(db_session)
    pm = await make_pm(db_session, head)
    uni = await _owned(client, db_session, head, pm)
    await move_ok(client, uni["id"], "target_university", "initial_contact")
    await _date_moves(db_session, uni["id"], FEB)
    await move_ok(client, uni["id"], "initial_contact", "interested")
    await _date_moves(db_session, uni["id"], IN_MARCH)
    [mine] = await _actuals(db_session, pm)
    assert mine["contacted"] == 0
    [feb] = await _actuals(db_session, pm, month=date(2025, 2, 1))
    assert feb["contacted"] == 1


@pytest.mark.asyncio
async def test_mous_counts_agreements_reaching_signed_in_the_month(client, db_session):
    """T6 = D11: a status event to `signed` in the month; other moves and other months do not count."""
    head = await make_head(db_session)
    pm = await make_pm(db_session, head)
    uni = await _owned(client, db_session, head, pm)
    await _signed_agreement(db_session, uni["id"], head, "signed", IN_MARCH)
    await _signed_agreement(db_session, uni["id"], head, "approved", IN_MARCH)
    await _signed_agreement(db_session, uni["id"], head, "signed", APRIL)
    [mine] = await _actuals(db_session, pm)
    assert mine["mous"] == 1


@pytest.mark.asyncio
async def test_month_boundaries_are_ist(client, db_session):
    """TG2: 1 March 00:30 IST (28 Feb 19:00 UTC) is March; 1 April 00:15 IST (31 March 18:45 UTC) is not."""
    head = await make_head(db_session)
    pm = await make_pm(db_session, head)
    early, late = await _owned(client, db_session, head, pm), await _owned(client, db_session, head, pm)
    await move_ok(client, early["id"], "target_university", "proposal_sent")
    await _date_moves(db_session, early["id"], datetime(2025, 2, 28, 19, tzinfo=UTC))
    await move_ok(client, late["id"], "target_university", "proposal_sent")
    await _date_moves(db_session, late["id"], datetime(2025, 3, 31, 18, 45, tzinfo=UTC))
    [mine] = await _actuals(db_session, pm)
    assert mine["proposals"] == 1


@pytest.mark.asyncio
async def test_past_months_are_never_rescored(client, db_session):
    """AC2 (TG9): after March, the university is reassigned, marked lost, moved back and deactivated; March's figures stay the same."""
    head = await make_head(db_session)
    pm, successor = await make_pm(db_session, head), await make_pm(db_session, head)
    uni = await _owned(client, db_session, head, pm, IN_MARCH)
    await move_ok(client, uni["id"], "target_university", "proposal_sent")
    await _date_moves(db_session, uni["id"], IN_MARCH + timedelta(days=1))
    before = await _actuals(db_session, pm, successor)
    assert before[0]["new_universities"] == 1 and before[0]["proposals"] == 1

    await move_ok(client, uni["id"], "proposal_sent", "interested", note="Back to talks")
    await _assign(client, head, uni["id"], successor)
    await login(client, head)
    assert (await client.post(url(uni["id"], "lost"), json={"reason": "University paused"})).status_code == 200
    await db_session.execute(update(University).where(University.id == uuid.UUID(uni["id"])).values(active=False))
    await db_session.commit()
    await _date_moves(db_session, uni["id"], APRIL)
    await _date_assignments(db_session, uni["id"], APRIL)
    assert await _actuals(db_session, pm, successor) == before


@pytest.mark.asyncio
async def test_a_manager_joining_mid_month_is_credited_only_after_the_assignment(client, db_session):
    """AC7 / TG8: the owner at the time of each event is credited -- before the handover the first manager, after it the joiner."""
    head = await make_head(db_session)
    first, joiner = await make_pm(db_session, head), await make_pm(db_session, head)
    uni = await _owned(client, db_session, head, first, datetime(2025, 3, 1, 6, tzinfo=UTC))
    await move_ok(client, uni["id"], "target_university", "proposal_sent")
    await _date_moves(db_session, uni["id"], datetime(2025, 3, 10, 6, tzinfo=UTC))
    await _assign(client, head, uni["id"], joiner)
    await _date_assignments(db_session, uni["id"], datetime(2025, 3, 15, 6, tzinfo=UTC))
    await login(client, joiner)
    await move_ok(client, uni["id"], "proposal_sent", "commercial_discussion")
    await _date_moves(db_session, uni["id"], datetime(2025, 3, 20, 6, tzinfo=UTC))
    a, b = await _actuals(db_session, first, joiner)
    assert (a["proposals"], a["negotiations"], a["new_universities"]) == (1, 0, 1)
    assert (b["proposals"], b["negotiations"], b["new_universities"]) == (0, 1, 0)


@pytest.mark.asyncio
async def test_an_event_before_any_assignment_is_credited_to_nobody(client, db_session):
    """TG8: no primary at the time -> uncredited, even after the university is assigned later."""
    head = await make_head(db_session)
    pm = await make_pm(db_session, head)
    uni = await _university(client, db_session, head)
    await move_ok(client, uni["id"], "target_university", "proposal_sent")
    await _date_moves(db_session, uni["id"], IN_MARCH)
    await _assign(client, head, uni["id"], pm)
    await _date_assignments(db_session, uni["id"], APRIL)
    [mine] = await _actuals(db_session, pm)
    assert mine["proposals"] == 0


@pytest.mark.asyncio
async def test_a_university_owned_before_assignment_history_is_not_new_when_reassigned(client, db_session):
    """T1: a row whose primary predates the history (a legacy owner) moving to `pm` is a reassignment, not a newly identified university."""
    head = await make_head(db_session)
    legacy, pm = await make_pm(db_session, head), await make_pm(db_session, head)
    uni = await _university(client, db_session, head)
    await db_session.execute(update(University).where(University.id == uuid.UUID(uni["id"])).values(primary_manager_user_id=legacy.id))
    await db_session.commit()
    await _assign(client, head, uni["id"], pm)
    await _date_assignments(db_session, uni["id"], IN_MARCH)
    assert [a["new_universities"] for a in await _actuals(db_session, legacy, pm)] == [0, 0]
