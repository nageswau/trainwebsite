"""pob-014 -- institution-supplied student pool with permission tracking (DEC-SCOPE-425 S1-S13; AC1-AC3). Shared database: every name
and contact is unique."""

import csv
import io
import random
from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, Candidate, CandidateImportBatch, Company, InstitutionDataPermission, JobApplication, RecCandidateSource
from app.services import candidates as candidate_svc
from app.services import share_gate
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm
from tests.rec038_helpers import _recruiter, _user, add, make_candidate, make_job
from tests.tel026_helpers import headers

pytestmark = pytest.mark.asyncio
COLLEGES = "/api/v1/recruiter/colleges"
IMPORTS = "/api/v1/recruiter/candidate-imports"
CANDIDATES = "/api/v1/recruiter/candidates"


def _mobile() -> str:
    return "9" + "".join(random.choices("0123456789", k=9))


def _csv(rows: list[dict]) -> bytes:
    columns = ("name", "mobile", "email", "qualification", "passing_year")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(c, "") for c in columns])
    return buffer.getvalue().encode()


def _student(**over) -> dict:
    return {"name": f"Student {uuid4().hex[:6]}", "mobile": _mobile(), "email": f"s{uuid4().hex[:10]}@example.com", "qualification": "B.Tech CSE",
            "passing_year": "2027", **over}  # fmt: skip


async def _world(client, db) -> dict:
    """A college (created by its BDM through the API), a placement manager, two recruiters of that manager and an hr_team user."""
    bdm = await make_bdm(db, await make_manager(db))
    await login(client, bdm)
    org = await create_org(client)
    client.cookies.clear()
    mgr = await _user(db, "placement_manager", "global")
    inside, outside = await _recruiter(db, mgr), await _recruiter(db, mgr)
    await db.commit()
    return {"org": org, "oid": org["id"], "mgr": mgr, "inside": inside, "outside": outside, "bdm": bdm}


def _permission_body(*users, **over) -> dict:
    today = date.today()
    return {"agreement_reference": f"MoU-{uuid4().hex[:6]}", "purposes": ["placement"], "valid_from": str(today - timedelta(days=1)),
            "expires_on": str(today + timedelta(days=180)), "user_ids": [str(u.id) for u in users], **over}  # fmt: skip


async def _permit(client, w, *users, **over) -> dict:
    r = await client.post(f"{COLLEGES}/{w['oid']}/data-permissions", json=_permission_body(*users, **over), headers=headers(w["mgr"]))
    assert r.status_code == 201, r.text
    return r.json()["permission"]


async def _source(db) -> str:
    return str(await db.scalar(select(RecCandidateSource.id).where(RecCandidateSource.name == "Referral")))


async def _import(client, db, user, raw: bytes, permission_id: str | None, *, preview=False, notice="consented"):
    data = {"source_id": await _source(db), "lawful_basis": "consent"}
    if permission_id:
        data |= {"institution_permission_id": permission_id, "notice_status": notice}
    hdrs = headers(user) | ({} if preview else {"Idempotency-Key": uuid4().hex})
    return await client.post(f"{IMPORTS}/preview" if preview else IMPORTS, data=data, files={"file": ("students.csv", raw, "text/csv")}, headers=hdrs)


async def _imported(client, db, w, *students, permission=None) -> tuple[dict, list[str]]:
    permission = permission or await _permit(client, w, w["inside"])
    r = await _import(client, db, w["inside"], _csv(list(students)), permission["id"])
    assert r.status_code == 201, r.text
    return permission, [row["candidate"]["id"] for row in r.json()["rows"] if row["status"] == "created"]


async def _pool(client, w, user, **params):
    return await client.get(f"{COLLEGES}/{w['oid']}/student-pool", params=params, headers=headers(user))


async def _expire(db, permission_id: str) -> None:
    yesterday = date.today() - timedelta(days=1)
    await db.execute(update(InstitutionDataPermission).where(InstitutionDataPermission.id == UUID(permission_id)).values(valid_from=yesterday - timedelta(days=30), expires_on=yesterday))
    await db.commit()


