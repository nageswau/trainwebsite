"""pob-013 -- college placement profiles for the placement team (DEC-SCOPE-410 P1-P14; AC1-AC3). Shared database: every name is unique."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, BdmOrganization, BdmOrgTpoInteraction
from tests.bdm001_helpers import make_manager, make_user
from tests.bdm002_helpers import ORGS, create_org, make_bdm
from tests.rec001_helpers import login, make_pm, make_recruiter

BASE = "/api/v1/recruiter/colleges"


def url(org_id: str, *rest: str) -> str:
    return "/".join((BASE, org_id, *rest))


async def _world(client, db, **org) -> dict:
    """A college BDM's organization (created through the API, so its code and keys are real) and a recruiter signed in."""
    bdm_mgr = await make_manager(db)
    bdm = await make_bdm(db, bdm_mgr)
    await login(client, bdm)
    created = await create_org(client, contacts=[{"name": "Ms Iyer", "designation": "TPO", "role": "placement_officer", "is_primary": True}], **org)
    recruiter = await make_recruiter(db, await make_pm(db))
    await login(client, recruiter)
    return {"org": created, "bdm": bdm, "bdm_mgr": bdm_mgr, "recruiter": recruiter}


async def _ok(response, status: int = 200) -> dict:
    assert response.status_code == status, response.text
    return response.json()["college"]


@pytest.mark.asyncio
async def test_ac1_a_recruiter_views_a_college_adds_a_batch_and_calendar_entry_and_logs_a_tpo_meeting(client, db_session):
    w = await _world(client, db_session, courses="B.Tech CSE, MBA")
    oid = w["org"]["id"]
    college = await _ok(await client.get(url(oid)))
    assert college["code"] == w["org"]["code"] and college["permissions"] == {"can_edit": True}
    assert college["courses_note"] == "B.Tech CSE, MBA" and college["relationship_stage"]
    assert [c["name"] for c in college["contacts"]] == ["Ms Iyer"] and college["contacts"][0]["preferred_contact_method"] is None
    assert college["batches"] == [] and college["calendar"] == [] and college["interactions"] == [] and college["interaction_total"] == 0

    course = (await _ok(await client.post(url(oid, "courses"), json={"department": "Computer Science", "course": "B.Tech CSE"}), 201))["courses"][0]
    college = await _ok(await client.post(url(oid, "batches"), json={"pass_out_year": 2027, "course_id": course["id"], "pass_out_date": "2027-05-31",
                                                                      "student_count": 120}), 201)  # fmt: skip
    assert college["batches"][0] | {"id": None} == {"id": None, "course_id": course["id"], "course": "B.Tech CSE", "pass_out_year": 2027,
                                                     "pass_out_date": "2027-05-31", "student_count": 120, "notes": None}  # fmt: skip
    college = await _ok(await client.post(url(oid, "calendar"), json={"title": "Pre-placement talk", "kind": "pre_placement_talk", "starts_on": "2026-12-01"}), 201)
    assert [(e["title"], e["kind"], e["starts_on"]) for e in college["calendar"]] == [("Pre-placement talk", "pre_placement_talk", "2026-12-01")]
    contact = college["contacts"][0]["id"]
    met = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    college = await _ok(await client.post(url(oid, "interactions"), json={"channel": "meeting", "occurred_at": met, "contact_id": contact,
                                                                          "summary": "Agreed the 2027 drive window", "next_step": "Share JD"}), 201)  # fmt: skip
    first = college["interactions"][0]
    assert college["interaction_total"] == 1 and first["contact_name"] == "Ms Iyer" and first["logged_by_name"] == w["recruiter"].full_name
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == oid, AuditLog.action.like("bdm_organization.placement_%")))).all()
    assert sorted(actions) == sorted(f"bdm_organization.placement_{a}" for a in ("course_create", "batch_create", "event_create", "interaction_create"))


@pytest.mark.asyncio
async def test_placement_writes_never_touch_the_bdm_organization_row(client, db_session):
    w = await _world(client, db_session)
    oid = w["org"]["id"]
    before = await db_session.scalar(select(BdmOrganization.updated_at).where(BdmOrganization.id == uuid.UUID(oid)))
    await _ok(await client.put(url(oid, "profile"), json={"drive_process": "Aptitude, then GD\nthen HR", "eligibility_rules": "60% aggregate"}))
    after = await db_session.scalar(select(BdmOrganization.updated_at).where(BdmOrganization.id == uuid.UUID(oid)).execution_options(populate_existing=True))
    assert after == before


