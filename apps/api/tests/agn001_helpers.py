import uuid
from contextlib import asynccontextmanager

import httpx
from httpx import ASGITransport
from sqlalchemy import select

from app.core.security import hash_password
from app.main import app
from app.models import AgentOrg, AgentOrgMember, User

PASSWORD = "Sup3r-Secret-Pass!"


def uniq(label: str = "agn") -> str:
    return f"{label}-{uuid.uuid4().hex[:8]}"


async def mk_user(db, *, role: str, division: str = "overseas", full_name: str = "AGN User", active: bool = True, profile: dict | None = None) -> User:
    user = User(email=f"{uniq(role)}@example.local", password_hash=hash_password(PASSWORD), full_name=full_name, role=role, division=division, active=active, profile=profile or {})
    db.add(user)
    await db.commit()
    return user


async def login(client, email: str, division: str = "overseas") -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": division})
    assert response.status_code == 200, response.text


async def register_agent(client, **overrides) -> dict:
    payload = {"email": f"{uniq('agn-reg')}@example.local", "password": PASSWORD, "full_name": "Test Agent", "division": "overseas", "account_type": "agent", **overrides}
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def membership(db, user_id) -> AgentOrgMember | None:
    return await db.scalar(select(AgentOrgMember).where(AgentOrgMember.user_id == user_id).execution_options(populate_existing=True))


async def org_of(db, user_id) -> AgentOrg | None:
    member = await membership(db, user_id)
    return None if member is None else await db.get(AgentOrg, member.org_id, populate_existing=True)


async def mk_active_org(db, *, name: str = "AGN Agency") -> dict:
    """An approved agent who is M001 of an active organisation."""
    from app.models import UserRoleAssignment
    from app.services.agent_orgs import ensure_agent_org

    master = await mk_user(db, role="agent", full_name=f"{name} Master")
    db.add(UserRoleAssignment(user_id=master.id, division="overseas", role="agent", approval_status="approved"))
    await db.flush()
    member = await ensure_agent_org(db, master, agency_name=name, status="active")
    await db.commit()
    return {"master": master, "member": member, "org": await db.get(AgentOrg, member.org_id)}


@asynccontextmanager
async def client_for(email: str, division: str = "overseas"):
    """A separate ASGI client with its own cookie jar, so two users can be in flight at once."""
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await login(c, email, division)
        yield c
