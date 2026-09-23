"""ENH-025 -- authorized photo upload/stream/delete (spec §3.4, §5, AC8, AC12)."""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AuditLog, SchoolStudent
from app.services.storage import storage
from enh005_helpers import login, mk_school, mk_staff
from enh025_helpers import jpeg_bytes, png_bytes

PHOTO = "/api/v1/school/students/{sid}/photo"


@pytest.fixture(autouse=True)
def _local_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "bucket", "")
    monkeypatch.setattr(storage, "local_dir", tmp_path)


@pytest_asyncio.fixture
async def world(db_session):
    return await mk_school(db_session, label="P", students=2)


async def _put(client, sid, data, name="p.jpg", ctype="image/jpeg"):
    return await client.put(PHOTO.format(sid=sid), files={"file": (name, data, ctype)})


async def _key(db_session, sid):
    return (await db_session.get(SchoolStudent, sid, populate_existing=True)).photo_key


@pytest.mark.asyncio
async def test_upload_strips_metadata_and_readers_in_scope_get_it(client, world):
    sid = world["students"][0].id
    await login(client, world["coordinator"].email)
    r = await _put(client, sid, jpeg_bytes(with_gps=True))
    assert r.status_code == 200 and r.json() == {"has_photo": True}
    assert (await client.get(f"/api/v1/school/students/{sid}")).json()["has_photo"] is True
    for role in ("coordinator", "principal", "teacher", "parent"):
        await login(client, world[role].email)
        got = await client.get(PHOTO.format(sid=sid))
        assert got.status_code == 200, role
        assert got.headers["content-type"] == "image/jpeg"
        assert got.headers["cache-control"] == "private, no-store"
        assert got.headers["x-content-type-options"] == "nosniff"
        assert got.headers["content-security-policy"] == "default-src 'none'; sandbox"
        assert b"GPSLatitude" not in got.content and got.content == jpeg_bytes(with_gps=False)


@pytest.mark.asyncio
async def test_out_of_scope_readers_are_refused(client, world, db_session):
    sid = world["students"][1].id  # not assigned to the teacher, not linked to the parent
    await login(client, world["coordinator"].email)
    await _put(client, sid, png_bytes(), "p.png", "image/png")
    for role in ("teacher", "parent"):
        await login(client, world[role].email)
        assert (await client.get(PHOTO.format(sid=sid))).status_code == 403, role
    other = await mk_school(db_session, label="PO", students=0)
    await login(client, other["coordinator"].email)
    assert (await client.get(PHOTO.format(sid=sid))).status_code == 403
    counselor = await mk_staff(db_session, world["school"], world["admin"], role="career_counselor")
    await login(client, counselor.email)
    assert (await client.get(PHOTO.format(sid=sid))).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("data", "name", "ctype", "status"),
    [
        (b"<svg xmlns='http://www.w3.org/2000/svg'/>", "x.svg", "image/svg+xml", 415),
        (b"<html><script>alert(1)</script></html>", "x.jpg", "image/jpeg", 415),
        (b"", "x.jpg", "image/jpeg", 422),
        (b"\xff\xd8\xff" + b"\x00" * (2 * 1024 * 1024), "big.jpg", "image/jpeg", 413),
        (b"\xff\xd8\xff\xe0\x00", "trunc.jpg", "image/jpeg", 422),
    ],
)
async def test_bad_uploads_are_rejected(client, world, data, name, ctype, status):
    await login(client, world["coordinator"].email)
    r = await _put(client, world["students"][0].id, data, name, ctype)
    assert r.status_code == status, r.text


@pytest.mark.asyncio
async def test_png_sent_with_jpeg_content_type_is_stored_as_png(client, world):
    sid = world["students"][0].id
    await login(client, world["coordinator"].email)
    assert (await _put(client, sid, png_bytes(), "p.jpg", "image/jpeg")).status_code == 200
    assert (await client.get(PHOTO.format(sid=sid))).headers["content-type"] == "image/png"


@pytest.mark.asyncio
async def test_only_own_school_coordinator_can_write(client, world, db_session):
    sid = world["students"][0].id
    for role in ("principal", "teacher", "parent"):
        await login(client, world[role].email)
        assert (await _put(client, sid, jpeg_bytes())).status_code == 403, role
        assert (await client.delete(PHOTO.format(sid=sid))).status_code == 403, role
    other = await mk_school(db_session, label="PW", students=0)
    await login(client, other["coordinator"].email)
    assert (await _put(client, sid, jpeg_bytes())).status_code == 403
    assert (await client.delete(PHOTO.format(sid=sid))).status_code == 403


@pytest.mark.asyncio
async def test_replace_deletes_the_old_object_and_delete_is_idempotent(client, world, db_session, tmp_path):
    sid = world["students"][0].id
    await login(client, world["coordinator"].email)
    await _put(client, sid, jpeg_bytes())
    first_key = await _key(db_session, sid)
    await _put(client, sid, png_bytes(), "p.png", "image/png")
    second_key = await _key(db_session, sid)
    assert first_key != second_key
    assert not (tmp_path / first_key).exists() and (tmp_path / second_key).exists()
    assert (await client.delete(PHOTO.format(sid=sid))).status_code == 204
    assert (await client.delete(PHOTO.format(sid=sid))).status_code == 204
    assert not (tmp_path / second_key).exists()
    assert (await client.get(PHOTO.format(sid=sid))).status_code == 404
    assert (await client.get(f"/api/v1/school/students/{sid}")).json()["has_photo"] is False


@pytest.mark.asyncio
async def test_replacing_when_the_old_file_is_already_gone_still_succeeds(client, world, db_session, tmp_path):
    sid = world["students"][0].id
    await login(client, world["coordinator"].email)
    await _put(client, sid, jpeg_bytes())
    (tmp_path / await _key(db_session, sid)).unlink()
    assert (await _put(client, sid, jpeg_bytes())).status_code == 200


@pytest.mark.asyncio
async def test_missing_object_on_read_is_404_not_500(client, world, db_session, tmp_path):
    sid = world["students"][0].id
    await login(client, world["coordinator"].email)
    await _put(client, sid, jpeg_bytes())
    (tmp_path / await _key(db_session, sid)).unlink()
    assert (await client.get(PHOTO.format(sid=sid))).status_code == 404


@pytest.mark.asyncio
async def test_key_never_leaks_into_responses_or_audit(client, world, db_session):
    sid = world["students"][0].id
    await login(client, world["coordinator"].email)
    await _put(client, sid, jpeg_bytes())
    key = await _key(db_session, sid)
    for url in (f"/api/v1/school/students/{sid}", "/api/v1/school/students", f"/api/v1/school/students/{sid}/overview"):
        assert key not in (await client.get(url)).text
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(sid), AuditLog.action.like("school.student_photo_%")))).all()
    assert rows and all(key not in str(r.metadata_json) for r in rows)


@pytest.mark.asyncio
async def test_commit_failure_removes_the_new_object(client, world, tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession

    sid = world["students"][0].id
    await login(client, world["coordinator"].email)

    async def boom(self):
        raise RuntimeError("commit failed")

    monkeypatch.setattr(AsyncSession, "commit", boom)
    with pytest.raises(RuntimeError):
        await _put(client, sid, jpeg_bytes())
    assert list((tmp_path / "school-student-photos").glob("*")) == []
