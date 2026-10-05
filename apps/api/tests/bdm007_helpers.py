"""bdm-007 test builders (on bdm-006's)."""

from tests.bdm006_helpers import APPTS, create_appt, move_to_past

REPORT = {"outcome": "interested", "discussion": "Principal keen on IT training."}


async def completed(client, db, org: dict, **report) -> dict:
    """An appointment of the logged-in BDM, past its start, completed with REPORT (+ overrides)."""
    a = await create_appt(client, org)
    await move_to_past(db, a["id"])
    response = await client.post(f"{APPTS}/{a['id']}/complete", json={**REPORT, **report})
    assert response.status_code == 200, response.text
    return response.json()["appointment"]
