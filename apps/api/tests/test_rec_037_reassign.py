"""rec-037 -- recruiter deactivation + bulk reassignment (spec §2 RC1-RC15; backlog AC1, AC2, P1, N1, E1)."""

import uuid
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import select

from app.models import AuditLog, Company, CompanyAssignmentHistory, Job, RecruiterFollowUp, User
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter, make_user

REASSIGN = "/api/v1/recruiter/manager/reassign"
TEAM = "/api/v1/recruiter/manager/team"
USERS = "/api/v1/admin/users"
COMPANIES = "/api/v1/recruiter/companies"
REQUIREMENTS = "/api/v1/recruiter/requirements"


async def _companies(db, n: int, owner: User | None, *, archived: bool = False) -> list[UUID]:
    rows = [Company(name=f"Reassign {uuid.uuid4().hex[:10]} Ltd", assigned_recruiter_user_id=owner.id if owner else None, archived_at=datetime.now(UTC) if archived else None) for _ in range(n)]
    db.add_all(rows)
    await db.commit()
    return [c.id for c in rows]


async def _requirement(db, company_id: UUID, owner: User | None, status: str = "sourcing") -> UUID:
    job = Job(company_id=company_id, title="Java developer", location="Pune", description="Spring", status=status, assigned_recruiter_user_id=owner.id if owner else None)
    db.add(job)
    await db.commit()
    return job.id


async def _follow_up(db, company_id: UUID, creator: User, status: str = "open") -> None:
    done = status == "done"
    db.add(
        RecruiterFollowUp(
            company_id=company_id,
            reason="new_requirement",
            due_at=datetime.now(UTC) + timedelta(days=2),
            status=status,
            completed_at=datetime.now(UTC) if done else None,
            completed_by_user_id=creator.id if done else None,
            created_by_user_id=creator.id,
        )
    )
    await db.commit()


async def _team(client, db):
    """A placement manager with two recruiters; signed in as the manager."""
    manager = await make_pm(db)
    a, b = await make_recruiter(db, manager), await make_recruiter(db, manager)
    await login(client, manager)
    return manager, a, b


async def _reassign(client, source: User, target_id, expected: int = 200) -> dict:
    response = await client.post(REASSIGN, json={"from_user_id": str(source.id), "to_user_id": str(target_id)})
    assert response.status_code == expected, response.text
    return response.json()


async def _deactivate(client, db, recruiter: User, expected: int, role: str = "super_admin", division: str = "global") -> dict:
    await as_role(client, db, role, division)
    response = await client.patch(f"{USERS}/{recruiter.id}", json={"active": False})
    assert response.status_code == expected, response.text
    return response.json()


async def _col(db, column, where):
    return await db.scalar(select(column).where(where))


# --- deactivation pre-check (RC1-RC3, RC11, RC12) --------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deactivating_a_recruiter_with_companies_and_requirements_is_refused_with_the_counts(client, db_session):
    _, a, _ = await _team(client, db_session)
    ids = await _companies(db_session, 2, a)
    await _requirement(db_session, ids[0], a)
    body = await _deactivate(client, db_session, a, 422)
    assert body["detail"] == ("This recruiter has 2 companies and 1 open requirement. A placement manager must reassign them (Team page) before deactivation.")
    assert await _col(db_session, User.active, User.id == a.id) is True


@pytest.mark.asyncio
async def test_it_admin_gets_the_same_refusal_and_counts_name_only_what_exists(client, db_session):
    _, a, _ = await _team(client, db_session)
    [other] = await _companies(db_session, 1, None)
    await _requirement(db_session, other, a, status="on_hold")
    body = await _deactivate(client, db_session, a, 422, role="it_admin", division="it")
    assert body["detail"] == "This recruiter has 1 open requirement. A placement manager must reassign them (Team page) before deactivation."


@pytest.mark.asyncio
async def test_archived_companies_and_ended_requirements_do_not_block_and_the_session_ends(client, db_session):
    _, a, _ = await _team(client, db_session)
    [archived] = await _companies(db_session, 1, a, archived=True)
    await _requirement(db_session, archived, a, status="closed")
    await _requirement(db_session, archived, a, status="cancelled")
    before = await _col(db_session, User.session_version, User.id == a.id)
    await _deactivate(client, db_session, a, 200)
    assert await _col(db_session, User.active, User.id == a.id) is False
    assert await _col(db_session, User.session_version, User.id == a.id) == before + 1


