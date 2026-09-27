"""ENH-021 -- internship certificate (spec §5.2, I5, S5/S6/S13, AC21-1/3/8)."""
import asyncio
from contextlib import asynccontextmanager
from datetime import date

import httpx
import pytest
import pytest_asyncio
from enh005_helpers import login, mk_school
from enh025_helpers import jpeg_bytes, png_bytes
from httpx import ASGITransport
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.main import app
from app.models import AuditLog, PortfolioEntry
from app.services.storage import storage

ENTRIES = "/api/v1/school/students/{sid}/portfolio/entries"
PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


@pytest.fixture(autouse=True)
def _local_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "bucket", "")
    monkeypatch.setattr(storage, "local_dir", tmp_path)
    return tmp_path


@pytest_asyncio.fixture
async def world(db_session, client):
    ctx = await mk_school(db_session, label="E21-Cert", students=2)
    await login(client, ctx["coordinator"].email)
    body = {"section": "internship", "title": "Intern", "organization": "Acme", "date_from": "2026-05-01", "date_to": "2026-06-01", "completion_status": "completed"}
    ctx["entry"] = (await client.post(ENTRIES.format(sid=ctx["students"][0].id), json=body)).json()
    ctx["url"] = f"{ENTRIES.format(sid=ctx['students'][0].id)}/{ctx['entry']['id']}/certificate"
    return ctx


async def _put(client, url, data, name="c.pdf", ctype="application/pdf"):
    return await client.put(url, files={"file": (name, data, ctype)})


def _objects(root):
    return [p for p in root.rglob("*") if p.is_file()]


def _downloads(entry_id):
    return select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.internship_certificate_download", AuditLog.entity_id == str(entry_id))


@pytest.mark.asyncio
async def test_pdf_upload_and_download_by_every_reader(client, world, db_session):
    r = await _put(client, world["url"], PDF)
    assert r.status_code == 200 and r.json() == {"has_certificate": True, "content_type": "application/pdf"}
    for role in ("coordinator", "principal", "teacher", "parent"):
        await login(client, world[role].email)
        got = await client.get(world["url"])
        assert got.status_code == 200, role
        assert got.content == PDF
        assert got.headers["content-disposition"] == 'attachment; filename="internship-certificate.pdf"'
        assert got.headers["x-content-type-options"] == "nosniff"
        assert got.headers["content-security-policy"] == "default-src 'none'; sandbox"
        assert got.headers["cache-control"] == "private, no-store"
    assert await db_session.scalar(_downloads(world["entry"]["id"])) == 4  # AC21-8


@pytest.mark.asyncio
async def test_images_have_metadata_stripped(client, world):
    assert (await _put(client, world["url"], jpeg_bytes(with_gps=True), "c.jpg", "image/jpeg")).status_code == 200
    got = await client.get(world["url"])
    assert b"GPSLatitude" not in got.content and got.headers["content-disposition"].endswith('.jpg"')


@pytest.mark.asyncio
async def test_type_is_decided_by_content_not_by_name(client, world):
    r = await _put(client, world["url"], b"<html><script>alert(1)</script></html>", "c.pdf", "application/pdf")
    assert (r.status_code, r.json()["detail"]) == (415, "certificate must be a PDF, JPEG or PNG file")


@pytest.mark.asyncio
async def test_size_and_empty_limits(client, world):
    assert (await _put(client, world["url"], b"")).status_code == 422
    big = PDF + b"0" * (5 * 1024 * 1024)
    r = await _put(client, world["url"], big)
    assert (r.status_code, r.json()["detail"]) == (413, "certificate must be at most 5 MB")


@pytest.mark.asyncio
async def test_only_completed_internships_take_a_certificate(client, world, db_session):
    row = await db_session.get(PortfolioEntry, world["entry"]["id"])
    row.completion_status = "in_progress"
    await db_session.commit()
    r = await _put(client, world["url"], PDF)
    assert (r.status_code, r.json()["detail"]) == (422, "A certificate can only be attached to a completed internship")