@pytest.mark.asyncio
async def test_ac2_a_recruiter_cannot_edit_bdm_owned_fields_or_mous(client, db_session):
    """P13: every BDM route keeps refusing the placement team; the placement view carries no MoU or commercial data."""
    w = await _world(client, db_session)
    oid = w["org"]["id"]
    assert (await client.patch(f"{ORGS}/{oid}", json={"name": "Renamed"})).status_code == 403
    assert (await client.get(f"{ORGS}/{oid}")).status_code == 403
    assert (await client.post(f"{ORGS}/{oid}/contacts", json={"name": "X"})).status_code == 403
    assert (await client.get(f"{ORGS}/{oid}/mou")).status_code == 403
    college = await _ok(await client.get(url(oid)))
    assert not {"mou", "pipeline", "assigned_bdm", "existing_partner", "onboarding", "phone", "email"} & set(college)


@pytest.mark.asyncio
async def test_ac3_search_by_course_graduating_year_and_location(client, db_session):
    tag = uuid.uuid4().hex[:6]
    w = await _world(client, db_session, city=f"Mysuru{tag}")
    oid = w["org"]["id"]
    await _ok(await client.post(url(oid, "courses"), json={"department": "Mechanical", "course": f"Robotics{tag}"}), 201)
    await _ok(await client.post(url(oid, "batches"), json={"pass_out_year": 2031}), 201)

    async def found(**params) -> list[str]:
        response = await client.get(BASE, params=params)
        assert response.status_code == 200, response.text
        return [row["id"] for row in response.json()["items"]]

    assert await found(course=f"robotics{tag}") == [oid]
    assert await found(course=f"Robotics{tag}", pass_out_year=2031) == [oid]
    assert await found(course=f"Robotics{tag}", pass_out_year=2030) == []
    assert await found(city=f"mysuru{tag}") == [oid]
    row = (await client.get(BASE, params={"course": f"Robotics{tag}"})).json()["items"][0]
    assert row["course_count"] == 1 and row["next_pass_out_year"] == 2031 and row["assigned_bdm_name"] == w["bdm"].full_name


@pytest.mark.asyncio
async def test_the_bdm_free_text_courses_are_searchable_too(client, db_session):
    tag = uuid.uuid4().hex[:6]
    w = await _world(client, db_session, courses=f"Aeronautics{tag}")
    assert [r["id"] for r in (await client.get(BASE, params={"course": f"aeronautics{tag}"})).json()["items"]] == [w["org"]["id"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["placement_manager", "bdm_manager_of_team"])
async def test_managers_read_but_cannot_write(client, db_session, role):
    w = await _world(client, db_session)
    oid = w["org"]["id"]
    reader = await make_pm(db_session) if role == "placement_manager" else w["bdm_mgr"]
    await login(client, reader)
    college = await _ok(await client.get(url(oid)))
    assert college["permissions"] == {"can_edit": False}
    response = await client.post(url(oid, "batches"), json={"pass_out_year": 2027})
    assert response.status_code == 403 and response.json()["detail"] == "Only the placement team or the assigned BDM can change the placement profile"


@pytest.mark.asyncio
async def test_the_assigned_bdm_writes_another_bdm_of_the_module_cannot(client, db_session):
    w = await _world(client, db_session)
    oid = w["org"]["id"]
    await login(client, w["bdm"])
    assert (await _ok(await client.post(url(oid, "batches"), json={"pass_out_year": 2028}), 201))["permissions"]["can_edit"] is True
    other = await make_bdm(db_session, w["bdm_mgr"])
    await login(client, other)
    assert (await _ok(await client.get(url(oid))))["permissions"]["can_edit"] is False  # same module: bdm-002 reads, never writes
    assert (await client.post(url(oid, "batches"), json={"pass_out_year": 2028})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("hr_team", "it"), ("placement_officer", "it"), ("it_student", "it"), ("employer", "it")])
async def test_other_roles_are_refused(client, db_session, role, division):
    w = await _world(client, db_session)
    await login(client, await make_user(db_session, role, division))
    assert (await client.get(BASE)).status_code == 403
    assert (await client.get(url(w["org"]["id"]))).status_code == 403