@pytest.mark.asyncio
async def test_deactivation_succeeds_after_reassignment(client, db_session):
    _, a, b = await _team(client, db_session)
    [cid] = await _companies(db_session, 1, a)
    await _requirement(db_session, cid, a)
    await _reassign(client, a, b.id)
    await _deactivate(client, db_session, a, 200)


@pytest.mark.asyncio
async def test_other_roles_deactivate_as_before(client, db_session):
    manager = await make_pm(db_session)
    await _deactivate(client, db_session, manager, 200)


# --- reassign (RC5-RC7, RC13; AC2, P1) -----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_moves_companies_requirements_and_follow_ups_with_history_and_audit(client, db_session):
    manager, a, b = await _team(client, db_session)
    third = await make_recruiter(db_session, manager)
    live, archived = await _companies(db_session, 1, a), await _companies(db_session, 1, a, archived=True)
    [elsewhere] = await _companies(db_session, 1, third)
    mine = [await _requirement(db_session, live[0], a), await _requirement(db_session, archived[0], a, status="closed"), await _requirement(db_session, elsewhere, a)]
    thirds = await _requirement(db_session, live[0], third)
    unassigned = await _requirement(db_session, live[0], None)
    await _follow_up(db_session, live[0], a)
    await _follow_up(db_session, live[0], a, status="done")
    body = await _reassign(client, a, b.id)
    assert body == {"from_user_id": str(a.id), "to_user_id": str(b.id), "moved": {"companies": 2, "requirements": 3, "follow_ups": 1}}
    owners = (await db_session.execute(select(Company.assigned_recruiter_user_id).where(Company.id.in_(live + archived)))).scalars().all()
    assert set(owners) == {b.id}
    job_owner = select(Job.assigned_recruiter_user_id).where
    assert {await db_session.scalar(job_owner(Job.id == j)) for j in mine} == {b.id}
    assert await db_session.scalar(job_owner(Job.id == thirds)) == third.id  # RC6
    assert await db_session.scalar(job_owner(Job.id == unassigned)) is None
    history = (
        await db_session.execute(
            select(CompanyAssignmentHistory.company_id, CompanyAssignmentHistory.from_user_id, CompanyAssignmentHistory.to_user_id, CompanyAssignmentHistory.changed_by_user_id).where(
                CompanyAssignmentHistory.company_id.in_(live + archived)
            )
        )
    ).all()
    assert sorted(history, key=str) == sorted([(c, a.id, b.id, manager.id) for c in live + archived], key=str)
    audits = (await db_session.execute(select(AuditLog.action, AuditLog.entity_id, AuditLog.metadata_json).where(AuditLog.user_id == manager.id))).all()
    assert sorted(e for act, e, _ in audits if act == "recruiter_company.assign") == sorted(str(c) for c in live + archived)
    assert sorted(e for act, e, _ in audits if act == "recruiter_requirement.assign") == sorted(str(j) for j in mine)
    assert all(m["reason"] == "reassign" for act, _, m in audits if act.endswith(".assign"))
    [summary] = [m for act, e, m in audits if act == "recruiter.reassign" and e == str(a.id)]
    assert summary == {"to_user_id": str(b.id), "moved": {"companies": 2, "requirements": 3, "follow_ups": 1}}


@pytest.mark.asyncio
async def test_twelve_companies_move_and_the_old_recruiter_loses_access(client, db_session):
    _, a, b = await _team(client, db_session)
    ids = await _companies(db_session, 12, a)
    job = await _requirement(db_session, ids[0], a)
    assert (await _reassign(client, a, b.id))["moved"]["companies"] == 12
    await login(client, a)
    assert (await client.get(f"{COMPANIES}/{ids[0]}")).status_code == 404
    assert (await client.get(f"{REQUIREMENTS}/{job}")).status_code == 404
    await login(client, b)
    assert (await client.get(f"{COMPANIES}/{ids[0]}")).status_code == 200
    assert (await client.get(f"{REQUIREMENTS}/{job}")).status_code == 200


