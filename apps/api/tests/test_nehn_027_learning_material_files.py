"""nehn-027 -- trainer learning materials: file upload and manage (DEC-SCOPE-294; spec
docs/superpowers/specs/2026-10-27-nehn-027-learning-material-files-design.md)."""

import datetime
import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, Batch, Enrollment, LearningResource, Program
from tests.agn001_helpers import client_for, mk_user

PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
MATERIALS = "/api/v1/workflows/it/trainer/materials"


async def _batch(db, trainer) -> Batch:
    program = Program(
        slug=f"prog-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"nehn-027 {uuid.uuid4().hex[:6]}",
        summary="Test",
        duration="8 weeks",
        eligibility="None",
        fees=10000,
        certification="Cert",
        curriculum=["M1"],
        placement_assistance="Yes",
        trainer_name="T",
        active=True,
    )
    db.add(program)
    await db.flush()
    batch = Batch(
        program_id=program.id,
        name=f"B-{uuid.uuid4().hex[:6]}",
        start_date=datetime.date.today(),
        end_date=datetime.date.today() + datetime.timedelta(days=90),
        schedule="Mon 7pm",
        capacity=20,
        enrollment_open=True,
        status="active",
        trainer_id=trainer.id,
    )
    db.add(batch)
    await db.flush()
    return batch


async def _world(db) -> dict:
    trainer = await mk_user(db, role="trainer", division="it")
    other_trainer = await mk_user(db, role="trainer", division="it")
    student_a = await mk_user(db, role="it_student", division="it")
    student_b = await mk_user(db, role="it_student", division="it")
    admin = await mk_user(db, role="it_admin", division="it")
    batch_a = await _batch(db, trainer)
    batch_b = await _batch(db, other_trainer)
    db.add(Enrollment(student_id=student_a.id, batch_id=batch_a.id, enrollment_code=f"EDU-{uuid.uuid4().hex[:8]}", status="active"))
    db.add(Enrollment(student_id=student_b.id, batch_id=batch_b.id, enrollment_code=f"EDU-{uuid.uuid4().hex[:8]}", status="active"))
    await db.commit()
    return {"trainer": trainer, "other_trainer": other_trainer, "student_a": student_a, "student_b": student_b, "admin": admin, "batch_a": batch_a, "batch_b": batch_b}


async def _upload(c, name: str = "week-1.pdf", data: bytes = PDF, content_type: str = "application/pdf", purpose: str = "learning_material") -> str:
    response = await c.post("/api/v1/files/upload", params={"purpose": purpose}, files={"file": (name, data, content_type)})
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _publish_file(c, batch_id, title: str = "Week 1 notes") -> dict:
    file_id = await _upload(c)
    response = await c.post(MATERIALS, json={"batch_id": str(batch_id), "title": title, "resource_type": "document", "file_id": file_id})
    assert response.status_code == 201, response.text
    return response.json()


async def _downloads(c) -> list[dict]:
    response = await c.get("/api/v1/portal/it/student/downloads")
    assert response.status_code == 200, response.text
    return response.json()["rows"]


@pytest.mark.asyncio
async def test_uploaded_pdf_reaches_only_the_batch_students(client, db_session):
    w = await _world(db_session)
    big = PDF + b"0" * (3 * 1024 * 1024)
    async with client_for(w["trainer"].email, "it") as c:
        file_id = await _upload(c, "Notes wk1.pdf", big)
        created = await c.post(MATERIALS, json={"batch_id": str(w["batch_a"].id), "title": "Week 1 notes", "resource_type": "document", "file_id": file_id})
        assert created.status_code == 201, created.text
        material = created.json()
        assert material["url"] == f"/api/v1/workflows/it/materials/{material['id']}/file"
        listed = (await c.get(MATERIALS, params={"batch_id": str(w["batch_a"].id)})).json()
        row = next(item for item in listed if item["id"] == material["id"])
        assert row["file"] == {"filename": "Notes wk1.pdf", "content_type": "application/pdf", "size": len(big)}
        assert row["batch"] == w["batch_a"].name
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "learning_resource.create", AuditLog.entity_id == material["id"]))
    assert audit.metadata_json["kind"] == "file"
    async with client_for(w["student_a"].email, "it") as c:
        rows = await _downloads(c)
        assert any(r["title"] == "Week 1 notes" and r["url"] == material["url"] for r in rows)
        learning = (await c.get("/api/v1/workflows/it/student/learning")).json()
        assert any(r["title"] == "Week 1 notes" and r["url"] == material["url"] for r in learning["resources"])
        download = await c.get(material["url"])
        assert download.status_code == 200 and download.content == big
        assert download.headers["x-content-type-options"] == "nosniff"
    async with client_for(w["student_b"].email, "it") as c:
        assert all(r["title"] != "Week 1 notes" for r in await _downloads(c))
        assert (await c.get(material["url"])).status_code == 404  # AC4: batch B learner
    async with client_for(w["trainer"].email, "it") as c:
        assert (await c.get(material["url"])).status_code == 200
        section = (await c.get("/api/v1/portal/it/trainer/materials")).json()  # QA-01: the trainer's table opens the file too
        assert {"key": "url", "label": "Open", "type": "link"} in section["columns"]
        assert any(r["url"] == material["url"] and r["resource"] == "Week 1 notes" for r in section["rows"])
    async with client_for(w["admin"].email, "it") as c:
        assert (await c.get(material["url"])).status_code == 200
    async with client_for(w["other_trainer"].email, "it") as c:
        assert (await c.get(material["url"])).status_code == 404


