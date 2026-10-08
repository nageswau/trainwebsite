"""rec-009 -- the candidate master: roles, create, list, detail, edit, duplicates (Q-07), archive, pool filter (spec §4-§7). Mobiles and
emails are random per test (the database is shared and never truncated)."""

import asyncio
import random
import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, Candidate, RecCandidateSource
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user

BASE = "/api/v1/recruiter/candidates"
OUTSIDERS = [("employer", "it"), ("it_admin", "it"), ("it_student", "it"), ("telecaller", "it"), ("bdm", "it")]


def mobile() -> str:
    return "9" + "".join(random.choices("0123456789", k=9))


def mail() -> str:
    return f"cand{uuid.uuid4().hex[:10]}@example.com"


async def source_id(db, name="Referral") -> str:
    return str(await db.scalar(select(RecCandidateSource.id).where(RecCandidateSource.name == name)))


async def body(db, **overrides) -> dict:
    data = {"name": "Rahul Sharma", "mobile": mobile(), "email": mail(), "source_id": await source_id(db)}
    data.update(overrides)
    return data


async def as_recruiter(client, db):
    user = await make_recruiter(db)
    await login(client, user)
    return user


async def create(client, db, **overrides) -> dict:
    response = await client.post(BASE, json=await body(db, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


# --- roles -----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), OUTSIDERS)
async def test_outsiders_are_refused_before_anything_is_read(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(BASE)).status_code == 403
    assert (await client.get(f"{BASE}/{uuid.uuid4()}")).status_code == 403
    assert (await client.post(BASE, json=await body(db_session))).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(BASE)).status_code == 401


@pytest.mark.asyncio
async def test_hr_team_reads_but_never_writes(client, db_session):
    await as_recruiter(client, db_session)
    created = await create(client, db_session)
    await as_role(client, db_session, "hr_team", "it")
    assert (await client.get(BASE)).status_code == 200
    detail = await client.get(f"{BASE}/{created['id']}")
    assert detail.status_code == 200 and detail.json()["can_edit"] is False
    assert (await client.post(BASE, json=await body(db_session))).status_code == 403
    assert (await client.patch(f"{BASE}/{created['id']}", json={"name": "X Y"})).status_code == 403
    assert (await client.post(f"{BASE}/{created['id']}/archive")).status_code == 403
    assert (await client.get(f"{BASE}/duplicate-check", params={"email": mail()})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["placement_manager", "super_admin"])
async def test_managers_and_super_admin_write(client, db_session, role):
    await as_role(client, db_session, role, "global")
    created = await create(client, db_session)
    assert created["can_edit"] is True


@pytest.mark.asyncio
async def test_a_recruiter_edits_a_candidate_another_recruiter_added(client, db_session):
    """R11: every recruiter edits the whole pool."""
    await as_recruiter(client, db_session)
    created = await create(client, db_session)
    await as_recruiter(client, db_session)
    response = await client.patch(f"{BASE}/{created['id']}", json={"status": "interviewing"})
    assert response.status_code == 200 and response.json()["status"] == "interviewing"


# --- create (AC1, AC2) -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_every_section_8_field_is_captured(client, db_session):
    user = await as_recruiter(client, db_session)
    data = await body(
        db_session,
        name="  Rahul Verma ", mobile="+91 98" + mobile()[2:], location="Hyderabad", qualification="B.Tech", college="JNTU",
        passing_year=2022, experience_months=30, current_company="ABC Technologies", current_salary="450000", expected_salary=600000.5,
        notice_days=30, preferred_locations=["Hyderabad", " Bengaluru ", "hyderabad", ""], preferred_role="Python Developer",
        linkedin="https://www.linkedin.com/in/rahul", source_id=await source_id(db_session, "Edusphere students"),
        source_detail="Edusphere Python Full Stack Course", status="available",
    )
    data["email"] = data["email"].upper()
    response = await client.post(BASE, json=data)
    assert response.status_code == 201, response.text
    out = response.json()
    assert out["candidate_code"].startswith("CAN-") and len(out["candidate_code"]) == 10
    assert out["name"] == "Rahul Verma" and out["email"] == data["email"].lower()
    assert (out["location"], out["qualification"], out["college"], out["passing_year"]) == ("Hyderabad", "B.Tech", "JNTU", 2022)
    assert (out["experience_months"], out["current_company"], out["notice_days"]) == (30, "ABC Technologies", 30)
    assert float(out["current_salary"]) == 450000 and float(out["expected_salary"]) == 600000.5
    assert out["preferred_locations"] == ["Hyderabad", "Bengaluru"] and out["preferred_role"] == "Python Developer"
    assert out["linkedin"] == "https://www.linkedin.com/in/rahul"
    assert out["source"]["name"] == "Edusphere students" and out["source_detail"] == "Edusphere Python Full Stack Course"
    assert out["status"] == "available" and out["archived"] is False and out["resumes"] == []
    assert out["created_by"]["id"] == str(user.id)
    row = await db_session.get(Candidate, uuid.UUID(out["id"]))
    assert row.mobile_normalized.startswith("+91") and row.user_id is None and row.opted_in is False


@pytest.mark.asyncio
async def test_only_a_mobile_or_only_an_email_is_enough(client, db_session):
    await as_recruiter(client, db_session)
    assert (await client.post(BASE, json=await body(db_session, email=None))).status_code == 201
    assert (await client.post(BASE, json=await body(db_session, mobile=None))).status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"mobile": None, "email": None}, "Enter a mobile number or an email"),
        ({"mobile": "", "email": "  "}, "Enter a mobile number or an email"),
        ({"source_id": None}, "Source is required"),
        ({"name": " "}, "Name is required"),
        ({"mobile": "12345"}, "Enter a valid mobile number"),
        ({"email": "not-an-email"}, "Enter a valid email address"),
        ({"linkedin": "javascript:alert(1)"}, "LinkedIn must be a link"),
        ({"passing_year": 1900}, "Passing year"),
        ({"experience_months": -1}, "Total experience"),
        ({"notice_days": 400}, "Notice period"),
        ({"current_salary": -5}, "Current salary"),
        ({"status": "blacklisted"}, "Status"),
        ({"preferred_locations": [f"City {i}" for i in range(11)]}, "at most 10"),
        ({"owner": "x"}, "Unknown field: owner"),
    ],
)
async def test_invalid_bodies_are_one_readable_422(client, db_session, change, message):
    await as_recruiter(client, db_session)
    data = await body(db_session)
    data.update(change)
    response = await client.post(BASE, json=data)
    assert response.status_code == 422 and message in response.json()["detail"], response.text


