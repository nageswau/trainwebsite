"""upc-017 -- course / program master (spec §1-§5; AC1, AC2, P1, N1, E1, U2; DEC-SCOPE-147 CO1-CO16)."""

import uuid

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, OverseasCourse, Scholarship, University
from app.services.partnership_access import COMMISSION_FIELDS
from tests.test_upc_026_documents import _owned
from tests.upc003_helpers import catalogue_country, create, internal_country, login, make_application, make_pm, make_user, url

MENU = "/api/v1/partnership/courses"


def courses_url(university_id, course_id=None) -> str:
    return url(university_id, "courses") + (f"/{course_id}" if course_id else "")


def course_body(**over) -> dict:
    """The backlog's positive scenario: "MSc Cyber Security, PG, 1 yr, Sep/Jan, £18,000, IELTS 6.5"."""
    return {
        "title": f"MSc Cyber Security {uuid.uuid4().hex[:6]}",
        "level": "PG",
        "category": "Computer Science",
        "duration": "1 year",
        "intakes": ["Sep", "Jan"],
        "tuition_amount": "18000",
        "tuition_currency": "GBP",
        "english_test": "IELTS",
        "english_score": "6.5",
    } | over


async def add_course(client, university_id, **over) -> dict:
    response = await client.post(courses_url(university_id), json=course_body(**over))
    assert response.status_code == 201, response.text
    return response.json()["course"]


async def scholarship(db, *, university_id=None, country_id=None, title="Global Excellence Award") -> Scholarship:
    row = Scholarship(title=title, university_id=university_id, country_id=country_id, eligibility="Merit", amount="£5,000", active=True)
    db.add(row)
    await db.commit()
    return row


# --- P1 + AC1: every §16 field is captured ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_records_every_field_and_reads_it_back(client, db_session):
    _, pm, _, uni = await _owned(client, db_session)
    award = await scholarship(db_session, university_id=uuid.UUID(uni["id"]))
    c = await add_course(
        client,
        uni["id"],
        application_fee="75",
        application_fee_currency="GBP",
        entry_requirements="2:1 honours degree in computing",
        application_process="Apply online, then upload transcripts",
        deadline="2027-06-30",
        scholarship_ids=[str(award.id)],
        commission={"percent": "12.5"},
    )
    assert c["title"].startswith("MSc Cyber Security") and c["level"] == "PG" and c["category"] == "Computer Science" and c["duration"] == "1 year"
    assert c["intakes"] == ["Jan", "Sep"] and c["intake"] == "Jan, Sep"  # calendar order; the catalogue text is re-derived (CO7)
    assert c["tuition_amount"] == "18000.00" and c["tuition_currency"] == "GBP" and c["tuition_fee"] == "GBP 18,000"  # CO4
    assert c["application_fee"] == "75.00" and c["application_fee_currency"] == "GBP"
    assert c["english_test"] == "IELTS" and c["english_score"] == "6.5"
    assert c["entry_requirements"] == "2:1 honours degree in computing" and c["application_process"] == "Apply online, then upload transcripts"
    assert c["deadline"] == "2027-06-30" and c["active"] is True
    assert c["scholarships"] == [{"id": str(award.id), "title": "Global Excellence Award", "amount": "£5,000"}]
    assert c["commission"] == {"percent": "12.50", "amount": None, "currency": None}
    assert c["university_id"] == uni["id"] and c["permissions"] == {"can_edit": True}
    listed = (await client.get(courses_url(uni["id"]))).json()
    assert [x["id"] for x in listed["items"]] == [c["id"]] and listed["total"] == 1 and listed["can_edit"] is True
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == c["id"]))).all()
    assert [a.action for a in audit] == ["university_course.create"]
    assert "12.5" not in str(audit[0].metadata_json) and "commission" in audit[0].metadata_json["fields"]  # field names only (CO16)


@pytest.mark.asyncio
async def test_patch_changes_only_the_fields_sent_and_rederives_the_catalogue_texts(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    c = await add_course(client, uni["id"], commission={"amount": "1500", "currency": "GBP"})
    response = await client.patch(courses_url(uni["id"], c["id"]), json={"tuition_amount": "19500.50", "intakes": ["May"], "commission": None})
    assert response.status_code == 200, response.text
    edited = response.json()["course"]
    assert edited["tuition_fee"] == "GBP 19,500.50" and edited["intake"] == "May" and edited["commission"] is None
    assert edited["title"] == c["title"] and edited["english_score"] == "6.5"
    cleared = (await client.patch(courses_url(uni["id"], c["id"]), json={"tuition_amount": None, "tuition_currency": None, "intakes": []})).json()["course"]
    assert cleared["tuition_fee"] == "" and cleared["intake"] == ""
    same = await client.patch(courses_url(uni["id"], c["id"]), json={"title": c["title"]})
    assert same.status_code == 200
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == c["id"]))).all()
    assert sorted(actions) == ["university_course.create", "university_course.update", "university_course.update"]  # no-change is not audited


