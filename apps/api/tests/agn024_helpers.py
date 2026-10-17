"""AGN-024 test helpers: a self-registered agent with its three KYC documents, and direct-DB verification for tests whose subject is
something else."""

import ipaddress
import secrets
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.models import AgentOrg, AgentOrgKycDocument
from tests.agn001_helpers import PASSWORD, org_of, uniq
from tests.agn009_helpers import PDF

KYC_FIELDS = {"pan_number": "ABCDE1234F", "aadhaar_last4": "1234", "license_number": "LIC-2026/001"}
REGISTER = "/api/v1/auth/register"


def fresh_ip() -> str:
    """A unique documentation-range address (2001:db8::/32): agent signups are throttled per client IP (K11, 5 per hour), so tests
    that register agents must not share one."""
    return str(ipaddress.IPv6Address((0x20010DB8 << 96) | secrets.randbits(96)))


def ip_headers(**extra) -> dict:
    return {"X-Forwarded-For": fresh_ip(), **extra}


def kyc_files(pan: bytes = PDF, aadhaar: bytes = PDF, license: bytes = PDF) -> dict:
    return {
        "pan_file": ("pan.pdf", pan, "application/pdf"),
        "aadhaar_file": ("aadhaar.pdf", aadhaar, "application/pdf"),
        "license_file": ("licence.pdf", license, "application/pdf"),
    }


def agent_form(**overrides) -> dict:
    return {"email": f"{uniq('agn024')}@example.local", "password": PASSWORD, "full_name": "KYC Agent", "division": "overseas", "account_type": "agent", **KYC_FIELDS, **overrides}


async def register_kyc_agent(client, files: dict | None = None, **overrides) -> dict:
    response = await client.post(REGISTER, data=agent_form(**overrides), files=files or kyc_files(), headers=ip_headers())
    assert response.status_code == 201, response.text
    return response.json()


async def org_for(db, user_id) -> AgentOrg:
    return await org_of(db, user_id)


async def verify_all(db, org_id, actor) -> None:
    await db.execute(
        update(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org_id)
        .values(status="verified", rejection_reason=None, reviewed_by_user_id=actor.id, reviewed_at=datetime.now(UTC))
    )
    await db.commit()


async def kyc_rows(db, org_id) -> list[AgentOrgKycDocument]:
    return list((await db.scalars(select(AgentOrgKycDocument).where(AgentOrgKycDocument.org_id == org_id).execution_options(populate_existing=True))).all())