@pytest.mark.asyncio
async def test_source_must_exist_and_be_active(client, db_session):
    await as_recruiter(client, db_session)
    inactive = RecCandidateSource(name=f"Old fair {uuid.uuid4().hex[:6]}", active=False, sort_order=99)
    db_session.add(inactive)
    await db_session.commit()
    for value in (str(inactive.id), str(uuid.uuid4())):
        response = await client.post(BASE, json=await body(db_session, source_id=value))
        assert response.status_code == 422 and response.json()["detail"] == "Choose an active candidate source"


# --- duplicates (AC3, Q-07) ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_same_mobile_in_another_format_is_blocked_with_the_panel(client, db_session):
    await as_recruiter(client, db_session)
    number = mobile()
    first = await create(client, db_session, mobile=number, email=None)
    response = await client.post(BASE, json=await body(db_session, mobile=f"+91-{number[:5]} {number[5:]}", email=None))
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "duplicate_candidate"
    [match] = detail["matches"]
    assert match["id"] == first["id"] and match["candidate_code"] == first["candidate_code"] and match["matched_on"] == ["mobile"]
    assert set(match) == {"id", "candidate_code", "name", "source_name", "status", "archived", "matched_on"}  # no contact data echoed


@pytest.mark.asyncio
async def test_the_same_email_in_another_case_is_blocked_even_when_archived(client, db_session):
    await as_recruiter(client, db_session)
    email = mail()
    first = await create(client, db_session, email=email)
    assert (await client.post(f"{BASE}/{first['id']}/archive")).status_code == 200
    response = await client.post(BASE, json=await body(db_session, email=email.upper()))
    assert response.status_code == 409
    [match] = response.json()["detail"]["matches"]
    assert match["archived"] is True and match["matched_on"] == ["email"]


