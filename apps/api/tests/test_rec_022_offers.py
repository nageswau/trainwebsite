"""rec-022 -- offer management (spec §1-§3; AC1-AC3; DEC-SCOPE-152 OF1-OF10). The shared test database is never truncated, so every value
is unique per test."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Company, JobApplication, JobOffer, JobOfferEvent, Notification
from app.services import offers as svc
from tests.rec001_helpers import as_role, login, make_recruiter, make_user
from tests.rec017_helpers import student_application
from tests.test_rec_017_tracking import _add, _candidate, _move, _requirement, _team

APPS = "/api/v1/recruiter/applications"
OFFERS = "/api/v1/recruiter/offers"
STUDENT = "/api/v1/workflows/it/student/offers"
WF = "/api/v1/workflows/it/offers"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


async def _setup(client, db, *, selected=True):
    manager, recruiter = await _team(client, db)
    job = await _requirement(db, recruiter)
    candidate = await _candidate(db, recruiter)
    application = (await _add(client, job, candidate)).json()["application"]
    if selected:
        assert (await _move(client, application["id"], "selected")).status_code == 200
    return {"manager": manager, "recruiter": recruiter, "job": job, "candidate": candidate, "application": application}


async def _record(client, application_id, **over):
    body = {"position": "Java Developer", "compensation": 600000, "currency": "INR"} | over
    return await client.post(f"{APPS}/{application_id}/offer", json=body)


async def _offer(client, application_id, **over) -> dict:
    response = await _record(client, application_id, **over)
    assert response.status_code == 201, response.text
    return response.json()["offer"]


async def _status(client, offer_id, status, note=None):
    return await client.post(f"{OFFERS}/{offer_id}/status", json={"status": status, **({"note": note} if note else {})})


async def _app_status(db, application_id) -> str:
    return await db.scalar(select(JobApplication.status).where(JobApplication.id == application_id).execution_options(populate_existing=True))


async def _upload(client, offer_id, data=PDF, name="Offer Letter.pdf"):
    return await client.put(f"{OFFERS}/{offer_id}/letter", files={"file": (name, data, "application/pdf")})


# --- the catalogue (OF1, OF3, OF9) --------------------------------------------------------------------------------------------------
def test_catalogue_matches_section_16():
    assert list(svc.STATUS_LABELS) == ["offer_pending", "offer_received", "accepted", "declined"]
    assert list(svc.STATUS_LABELS.values()) == ["Offer Pending", "Offer Received", "Accepted", "Declined"]
    assert svc.MOVES == {"offer_pending": ("offer_received", "accepted", "declined"), "offer_received": ("accepted", "declined"), "accepted": (), "declined": ()}


@pytest.mark.parametrize(
    ("word", "key"),
    [
        ("offered", "offer_received"),
        ("pending", "offer_pending"),
        ("accepted", "accepted"),
        ("joined", "accepted"),
        ("declined", "declined"),
        ("rejected", "declined"),
        ("offer_pending", "offer_pending"),
        ("offer_received", "offer_received"),
        ("lunch", None),
    ],
)
def test_legacy_words_map_to_keys(word, key):
    assert svc.from_legacy(word) == key


# --- record (OF4, AC1) --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_record_on_a_selected_application_with_history_company_stage_and_audit(client, db_session):
    s = await _setup(client, db_session)
    empty = await client.get(f"{APPS}/{s['application']['id']}/offer")
    assert empty.status_code == 200 and empty.json() == {"offer": None, "can_create": True, "suggested_position": s["job"].title}
    joining = (date.today() + timedelta(days=30)).isoformat()
    item = await _offer(client, s["application"]["id"], joining_date=joining)
    assert (item["status"], item["status_label"], item["position"], item["currency"]) == ("offer_pending", "Offer Pending", "Java Developer", "INR")
    assert float(item["compensation"]) == 600000 and item["offered_on"] == date.today().isoformat() and item["joining_date"] == joining
    assert item["letter"] is None and item["letter_url"] is None
    assert item["candidate"]["id"] == str(s["candidate"].id) and item["requirement"]["id"] == str(s["job"].id)
    assert item["application"]["status"] == "selected"
    assert [(h["event"], h["from_status"], h["to_status"]) for h in item["history"]] == [("created", None, "offer_pending")]
    assert {m["key"] for m in item["allowed_statuses"]} == {"offer_received", "accepted", "declined"}
    assert item["can_edit"] and item["can_upload"]
    company = await db_session.scalar(select(Company).where(Company.id == s["job"].company_id).execution_options(populate_existing=True))
    assert company.stage == "selected"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_offer.create", AuditLog.entity_id == item["id"]))
    assert audit is not None and "600000" not in str(audit.metadata_json)
    again = await client.get(f"{APPS}/{s['application']['id']}/offer")
    assert again.json()["offer"]["id"] == item["id"] and again.json()["can_create"] is False


@pytest.mark.asyncio
async def test_an_offer_only_for_a_selected_application(client, db_session):
    s = await _setup(client, db_session, selected=False)
    response = await _record(client, s["application"]["id"])
    assert response.status_code == 409 and "Selected" in response.json()["detail"]
    assert (await client.get(f"{APPS}/{s['application']['id']}/offer")).json()["can_create"] is False


@pytest.mark.asyncio
async def test_a_second_offer_is_409(client, db_session):
    s = await _setup(client, db_session)
    await _offer(client, s["application"]["id"])
    assert (await _record(client, s["application"]["id"])).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("over", "field"),
    [
        ({"position": " "}, "position"),
        ({"position": "x" * 161}, "position"),
        ({"compensation": 0}, "compensation"),
        ({"compensation": -5}, "compensation"),
        ({"currency": "rupees"}, "currency"),
        ({"status": "accepted"}, "status"),
        ({"offered_on": (date.today() + timedelta(days=1)).isoformat()}, "offered_on"),
        ({"offered_on": date.today().isoformat(), "joining_date": (date.today() - timedelta(days=1)).isoformat()}, "joining_date"),
        ({"letter_url": "https://x.example.com"}, "letter_url"),
    ],
)
async def test_record_validation_422(client, db_session, over, field):
    s = await _setup(client, db_session)
    response = await _record(client, s["application"]["id"], **over)
    assert response.status_code == 422, response.text
    assert any(field in e["loc"] for e in response.json()["detail"])


@pytest.mark.asyncio
@pytest.mark.parametrize(("over", "message"), [
    ({"compensation": 0}, "Enter a salary above 0"),
    ({"compensation": 1e13}, "Enter a salary below 1,000,000,000,000 with at most 2 decimals"),
    ({"compensation": 10.123}, "Enter a salary below 1,000,000,000,000 with at most 2 decimals"),
    ({"currency": "rs1"}, "Enter a 3-letter currency code, such as INR"),
])
async def test_salary_and_currency_errors_are_plain_words(client, db_session, over, message):
    """QA-01: the form shows these messages as they are, so they must not be pydantic's own wording."""
    s = await _setup(client, db_session)
    response = await _record(client, s["application"]["id"], **over)
    assert response.status_code == 422
    assert message in response.json()["detail"][0]["msg"]