@pytest.mark.asyncio
async def test_edit_reorder_and_soft_delete(client, db_session):
    w = await _world(db_session)
    async with client_for(w["trainer"].email, "it") as c:
        first = await _publish_file(c, w["batch_a"].id, "Slides")
        link = await c.post(MATERIALS, json={"batch_id": str(w["batch_a"].id), "title": "Recording", "resource_type": "video", "url": "https://youtu.be/abc"})
        assert link.status_code == 201
        edited = await c.patch(f"{MATERIALS}/{first['id']}", json={"title": "Week 1 slides", "sort_order": 5})
        assert edited.status_code == 200, edited.text
        assert edited.json()["title"] == "Week 1 slides" and edited.json()["sort_order"] == 5
        order = [item["title"] for item in (await c.get(MATERIALS, params={"batch_id": str(w["batch_a"].id)})).json()]
        assert order == ["Recording", "Week 1 slides"]  # sort_order ascending
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "learning_resource.update", AuditLog.entity_id == first["id"]))
    assert set(audit.metadata_json["fields"]) == {"title", "sort_order"}
    async with client_for(w["student_a"].email, "it") as c:
        assert [r["title"] for r in await _downloads(c) if r["title"] in {"Recording", "Week 1 slides"}] == ["Recording", "Week 1 slides"]
    async with client_for(w["trainer"].email, "it") as c:
        deleted = await c.delete(f"{MATERIALS}/{first['id']}")
        assert deleted.status_code == 204
        assert (await c.delete(f"{MATERIALS}/{first['id']}")).status_code == 404
        assert (await c.patch(f"{MATERIALS}/{first['id']}", json={"title": "Back"})).status_code == 404
        assert all(item["id"] != first["id"] for item in (await c.get(MATERIALS)).json())
    stored = await db_session.get(LearningResource, uuid.UUID(first["id"]))
    await db_session.refresh(stored)
    assert stored.deleted_at is not None  # soft
    async with client_for(w["student_a"].email, "it") as c:
        assert all(r["title"] != "Week 1 slides" for r in await _downloads(c))
        assert (await c.get(first["url"])).status_code == 404


@pytest.mark.asyncio
async def test_link_resource_still_works_and_rejects_unsafe_schemes(client, db_session):
    w = await _world(db_session)
    async with client_for(w["trainer"].email, "it") as c:
        created = await c.post(MATERIALS, json={"batch_id": str(w["batch_a"].id), "title": "Docs", "resource_type": "link", "url": "https://fastapi.tiangolo.com"})
        assert created.status_code == 201 and created.json()["url"] == "https://fastapi.tiangolo.com"
        bad = await c.post(MATERIALS, json={"batch_id": str(w["batch_a"].id), "title": "Bad", "resource_type": "link", "url": "javascript:alert(1)"})
        assert bad.status_code == 422
        assert (await c.patch(f"{MATERIALS}/{created.json()['id']}", json={"url": "javascript:alert(1)"})).status_code == 422
        # a link resource has no file to download
        assert (await c.get(f"/api/v1/workflows/it/materials/{created.json()['id']}/file")).status_code == 404
    async with client_for(w["student_a"].email, "it") as c:
        assert any(r["title"] == "Docs" and r["url"] == "https://fastapi.tiangolo.com" for r in await _downloads(c))


