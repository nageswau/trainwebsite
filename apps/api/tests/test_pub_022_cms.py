"""PUB-022 -- CMS management of testimonials and the site rating badge (DEC-SCOPE-210 SP2/SP5/SP6/SP9; spec §4.2).

The test DB is shared and never truncated: every test creates its own rows and asserts on their ids only."""

import struct
import uuid
import zlib

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import AuditLog, SiteRatingBadge, Testimonial, User
from app.services.storage import storage

PASSWORD = "Sup3r-Secret-Pass!"
ROLE_DIVISION = {"super_admin": "global", "it_admin": "it", "overseas_admin": "overseas", "it_student": "it", "counselor": "overseas"}


def png_bytes(text_chunk: bytes = b"") -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    extra = chunk(b"tEXt", text_chunk) if text_chunk else b""
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + extra + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b"")


JPEG = (
    b"\xff\xd8"
    + b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    + b"\xff\xe1\x00\x12Exif\x00\x00GPS-SECRET"
    + b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x12\x34"
    + b"\xff\xd9"
)


async def make_user(db_session, role: str) -> User:
    user = User(
        email=f"pub022-{role}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password(PASSWORD),
        full_name=f"PUB-022 {role}",
        role=role,
        division=ROLE_DIVISION[role],
        active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def login(client, user: User) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD, "division": user.division})
    assert response.status_code == 200, response.text


async def as_role(client, db_session, role: str) -> User:
    user = await make_user(db_session, role)
    await login(client, user)
    return user


def body(division: str = "it", **overrides) -> dict:
    data = {"division": division, "person_name": f"Person {uuid.uuid4().hex[:6]}", "headline": "Great support", "quote": "They helped me all the way.", "rating": 5}
    data.update(overrides)
    return data


