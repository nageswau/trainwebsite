import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
import pytest_asyncio
from enh005_helpers import login, mk_request, mk_result, mk_school, mk_staff, mk_student, mk_user
from httpx import ASGITransport
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.main import app
from app.models import AuditLog, SchoolAcademicResult, SchoolParentLink, SchoolStudent, SchoolStudentGradeHistory, SchoolStudentTransferRequest, User

# ENH-005 spec §5.4 "Concurrency, stated once". Each test holds a row lock in a SEPARATE session so both competing requests are
# genuinely queued behind it, then releases it: the interleaving is forced rather than left to timing.

APPROVE = "/api/v1/overseas-admin/school-transfer-requests/{rid}/approve"
PROMOTE = "/api/v1/school/students/promotions"


@asynccontextmanager
async def _client_for(email: str):
    """A separate ASGI client with its own cookie jar, so two users can be in flight at once."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await login(c, email)
        yield c


@asynccontextmanager
async def _held(model, pk):
    """Another transaction holding this row's lock until the block ends."""
    session = SessionLocal()
    try:
        await session.execute(select(model).where(model.id == pk).with_for_update())
        yield
    finally:
        await session.rollback()
        await session.close()


async def _fresh(db, model, pk):
    return await db.get(model, pk, populate_existing=True)


@pytest_asyncio.fixture
async def world(db_session):
    a = await mk_school(db_session, label="A", students=2)
    b = await mk_school(db_session, label="B", students=0)
    request = await mk_request(db_session, a["students"][0], from_school=a["school"], to_school=b["school"], filed_by_school=a["school"], requester=a["coordinator"])
    return {"a": a, "b": b, "kid": a["students"][0], "request": request, "admin": a["admin"]}


@pytest.mark.asyncio
async def test_two_simultaneous_approvals_of_one_request_one_wins_and_one_is_409(db_session, world):
    w = world
    async with _client_for(w["admin"].email) as first, _client_for(w["admin"].email) as second:
        async with _held(SchoolStudentTransferRequest, w["request"].id):  # both queue on the request row
            tasks = [asyncio.create_task(c.post(APPROVE.format(rid=w["request"].id))) for c in (first, second)]
            await asyncio.sleep(0.5)
        results = await asyncio.gather(*tasks)

    assert sorted(r.status_code for r in results) == [200, 409]
    assert (await _fresh(db_session, SchoolStudent, w["kid"].id)).school_id == w["b"]["school"].id
    transfers = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.student_transfer", AuditLog.entity_id == str(w["request"].id)))
    moved = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.user_school_scope_changed", AuditLog.entity_id == str(w["a"]["parent"].id)))
    assert (transfers, moved) == (1, 1)  # the move, and the parent's re-scoping, each happened exactly once


@pytest.mark.asyncio
@pytest.mark.parametrize("promotion_first", [False, True])
async def test_a_promotion_racing_a_transfer_is_safe_in_either_order(db_session, world, promotion_first):
    """Both requests queue behind a held student lock in a fixed order (Postgres grants a row lock to waiters in arrival order), so each
    interleaving is exercised deliberately. The promotion is `POST /school/students/promotions` (ENH-004), which locks the student under
    a school filter."""
    w = world
    kid = w["kid"]
    body = {"items": [{"student_id": str(kid.id), "action": "promote"}]}
    async with _client_for(w["admin"].email) as admin, _client_for(w["a"]["coordinator"].email) as coordinator:
        approve = lambda: asyncio.create_task(admin.post(APPROVE.format(rid=w["request"].id)))  # noqa: E731
        promote = lambda: asyncio.create_task(coordinator.post(PROMOTE, json=body))  # noqa: E731
        async with _held(SchoolStudent, kid.id):
            first = (promote if promotion_first else approve)()
            await asyncio.sleep(0.4)
            second = (approve if promotion_first else promote)()
            await asyncio.sleep(0.4)
        r1, r2 = await asyncio.gather(first, second)
    promoted, approved = (r1, r2) if promotion_first else (r2, r1)

    assert approved.status_code == 200, approved.text  # the transfer succeeds in both orders
    assert (await _fresh(db_session, SchoolStudent, kid.id)).school_id == w["b"]["school"].id
    history = await db_session.scalar(select(func.count()).select_from(SchoolStudentGradeHistory).where(SchoolStudentGradeHistory.school_student_id == kid.id))
    if promotion_first:
        # The promotion committed first (200 when an academic year is active, as in the seeded database; 409 when none is, and it then
        # wrote nothing), and the transfer then moved the promoted student.
        assert promoted.status_code in (200, 409), promoted.text
        assert history == (1 if promoted.status_code == 200 else 0)
    else:
        # The transfer committed first, so the student no longer matches the promotion's school filter: the generic 403, nothing written.
        assert promoted.status_code == 403, promoted.text
        assert history == 0