# --- AC1 ------------------------------------------------------------------------------------------------------------------------------
async def test_ac1_an_imported_list_carries_its_source_and_permission(client, db_session):
    w = await _world(client, db_session)
    permission = await _permit(client, w, w["inside"], purposes=["placement", "internship"])
    assert permission["status"] == "active" and [u["id"] for u in permission["users"]] == [str(w["inside"].id)]
    student = _student(passing_year="2027")
    preview = await _import(client, db_session, w["inside"], _csv([student]), permission["id"], preview=True)
    assert preview.status_code == 200 and preview.json()["new_count"] == 1, preview.text
    r = await _import(client, db_session, w["inside"], _csv([student]), permission["id"])
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["institution_permission"]["id"] == permission["id"] and body["institution_permission"]["organization_name"] == w["org"]["name"]
    batch = await db_session.get(CandidateImportBatch, UUID(body["id"]))
    assert str(batch.institution_permission_id) == permission["id"] and batch.source_id is not None
    candidate = await db_session.get(Candidate, UUID(body["rows"][0]["candidate"]["id"]))
    await db_session.refresh(candidate)
    assert (str(candidate.institution_org_id), str(candidate.institution_permission_id), candidate.institution_notice_status) == (w["oid"], permission["id"], "consented")
    assert candidate.college == w["org"]["name"] and candidate.passing_year == 2027

    pool = await _pool(client, w, w["inside"])
    assert pool.status_code == 200, pool.text
    students = pool.json()["students"]
    assert students["total"] == 1 and students["items"][0] | {"id": None} == {
        "id": None, "candidate_code": candidate.candidate_code, "name": student["name"], "passing_year": 2027, "qualification": "B.Tech CSE",
        "notice_status": "consented", "permission_id": permission["id"], "placement_status": None,
    }  # fmt: skip
    assert pool.json()["permissions"][0]["student_count"] == 1 and pool.json()["college"]["name"] == w["org"]["name"]
    assert (await client.get(f"{IMPORTS}/{body['id']}", headers=headers(w["inside"]))).json()["institution_permission"]["id"] == permission["id"]


async def test_an_import_under_a_permission_needs_a_notice_status_and_an_active_listed_permission(client, db_session):
    w = await _world(client, db_session)
    permission = await _permit(client, w, w["inside"])
    raw = _csv([_student()])
    assert (await _import(client, db_session, w["inside"], raw, permission["id"], notice="")).status_code == 422
    assert (await _import(client, db_session, w["inside"], raw, permission["id"], notice="maybe")).status_code == 422
    assert (await _import(client, db_session, w["outside"], raw, permission["id"])).status_code == 404  # not listed
    assert (await _import(client, db_session, w["inside"], raw, str(uuid4()))).status_code == 404
    await _expire(db_session, permission["id"])
    assert (await _import(client, db_session, w["inside"], raw, permission["id"], preview=True)).status_code == 404


async def test_a_known_person_is_matched_and_left_unchanged(client, db_session):
    """S7/S12: an existing candidate on the college's list keeps its record (hrc-013 I7) -- no institution stamp, still visible to all."""
    w = await _world(client, db_session)
    known = await make_candidate(db_session, w["mgr"])
    await db_session.commit()
    _, created = await _imported(client, db_session, w, _student(email=known.email, mobile=""))
    assert created == []
    await db_session.refresh(known)
    assert known.institution_permission_id is None
    assert (await client.get(f"{CANDIDATES}/{known.id}", headers=headers(w["outside"]))).status_code == 200


# --- AC2 ------------------------------------------------------------------------------------------------------------------------------
async def test_ac2_a_user_outside_the_agreement_cannot_see_the_students(client, db_session):
    w = await _world(client, db_session)
    student = _student()
    permission, [cid] = await _imported(client, db_session, w, student)
    code = (await db_session.get(Candidate, UUID(cid))).candidate_code
    inside, outside = headers(w["inside"]), headers(w["outside"])
    assert (await client.get(f"{CANDIDATES}/{cid}", headers=inside)).status_code == 200
    for path in (f"{CANDIDATES}/{cid}", f"{CANDIDATES}/{cid}/notes", f"{CANDIDATES}/{cid}/timeline"):
        assert (await client.get(path, headers=outside)).status_code == 404, path
    listed = await client.get(CANDIDATES, params={"q": code}, headers=outside)
    assert listed.status_code == 200 and listed.json()["total"] == 0
    assert (await client.get(CANDIDATES, params={"q": code}, headers=inside)).json()["total"] == 1
    for user, total in ((w["inside"], 1), (w["outside"], 0)):
        found = await client.get(CANDIDATES, params={"institution_id": w["oid"]}, headers=headers(user))
        assert found.status_code == 200 and found.json()["total"] == total, found.text
    pool = (await _pool(client, w, w["outside"])).json()
    assert pool["students"]["total"] == 0 and pool["permissions"] == [] and pool["can_manage"] is False
    # S3: no role bypasses the list -- the manager who wrote it is not on it
    assert (await client.get(f"{CANDIDATES}/{cid}", headers=headers(w["mgr"]))).status_code == 404
    manager_pool = (await _pool(client, w, w["mgr"])).json()
    assert [p["id"] for p in manager_pool["permissions"]] == [permission["id"]] and manager_pool["students"]["total"] == 0