@pytest.mark.asyncio
async def test_replace_and_remove_delete_the_old_object(client, world, _local_storage):
    await _put(client, world["url"], PDF)
    await _put(client, world["url"], png_bytes(), "c.png", "image/png")
    assert len(_objects(_local_storage)) == 1
    assert (await client.delete(world["url"])).status_code == 204
    assert _objects(_local_storage) == []
    assert (await client.get(world["url"])).status_code == 404
    assert (await client.delete(world["url"])).status_code == 204  # idempotent


@pytest.mark.asyncio
async def test_deleting_the_entry_deletes_its_certificate(client, world, _local_storage):
    await _put(client, world["url"], PDF)
    entry_url = world["url"].removesuffix("/certificate")
    assert (await client.delete(entry_url)).status_code == 204
    assert _objects(_local_storage) == []


@pytest.mark.asyncio
async def test_failed_commit_leaves_no_new_object(client, world, _local_storage, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    async def failing(self):
        raise RuntimeError("db down")
    monkeypatch.setattr(AsyncSession, "commit", failing)
    with pytest.raises(RuntimeError):
        await _put(client, world["url"], PDF)
    monkeypatch.undo()
    assert _objects(_local_storage) == []


@pytest.mark.asyncio
async def test_authorization(client, world, db_session):
    await _put(client, world["url"], PDF)
    await login(client, world["parent"].email)
    assert (await _put(client, world["url"], PDF)).status_code == 403  # readers cannot write
    other = await mk_school(db_session, label="E21-CertO")
    await login(client, other["coordinator"].email)
    assert (await client.get(world["url"])).status_code == 403
    await login(client, world["coordinator"].email)
    project = (await client.post(ENTRIES.format(sid=world["students"][0].id), json={"section": "project", "title": "P"})).json()
    project_url = f"{ENTRIES.format(sid=world['students'][0].id)}/{project['id']}/certificate"
    assert (await _put(client, project_url, PDF)).status_code == 404


@pytest.mark.asyncio
async def test_denied_download_writes_no_audit(client, world, db_session):
    await _put(client, world["url"], PDF)
    other = await mk_school(db_session, label="E21-CertD")
    await login(client, other["coordinator"].email)
    await client.get(world["url"])
    assert await db_session.scalar(_downloads(world["entry"]["id"])) == 0


@pytest.mark.asyncio
async def test_gold_school_cannot_manage_certificates(client, db_session):
    gold = await mk_school(db_session, label="E21-CertG", tier="gold")
    c = gold["coordinator"]
    entry = PortfolioEntry(school_student_id=gold["students"][0].id, section="internship", title="Old", organization="Acme",
                           completion_status="completed", date_to=date(2026, 6, 1), created_by_user_id=c.id, updated_by_user_id=c.id)
    db_session.add(entry)
    await db_session.commit()
    await login(client, c.email)
    r = await _put(client, f"{ENTRIES.format(sid=gold['students'][0].id)}/{entry.id}/certificate", PDF)
    assert r.status_code == 403


@asynccontextmanager
async def _client_for(email):
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await login(c, email)
        yield c


@asynccontextmanager
async def _held(pk):
    """Another transaction holding the entry's row lock until the block ends, so both uploads queue behind it."""
    session = SessionLocal()
    try:
        await session.execute(select(PortfolioEntry).where(PortfolioEntry.id == pk).with_for_update())
        yield
    finally:
        await session.rollback()
        await session.close()


@pytest.mark.asyncio
async def test_concurrent_uploads_leave_exactly_one_object(world, _local_storage, db_session):
    async with _client_for(world["coordinator"].email) as a, _client_for(world["coordinator"].email) as b:
        async with _held(world["entry"]["id"]):
            t1 = asyncio.create_task(_put(a, world["url"], PDF))
            t2 = asyncio.create_task(_put(b, world["url"], png_bytes(), "c.png", "image/png"))
            await asyncio.sleep(0.3)
        assert {(await t1).status_code, (await t2).status_code} == {200}
    row = await db_session.get(PortfolioEntry, world["entry"]["id"], populate_existing=True)
    objects = _objects(_local_storage)
    assert len(objects) == 1 and objects[0].as_posix().endswith(row.certificate_key)
