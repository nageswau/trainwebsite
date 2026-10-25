"""ccrm-017 (DEC-SCOPE-258, J1-J6) -- a direct student's derived journey stage: the rule in app/student_journey.py and its place on the
ccrm-009 overview (GET /counselor/students/{id}/overview). Read-only and never stored on an application."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models import Appointment, OverseasStudentCounselor
from app.student_journey import STAGES, derive, steps
from tests.agn001_helpers import login, mk_user, uniq
from tests.enh031_helpers import mk_application, mk_university

NOW = datetime.now(UTC)


def app(status: str, outcome: str | None = None, minutes: int = 0):
    return SimpleNamespace(status=status, outcome=outcome, updated_at=NOW - timedelta(minutes=minutes))


def test_six_stages_in_order():
    assert [key for key, _ in STAGES] == ["lead", "counselling", "applying", "offer", "visa", "enrolled"]


@pytest.mark.parametrize(
    ("status", "stage"),
    [
        ("enquiry", "counselling"),
        ("eligibility_evaluation", "counselling"),
        ("university_selection", "applying"),
        ("offer", "offer"),
        ("visa_documentation", "visa"),
        ("status_tracking", "visa"),
        ("enrolled", "enrolled"),
        ("university_review", "applying"),  # browser QA-01: the seed's pre-DEC-WF-001 status
        ("profile_evaluation", "counselling"),
        ("Masters legacy", "counselling"),
    ],
)
def test_each_application_stage_maps_to_a_journey_stage(status, stage):  # J2
    assert derive([app(status)], engaged=False)[0] == stage


def test_the_furthest_live_application_wins_and_closed_ones_are_ignored():  # J3
    offer, visa_refused, withdrawn = app("offer"), app("status_tracking", "visa_refused"), app("visa_documentation", minutes=5)
    withdrawn.status = "withdrawn"
    stage, best, note = derive([app("enquiry"), offer, visa_refused, withdrawn], engaged=True)
    assert (stage, best, note) == ("offer", offer, None)


def test_a_tie_goes_to_the_most_recently_updated_application():
    older, newer = app("offer", minutes=30), app("offer", minutes=1)
    assert derive([older, newer], engaged=True)[1] is newer


@pytest.mark.parametrize(("outcome", "note"), [("on_hold", "On hold"), ("deferred", "Deferred")])
def test_on_hold_and_deferred_stay_live_with_a_note(outcome, note):
    held = app("university_selection", outcome)
    assert derive([held], engaged=True) == ("applying", held, note)


def test_every_application_closed_is_counselling_with_a_note():  # J4
    assert derive([app("offer", "rejected"), app("offer", "offer_declined")], engaged=False) == ("counselling", None, "All applications closed")


def test_no_application_is_lead_unless_the_student_is_engaged():  # J4
    assert derive([], engaged=False) == ("lead", None, None)
    assert derive([], engaged=True) == ("counselling", None, None)


def test_steps_mark_done_current_and_upcoming():
    assert steps("offer") == [
        {"key": "lead", "label": "Lead", "state": "done"},
        {"key": "counselling", "label": "Counselling", "state": "done"},
        {"key": "applying", "label": "Applying", "state": "done"},
        {"key": "offer", "label": "Offer", "state": "current"},
        {"key": "visa", "label": "Visa", "state": "upcoming"},
        {"key": "enrolled", "label": "Enrolled", "state": "upcoming"},
    ]


# --- the overview (J5) ---------------------------------------------------------------------------------------------------------------


def url(student_id) -> str:
    return f"/api/v1/counselor/students/{student_id}/overview"


@pytest.mark.asyncio
async def test_overview_carries_the_journey_from_the_best_application(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    other = await mk_user(db_session, role="counselor")
    student = await mk_user(db_session, role="overseas_student")
    uni = await mk_university(db_session, name=uniq("Journey Uni"))
    await mk_application(db_session, student=student, university=await mk_university(db_session, name=uniq("J2")), counselor=counselor, status="enquiry")
    best = await mk_application(db_session, student=student, university=uni, counselor=other, status="visa_documentation")  # another counselor's: still counts (V1)
    closed = await mk_application(db_session, student=student, university=await mk_university(db_session, name=uniq("J3")), counselor=counselor, status="status_tracking")
    closed.outcome = "visa_refused"
    await db_session.commit()
    await login(client, counselor.email)
    response = await client.get(url(student.id))
    assert response.status_code == 200, response.text
    journey = response.json()["journey"]
    assert journey["stage"] == "visa" and journey["label"] == "Visa" and journey["note"] is None
    assert journey["application"] == {"id": str(best.id), "application_code": best.application_code, "university": uni.name}
    assert [s["state"] for s in journey["steps"]] == ["done", "done", "done", "done", "current", "upcoming"]
    # each application keeps its own status beside the journey (spec §6 critical rule)
    assert {a["status"] for a in response.json()["applications"]} == {"enquiry", "visa_documentation", "status_tracking"}


@pytest.mark.asyncio
async def test_overview_journey_without_applications(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    admin = await mk_user(db_session, role="overseas_admin")
    walk_in = await mk_user(db_session, role="overseas_student")
    db_session.add(OverseasStudentCounselor(student_user_id=walk_in.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    self_registered = await mk_user(db_session, role="overseas_student")
    booked = await mk_user(db_session, role="overseas_student")
    db_session.add(Appointment(division="overseas", student_id=booked.id, staff_id=counselor.id, scheduled_at=NOW + timedelta(days=1), appointment_type="Counselling"))
    cancelled = await mk_user(db_session, role="overseas_student")
    db_session.add(Appointment(division="overseas", student_id=cancelled.id, staff_id=counselor.id, scheduled_at=NOW, appointment_type="Counselling", status="cancelled"))
    await db_session.commit()
    await login(client, admin.email)
    stage = {}
    for name, student in (("walk_in", walk_in), ("self", self_registered), ("booked", booked), ("cancelled", cancelled)):
        journey = (await client.get(url(student.id))).json()["journey"]
        assert journey["application"] is None and journey["note"] is None
        stage[name] = journey["stage"]
    assert stage == {"walk_in": "counselling", "self": "lead", "booked": "counselling", "cancelled": "lead"}


@pytest.mark.asyncio
async def test_another_counselors_student_is_still_404(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    stranger = await mk_user(db_session, role="overseas_student")
    await login(client, counselor.email)
    assert (await client.get(url(stranger.id))).status_code == 404