async def test_without_a_viewer_institution_students_are_hidden(client, db_session):
    """S6 fail closed: system reads (talent pools, dashboards, the duplicate queue) pass no viewer."""
    w = await _world(client, db_session)
    _, [cid] = await _imported(client, db_session, w, _student())
    assert await db_session.scalar(select(Candidate.id).where(Candidate.id == UUID(cid), *candidate_svc.pool_filter())) is None
    assert await db_session.scalar(select(Candidate.id).where(Candidate.id == UUID(cid), *candidate_svc.pool_filter(w["inside"].id))) is not None


async def test_the_duplicate_panel_never_names_a_hidden_student(client, db_session):
    """S8: a manual add with a hidden student's email is still refused (one person, one candidate) but names no one."""
    w = await _world(client, db_session)
    student = _student()
    _, [cid] = await _imported(client, db_session, w, student)
    r = await client.post(CANDIDATES, json={"name": "Someone", "email": student["email"], "source_id": await _source(db_session)}, headers=headers(w["outside"]))
    assert r.status_code == 409, r.text
    [match] = r.json()["detail"]["matches"]
    assert match["name"] == "Restricted record" and match["candidate_code"] is None and match["id"] is None
    again = await _import(client, db_session, w["outside"], _csv([student]), None)
    row = again.json()["rows"][0]
    assert row["status"] == "matched" and row["candidate"] is None and row["reason"] == "Already a candidate (restricted record)"


# --- AC3 ------------------------------------------------------------------------------------------------------------------------------
async def test_ac3_once_the_permission_expires_the_students_are_hidden_and_not_shareable(client, db_session):
    w = await _world(client, db_session)
    permission, [cid] = await _imported(client, db_session, w, _student())
    student = await db_session.get(Candidate, UUID(cid))
    assert [c.id for c in await share_gate.people(db_session, [student.id], w["inside"])] == [student.id]
    await _expire(db_session, permission["id"])
    assert (await client.get(f"{CANDIDATES}/{cid}", headers=headers(w["inside"]))).status_code == 404
    pool = (await _pool(client, w, w["inside"])).json()
    assert pool["students"]["total"] == 0 and pool["permissions"][0]["status"] == "expired"
    found = await client.get(CANDIDATES, params={"institution_id": w["oid"]}, headers=headers(w["inside"]))
    assert found.json()["total"] == 0
    with pytest.raises(Exception) as refused:
        await share_gate.people(db_session, [student.id], w["inside"])
    assert getattr(refused.value, "status_code", None) == 422


async def test_sharing_needs_the_placement_purpose(client, db_session):
    """S9: purpose limitation -- a permission for training only does not allow sending a profile to an employer."""
    w = await _world(client, db_session)
    permission = await _permit(client, w, w["inside"], purposes=["training"])
    _, [cid] = await _imported(client, db_session, w, _student(), permission=permission)
    with pytest.raises(Exception) as refused:
        await share_gate.people(db_session, [UUID(cid)], w["inside"])
    assert refused.value.status_code == 422 and "purpose" in refused.value.detail


async def test_a_revoked_permission_hides_its_students_and_cannot_change(client, db_session):
    w = await _world(client, db_session)
    permission, [cid] = await _imported(client, db_session, w, _student())
    base = f"{COLLEGES}/{w['oid']}/data-permissions/{permission['id']}"
    revoked = await client.post(f"{base}/revoke", headers=headers(w["mgr"]))
    assert revoked.status_code == 200 and revoked.json()["permission"]["status"] == "revoked"
    assert (await client.get(f"{CANDIDATES}/{cid}", headers=headers(w["inside"]))).status_code == 404
    assert (await client.patch(base, json={"notes": "x"}, headers=headers(w["mgr"]))).status_code == 409
    assert (await client.post(f"{base}/revoke", headers=headers(w["mgr"]))).status_code == 409


# --- permission writes ----------------------------------------------------------------------------------------------------------------
async def test_only_placement_managers_and_super_admin_write_permissions(client, db_session):
    w = await _world(client, db_session)
    url = f"{COLLEGES}/{w['oid']}/data-permissions"
    body = _permission_body(w["inside"])
    for user in (w["inside"], w["bdm"]):
        assert (await client.post(url, json=body, headers=headers(user))).status_code == 403
    assert (await client.post(f"{COLLEGES}/{uuid4()}/data-permissions", json=body, headers=headers(w["mgr"]))).status_code == 404
    admin = await _user(db_session, "super_admin", "global")
    await db_session.commit()
    created = await client.post(url, json=body, headers=headers(admin))
    assert created.status_code == 201, created.text
    pid = created.json()["permission"]["id"]
    changed = await client.patch(f"{url}/{pid}", json={"expires_on": str(date.today() + timedelta(days=30)), "user_ids": [str(w["inside"].id), str(w["outside"].id)]},
                                 headers=headers(w["mgr"]))  # fmt: skip
    assert changed.status_code == 200, changed.text
    assert sorted(u["id"] for u in changed.json()["permission"]["users"]) == sorted([str(w["inside"].id), str(w["outside"].id)])
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == pid))).all()
    assert sorted(actions) == ["institution_permission.create", "institution_permission.update"]