@pytest.mark.asyncio
async def test_create_needs_exactly_one_source_and_an_own_unattached_file(client, db_session):
    w = await _world(db_session)
    async with client_for(w["other_trainer"].email, "it") as c:
        foreign = await _upload(c)
    async with client_for(w["trainer"].email, "it") as c:
        base = {"batch_id": str(w["batch_a"].id), "title": "Notes", "resource_type": "document"}
        assert (await c.post(MATERIALS, json=base)).status_code == 422
        own = await _upload(c)
        assert (await c.post(MATERIALS, json={**base, "file_id": own, "url": "https://example.com"})).status_code == 422
        refused = await c.post(MATERIALS, json={**base, "file_id": foreign})
        assert refused.status_code == 422 and refused.json()["detail"] == "This file cannot be attached to a material"
        wrong_purpose = await _upload(c, purpose="assignment_submission")
        assert (await c.post(MATERIALS, json={**base, "file_id": wrong_purpose})).status_code == 422
        assert (await c.post(MATERIALS, json={**base, "file_id": own})).status_code == 201
        assert (await c.post(MATERIALS, json={**base, "file_id": own})).status_code == 422  # already attached
        video = await c.post(MATERIALS, json={**base, "resource_type": "video", "file_id": await _upload(c)})
        assert video.status_code == 422 and "link" in video.json()["detail"]
        # the policy refuses a video file and anything over 20 MB before it is stored
        mp4 = await c.post("/api/v1/files/upload", params={"purpose": "learning_material"}, files={"file": ("class.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")})
        assert mp4.status_code == 415
        huge = await c.post("/api/v1/files/upload", params={"purpose": "learning_material"}, files={"file": ("big.pdf", PDF + b"0" * (20 * 1024 * 1024), "application/pdf")})
        assert huge.status_code == 413


@pytest.mark.asyncio
async def test_manage_routes_are_scoped_to_the_batch_trainer(client, db_session):
    w = await _world(db_session)
    async with client_for(w["trainer"].email, "it") as c:
        material = await _publish_file(c, w["batch_a"].id)
        link = await c.patch(f"{MATERIALS}/{material['id']}", json={"url": "https://example.com"})
        assert link.status_code == 422  # a file resource has no url to edit
        video = await c.patch(f"{MATERIALS}/{material['id']}", json={"resource_type": "recording"})
        assert video.status_code == 422
        assert (await c.patch(f"{MATERIALS}/{material['id']}", json={})).status_code == 422
    async with client_for(w["other_trainer"].email, "it") as c:
        assert (await c.patch(f"{MATERIALS}/{material['id']}", json={"title": "Mine now"})).status_code == 403
        assert (await c.delete(f"{MATERIALS}/{material['id']}")).status_code == 403
        assert all(item["id"] != material["id"] for item in (await c.get(MATERIALS)).json())
        assert (await c.get(MATERIALS, params={"batch_id": str(w["batch_a"].id)})).json() == []
    async with client_for(w["student_a"].email, "it") as c:
        assert (await c.get(MATERIALS)).status_code == 403
        assert (await c.patch(f"{MATERIALS}/{material['id']}", json={"title": "x1"})).status_code == 403
    async with client_for(w["admin"].email, "it") as c:
        assert any(item["id"] == material["id"] for item in (await c.get(MATERIALS)).json())
        assert (await c.patch(f"{MATERIALS}/{material['id']}", json={"title": "Admin fixed"})).status_code == 200
    async with client_for(w["trainer"].email, "it") as c:
        assert (await c.patch(f"{MATERIALS}/{uuid.uuid4()}", json={"title": "Nope"})).status_code == 404
    # a trainer moved off the batch loses access at once
    w["batch_a"].trainer_id = w["other_trainer"].id
    await db_session.commit()
    async with client_for(w["trainer"].email, "it") as c:
        assert (await c.get(material["url"])).status_code == 404
        assert (await c.delete(f"{MATERIALS}/{material['id']}")).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_refused(client):
    rid = uuid.uuid4()
    assert (await client.get(MATERIALS)).status_code == 401
    assert (await client.patch(f"{MATERIALS}/{rid}", json={"title": "x1"})).status_code == 401
    assert (await client.delete(f"{MATERIALS}/{rid}")).status_code == 401
    assert (await client.get(f"/api/v1/workflows/it/materials/{rid}/file")).status_code == 401