@pytest.mark.asyncio
async def test_record_received_notifies_the_student(client, db_session):
    s = await _setup(client, db_session)
    student = await make_user(db_session, "it_student", "it")
    application = await student_application(db_session, s["job"].id, student, "selected")
    await db_session.commit()
    item = await _offer(client, application.id, status="offer_received")
    assert item["status"] == "offer_received"
    note = await db_session.scalar(select(Notification).where(Notification.user_id == student.id, Notification.title == "Job offer received"))
    assert note is not None and "600000" not in note.body


# --- moves (OF3, OF6, AC2) ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_received_then_accepted_keeps_the_application_selected_with_history(client, db_session):
    s = await _setup(client, db_session)
    item = await _offer(client, s["application"]["id"])
    received = await _status(client, item["id"], "offer_received", "Letter emailed")
    assert received.status_code == 200 and received.json()["offer"]["status"] == "offer_received"
    accepted = (await _status(client, item["id"], "accepted")).json()["offer"]
    assert accepted["status"] == "accepted" and accepted["allowed_statuses"] == [] and not accepted["can_edit"]
    assert [(h["event"], h["from_status"], h["to_status"], h["note"]) for h in accepted["history"]] == [
        ("created", None, "offer_pending", None),
        ("status", "offer_pending", "offer_received", "Letter emailed"),
        ("status", "offer_received", "accepted", None),
    ]
    assert await _app_status(db_session, s["application"]["id"]) == "selected"
    final = await _status(client, item["id"], "declined")
    assert final.status_code == 409


@pytest.mark.asyncio
async def test_declined_withdraws_the_application(client, db_session):
    s = await _setup(client, db_session)
    item = await _offer(client, s["application"]["id"], status="offer_received")
    declined = (await _status(client, item["id"], "declined")).json()["offer"]
    assert declined["status"] == "declined" and declined["application"]["status"] == "withdrawn"
    assert await _app_status(db_session, s["application"]["id"]) == "withdrawn"
    assert not declined["can_upload"]