async def create(client, **overrides) -> dict:
    response = await client.post("/api/v1/cms/testimonials", json=body(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


# --- permissions (SP2, SP5) ---


@pytest.mark.asyncio
async def test_super_admin_manages_both_divisions(client, db_session):
    await as_role(client, db_session, "super_admin")
    it = await create(client, division="it")
    ovs = await create(client, division="overseas")
    listed = {row["id"] for row in (await client.get("/api/v1/cms/manage/testimonials")).json()}
    assert {it["id"], ovs["id"]} <= listed
    assert (await client.patch(f"/api/v1/cms/testimonials/{ovs['id']}", json={"headline": "Edited"})).json()["headline"] == "Edited"


@pytest.mark.asyncio
async def test_division_admin_is_limited_to_their_division(client, db_session):
    await as_role(client, db_session, "super_admin")
    ovs = await create(client, division="overseas")
    await as_role(client, db_session, "it_admin")
    mine = await create(client, division="it")
    listed = (await client.get("/api/v1/cms/manage/testimonials?division=overseas")).json()
    assert all(row["division"] == "it" for row in listed) and mine["id"] in {row["id"] for row in listed}
    assert (await client.post("/api/v1/cms/testimonials", json=body("overseas"))).status_code == 403


@pytest.mark.asyncio
async def test_other_division_is_404(client, db_session):
    await as_role(client, db_session, "super_admin")
    ovs = await create(client, division="overseas")
    await as_role(client, db_session, "it_admin")
    tid = ovs["id"]
    assert (await client.patch(f"/api/v1/cms/testimonials/{tid}", json={"headline": "x"})).status_code == 404
    assert (await client.delete(f"/api/v1/cms/testimonials/{tid}")).status_code == 404
    assert (await client.put(f"/api/v1/cms/testimonials/{tid}/photo", files={"file": ("a.png", png_bytes(), "image/png")})).status_code == 404
    assert (await client.delete(f"/api/v1/cms/testimonials/{tid}/photo")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["it_student", "counselor"])
async def test_non_editors_are_403(client, db_session, role):
    await as_role(client, db_session, role)
    assert (await client.get("/api/v1/cms/manage/testimonials")).status_code == 403
    assert (await client.post("/api/v1/cms/testimonials", json=body())).status_code == 403
    assert (await client.patch(f"/api/v1/cms/testimonials/{uuid.uuid4()}", json={"headline": "x"})).status_code == 403
    assert (await client.get("/api/v1/cms/rating-badge")).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["it_admin", "overseas_admin"])
async def test_badge_is_super_admin_only(client, db_session, role):
    await as_role(client, db_session, role)
    assert (await client.get("/api/v1/cms/rating-badge")).status_code == 403
    payload = {"source_name": "Google", "rating": 4.8, "review_count": 10, "as_of": "2026-10-01"}
    assert (await client.put("/api/v1/cms/rating-badge", json=payload)).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_401(client):
    assert (await client.get("/api/v1/cms/manage/testimonials")).status_code == 401
    assert (await client.post("/api/v1/cms/testimonials", json=body())).status_code == 401


# --- consent (SP6, SP9) ---


@pytest.mark.asyncio
async def test_publish_without_consent_is_422(client, db_session):
    await as_role(client, db_session, "it_admin")
    response = await client.post("/api/v1/cms/testimonials", json=body(published=True))
    assert response.status_code == 422 and response.json()["detail"] == "Record consent before publishing"
    created = await create(client)
    assert (await client.patch(f"/api/v1/cms/testimonials/{created['id']}", json={"published": True})).status_code == 422


@pytest.mark.asyncio
async def test_consent_is_recorded_by_the_server_and_unticking_unpublishes(client, db_session):
    admin = await as_role(client, db_session, "it_admin")
    created = await create(client, consent_confirmed=True, published=True)
    assert created["published"] and created["consent_confirmed"] and created["consent_at"]
    row = await db_session.get(Testimonial, uuid.UUID(created["id"]))
    await db_session.refresh(row)
    assert row.consent_by_user_id == admin.id
    updated = (await client.patch(f"/api/v1/cms/testimonials/{created['id']}", json={"consent_confirmed": False})).json()
    assert updated["consent_confirmed"] is False and updated["published"] is False and updated["consent_at"] is None


@pytest.mark.asyncio
async def test_consent_fields_cannot_be_sent(client, db_session):
    await as_role(client, db_session, "it_admin")
    for extra in ({"consent_at": "2020-01-01T00:00:00Z"}, {"consent_by_user_id": str(uuid.uuid4())}, {"photo_key": "x"}):
        assert (await client.post("/api/v1/cms/testimonials", json=body(**extra))).status_code == 422


@pytest.mark.asyncio
async def test_consent_timestamp_is_stable(client, db_session):
    await as_role(client, db_session, "it_admin")
    created = await create(client, consent_confirmed=True)
    again = (await client.patch(f"/api/v1/cms/testimonials/{created['id']}", json={"consent_confirmed": True, "published": True})).json()
    assert again["consent_at"] == created["consent_at"] and again["published"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [{"rating": 0}, {"rating": 6}, {"rating": "5"}, {"person_name": "   "}, {"quote": ""}, {"division": "school"}, {"headline": "x" * 201}, {"quote": "bad‮text"}],
)
async def test_create_validation(client, db_session, bad):
    await as_role(client, db_session, "super_admin")
    assert (await client.post("/api/v1/cms/testimonials", json=body(**bad))).status_code == 422


@pytest.mark.asyncio
async def test_patch_rejects_division_and_null_required_fields(client, db_session):
    await as_role(client, db_session, "super_admin")
    created = await create(client, context="MSc Data Science")
    tid = created["id"]
    assert (await client.patch(f"/api/v1/cms/testimonials/{tid}", json={"division": "overseas"})).status_code == 422
    assert (await client.patch(f"/api/v1/cms/testimonials/{tid}", json={"person_name": None})).status_code == 422
    cleared = (await client.patch(f"/api/v1/cms/testimonials/{tid}", json={"context": None})).json()
    assert cleared["context"] is None


# --- photo + delete ---


@pytest.mark.asyncio
async def test_photo_upload_png_and_jpeg_strips_metadata(client, db_session):
    await as_role(client, db_session, "it_admin")
    created = await create(client)
    tid = created["id"]
    up = await client.put(f"/api/v1/cms/testimonials/{tid}/photo", files={"file": ("me.png", png_bytes(b"Comment\x00secret"), "image/png")})
    assert up.status_code == 200 and up.json()["has_photo"] is True and "photo_key" not in up.json()
    row = await db_session.get(Testimonial, uuid.UUID(tid))
    await db_session.refresh(row)
    first_key = row.photo_key
    assert b"secret" not in storage.read_bytes(first_key) and row.photo_content_type == "image/png"
    up = await client.put(f"/api/v1/cms/testimonials/{tid}/photo", files={"file": ("me.jpg", JPEG, "image/jpeg")})
    assert up.status_code == 200
    await db_session.refresh(row)
    assert row.photo_content_type == "image/jpeg" and b"GPS-SECRET" not in storage.read_bytes(row.photo_key)
    with pytest.raises(Exception):
        storage.read_bytes(first_key)  # the replaced photo is gone
    removed = await client.delete(f"/api/v1/cms/testimonials/{tid}/photo")
    assert removed.status_code == 200 and removed.json()["has_photo"] is False


@pytest.mark.asyncio
async def test_photo_rejects_wrong_type_and_oversize(client, db_session):
    await as_role(client, db_session, "it_admin")
    tid = (await create(client))["id"]
    fake = await client.put(f"/api/v1/cms/testimonials/{tid}/photo", files={"file": ("fake.png", b"GIF89a not a png", "image/png")})
    assert fake.status_code == 415
    big = png_bytes() + b"\x00" * (2 * 1024 * 1024)
    assert (await client.put(f"/api/v1/cms/testimonials/{tid}/photo", files={"file": ("big.png", big, "image/png")})).status_code == 413
    assert (await client.put(f"/api/v1/cms/testimonials/{tid}/photo", files={"file": ("e.png", b"", "image/png")})).status_code == 422


@pytest.mark.asyncio
async def test_delete_removes_row_photo_and_keeps_no_personal_data_in_audit(client, db_session):
    await as_role(client, db_session, "it_admin")
    created = await create(client, person_name="Private Person", quote="Private words here")
    tid = created["id"]
    await client.put(f"/api/v1/cms/testimonials/{tid}/photo", files={"file": ("me.png", png_bytes(), "image/png")})
    row = await db_session.get(Testimonial, uuid.UUID(tid))
    await db_session.refresh(row)
    key = row.photo_key
    db_session.expunge(row)
    assert (await client.delete(f"/api/v1/cms/testimonials/{tid}")).status_code == 204
    assert await db_session.get(Testimonial, uuid.UUID(tid)) is None
    with pytest.raises(Exception):
        storage.read_bytes(key)
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_type == "testimonial", AuditLog.entity_id == tid))).all()
    assert {a.action for a in audits} >= {"cms.testimonial.create", "cms.testimonial.delete"}
    for a in audits:
        assert "Private" not in repr(a.metadata_json)