@pytest.mark.asyncio
async def test_duplicate_check_lists_matches_and_can_exclude_the_record_being_edited(client, db_session):
    await as_recruiter(client, db_session)
    first = await create(client, db_session)
    found = await client.get(f"{BASE}/duplicate-check", params={"mobile": first["mobile"], "email": first["email"]})
    assert [m["matched_on"] for m in found.json()["matches"]] == [["mobile", "email"]]
    excluded = await client.get(f"{BASE}/duplicate-check", params={"email": first["email"], "exclude_id": first["id"]})
    assert excluded.json()["matches"] == []
    assert (await client.get(f"{BASE}/duplicate-check", params={"mobile": "123"})).json()["matches"] == []


@pytest.mark.asyncio
async def test_editing_into_another_candidates_email_is_blocked(client, db_session):
    await as_recruiter(client, db_session)
    first, second = await create(client, db_session), await create(client, db_session)
    response = await client.patch(f"{BASE}/{second['id']}", json={"email": first["email"]})
    assert response.status_code == 409 and response.json()["detail"]["matches"][0]["id"] == first["id"]
    same = await client.patch(f"{BASE}/{second['id']}", json={"email": second["email"].upper()})  # its own email is no duplicate
    assert same.status_code == 200


@pytest.mark.asyncio
async def test_two_concurrent_creates_of_one_person_give_one_201_and_one_409(db_session):
    user = await make_recruiter(db_session)
    data = await body(db_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as a, AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as b:
        for c in (a, b):  # sign in one after the other: the first login backfills a role assignment, which is not what is under test
            await login(c, user)
        responses = await asyncio.gather(a.post(BASE, json=data), b.post(BASE, json=data))
    assert sorted(r.status_code for r in responses) == [201, 409]
    conflict = next(r for r in responses if r.status_code == 409)
    assert conflict.json()["detail"]["code"] == "duplicate_candidate"


# --- list (AC2, S2-§13) ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_shows_the_source_and_filters(client, db_session):
    await as_recruiter(client, db_session)
    tag = uuid.uuid4().hex[:8]
    a = await create(client, db_session, name=f"Anita {tag}", source_id=await source_id(db_session, "LinkedIn"))
    b = await create(client, db_session, name=f"Bala {tag}", status="placed")
    page = (await client.get(BASE, params={"q": tag})).json()
    assert page["total"] == 2 and [i["id"] for i in page["items"]] == [b["id"], a["id"]]  # newest first
    assert page["items"][1]["source"]["name"] == "LinkedIn"
    assert set(page["items"][0]) == {
        "id", "candidate_code", "name", "location", "experience_months", "preferred_role", "source", "source_detail", "status", "archived", "created_at",
    }
    assert [i["id"] for i in (await client.get(BASE, params={"q": tag, "status": "placed"})).json()["items"]] == [b["id"]]
    by_source = await client.get(BASE, params={"q": tag, "source_id": a["source"]["id"]})
    assert [i["id"] for i in by_source.json()["items"]] == [a["id"]]
    for q in (a["candidate_code"], a["email"].upper(), a["mobile"][-6:]):
        assert [i["id"] for i in (await client.get(BASE, params={"q": q})).json()["items"]] == [a["id"]]


@pytest.mark.asyncio
async def test_archived_are_hidden_by_default_and_listed_on_request(client, db_session):
    await as_recruiter(client, db_session)
    tag = uuid.uuid4().hex[:8]
    created = await create(client, db_session, name=f"Arch {tag}")
    await client.post(f"{BASE}/{created['id']}/archive")
    assert (await client.get(BASE, params={"q": tag})).json()["total"] == 0
    archived = (await client.get(BASE, params={"q": tag, "archived": True})).json()
    assert [i["id"] for i in archived["items"]] == [created["id"]] and archived["items"][0]["archived"] is True


# --- edit, archive, restore ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_changes_only_what_is_sent_and_audits_field_names(client, db_session):
    user = await as_recruiter(client, db_session)
    created = await create(client, db_session, location="Pune")
    response = await client.patch(f"{BASE}/{created['id']}", json={"location": "Chennai", "notice_days": 15, "preferred_locations": ["Chennai"]})
    out = response.json()
    assert response.status_code == 200 and out["location"] == "Chennai" and out["notice_days"] == 15 and out["name"] == created["name"]
    assert out["updated_by"]["id"] == str(user.id)
    audit = await db_session.scalar(
        select(AuditLog).where(AuditLog.action == "candidate.update", AuditLog.entity_id == created["id"]).order_by(AuditLog.created_at.desc())
    )
    assert audit.metadata_json == {"fields": ["location", "notice_days", "preferred_locations"]}
    assert created["email"] not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_patch_cannot_clear_both_contacts_or_null_the_name(client, db_session):
    await as_recruiter(client, db_session)
    created = await create(client, db_session)
    response = await client.patch(f"{BASE}/{created['id']}", json={"mobile": None, "email": None})
    assert response.status_code == 422 and response.json()["detail"] == "Enter a mobile number or an email"
    assert (await client.patch(f"{BASE}/{created['id']}", json={"mobile": None})).status_code == 200  # the email remains
    assert (await client.patch(f"{BASE}/{created['id']}", json={"email": None})).status_code == 422
    assert (await client.patch(f"{BASE}/{created['id']}", json={"name": None})).json()["detail"] == "Name is required"


@pytest.mark.asyncio
async def test_keeping_a_since_deactivated_source_is_allowed_but_moving_to_one_is_not(client, db_session):
    await as_recruiter(client, db_session)
    source = RecCandidateSource(name=f"Expo {uuid.uuid4().hex[:6]}", active=True, sort_order=98)
    db_session.add(source)
    await db_session.commit()
    created = await create(client, db_session, source_id=str(source.id))
    source.active = False
    await db_session.commit()
    assert (await client.patch(f"{BASE}/{created['id']}", json={"source_id": str(source.id), "location": "Goa"})).status_code == 200
    other = await create(client, db_session)
    assert (await client.patch(f"{BASE}/{other['id']}", json={"source_id": str(source.id)})).status_code == 422


@pytest.mark.asyncio
async def test_archive_and_restore(client, db_session):
    await as_recruiter(client, db_session)
    created = await create(client, db_session)
    archived = await client.post(f"{BASE}/{created['id']}/archive")
    assert archived.status_code == 200 and archived.json()["archived"] is True and archived.json()["archived_at"]
    assert (await client.post(f"{BASE}/{created['id']}/archive")).status_code == 409
    edit = await client.patch(f"{BASE}/{created['id']}", json={"location": "Goa"})
    assert edit.status_code == 409 and edit.json()["detail"] == "Restore this candidate first"
    restored = await client.post(f"{BASE}/{created['id']}/restore")
    assert restored.status_code == 200 and restored.json()["archived"] is False
    assert (await client.post(f"{BASE}/{created['id']}/restore")).status_code == 409
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == created["id"]))).all()
    assert {"candidate.create", "candidate.archive", "candidate.restore"} <= set(actions)