@pytest.mark.asyncio
async def test_received_cannot_go_back_to_pending(client, db_session):
    s = await _setup(client, db_session)
    item = await _offer(client, s["application"]["id"], status="offer_received")
    assert (await _status(client, item["id"], "offer_pending")).status_code == 422  # never a move target (OF3)
    assert (await _status(client, item["id"], "offer_received")).status_code == 409
    assert (await client.post(f"{OFFERS}/{item['id']}/status", json={"status": "joined"})).status_code == 422


# --- revise (OF5) -------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_revised_offer_records_the_changed_field_names_only(client, db_session):
    s = await _setup(client, db_session)
    item = await _offer(client, s["application"]["id"])
    same = await client.patch(f"{OFFERS}/{item['id']}", json={"position": "Java Developer"})
    assert same.status_code == 200 and len(same.json()["offer"]["history"]) == 1
    revised = (await client.patch(f"{OFFERS}/{item['id']}", json={"compensation": 650000, "position": "Senior Java Developer"})).json()["offer"]
    assert float(revised["compensation"]) == 650000 and revised["position"] == "Senior Java Developer"
    assert (revised["history"][-1]["event"], revised["history"][-1]["fields"]) == ("revised", ["compensation", "position"])
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_offer.update", AuditLog.entity_id == item["id"]))
    assert audit.metadata_json == {"fields": ["compensation", "position"]}
    bad = await client.patch(f"{OFFERS}/{item['id']}", json={"position": None})
    assert bad.status_code == 422
    await _status(client, item["id"], "accepted")
    assert (await client.patch(f"{OFFERS}/{item['id']}", json={"position": "Lead"})).status_code == 409


# --- the letter (OF7) ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_upload_replace_and_download_the_letter(client, db_session):
    s = await _setup(client, db_session)
    item = await _offer(client, s["application"]["id"])
    first = await _upload(client, item["id"])
    assert first.status_code == 200, first.text
    letter = first.json()["offer"]["letter"]
    assert letter["name"] == "Offer Letter.pdf" and letter["content_type"] == "application/pdf"
    assert "job-offers/" not in first.text and "letter_key" not in first.text
    second = (await _upload(client, item["id"], PDF + b"% v2\n", "v2.pdf")).json()["offer"]
    assert second["letter"]["name"] == "v2.pdf"
    events = (await db_session.scalars(select(JobOfferEvent).where(JobOfferEvent.offer_id == item["id"], JobOfferEvent.event == "letter").order_by(JobOfferEvent.position))).all()
    assert len(events) == 2 and events[0].letter_key is None and events[1].letter_key is not None
    download = await client.get(f"{OFFERS}/{item['id']}/letter")
    assert download.status_code == 200 and download.content == PDF + b"% v2\n"
    assert download.headers["content-type"] == "application/pdf" and download.headers["x-content-type-options"] == "nosniff"
    assert f"offer-{s['candidate'].candidate_code}.pdf" in download.headers["content-disposition"]
    assert await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_offer.letter_downloaded", AuditLog.entity_id == item["id"]))


@pytest.mark.asyncio
async def test_letter_rules(client, db_session):
    s = await _setup(client, db_session)
    item = await _offer(client, s["application"]["id"])
    assert (await client.get(f"{OFFERS}/{item['id']}/letter")).status_code == 404
    assert (await _upload(client, item["id"], b"MZ not a pdf", "x.exe")).status_code == 415
    assert (await _upload(client, item["id"], b"", "x.pdf")).status_code == 422
    await _status(client, item["id"], "declined")
    assert (await _upload(client, item["id"])).status_code == 409


@pytest.mark.asyncio
async def test_a_legacy_letter_url_is_shown_only_when_http(client, db_session):
    s = await _setup(client, db_session)
    item = await _offer(client, s["application"]["id"])
    offer = await db_session.get(JobOffer, item["id"])
    offer.letter_url = "javascript:alert(1)"
    await db_session.commit()
    assert (await client.get(f"{APPS}/{s['application']['id']}/offer")).json()["offer"]["letter_url"] is None
    offer.letter_url = "https://files.example.com/letter.pdf"
    await db_session.commit()
    assert (await client.get(f"{APPS}/{s['application']['id']}/offer")).json()["offer"]["letter_url"] == "https://files.example.com/letter.pdf"


