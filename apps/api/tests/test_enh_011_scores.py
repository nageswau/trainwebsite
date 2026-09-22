import pytest
from enh005_helpers import move_student_directly
from enh011_helpers import ASSESSMENTS, BATCHES, ENROLMENTS, create_batch, enrol, login, skills_world
from sqlalchemy import select

from app.models import AuditLog

# ENH-011 spec §5.1: several named assessments per batch (D8), scores upserted with optional remarks. AC-04, AC-06, AC-07.


async def _setup(client, w):
    await login(client, w["counselor"].email)
    batch = await create_batch(client, w["a"]["school"].id)
    rows = await enrol(client, batch["id"], *w["a"]["students"])
    return batch, rows


async def _assessment(client, batch_id, name="Presentation", max_score=20):
    response = await client.post(f"{BATCHES}/{batch_id}/assessments", json={"name": name, "max_score": max_score})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_multiple_assessments_and_duplicate_name_409(client, db_session):
    w = await skills_world(db_session)
    batch, _rows = await _setup(client, w)
    first = await _assessment(client, batch["id"], "Presentation", 20)
    await _assessment(client, batch["id"], "Final project", "100.50")
    assert first["max_score"] == 20.0
    duplicate = await client.post(f"{BATCHES}/{batch['id']}/assessments", json={"name": "Presentation", "max_score": 10})
    assert duplicate.status_code == 409 and "already has an assessment" in duplicate.json()["detail"]
    detail = (await client.get(f"{BATCHES}/{batch['id']}")).json()
    assert [(a["name"], a["max_score"]) for a in detail["assessments"]] == [("Presentation", 20.0), ("Final project", 100.5)]
    assert (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.skill_assessment_create", AuditLog.entity_id == first["id"]))).one()


@pytest.mark.asyncio
async def test_scores_upsert_and_remarks_stored(client, db_session):
    w = await skills_world(db_session)
    batch, (r0, r1) = await _setup(client, w)
    assessment = await _assessment(client, batch["id"])
    url = f"{ASSESSMENTS}/{assessment['id']}/scores"
    first = await client.put(url, json={"scores": [{"enrollment_id": r0["id"], "score": 15, "remarks": "Improve eye contact"}, {"enrollment_id": r1["id"], "score": "18.5"}]})
    assert first.status_code == 200
    second = (await client.put(url, json={"scores": [{"enrollment_id": r0["id"], "score": 17}]})).json()
    assert {(s["enrollment_id"], s["score"], s["remarks"]) for s in second["scores"]} == {(r0["id"], 17.0, None), (r1["id"], 18.5, None)}
    assert second["id"] == assessment["id"] and second["max_score"] == 20.0
    detail = (await client.get(f"{BATCHES}/{batch['id']}")).json()
    by_id = {e["id"]: e["scores"] for e in detail["enrollments"]}
    assert by_id[r1["id"]] == [{"assessment_id": assessment["id"], "score": 18.5, "remarks": None}]
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.skill_scores_record", AuditLog.entity_id == assessment["id"]))).all()
    assert len(audit) == 2 and "Improve" not in str(audit[0].metadata_json)


@pytest.mark.asyncio
async def test_score_lists_are_in_a_stated_order_after_an_upsert(client, db_session):
    """QA-04: as for attendance -- the updated row must not move to the end of the returned list."""
    w = await skills_world(db_session)
    batch, rows = await _setup(client, w)
    first, second = sorted(rows, key=lambda r: r["id"])
    assessment = await _assessment(client, batch["id"])
    url = f"{ASSESSMENTS}/{assessment['id']}/scores"
    await client.put(url, json={"scores": [{"enrollment_id": first["id"], "score": 10}, {"enrollment_id": second["id"], "score": 11}]})
    response = (await client.put(url, json={"scores": [{"enrollment_id": first["id"], "score": 12}]})).json()
    assert [s["enrollment_id"] for s in response["scores"]] == [first["id"], second["id"]]


@pytest.mark.asyncio
async def test_score_above_max_is_422_and_nothing_written(client, db_session):
    w = await skills_world(db_session)
    batch, (r0, r1) = await _setup(client, w)
    assessment = await _assessment(client, batch["id"], max_score=20)
    response = await client.put(f"{ASSESSMENTS}/{assessment['id']}/scores", json={"scores": [{"enrollment_id": r0["id"], "score": 10}, {"enrollment_id": r1["id"], "score": "20.01"}]})
    assert response.status_code == 422 and "out of 20" in response.json()["detail"]
    detail = (await client.get(f"{BATCHES}/{batch['id']}")).json()
    assert all(e["scores"] == [] for e in detail["enrollments"])


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["withdrawn", "frozen"])
async def test_scores_for_frozen_or_withdrawn_409(client, db_session, state):
    w = await skills_world(db_session)
    batch, (r0, _r1) = await _setup(client, w)
    assessment = await _assessment(client, batch["id"])
    if state == "frozen":
        await move_student_directly(db_session, w["a"]["students"][0], w["b"]["school"])
        r0 = next(r for r in (await client.get(f"{BATCHES}/{batch['id']}")).json()["enrollments"] if r["frozen"])
    else:
        await client.patch(f"{ENROLMENTS}/{r0['id']}", json={"status": "withdrawn"})
    response = await client.put(f"{ASSESSMENTS}/{assessment['id']}/scores", json={"scores": [{"enrollment_id": r0["id"], "score": 5}]})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_closed_batch_rejects_assessment_and_scores_409(client, db_session):
    w = await skills_world(db_session)
    batch, (r0, _r1) = await _setup(client, w)
    assessment = await _assessment(client, batch["id"])
    await client.patch(f"{BATCHES}/{batch['id']}", json={"status": "closed"})
    assert (await client.post(f"{BATCHES}/{batch['id']}/assessments", json={"name": "Late", "max_score": 5})).status_code == 409
    assert (await client.put(f"{ASSESSMENTS}/{assessment['id']}/scores", json={"scores": [{"enrollment_id": r0["id"], "score": 5}]})).status_code == 409


@pytest.mark.asyncio
async def test_assessment_outside_portfolio_is_404(client, db_session):
    w = await skills_world(db_session)
    batch, (r0, _r1) = await _setup(client, w)
    assessment = await _assessment(client, batch["id"])
    await login(client, w["counselor_b"].email)
    assert (await client.put(f"{ASSESSMENTS}/{assessment['id']}/scores", json={"scores": [{"enrollment_id": r0["id"], "score": 5}]})).status_code == 404