@pytest.mark.asyncio
async def test_two_siblings_transferred_at_once_leave_their_shared_parent_at_the_new_school_with_both_links(db_session):
    a = await mk_school(db_session, label="A", students=0)
    b = await mk_school(db_session, label="B", students=0)
    kids = [await mk_student(db_session, a["school"], a["coordinator"], f"sib{i}") for i in range(2)]
    parent = await mk_user(db_session, role="school_parent", name="Shared parent", school_id=a["school"].id, assigned_by=a["coordinator"])
    await db_session.flush()
    db_session.add_all([SchoolParentLink(parent_user_id=parent.id, school_student_id=k.id, linked_by_user_id=a["coordinator"].id) for k in kids])
    await db_session.commit()
    requests = [await mk_request(db_session, k, from_school=a["school"], to_school=b["school"], filed_by_school=a["school"], requester=a["coordinator"]) for k in kids]

    async with _client_for(a["admin"].email) as one, _client_for(a["admin"].email) as two:
        async with _held(User, parent.id):  # both approvals reach the shared parent's row and queue there
            tasks = [asyncio.create_task(c.post(APPROVE.format(rid=r.id))) for c, r in ((one, requests[0]), (two, requests[1]))]
            await asyncio.sleep(0.7)
        results = await asyncio.gather(*tasks)

    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert (await _fresh(db_session, User, parent.id)).profile["school_id"] == str(b["school"].id)
    for kid in kids:
        assert (await _fresh(db_session, SchoolStudent, kid.id)).school_id == b["school"].id
    links = await db_session.scalar(select(func.count()).select_from(SchoolParentLink).where(SchoolParentLink.parent_user_id == parent.id))
    assert links == 2
    moved = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.user_school_scope_changed", AuditLog.entity_id == str(parent.id)))
    assert moved == 1  # serialised on the parent: the first saw the sibling still at A (kept), the second found none left (moved)


@pytest.mark.asyncio
async def test_an_approval_racing_a_result_verification_cannot_deadlock_and_the_result_ends_withdrawn(db_session, world):
    w = world
    uploader = await mk_staff(db_session, w["a"]["school"], w["admin"])
    reviewer = await mk_staff(db_session, w["a"]["school"], w["admin"])
    result = await mk_result(db_session, w["kid"], uploader, "draft")
    async with _client_for(w["admin"].email) as admin, _client_for(reviewer.email) as staff:
        async with _held(SchoolAcademicResult, result.id):  # the result row is busy: the approval (mid-transaction) and the verify both queue for it
            approval = asyncio.create_task(admin.post(APPROVE.format(rid=w["request"].id)))
            verify = asyncio.create_task(staff.post(f"/api/v1/school/academic-team/results/{result.id}/verify"))
            await asyncio.sleep(0.7)
        approved, verified = await asyncio.wait_for(asyncio.gather(approval, verify), timeout=20)  # a deadlock would time out here

    assert approved.status_code == 200, approved.text
    assert verified.status_code in (200, 403, 409), verified.text  # verified first, or refused because the student had already moved
    assert (await _fresh(db_session, SchoolAcademicResult, result.id)).status == "withdrawn"