@pytest.mark.asyncio
async def test_a_recruiter_without_a_profile_is_refused(client, db_session):
    await login(client, await make_user(db_session, "placement_team", "it"))
    response = await client.get(BASE)
    assert response.status_code == 403 and "profile" in response.json()["detail"]


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(BASE)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("org_type", ["school", "corporate"])
async def test_non_college_organizations_are_out_of_scope(client, db_session, org_type):
    bdm = await make_bdm(db_session, await make_manager(db_session), "school" if org_type == "school" else "college")
    await login(client, bdm)
    org = await create_org(client, org_type=org_type)
    await login(client, await make_recruiter(db_session, await make_pm(db_session)))
    assert (await client.get(url(org["id"]))).status_code == 404
    assert org["id"] not in [r["id"] for r in (await client.get(BASE, params={"q": org["code"]})).json()["items"]]


@pytest.mark.asyncio
async def test_an_agent_module_university_is_not_a_placement_college(client, db_session):
    """P2 / backlog edge case: an overseas-partner university stays out of the placement view."""
    bdm = await make_bdm(db_session, await make_manager(db_session), "agent")
    await login(client, bdm)
    org = await create_org(client, org_type="university")
    await login(client, await make_recruiter(db_session, await make_pm(db_session)))
    assert (await client.get(url(org["id"]))).status_code == 404


@pytest.mark.asyncio
async def test_archived_college_is_hidden_from_the_placement_team_and_read_only_for_the_bdm(client, db_session):
    w = await _world(client, db_session)
    oid = w["org"]["id"]
    await login(client, w["bdm"])
    assert (await client.post(f"{ORGS}/{oid}/archive")).status_code == 200
    college = await _ok(await client.get(url(oid)))
    assert college["archived"] is True and college["permissions"]["can_edit"] is False
    response = await client.post(url(oid, "batches"), json={"pass_out_year": 2027})
    assert response.status_code == 409 and response.json()["detail"] == "Restore this organization first"
    await login(client, w["recruiter"])
    assert (await client.get(url(oid))).status_code == 404


@pytest.mark.asyncio
async def test_unknown_college_is_404(client, db_session):
    await login(client, await make_recruiter(db_session, await make_pm(db_session)))
    assert (await client.get(url(str(uuid.uuid4())))).status_code == 404
    assert (await client.post(url(str(uuid.uuid4()), "batches"), json={"pass_out_year": 2027})).status_code == 404


@pytest.mark.asyncio
async def test_courses_are_unique_per_college_and_a_course_with_batches_cannot_be_deleted(client, db_session):
    w = await _world(client, db_session)
    oid = w["org"]["id"]
    course = (await _ok(await client.post(url(oid, "courses"), json={"department": "ECE", "course": "B.Tech ECE"}), 201))["courses"][0]
    duplicate = await client.post(url(oid, "courses"), json={"department": "ece", "course": "  b.tech ece "})
    assert duplicate.status_code == 409 and duplicate.json()["detail"] == "This course is already listed"
    batch = (await _ok(await client.post(url(oid, "batches"), json={"pass_out_year": 2027, "course_id": course["id"]}), 201))["batches"][0]
    refused = await client.delete(url(oid, "courses", course["id"]))
    assert refused.status_code == 409 and refused.json()["detail"] == "Remove this course's batches first"
    await _ok(await client.delete(url(oid, "batches", batch["id"])))
    assert (await _ok(await client.delete(url(oid, "courses", course["id"]))))["courses"] == []


@pytest.mark.asyncio
async def test_child_ids_of_another_college_read_as_missing(client, db_session):
    first, second = await _world(client, db_session), await _world(client, db_session)
    a, b = first["org"]["id"], second["org"]["id"]
    course = (await _ok(await client.post(url(a, "courses"), json={"course": "MBA"}), 201))["courses"][0]
    event = (await _ok(await client.post(url(a, "calendar"), json={"title": "Drive", "kind": "campus_drive", "starts_on": "2027-01-10"}), 201))["calendar"][0]
    assert (await client.post(url(b, "batches"), json={"pass_out_year": 2027, "course_id": course["id"]})).status_code == 422
    assert (await client.delete(url(b, "courses", course["id"]))).status_code == 404
    assert (await client.delete(url(b, "calendar", event["id"]))).status_code == 404
    contact = (await _ok(await client.get(url(a))))["contacts"][0]["id"]
    now = datetime.now(UTC).isoformat()
    assert (await client.post(url(b, "interactions"), json={"channel": "call", "occurred_at": now, "contact_id": contact, "summary": "x"})).status_code == 422
    assert (await client.patch(url(b, "contacts", contact), json={"office_details": "Block A"})).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "body", "message"),
    [
        ("batches", {"pass_out_year": 1999}, "Pass-out year must be a year from 2000 to 2100"),
        ("batches", {"pass_out_year": "2027"}, "Pass-out year must be a year from 2000 to 2100"),
        ("batches", {"pass_out_year": 2027, "pass_out_date": "2026-05-01"}, "The pass-out date must fall in the pass-out year"),
        ("batches", {"pass_out_year": 2027, "student_count": -1}, "Number of students must be a whole number from 0 to 100,000"),
        ("calendar", {"title": "  ", "kind": "exam", "starts_on": "2027-01-01"}, "Title is required"),
        ("calendar", {"title": "Exam", "kind": "exam", "starts_on": "2027-01-05", "ends_on": "2027-01-01"}, "The end date can't be before the start date"),
        ("courses", {"course": ""}, "Course is required"),
        ("interactions", {"channel": "meeting", "occurred_at": "2026-01-01T10:00:00Z", "summary": " "}, "Summary is required"),
    ],
)
async def test_validation_messages(client, db_session, path, body, message):
    w = await _world(client, db_session)
    response = await client.post(url(w["org"]["id"], path), json=body)
    assert response.status_code == 422, response.text
    assert message in response.text