@pytest.mark.asyncio
async def test_an_inactive_recruiter_can_still_be_handed_over(client, db_session):
    manager = await make_pm(db_session)
    a, b = await make_recruiter(db_session, manager, active=False), await make_recruiter(db_session, manager)
    await _companies(db_session, 1, a)
    await login(client, manager)
    assert (await _reassign(client, a, b.id))["moved"]["companies"] == 1


@pytest.mark.asyncio
async def test_super_admin_moves_a_recruiter_with_no_manager_but_a_manager_cannot(client, db_session):
    _, _, b = await _team(client, db_session)
    orphan = await make_recruiter(db_session, None)
    await _companies(db_session, 1, orphan)
    body = await _reassign(client, orphan, b.id, 403)
    assert body["detail"] == "This recruiter is not in your team"
    await as_role(client, db_session, "super_admin", "global")
    assert (await _reassign(client, orphan, b.id))["moved"]["companies"] == 1


# --- refusals (RC4, RC8; N1) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_invalid_targets_are_one_422(client, db_session):
    manager, a, _ = await _team(client, db_session)
    await _companies(db_session, 1, a)
    outsider = await make_recruiter(db_session, await make_pm(db_session))
    inactive = await make_recruiter(db_session, manager, active=False)
    not_recruiter = await make_user(db_session, "hr_team", "it")
    await login(client, manager)
    for target in (outsider.id, inactive.id, a.id, not_recruiter.id, uuid.uuid4()):
        assert (await _reassign(client, a, target, 422))["detail"] == "Choose an active recruiter from your team"
    assert await _col(db_session, Company.assigned_recruiter_user_id, Company.assigned_recruiter_user_id == a.id) == a.id


@pytest.mark.asyncio
async def test_source_outside_the_team_is_403_and_unknown_is_404(client, db_session):
    _, _, b = await _team(client, db_session)
    outsider = await make_recruiter(db_session, await make_pm(db_session))
    assert (await _reassign(client, outsider, b.id, 403))["detail"] == "This recruiter is not in your team"
    hr = await make_user(db_session, "hr_team", "it")
    for source in (hr, User(id=uuid.uuid4())):
        assert (await _reassign(client, source, b.id, 404))["detail"] == "Recruiter not found"


@pytest.mark.asyncio
async def test_nothing_to_move_is_409(client, db_session):
    _, a, b = await _team(client, db_session)
    assert (await _reassign(client, a, b.id, 409))["detail"] == "This recruiter has no companies or requirements to reassign"


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("placement_team", "it"), ("it_admin", "it"), ("hr_team", "it"), ("bdm", "it")])
async def test_other_roles_are_403(client, db_session, role, division):
    _, a, b = await _team(client, db_session)
    await _companies(db_session, 1, a)
    if role == "placement_team":
        await login(client, a)
    else:
        await as_role(client, db_session, role, division)
    await _reassign(client, a, b.id, 403)


@pytest.mark.asyncio
async def test_extra_keys_are_422_and_signed_out_is_401(client, db_session):
    _, a, b = await _team(client, db_session)
    response = await client.post(REASSIGN, json={"from_user_id": str(a.id), "to_user_id": str(b.id), "only": "companies"})
    assert response.status_code == 422
    client.cookies.clear()
    assert (await client.post(REASSIGN, json={"from_user_id": str(a.id), "to_user_id": str(b.id)})).status_code == 401


# --- team rows (RC15) ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_team_rows_carry_each_recruiters_work(client, db_session):
    manager, a, b = await _team(client, db_session)
    ids = await _companies(db_session, 2, a)
    await _companies(db_session, 1, a, archived=True)
    await _requirement(db_session, ids[0], a)
    await _follow_up(db_session, ids[0], manager)
    await _follow_up(db_session, ids[1], manager, status="done")
    rows = {r["id"]: r for r in (await client.get(TEAM)).json()["items"]}
    assert rows[str(a.id)]["work"] == {"companies": 3, "requirements": 1, "follow_ups": 1}
    assert rows[str(b.id)]["work"] == {"companies": 0, "requirements": 0, "follow_ups": 0}