# --- who (OF8) ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_reads_but_cannot_write_and_another_recruiter_gets_404(client, db_session):
    s = await _setup(client, db_session)
    item = await _offer(client, s["application"]["id"])
    await login(client, s["manager"])
    read = (await client.get(f"{APPS}/{s['application']['id']}/offer")).json()
    assert read["offer"]["allowed_statuses"] == [] and not read["offer"]["can_edit"] and not read["offer"]["can_upload"] and not read["can_create"]
    assert (await _status(client, item["id"], "accepted")).status_code == 403
    assert (await client.patch(f"{OFFERS}/{item['id']}", json={"position": "Lead"})).status_code == 403
    assert (await _upload(client, item["id"])).status_code == 403
    stranger = await make_recruiter(db_session, s["manager"])
    await login(client, stranger)
    assert (await client.get(f"{APPS}/{s['application']['id']}/offer")).status_code == 404
    assert (await _status(client, item["id"], "accepted")).status_code == 404
    assert (await client.get(f"{OFFERS}/{item['id']}/letter")).status_code == 404
    assert (await _record(client, s["application"]["id"])).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["hr_team", "it_admin", "employer", "it_student"])
async def test_other_roles_are_refused_on_the_recruiter_routes(client, db_session, role):
    s = await _setup(client, db_session)
    item = await _offer(client, s["application"]["id"])
    await as_role(client, db_session, role, "it")
    assert (await client.get(f"{APPS}/{s['application']['id']}/offer")).status_code == 403
    assert (await _status(client, item["id"], "accepted")).status_code in (403, 404)
    assert (await client.get(f"{OFFERS}/{item['id']}/letter")).status_code in (403, 404)


@pytest.mark.asyncio
async def test_the_student_reads_only_their_own_offers_and_letter(client, db_session):
    s = await _setup(client, db_session)
    student = await make_user(db_session, "it_student", "it")
    application = await student_application(db_session, s["job"].id, student, "selected")
    await db_session.commit()
    item = await _offer(client, application.id, status="offer_received")
    await _upload(client, item["id"])
    other = await _offer(client, s["application"]["id"])  # the external candidate's offer
    await login(client, student)
    listed = await client.get(STUDENT)
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [i["id"] for i in items] == [item["id"]]
    mine = items[0]
    assert (mine["status_label"], mine["position"], mine["has_letter"], mine["company"]) == ("Offer Received", "Java Developer", True, (await db_session.get(Company, s["job"].company_id)).name)
    assert "history" not in mine and "candidate" not in mine
    assert (await client.get(f"{STUDENT}/{item['id']}/letter")).content == PDF
    assert (await client.get(f"{STUDENT}/{other['id']}/letter")).status_code == 404
    await as_role(client, db_session, "placement_team", "it")
    assert (await client.get(STUDENT)).status_code == 403


# --- the legacy routes (OF9, AC3) ---------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_legacy_routes_map_words_write_history_and_keep_accepted_joined(client, db_session):
    s = await _setup(client, db_session)
    student = await make_user(db_session, "it_student", "it")
    application = await student_application(db_session, s["job"].id, student, "interview")
    await db_session.commit()
    await as_role(client, db_session, "placement_team", "it")
    created = await client.post(WF, json={"application_id": str(application.id), "compensation": 500000, "letter_url": "https://x.example.com/l.pdf"})
    assert created.status_code == 201 and created.json()["status"] == "offer_received"
    assert await _app_status(db_session, application.id) == "selected"
    offer_id = created.json()["id"]
    assert (await client.patch(f"{WF}/{offer_id}", json={"status": "lunch"})).status_code == 422
    joined = await client.patch(f"{WF}/{offer_id}", json={"status": "joined"})
    assert joined.status_code == 200 and joined.json()["status"] == "accepted"
    assert await _app_status(db_session, application.id) == "joined"
    events = (await db_session.scalars(select(JobOfferEvent).where(JobOfferEvent.offer_id == offer_id).order_by(JobOfferEvent.position))).all()
    assert [(e.event, e.from_status, e.to_status) for e in events] == [("created", None, "offer_received"), ("status", "offer_received", "accepted")]
    assert (await client.post(WF, json={"application_id": str(application.id)})).status_code == 409


@pytest.mark.asyncio
async def test_the_student_placement_status_page_no_longer_repeats_offers(client, db_session):
    """QA-04: the "My offers" card (GET /workflows/it/student/offers) supersedes the portal's text-only Offers panel."""
    student = await make_user(db_session, "it_student", "it")
    await login(client, student)
    body = (await client.get("/api/v1/portal/it/student/placement-status")).json()
    assert body["title"] == "Placement Status"
    assert all(panel["title"] != "Offers" for panel in body.get("panels") or [])