# --- pool filter, unknown ids ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_linked_student_who_has_not_opted_in_is_outside_the_pool(client, db_session):
    recruiter = await as_recruiter(client, db_session)
    student = await make_user(db_session, "it_student", "it")
    tag = uuid.uuid4().hex[:8]
    row = Candidate(
        candidate_code=f"T-{tag}", name=f"Student {tag}", email=mail(), source_id=uuid.UUID(await source_id(db_session)),
        user_id=student.id, opted_in=False, created_by_user_id=recruiter.id, preferred_locations=[],
    )
    db_session.add(row)
    await db_session.commit()
    assert (await client.get(BASE, params={"q": tag})).json()["total"] == 0
    assert (await client.get(f"{BASE}/{row.id}")).status_code == 404
    assert (await client.patch(f"{BASE}/{row.id}", json={"location": "X"})).status_code == 404
    row.opted_in = True
    await db_session.commit()
    assert (await client.get(f"{BASE}/{row.id}")).status_code == 200


@pytest.mark.asyncio
async def test_unknown_ids_are_404(client, db_session):
    await make_pm(db_session)
    await as_recruiter(client, db_session)
    missing = uuid.uuid4()
    assert (await client.get(f"{BASE}/{missing}")).status_code == 404
    assert (await client.patch(f"{BASE}/{missing}", json={"location": "X"})).status_code == 404
    assert (await client.post(f"{BASE}/{missing}/archive")).status_code == 404