@pytest.mark.asyncio
async def test_a_legacy_level_stays_until_the_level_is_edited(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    legacy = OverseasCourse(university_id=uuid.UUID(uni["id"]), title="MSc Old", level="Masters", category="Tech", duration="1 year", tuition_fee="£9,000", intake="Winter")
    db_session.add(legacy)
    await db_session.commit()
    response = await client.patch(courses_url(uni["id"], legacy.id), json={"duration": "12 months"})
    assert response.status_code == 200, response.text
    assert response.json()["course"]["level"] == "Masters" and response.json()["course"]["tuition_fee"] == "£9,000"  # untouched (CO3, CO4)
    assert (await client.patch(courses_url(uni["id"], legacy.id), json={"level": "Masters"})).status_code == 422


# --- N1 + CO4-CO9: validation ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_invalid_values_are_422(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    other_uni = await create_other(client, db_session, head, pm)
    foreign = await scholarship(db_session, university_id=uuid.UUID(other_uni["id"]))
    post = lambda **over: client.post(courses_url(uni["id"]), json=course_body(**over))  # noqa: E731
    assert (await post(tuition_amount="-1")).status_code == 422  # the backlog's negative scenario
    assert (await post(application_fee="-5", application_fee_currency="GBP")).status_code == 422
    assert (await post(tuition_currency=None)).status_code == 422  # amount without currency
    assert (await post(application_fee="75")).status_code == 422
    assert (await post(english_test=None)).status_code == 422  # a score needs a test
    assert (await post(english_score="9.5")).status_code == 422  # IELTS tops out at 9
    assert (await post(english_test="TOEFL", english_score="121")).status_code == 422
    assert (await post(english_test="TOEFL", english_score="100")).status_code == 201
    assert (await post(level="Masters")).status_code == 422
    assert (await post(intakes=["Sept"])).status_code == 422
    assert (await post(tuition_currency="JPY")).status_code == 422
    assert (await post(title="  ")).status_code == 422
    assert (await post(scholarship_ids=[str(foreign.id)])).status_code == 422
    assert (await post(commission={"percent": "10", "amount": "5", "currency": "GBP"})).status_code == 422
    assert (await post(commission={"amount": "5"})).status_code == 422
    assert (await post(commission={"percent": "101"})).status_code == 422
    assert (await post(unknown="x")).status_code == 422
    c = await add_course(client, uni["id"])
    assert (await client.patch(courses_url(uni["id"], c["id"]), json={"title": None})).status_code == 422
    assert (await client.patch(courses_url(uni["id"], c["id"]), json={"tuition_currency": None})).status_code == 422


async def create_other(client, db, head, pm) -> dict:
    await login(client, head)
    other = await create(client, (await catalogue_country(db)).id)
    await login(client, pm)
    return other


@pytest.mark.asyncio
async def test_scholarships_of_this_university_or_its_country_are_offered(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    country_id = (await catalogue_country(db_session)).id
    own = await scholarship(db_session, university_id=uuid.UUID(uni["id"]), title=f"Own {uuid.uuid4().hex[:6]}")
    national = await scholarship(db_session, country_id=country_id, title=f"National {uuid.uuid4().hex[:6]}")
    elsewhere = await scholarship(db_session, country_id=(await internal_country(db_session)).id, title=f"Elsewhere {uuid.uuid4().hex[:6]}")
    options = (await client.get(url(uni["id"], "course-options"))).json()["scholarships"]
    ids = {o["id"] for o in options}
    assert {str(own.id), str(national.id)} <= ids and str(elsewhere.id) not in ids
    c = await add_course(client, uni["id"], scholarship_ids=[str(national.id)])
    assert c["scholarships"][0]["id"] == str(national.id)
    other = await make_pm(db_session, head)
    await login(client, other)
    assert (await client.get(url(uni["id"], "course-options"))).status_code == 403  # options are for the writers


# --- CO12: duplicates -----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_same_title_and_level_in_one_university_is_409(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    c = await add_course(client, uni["id"], title="MSc Cyber Security")
    again = await client.post(courses_url(uni["id"]), json=course_body(title="  msc   CYBER security "))
    assert again.status_code == 409 and "already" in again.json()["detail"]
    assert (await client.post(courses_url(uni["id"]), json=course_body(title="MSc Cyber Security", level="PhD"))).status_code == 201
    other = await add_course(client, uni["id"], title="MSc Networks")
    assert (await client.patch(courses_url(uni["id"], other["id"]), json={"title": "MSC CYBER SECURITY"})).status_code == 409
    assert (await client.patch(courses_url(uni["id"], c["id"]), json={"title": "MSc Cyber Security"})).status_code == 200  # itself
    elsewhere = await create_other(client, db_session, head, pm)
    await login(client, head)
    assert (await client.post(courses_url(elsewhere["id"]), json=course_body(title="MSc Cyber Security"))).status_code == 201


# --- E1 + AC2 + CO11: deactivation with open applications ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deactivating_a_course_with_applications_is_allowed_and_keeps_them(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    c = await add_course(client, uni["id"])
    application = await make_application(db_session, uuid.UUID(uni["id"]))
    await db_session.execute(update(type(application)).where(type(application).id == application.id).values(course_id=uuid.UUID(c["id"])))
    await db_session.commit()
    response = await client.patch(courses_url(uni["id"], c["id"]), json={"active": False})
    assert response.status_code == 200 and response.json()["course"]["active"] is False
    await db_session.refresh(application)
    assert str(application.course_id) == c["id"]
    assert (await client.get(courses_url(uni["id"]))).json()["total"] == 0  # the default list is the active offer
    everything = (await client.get(courses_url(uni["id"]), params={"include_inactive": "true"})).json()
    assert [(x["id"], x["active"]) for x in everything["items"]] == [(c["id"], False)]
    assert (await client.patch(courses_url(uni["id"], c["id"]), json={"active": True})).json()["course"]["active"] is True


# --- CO1 + U2: who reads, who writes, who sees commission ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_overseas_admin_maintains_courses_but_never_sees_or_sets_commission(client, db_session):
    head, _, _, uni = await _owned(client, db_session)
    await add_course(client, uni["id"], commission={"percent": "10"})
    admin = await make_user(db_session, "overseas_admin", "overseas")
    await login(client, admin)
    listed = await client.get(courses_url(uni["id"]))
    assert listed.status_code == 200 and listed.json()["can_edit"] is True
    assert all("commission" not in item for item in listed.json()["items"]) and "commission" not in listed.text
    refused = await client.post(courses_url(uni["id"]), json=course_body(commission={"percent": "5"}))
    assert refused.status_code == 403
    created = await client.post(courses_url(uni["id"]), json=course_body())
    assert created.status_code == 201 and "commission" not in created.json()["course"]
    assert (await client.patch(courses_url(uni["id"], created.json()["course"]["id"]), json={"commission": None})).status_code == 403
    menu = await client.get(MENU)
    assert menu.status_code == 200 and "commission" not in menu.text
    await login(client, head)
    assert all("commission" in item for item in (await client.get(courses_url(uni["id"]))).json()["items"])
    assert "commission" in COMMISSION_FIELDS


@pytest.mark.asyncio
async def test_access_by_role_and_scope(client, db_session):
    head, pm, other_pm, uni = await _owned(client, db_session)
    c = await add_course(client, uni["id"])
    await login(client, other_pm)  # a manager of the same team who does not own this university reads but cannot write
    assert (await client.get(courses_url(uni["id"]))).json()["can_edit"] is False
    assert (await client.post(courses_url(uni["id"]), json=course_body())).status_code == 403
    assert (await client.patch(courses_url(uni["id"], c["id"]), json={"duration": "2 years"})).status_code == 403
    for role in ("counselor", "bdm", "agent", "university_rep", "overseas_student"):
        await login(client, await make_user(db_session, role, "overseas"))
        assert (await client.get(courses_url(uni["id"]))).status_code == 403, role
        assert (await client.get(MENU)).status_code == 403, role
    client.cookies.clear()
    assert (await client.get(courses_url(uni["id"]))).status_code == 401
    await login(client, pm)
    assert (await client.get(courses_url(uuid.uuid4()))).status_code == 404
    other_uni = await create_other(client, db_session, head, pm)
    await login(client, head)
    assert (await client.patch(courses_url(other_uni["id"], c["id"]), json={"duration": "2 years"})).status_code == 404  # no IDOR via the URL
    await db_session.execute(update(University).where(University.id == uuid.UUID(uni["id"])).values(active=False))
    await db_session.commit()
    assert (await client.post(courses_url(uni["id"]), json=course_body())).status_code == 409


# --- CO15: the "Courses & Programs" menu ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_menu_lists_every_university_course_with_filters(client, db_session):
    _, _, _, uni = await _owned(client, db_session)
    tag = uuid.uuid4().hex[:8]
    pg = await add_course(client, uni["id"], title=f"MSc Menu {tag}")
    phd = await add_course(client, uni["id"], title=f"PhD Menu {tag}", level="PhD")
    await client.patch(courses_url(uni["id"], phd["id"]), json={"active": False})
    page = (await client.get(MENU, params={"q": tag})).json()
    assert [x["id"] for x in page["items"]] == [pg["id"]] and page["items"][0]["university"]["id"] == uni["id"]
    assert page["items"][0]["university"]["country"] == "United Kingdom" and page["limit"] == 50
    assert [x["id"] for x in (await client.get(MENU, params={"q": tag, "status": "inactive"})).json()["items"]] == [phd["id"]]
    assert {x["id"] for x in (await client.get(MENU, params={"q": tag, "status": "all"})).json()["items"]} == {pg["id"], phd["id"]}
    assert (await client.get(MENU, params={"q": tag, "level": "PhD", "status": "all"})).json()["total"] == 1
    assert (await client.get(MENU, params={"q": uni["university_code"]})).json()["total"] == 1
    assert (await client.get(MENU, params={"level": "Masters"})).status_code == 422