@pytest.mark.asyncio
async def test_delete_with_missing_photo_file(client, db_session):
    await as_role(client, db_session, "it_admin")
    tid = (await create(client))["id"]
    await client.put(f"/api/v1/cms/testimonials/{tid}/photo", files={"file": ("me.png", png_bytes(), "image/png")})
    row = await db_session.get(Testimonial, uuid.UUID(tid))
    await db_session.refresh(row)
    storage.delete(row.photo_key)
    db_session.expunge(row)
    assert (await client.delete(f"/api/v1/cms/testimonials/{tid}")).status_code == 204


# --- badge (SP5) ---


@pytest.mark.asyncio
async def test_super_admin_puts_the_badge(client, db_session):
    await as_role(client, db_session, "super_admin")
    payload = {"source_name": "Google", "rating": 4.8, "review_count": 1234, "review_url": "https://g.page/r/example", "as_of": "2026-10-01", "published": False}
    saved = await client.put("/api/v1/cms/rating-badge", json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["rating"] == 4.8 and saved.json()["published"] is False
    assert (await client.get("/api/v1/cms/rating-badge")).json()["review_count"] == 1234
    badge = await db_session.get(SiteRatingBadge, 1)
    assert badge is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [{"rating": 5.5}, {"rating": -0.1}, {"rating": 4.85}, {"review_count": -1}, {"review_url": "http://insecure.example"}, {"review_url": "javascript:alert(1)"}, {"source_name": " "}],
)
async def test_badge_validation(client, db_session, bad):
    await as_role(client, db_session, "super_admin")
    payload = {"source_name": "Google", "rating": 4.8, "review_count": 10, "as_of": "2026-10-01", **bad}
    assert (await client.put("/api/v1/cms/rating-badge", json=payload)).status_code == 422