@pytest.mark.parametrize(
    "over",
    [
        {"purposes": []},
        {"purposes": ["marketing"]},
        {"agreement_reference": " "},
        {"expires_on": "2020-01-01"},
        {"user_ids": []},
        {"mou_id": str(uuid4())},
    ],
)
async def test_permission_validation(client, db_session, over):
    w = await _world(client, db_session)
    r = await client.post(f"{COLLEGES}/{w['oid']}/data-permissions", json=_permission_body(w["inside"], **over), headers=headers(w["mgr"]))
    assert r.status_code == 422, r.text


async def test_only_candidate_readers_can_be_listed(client, db_session):
    w = await _world(client, db_session)
    url = f"{COLLEGES}/{w['oid']}/data-permissions"
    for user_id in (str(w["bdm"].id), str(uuid4())):
        r = await client.post(url, json=_permission_body(user_ids=[user_id]), headers=headers(w["mgr"]))
        assert r.status_code == 422 and "can view candidates" in r.text


async def test_the_pool_filters_by_batch_course_and_name_and_shows_the_placement_status(client, db_session):
    w = await _world(client, db_session)
    a, b = _student(passing_year="2026", qualification="MBA"), _student(passing_year="2027", qualification="B.Tech CSE")
    _, ids = await _imported(client, db_session, w, a, b)
    assert len(ids) == 2
    inside = w["inside"]
    assert [s["name"] for s in (await _pool(client, w, inside, pass_out_year=2026)).json()["students"]["items"]] == [a["name"]]
    assert [s["name"] for s in (await _pool(client, w, inside, course="b.tech")).json()["students"]["items"]] == [b["name"]]
    assert [s["name"] for s in (await _pool(client, w, inside, q=b["name"][-6:])).json()["students"]["items"]] == [b["name"]]
    assert (await _pool(client, w, inside, pass_out_year=1900)).status_code == 422
    company = await add(db_session, Company(name=f"Acme {uuid4().hex[:6]}", assigned_recruiter_user_id=inside.id, assigned_bdm_user_id=w["bdm"].id, created_by_user_id=inside.id))
    job = await make_job(db_session, company, inside)
    await add(db_session, JobApplication(job_id=job.id, candidate_id=UUID(ids[0]), status="shortlisted", added_by_user_id=inside.id))
    await db_session.commit()
    rows = {s["id"]: s["placement_status"] for s in (await _pool(client, w, inside)).json()["students"]["items"]}
    assert rows == {ids[0]: "shortlisted", ids[1]: None}


async def test_the_pool_is_scoped_like_the_college(client, db_session):
    w = await _world(client, db_session)
    assert (await client.get(f"{COLLEGES}/{uuid4()}/student-pool", headers=headers(w["inside"]))).status_code == 404
    hr = await _user(db_session, "hr_team", "global")
    await db_session.commit()
    assert (await client.get(f"{COLLEGES}/{w['oid']}/student-pool", headers=headers(hr))).status_code == 403


async def test_qa01_validation_messages_are_plain(client, db_session):
    """Browser QA-01: an empty purpose or people list is explained in words, not as a list-length error."""
    w = await _world(client, db_session)
    url = f"{COLLEGES}/{w['oid']}/data-permissions"
    for over, message in (({"purposes": []}, "Choose at least one permitted purpose"), ({"user_ids": []}, "Choose at least one person")):
        r = await client.post(url, json=_permission_body(w["inside"], **over), headers=headers(w["mgr"]))
        assert r.status_code == 422 and message in r.text and "List should have" not in r.text, r.text


async def test_a_required_field_cannot_be_cleared(client, db_session):
    w = await _world(client, db_session)
    permission = await _permit(client, w, w["inside"])
    base = f"{COLLEGES}/{w['oid']}/data-permissions/{permission['id']}"
    for field in ("agreement_reference", "purposes", "valid_from", "expires_on", "user_ids"):
        assert (await client.patch(base, json={field: None}, headers=headers(w["mgr"]))).status_code == 422, field
