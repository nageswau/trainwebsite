"""rec-023 -- joining management + placement closure (spec §1-§3; AC1-AC2; DEC-SCOPE-158 JN1-JN10). The shared test database is never
truncated, so every value is unique per test."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Company, Job, JobApplication, JobOffer, JobOfferEvent
from app.services import joinings as svc
from tests.rec001_helpers import as_role, login, make_recruiter, make_user
from tests.rec017_helpers import student_application
from tests.test_rec_017_tracking import _add, _candidate, _move
from tests.test_rec_022_offers import APPS, OFFERS, PDF, WF, _app_status, _offer, _setup, _status

JOININGS = "/api/v1/recruiter/joinings"
TODAY = date.today()


async def _accepted(client, db, **setup) -> dict:
    s = await _setup(client, db, **setup)
    s["offer"] = await _offer(client, s["application"]["id"], joining_date=(TODAY + timedelta(days=10)).isoformat())
    accepted = await _status(client, s["offer"]["id"], "accepted")
    assert accepted.status_code == 200, accepted.text
    s["offer"] = accepted.json()["offer"]
    return s


async def _joining(client, offer_id, **body):
    return await client.put(f"{OFFERS}/{offer_id}/joining", json=body)


async def _proof(client, offer_id, data=PDF, name="Joining mail.pdf"):
    return await client.put(f"{OFFERS}/{offer_id}/joining/proof", files={"file": (name, data, "application/pdf")})


async def _fresh(db, model, id_):
    return await db.scalar(select(model).where(model.id == id_).execution_options(populate_existing=True))


JOINED = {"joining_status": "joined", "actual_joining_date": TODAY.isoformat(), "confirmed_by": "HR - Priya"}


# --- JN2: Accepted starts the joining -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_accepted_starts_a_pending_joining_and_earlier_offers_have_none(client, db_session):
    s = await _setup(client, db_session)
    item = await _offer(client, s["application"]["id"])
    assert item["joining"] is None
    assert (await _joining(client, item["id"], joining_location="Pune")).status_code == 409
    accepted = (await _status(client, item["id"], "accepted")).json()["offer"]
    joining = accepted["joining"]
    assert (joining["status"], joining["status_label"], joining["actual_joining_date"], joining["proof"]) == ("pending", "Pending", None, None)
    assert joining["can_edit"] and joining["can_upload_proof"] and joining["overdue"] is False
    assert [m["key"] for m in joining["allowed_statuses"]] == ["joined", "did_not_join"]


@pytest.mark.asyncio
async def test_a_legacy_accepted_offer_is_marked_joined(client, db_session):
    s = await _setup(client, db_session)
    student = await make_user(db_session, "it_student", "it")
    application = await student_application(db_session, s["job"].id, student, "interview")
    await db_session.commit()
    await as_role(client, db_session, "placement_team", "it")
    offer_id = (await client.post(WF, json={"application_id": str(application.id)})).json()["id"]
    assert (await client.patch(f"{WF}/{offer_id}", json={"status": "accepted"})).status_code == 200
    assert (await _fresh(db_session, JobOffer, offer_id)).joining_status == "joined"
    assert await _app_status(db_session, application.id) == "joined"


# --- details (pending) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_details_save_while_pending_with_field_names_in_history_and_audit(client, db_session):
    s = await _accepted(client, db_session)
    expected = (TODAY + timedelta(days=14)).isoformat()
    body = {"expected_joining_date": expected, "joining_location": "Pune office", "reporting_manager": "Anil Kumar"}
    saved = await _joining(client, s["offer"]["id"], **body)
    assert saved.status_code == 200, saved.text
    offer = saved.json()["offer"]
    j = offer["joining"]
    assert (j["status"], j["expected_joining_date"], j["location"], j["reporting_manager"]) == ("pending", expected, "Pune office", "Anil Kumar")
    assert offer["joining_date"] == expected  # JN1: the offer's joining date is the expected joining date
    assert (offer["history"][-1]["event"], offer["history"][-1]["fields"]) == ("joining", ["expected_joining_date", "joining_location", "reporting_manager"])
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_joining.update", AuditLog.entity_id == offer["id"]))
    assert audit.metadata_json == {"fields": ["expected_joining_date", "joining_location", "reporting_manager"], "status": "pending"}
    again = (await _joining(client, s["offer"]["id"], **body)).json()["offer"]
    assert len(again["history"]) == len(offer["history"])  # unchanged = no history row


# --- AC1 / JN4 / JN7: Joined -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_joined_moves_the_application_and_the_company_and_is_final(client, db_session):
    s = await _accepted(client, db_session)
    joined = await _joining(client, s["offer"]["id"], **JOINED, joining_location="Pune", confirmed_on=TODAY.isoformat())
    assert joined.status_code == 200, joined.text
    offer = joined.json()["offer"]
    j = offer["joining"]
    assert (j["status"], j["status_label"], j["actual_joining_date"], j["confirmed_by"]) == ("joined", "Joined", TODAY.isoformat(), "HR - Priya")
    assert not j["can_edit"] and j["allowed_statuses"] == [] and j["can_upload_proof"]
    assert offer["application"]["status"] == "joined" and await _app_status(db_session, s["application"]["id"]) == "joined"
    assert [h["event"] for h in offer["history"]][-2:] == ["joining", "joined"]
    company = await _fresh(db_session, Company, s["job"].company_id)
    assert company.stage == "joined"
    assert (await _joining(client, s["offer"]["id"], **JOINED)).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"joining_status": "joined", "confirmed_by": "HR"}, "actual_joining_date"),
        ({"joining_status": "joined", "actual_joining_date": TODAY.isoformat()}, "confirmed_by"),
        ({**JOINED, "actual_joining_date": (TODAY + timedelta(days=2)).isoformat()}, "actual_joining_date"),  # +2: the rule uses the IST date
        ({**JOINED, "actual_joining_date": (TODAY - timedelta(days=2)).isoformat()}, "actual_joining_date"),  # before the offer date
        ({"expected_joining_date": (TODAY - timedelta(days=1)).isoformat()}, "expected_joining_date"),
        ({"confirmed_on": (TODAY + timedelta(days=2)).isoformat()}, "confirmed_on"),
        ({"joining_status": "did_not_join"}, "reason"),
        ({"joining_status": "did_not_join", "reason": " x "}, "reason"),
    ],
)
async def test_joining_validation_422(client, db_session, body, field):
    s = await _accepted(client, db_session)
    response = await _joining(client, s["offer"]["id"], **body)
    assert response.status_code == 422, response.text
    assert any(field in e["loc"] for e in response.json()["detail"])
    assert (await _fresh(db_session, JobOffer, s["offer"]["id"])).joining_status == "pending"


@pytest.mark.asyncio
async def test_each_field_error_names_its_own_field(client, db_session):
    """QA-01: the expected-date error names the expected joining date (the form's label), not the offer's generic joining date."""
    s = await _accepted(client, db_session)
    response = await _joining(client, s["offer"]["id"], expected_joining_date=(TODAY - timedelta(days=2)).isoformat())
    assert response.json()["detail"][0]["msg"] == "The expected joining date cannot be before the offer date"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"joining_status": "left"}, {"joining_location": "x" * 161}, {"extra": 1}, {"reason": "x" * 501}])
async def test_joining_schema_422(client, db_session, body):
    s = await _accepted(client, db_session)
    assert (await _joining(client, s["offer"]["id"], **body)).status_code == 422


@pytest.mark.asyncio
async def test_joined_with_a_proof_file_needs_no_confirmation_name(client, db_session):
    s = await _accepted(client, db_session)
    uploaded = await _proof(client, s["offer"]["id"])
    assert uploaded.status_code == 200, uploaded.text
    proof = uploaded.json()["offer"]["joining"]["proof"]
    assert proof["name"] == "Joining mail.pdf" and proof["content_type"] == "application/pdf"
    assert "job-joinings/" not in uploaded.text and "proof_key" not in uploaded.text
    joined = await _joining(client, s["offer"]["id"], joining_status="joined", actual_joining_date=TODAY.isoformat())
    assert joined.status_code == 200, joined.text


@pytest.mark.asyncio
async def test_joined_needs_the_application_still_selected(client, db_session):
    s = await _accepted(client, db_session)
    application = await _fresh(db_session, JobApplication, s["application"]["id"])
    application.status = "withdrawn"
    await db_session.commit()
    response = await _joining(client, s["offer"]["id"], **JOINED)
    assert response.status_code == 409 and response.json()["detail"] == svc.NOT_SELECTED


# --- JN7: vacancies close the requirement ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_last_vacancy_filled_closes_the_requirement(client, db_session):
    s = await _accepted(client, db_session)
    job = await _fresh(db_session, Job, s["job"].id)
    job.vacancies, job.status = 2, "selected"
    await db_session.commit()
    await _joining(client, s["offer"]["id"], **JOINED)
    assert (await _fresh(db_session, Job, s["job"].id)).status == "selected"  # 1 of 2 filled
    second = await _candidate(db_session, s["recruiter"])
    app2 = (await _add(client, s["job"], second)).json()["application"]
    await _move(client, app2["id"], "selected")
    offer2 = await _offer(client, app2["id"])
    await _status(client, offer2["id"], "accepted")
    assert (await _joining(client, offer2["id"], **JOINED)).status_code == 200
    closed = await _fresh(db_session, Job, s["job"].id)
    assert closed.status == "closed"
    company = await _fresh(db_session, Company, s["job"].company_id)
    assert company.stage == "requirement_closed"


@pytest.mark.asyncio
async def test_without_vacancies_the_requirement_stays_open(client, db_session):
    s = await _accepted(client, db_session)
    await _joining(client, s["offer"]["id"], **JOINED)
    assert (await _fresh(db_session, Job, s["job"].id)).status == "requirement_received"


# --- AC2 / JN8: Did Not Join -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_did_not_join_needs_a_reason_and_withdraws_the_application(client, db_session):
    s = await _accepted(client, db_session)
    response = await _joining(client, s["offer"]["id"], joining_status="did_not_join", reason="Took another offer")
    assert response.status_code == 200, response.text
    offer = response.json()["offer"]
    assert (offer["joining"]["status_label"], offer["joining"]["reason"]) == ("Did Not Join", "Took another offer")
    assert offer["application"]["status"] == "withdrawn"
    assert (offer["history"][-1]["event"], offer["history"][-1]["note"]) == ("did_not_join", "Took another offer")
    assert not offer["joining"]["can_upload_proof"] and (await _proof(client, s["offer"]["id"])).status_code == 409
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_joining.update", AuditLog.entity_id == offer["id"]))
    assert "another" not in str(audit.metadata_json)


# --- JN9: the rec-017 route cannot skip the joining ------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_application_route_cannot_set_joined_once_an_offer_exists(client, db_session):
    s = await _accepted(client, db_session)
    response = await _move(client, s["application"]["id"], "joined")
    assert response.status_code == 409 and response.json()["detail"] == svc.USE_JOINING
    assert await _app_status(db_session, s["application"]["id"]) == "selected"


# --- the proof (JN4, security) ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_proof_replace_download_and_rules(client, db_session):
    s = await _accepted(client, db_session)
    assert (await client.get(f"{OFFERS}/{s['offer']['id']}/joining/proof")).status_code == 404
    assert (await _proof(client, s["offer"]["id"], b"MZ not a pdf", "x.exe")).status_code == 415
    await _proof(client, s["offer"]["id"])
    await _proof(client, s["offer"]["id"], PDF + b"% v2\n", "v2.pdf")
    events = (await db_session.scalars(select(JobOfferEvent).where(JobOfferEvent.offer_id == s["offer"]["id"], JobOfferEvent.event == "proof").order_by(JobOfferEvent.position))).all()
    assert len(events) == 2 and events[0].letter_key is None and events[1].letter_key.startswith("job-joinings/")
    download = await client.get(f"{OFFERS}/{s['offer']['id']}/joining/proof")
    assert download.status_code == 200 and download.content == PDF + b"% v2\n"
    assert download.headers["x-content-type-options"] == "nosniff"
    assert f"joining-proof-{s['candidate'].candidate_code}.pdf" in download.headers["content-disposition"]
    assert await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_joining.proof_downloaded", AuditLog.entity_id == s["offer"]["id"]))


# --- JN10: who --------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_reads_but_cannot_write_and_another_recruiter_gets_404(client, db_session):
    s = await _accepted(client, db_session)
    await _proof(client, s["offer"]["id"])
    await login(client, s["manager"])
    read = (await client.get(f"{APPS}/{s['application']['id']}/offer")).json()["offer"]["joining"]
    assert read["status"] == "pending" and not read["can_edit"] and not read["can_upload_proof"] and read["allowed_statuses"] == []
    assert (await _joining(client, s["offer"]["id"], **JOINED)).status_code == 403
    assert (await _proof(client, s["offer"]["id"])).status_code == 403
    assert (await client.get(f"{OFFERS}/{s['offer']['id']}/joining/proof")).status_code == 200
    assert (await client.get(f"{JOININGS}?view=due")).status_code == 200
    stranger = await make_recruiter(db_session, s["manager"])
    await login(client, stranger)
    assert (await _joining(client, s["offer"]["id"], **JOINED)).status_code == 404
    assert (await client.get(f"{OFFERS}/{s['offer']['id']}/joining/proof")).status_code == 404
    assert s["offer"]["id"] not in {i["id"] for i in (await client.get(f"{JOININGS}?view=due&limit=100")).json()["items"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["hr_team", "it_admin", "employer", "it_student"])
async def test_other_roles_are_refused(client, db_session, role):
    s = await _accepted(client, db_session)
    await as_role(client, db_session, role, "it")
    assert (await _joining(client, s["offer"]["id"], **JOINED)).status_code in (403, 404)
    assert (await client.get(JOININGS)).status_code == 403


# --- the list ---------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_joinings_list_views_counts_and_overdue(client, db_session):
    s = await _accepted(client, db_session)
    offer = await _fresh(db_session, JobOffer, s["offer"]["id"])
    offer.joining_date = TODAY - timedelta(days=1)
    await db_session.commit()
    due = await client.get(f"{JOININGS}?view=due&limit=100")
    assert due.status_code == 200, due.text
    body = due.json()
    mine = next(i for i in body["items"] if i["id"] == s["offer"]["id"])
    assert mine["joining"]["overdue"] is True and mine["joining"]["status"] == "pending" and mine["candidate"]["id"] == str(s["candidate"].id)
    assert set(body["counts"]) == {"due", "joined", "did_not_join"} and body["counts"]["due"] >= 1
    assert (await client.get(f"{JOININGS}?view=lunch")).status_code == 422
    # the requirement's own recruiter sees only their scope: a fresh recruiter's list is empty
    s2 = await _accepted(client, db_session)
    await _joining(client, s2["offer"]["id"], **JOINED)
    listed = (await client.get(f"{JOININGS}?view=joined")).json()
    assert [i["id"] for i in listed["items"]] == [s2["offer"]["id"]] and listed["counts"] == {"due": 0, "joined": 1, "did_not_join": 0}
