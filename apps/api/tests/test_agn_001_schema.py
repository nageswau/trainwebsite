import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import AgentOrg, AgentOrgMember
from tests.agn001_helpers import mk_user


@pytest.mark.asyncio
async def test_alembic_head_is_0046(db_session):
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    script = ScriptDirectory.from_config(config)
    assert await db_session.scalar(text("SELECT version_num FROM alembic_version")) == script.get_current_head() == "0046_agent_orgs"


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [{"status": "approved"}, {"master_seq": -1}])
async def test_org_checks_reject_bad_values(db_session, overrides):
    db_session.add(AgentOrg(**{"name": "Chk", "prefix": f"Q{uuid.uuid4().hex[:6].upper()}", "status": "pending", "master_seq": 0, **overrides}))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_a_user_belongs_to_one_organisation_only(db_session):
    user = await mk_user(db_session, role="agent")
    orgs = [AgentOrg(name="One", prefix=f"Q{uuid.uuid4().hex[:6].upper()}", status="pending", master_seq=1) for _ in range(2)]
    db_session.add_all(orgs)
    await db_session.flush()
    db_session.add(AgentOrgMember(org_id=orgs[0].id, user_id=user.id, role="master", seq=1, code=f"{orgs[0].prefix}-M001", status="active"))
    await db_session.flush()
    db_session.add(AgentOrgMember(org_id=orgs[1].id, user_id=user.id, role="master", seq=1, code=f"{orgs[1].prefix}-M001", status="active"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [{"role": "staff"}, {"status": "invited"}])
async def test_member_checks_reject_bad_values(db_session, overrides):
    user = await mk_user(db_session, role="agent")
    org = AgentOrg(name="Chk", prefix=f"Q{uuid.uuid4().hex[:6].upper()}", status="pending", master_seq=1)
    db_session.add(org)
    await db_session.flush()
    db_session.add(AgentOrgMember(**{"org_id": org.id, "user_id": user.id, "role": "master", "seq": 1, "code": f"{org.prefix}-M001", "status": "active", **overrides}))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