@pytest.mark.asyncio
async def test_an_interaction_cannot_be_in_the_future_and_the_list_is_bounded(client, db_session):
    w = await _world(client, db_session)
    oid = w["org"]["id"]
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    response = await client.post(url(oid, "interactions"), json={"channel": "call", "occurred_at": future, "summary": "x"})
    assert response.status_code == 422 and response.json()["detail"] == "An interaction can't be in the future"
    base = datetime.now(UTC) - timedelta(days=60)
    for i in range(52):
        db_session.add(BdmOrgTpoInteraction(organization_id=uuid.UUID(oid), channel="email", occurred_at=base + timedelta(hours=i), summary=f"n{i}",
                                            logged_by_user_id=w["recruiter"].id))  # fmt: skip
    await db_session.commit()
    college = await _ok(await client.get(url(oid)))
    assert college["interaction_total"] == 52 and len(college["interactions"]) == 50 and college["interactions"][0]["summary"] == "n51"


@pytest.mark.asyncio
async def test_tpo_contact_office_and_preferred_method(client, db_session):
    w = await _world(client, db_session)
    oid = w["org"]["id"]
    contact = (await _ok(await client.get(url(oid))))["contacts"][0]["id"]
    college = await _ok(await client.patch(url(oid, "contacts", contact), json={"office_details": "Placement cell, Block A", "preferred_contact_method": "whatsapp"}))
    assert college["contacts"][0] | {"id": None} >= {"office_details": "Placement cell, Block A", "preferred_contact_method": "whatsapp"}
    assert (await client.patch(url(oid, "contacts", contact), json={"preferred_contact_method": "fax"})).status_code == 422
    assert (await client.patch(url(oid, "contacts", contact), json={"name": "Renamed"})).status_code == 422  # BDM fields stay on bdm-002
    unchanged = await client.patch(url(oid, "contacts", contact), json={"preferred_contact_method": "whatsapp"})
    assert unchanged.status_code == 200
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == oid, AuditLog.action == "bdm_organization.placement_contact_update"))).all()
    assert len(rows) == 1 and rows[0].metadata_json["fields"] == ["office_details", "preferred_contact_method"]


@pytest.mark.asyncio
async def test_profile_put_replaces_and_a_no_change_save_writes_no_audit(client, db_session):
    w = await _world(client, db_session)
    oid = w["org"]["id"]
    college = await _ok(await client.put(url(oid, "profile"), json={"drive_process": "Online test\r\nthen interviews"}))
    assert college["profile"]["drive_process"] == "Online test\nthen interviews" and college["profile"]["updated_by_name"] == w["recruiter"].full_name
    await _ok(await client.put(url(oid, "profile"), json={"drive_process": "Online test\nthen interviews"}))
    college = await _ok(await client.put(url(oid, "profile"), json={"eligibility_rules": "No backlogs"}))
    assert college["profile"]["drive_process"] is None and college["profile"]["eligibility_rules"] == "No backlogs"
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == oid, AuditLog.action == "bdm_organization.placement_profile"))).all()
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_bdm_contact_output_is_unchanged(client, db_session):
    """P10: the bdm-002 contact shape gains nothing (BDM regression guard)."""
    w = await _world(client, db_session)
    await login(client, w["bdm"])
    contact = (await client.get(f"{ORGS}/{w['org']['id']}")).json()["organization"]["contacts"][0]
    assert set(contact) == {"id", "name", "designation", "role", "phone", "email", "is_primary"}
