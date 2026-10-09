"""rec-018 -- screening form + result (spec §2-§3; AC1, AC2; DEC-SCOPE-140 SC1-SC8). Names are unique per test (the database is shared
and never truncated)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import ApplicationScreening, AuditLog, Company, JobApplicationStatusHistory, Notification
from app.services import application_screening as screening_svc
from tests.rec001_helpers import as_role, login, make_recruiter, make_user
from tests.test_rec_017_tracking import APPS, REQ, _add, _candidate, _move, _requirement, _team

FULL = {
    "qualification_verified": True,
    "experience_verified": True,
    "skills_verified": False,
    "expected_salary": "650000.00",
    "notice_days": 30,
    "location_preference": "Pune or Bengaluru",
    "communication_rating": 4,
    "technical_rating": 5,
    "availability": "Immediate",
    "willing_to_relocate": True,
    "remarks": "Strong Java, good communicator",
    "result": "shortlisted",
}


async def _screen(client, application_id, **body):
    return await client.put(f"{APPS}/{application_id}/screening", json=body)


async def _application(client, db, status="sourced", recruiter=None):
    if recruiter is None:
        _, recruiter = await _team(client, db)
    job = await _requirement(db, recruiter)
    app_id = (await _add(client, job, await _candidate(db, recruiter), status=status)).json()["application"]["id"]
    return recruiter, job, app_id


async def _history(db, app_id):
    rows = (await db.scalars(select(JobApplicationStatusHistory).where(JobApplicationStatusHistory.application_id == uuid.UUID(app_id)).order_by(JobApplicationStatusHistory.created_at))).all()
    return [(r.from_status, r.to_status, r.note) for r in rows]


# --- AC1 / SC3 --------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_shortlisted_moves_the_status_and_writes_history(client, db_session):
    _, _, app_id = await _application(client, db_session)
    empty = await client.get(f"{APPS}/{app_id}/screening")
    assert empty.status_code == 200
    assert empty.json()["screening"] is None and empty.json()["can_edit"] is True
    assert [r["key"] for r in empty.json()["results"]] == ["shortlisted", "hold", "rejected", "need_more_info"]
    response = await _screen(client, app_id, **FULL)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["application"]["status"] == "shortlisted"
    assert body["application"]["screening_result"] == {"key": "shortlisted", "label": "Shortlisted"}
    saved = body["screening"]
    assert {k: saved[k] for k in FULL} == {**FULL, "expected_salary": 650000.0}
    assert saved["result_label"] == "Shortlisted" and saved["screened_by"]["full_name"]
    assert (await _history(db_session, app_id))[-1] == ("sourced", "shortlisted", "Screening: Shortlisted")
    again = (await client.get(f"{APPS}/{app_id}/screening")).json()["screening"]
    assert again["remarks"] == FULL["remarks"]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["shortlisted", "interview"])
async def test_shortlisted_never_moves_an_application_backwards(client, db_session, status):
    _, _, app_id = await _application(client, db_session, status="shortlisted")
    if status == "interview":
        assert (await _move(client, app_id, "interview")).status_code == 200
    response = await _screen(client, app_id, result="shortlisted")
    assert response.status_code == 200 and response.json()["application"]["status"] == status


@pytest.mark.asyncio
async def test_rejected_with_remarks_rejects_the_application(client, db_session):
    _, _, app_id = await _application(client, db_session, status="screened")
    response = await _screen(client, app_id, result="rejected", remarks="Salary expectation too high")
    assert response.status_code == 200 and response.json()["application"]["status"] == "rejected"
    assert (await _history(db_session, app_id))[-1] == ("screened", "rejected", "Screening: Rejected")


# --- AC2 / validation ---------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("remarks", [None, "", "   "])
async def test_ac2_rejected_requires_remarks(client, db_session, remarks):
    _, _, app_id = await _application(client, db_session)
    body = {"result": "rejected", **({"remarks": remarks} if remarks is not None else {})}
    response = await _screen(client, app_id, **body)
    assert response.status_code == 422 and "Remarks are required" in response.text
    assert (await client.get(f"{APPS}/{app_id}/screening")).json()["screening"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"communication_rating": 0},
        {"technical_rating": 6},
        {"notice_days": -1},
        {"notice_days": 366},
        {"expected_salary": -5},
        {"result": "maybe"},
        {},
        {"remarks": "x" * 2001},
        {"location_preference": "x" * 201},
        {"availability": "a\x00b"},
        {"extra": 1},
    ],
)
async def test_out_of_range_or_unknown_values_are_422(client, db_session, body):
    _, _, app_id = await _application(client, db_session)
    payload = {"result": "hold", **body} if body else {}  # {} = the required result left out
    assert (await _screen(client, app_id, **payload)).status_code == 422


# --- SC2 / SC4 / SC5 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("result", "label"), [("hold", "Hold"), ("need_more_info", "Need More Information")])
async def test_hold_and_need_more_info_keep_the_status_and_flag_the_board(client, db_session, result, label):
    _, job, app_id = await _application(client, db_session, status="screened")
    response = await _screen(client, app_id, result=result, remarks="Waiting for certificates")
    assert response.status_code == 200 and response.json()["application"]["status"] == "screened"
    assert len(await _history(db_session, app_id)) == 1
    board = (await client.get(f"{REQ}/{job.id}/candidates")).json()["items"][0]
    assert board["screening_result"] == {"key": result, "label": label}


@pytest.mark.asyncio
async def test_re_screening_after_hold_overwrites_the_one_current_screening(client, db_session):
    _, _, app_id = await _application(client, db_session)
    assert (await _screen(client, app_id, result="hold", notice_days=60)).status_code == 200
    second = await _screen(client, app_id, result="shortlisted", technical_rating=4)
    assert second.status_code == 200 and second.json()["application"]["status"] == "shortlisted"
    saved = second.json()["screening"]
    assert saved["notice_days"] is None and saved["technical_rating"] == 4  # PUT replaces the form (SC5)
    rows = (await db_session.scalars(select(ApplicationScreening).where(ApplicationScreening.application_id == uuid.UUID(app_id)))).all()
    assert len(rows) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("closed", ["rejected", "withdrawn", "selected"])
async def test_a_closed_application_cannot_be_screened(client, db_session, closed):
    _, _, app_id = await _application(client, db_session)
    assert (await _move(client, app_id, closed, "Closed")).status_code == 200
    assert (await client.get(f"{APPS}/{app_id}/screening")).json()["can_edit"] is False
    response = await _screen(client, app_id, result="hold")
    assert response.status_code == 409 and response.json()["detail"] == screening_svc.NOT_OPEN


@pytest.mark.asyncio
async def test_audit_holds_field_names_never_values_and_an_unchanged_save_is_a_no_op(client, db_session):
    _, _, app_id = await _application(client, db_session)
    assert (await _screen(client, app_id, **{**FULL, "result": "hold"})).status_code == 200
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == app_id, AuditLog.action == screening_svc.AUDIT))).all()
    assert len(audits) == 1
    meta = audits[0].metadata_json
    assert meta["result"] == "hold" and "expected_salary" in meta["fields"]
    assert "650000" not in str(meta) and FULL["remarks"] not in str(meta)
    again = await _screen(client, app_id, **{**FULL, "result": "hold"})
    assert again.status_code == 200
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == app_id, AuditLog.action == screening_svc.AUDIT))).all()
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_a_student_is_notified_when_screening_moves_the_status(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    student = await make_user(db_session, "it_student", "it")
    candidate = await _candidate(db_session, recruiter, user_id=student.id, opted_in=True)
    app_id = (await _add(client, job, candidate)).json()["application"]["id"]
    assert (await _screen(client, app_id, result="shortlisted")).status_code == 200
    note = await db_session.scalar(select(Notification).where(Notification.user_id == student.id).order_by(Notification.created_at.desc()))
    assert note.body == "Your application status is now Shortlisted."


# --- RBAC (SC8) ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_and_assigned_bdm_read_but_never_write(client, db_session):
    manager, recruiter = await _team(client, db_session)
    _, job, app_id = await _application(client, db_session, recruiter=recruiter)
    assert (await _screen(client, app_id, result="hold")).status_code == 200
    bdm = await make_user(db_session, "bdm", "global")
    company = await db_session.get(Company, job.company_id)
    company.assigned_bdm_user_id = bdm.id
    await db_session.commit()
    for reader in (manager, bdm):
        await login(client, reader)
        read = await client.get(f"{APPS}/{app_id}/screening")
        assert read.status_code == 200 and read.json()["can_edit"] is False and read.json()["screening"]["result"] == "hold"
        assert (await _screen(client, app_id, result="shortlisted")).status_code == 403


@pytest.mark.asyncio
async def test_super_admin_writes(client, db_session):
    recruiter = await make_recruiter(db_session, None)
    job = await _requirement(db_session, recruiter)
    await as_role(client, db_session, "super_admin", "global")
    app_id = (await _add(client, job, await _candidate(db_session, recruiter))).json()["application"]["id"]
    assert (await _screen(client, app_id, result="shortlisted")).status_code == 200


@pytest.mark.asyncio
async def test_another_recruiters_application_is_404(client, db_session):
    _, recruiter = await _team(client, db_session)
    other = await make_recruiter(db_session, None)
    await login(client, other)
    _, _, app_id = await _application(client, db_session, recruiter=other)
    await login(client, recruiter)
    assert (await client.get(f"{APPS}/{app_id}/screening")).status_code == 404
    assert (await _screen(client, app_id, result="hold")).status_code == 404
    assert (await client.get(f"{APPS}/{uuid.uuid4()}/screening")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("it_student", "it"), ("employer", "it"), ("hr_team", "it"), ("overseas_admin", "overseas"), ("telecaller", "global")])
async def test_outsiders_are_refused(client, db_session, role, division):
    _, _, app_id = await _application(client, db_session)
    await as_role(client, db_session, role, division)
    assert (await client.get(f"{APPS}/{app_id}/screening")).status_code == 403
    assert (await _screen(client, app_id, result="hold")).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(f"{APPS}/{uuid.uuid4()}/screening")).status_code == 401
    assert (await client.put(f"{APPS}/{uuid.uuid4()}/screening", json={"result": "hold"})).status_code == 401
