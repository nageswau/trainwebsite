"""tel-019 -- a telecaller files a BDM meeting request (spec §3; DEC-SCOPE-098 MR1, MR5-MR8): options, create and the telecaller's own
list. The shared test database is never truncated."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, BdmMeetingRequest
from tests.tel019_helpers import (
    OPTIONS,
    TEL,
    as_user,
    at,
    body,
    file_request,
    make_bdm,
    make_manager,
    make_tl_manager,
    make_user,
    telecaller,
)


# --- create --------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_pool_request_is_filed_pending_with_a_code_and_a_pii_free_audit(client, db_session):
    tel = await telecaller(db_session)
    out = await file_request(client, tel)
    assert out["code"].startswith("MRQ-") and len(out["code"]) == 10
    assert out["status"] == "pending" and out["request_type"] == "college" and out["bdm_type"] == "college"
    assert out["type_label"] == "College meeting" and out["bdm"] is None and out["appointment"] is None
    assert out["requester"]["id"] == str(tel.id)
    assert out["organization_name"] == "Govt College Kochi" and out["person_name"] == "Dr Rao" and out["contact_phone"] == "+91 98765 43210"
    assert out["mode"] == "In person" and out["location"] == "Main campus" and out["remarks"] == "Prefers mornings"
    assert out["permissions"] == {"can_accept": False, "can_decline": False}
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == out["id"], AuditLog.action == "bdm_meeting_request.create"))
    assert audit is not None and audit.user_id == tel.id
    assert not any(pii in str(audit.metadata_json) for pii in ("Rao", "98765", "college.example", "Kochi", "partnership", "mornings"))


@pytest.mark.asyncio
async def test_a_corporate_request_goes_to_college_bdms(client, db_session):
    out = await file_request(client, await telecaller(db_session), request_type="corporate")
    assert (out["request_type"], out["bdm_type"], out["type_label"]) == ("corporate", "college", "Corporate meeting")


@pytest.mark.asyncio
async def test_a_named_request_is_for_that_bdm(client, db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session), "school")
    out = await file_request(client, await telecaller(db_session), request_type="school", bdm_user_id=str(bdm.id))
    assert out["bdm"] == {"id": str(bdm.id), "full_name": bdm.full_name} and out["bdm_type"] == "school"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["wrong_type", "inactive", "not_a_bdm", "unknown"])
async def test_a_named_target_must_be_an_active_bdm_of_the_type(client, db_session, case):
    manager = await make_manager(db_session)
    target = {
        "wrong_type": lambda: make_bdm(db_session, manager, "agent"),
        "inactive": lambda: make_bdm(db_session, manager, "college", active=False),
        "not_a_bdm": lambda: make_user(db_session, "counselor", "it"),
    }
    target_id = str(uuid.uuid4()) if case == "unknown" else str((await target[case]()).id)
    await as_user(client, await telecaller(db_session))
    response = await client.post(TEL, json=body(bdm_user_id=target_id))
    assert response.status_code == 422, response.text
    assert "Choose an active College BDM" in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("over, message", [
    ({"proposed_at": at(days=-1)}, "Choose a time in the future"),
    ({"proposed_at": at(days=400)}, "Choose a time within the next year"),
    ({"purpose": "   "}, "Purpose is required"),
    ({"organization_name": ""}, "Organization is required"),
    ({"person_name": "A\x07B"}, "Person contains invalid characters"),
    ({"contact_phone": "call me"}, "Phone"),
    ({"contact_email": "not-an-email"}, "email"),
    ({"mode": "Carrier pigeon"}, "mode"),
    ({"request_type": "hospital"}, "request_type"),
    ({"status": "accepted"}, "Extra inputs"),
])
async def test_invalid_requests_are_refused_with_422(client, db_session, over, message):
    await as_user(client, await telecaller(db_session))
    response = await client.post(TEL, json=body(**over))
    assert response.status_code == 422, response.text
    assert message in response.text


@pytest.mark.asyncio
async def test_blank_optional_fields_are_stored_as_null(client, db_session):
    out = await file_request(client, await telecaller(db_session), contact_email="  ", location="", remarks=None)
    assert (out["contact_email"], out["location"], out["remarks"]) == (None, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["telecaller_manager", "bdm", "counselor", "super_admin"])
async def test_only_a_telecaller_files_requests(client, db_session, role):
    if role == "telecaller_manager":
        user = await make_tl_manager(db_session)
    elif role == "bdm":
        user = await make_bdm(db_session, await make_manager(db_session))
    else:
        user = await make_user(db_session, role, "it")
    await as_user(client, user)
    assert (await client.post(TEL, json=body())).status_code == 403
    assert (await client.get(TEL)).status_code == 403
    assert (await client.get(OPTIONS)).status_code == 403


# --- options / list ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_options_list_the_types_modes_and_active_bdms_by_type(client, db_session):
    manager = await make_manager(db_session)
    college, school = await make_bdm(db_session, manager, "college"), await make_bdm(db_session, manager, "school")
    gone = await make_bdm(db_session, manager, "college", active=False)
    await as_user(client, await telecaller(db_session))
    out = (await client.get(OPTIONS)).json()
    assert [t["key"] for t in out["types"]] == ["college", "agent", "school", "corporate"]
    assert {t["key"]: t["bdm_type"] for t in out["types"]}["corporate"] == "college"
    assert out["modes"] == ["Online", "Phone", "In person"]
    college_ids = {b["id"] for b in out["bdms"]["college"]}
    assert str(college.id) in college_ids and str(gone.id) not in college_ids and str(school.id) not in college_ids
    assert str(school.id) in {b["id"] for b in out["bdms"]["school"]}


@pytest.mark.asyncio
async def test_a_telecaller_lists_only_their_own_requests_newest_first(client, db_session):
    mine, other = await telecaller(db_session), await telecaller(db_session)
    theirs = await file_request(client, other)
    first = await file_request(client, mine)
    second = await file_request(client, mine, request_type="agent")
    page = (await client.get(TEL)).json()
    assert [r["id"] for r in page["items"]] == [second["id"], first["id"]] and page["total"] == 2
    assert theirs["id"] not in {r["id"] for r in page["items"]}
    pending = (await client.get(TEL, params={"status": "accepted"})).json()
    assert pending["items"] == [] and pending["total"] == 0


@pytest.mark.asyncio
async def test_the_stored_row_matches_the_response(client, db_session):
    out = await file_request(client, await telecaller(db_session))
    row = await db_session.scalar(select(BdmMeetingRequest).where(BdmMeetingRequest.id == uuid.UUID(out["id"])))
    assert row.status == "pending" and row.bdm_user_id is None and row.decided_at is None and row.code == out["code"]
