"""bdm-017 test builders. Unique values per call: the test database is shared and never truncated."""

import uuid

from tests.bdm001_helpers import login

ADMIN_LEADS = "/api/v1/admin/leads"


def org_leads(org_id) -> str:
    return f"/api/v1/bdm/organizations/{org_id}/leads"


def conversion(lead_id) -> str:
    return f"{ADMIN_LEADS}/{lead_id}/conversion"


def student_email() -> str:
    return f"lead-{uuid.uuid4().hex[:10]}@example.local"


def lead_body(**over) -> dict:
    body = {"name": "Asha Nair", "email": student_email(), "phone": "+91 90000 11111", "interest": "B.Tech admissions"}
    body.update(over)
    return body


async def add_lead(client, org_id, **over) -> dict:
    response = await client.post(org_leads(org_id), json=lead_body(**over))
    assert response.status_code == 201, response.text
    return response.json()


async def as_user(client, user) -> None:
    client.cookies.clear()
    await login(client, user)
