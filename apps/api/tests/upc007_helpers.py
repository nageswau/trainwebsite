"""upc-007 test builders, on top of upc-003's. Every value is unique per call: the test database is shared and never truncated."""

import uuid

from sqlalchemy import select

from app.models import UniversityStageHistory
from tests.upc003_helpers import catalogue_country, create, login, make_head, make_pm, url

PIPELINE = "/api/v1/partnership/pipeline"


async def owned_university(client, db, **overrides):
    """A head, their manager `pm` (assigned primary) and a new university; the client ends signed in as `pm`."""
    head = await make_head(db)
    pm = await make_pm(db, head)
    await login(client, head)
    uni = await create(client, (await catalogue_country(db)).id, **overrides)
    response = await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id)})
    assert response.status_code == 200, response.text
    await login(client, pm)
    return head, pm, uni


async def move(client, university_id, from_stage: str, to_stage: str, note: str | None = None):
    body = {"from_stage": from_stage, "to_stage": to_stage} | ({"note": note} if note is not None else {})
    return await client.post(url(university_id, "stage"), json=body)


async def move_ok(client, university_id, from_stage: str, to_stage: str, note: str | None = None) -> dict:
    response = await move(client, university_id, from_stage, to_stage, note)
    assert response.status_code == 200, response.text
    return response.json()["university"]


async def history(db, university_id) -> list[UniversityStageHistory]:
    db.expire_all()
    stmt = select(UniversityStageHistory).where(UniversityStageHistory.university_id == uuid.UUID(str(university_id))).order_by(UniversityStageHistory.position)
    return list((await db.scalars(stmt)).all())
