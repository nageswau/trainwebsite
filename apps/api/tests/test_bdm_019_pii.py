"""bdm-019 AC4 -- no agent student PII is reachable from any BDM route: the link gives aggregates only (spec §6, A7)."""

import pytest
from sqlalchemy import select

from app.models import AgentOrgMember, AgentStudent, User
from tests.agn004_helpers import RECORDS
from tests.agn022_helpers import APPLICATIONS, DETAIL, STUDENTS, network_world
from tests.bdm001_helpers import login
from tests.bdm002_helpers import ORGS
from tests.bdm018_helpers import QUEUE
from tests.bdm019_helpers import link_agent, pending_agent


async def _secrets(db, org_id) -> list[str]:
    """Every agency student's name and email, and every member's name and email."""
    members = select(AgentOrgMember.user_id).where(AgentOrgMember.org_id == org_id)
    students = (await db.execute(select(AgentStudent.full_name, AgentStudent.email).where(AgentStudent.agent_id.in_(members)))).all()
    people = (await db.execute(select(User.full_name, User.email).where(User.id.in_(members)))).all()
    return [v for row in (*students, *people) for v in row if v]


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["owner", "manager"])
async def test_bdm_responses_carry_no_agency_names_or_emails(client, db_session, actor):
    n = await network_world(db_session)
    w = await pending_agent(client, db_session)
    assert (await link_agent(client, w["item"]["id"], n["org"].prefix)).status_code == 200
    secrets = await _secrets(db_session, n["org"].id)
    assert len(secrets) >= 8  # the fixture has named students and members to leak
    await login(client, w[actor])
    bodies = [
        (await client.get(f"{ORGS}/{w['org']['id']}")).text,
        (await client.get(ORGS, params={"limit": 100})).text,
        (await client.get(f"{ORGS}/{w['org']['id']}/stage-history")).text,
    ]
    for body in bodies:
        assert not [s for s in secrets if s in body]


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["owner", "manager"])
async def test_a_bdm_cannot_reach_the_agencys_students(client, db_session, actor):  # backlog negative scenario
    n = await network_world(db_session)
    w = await pending_agent(client, db_session)
    assert (await link_agent(client, w["item"]["id"], n["org"].prefix)).status_code == 200
    await login(client, w[actor])
    oid = n["org"].id
    assert (await client.get(f"{ORGS}/{w['org']['id']}/students")).status_code == 404
    assert (await client.get(f"{ORGS}/{w['org']['id']}/agent/students")).status_code == 404
    for url in (STUDENTS.format(oid=oid), APPLICATIONS.format(oid=oid), DETAIL.format(oid=oid), QUEUE):
        assert (await client.get(url)).status_code == 403, url
    assert (await client.get(RECORDS)).status_code in (403, 404)
