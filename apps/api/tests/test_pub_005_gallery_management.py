"""PUB-005 -- News and gallery (CMS-managed).

News (`BlogPost`) already had full admin CRUD (`GET/POST /cms/posts`,
`GET /cms/manage/posts`, `PATCH /cms/posts/{id}`) and a working public read with an
honest empty state -- no gap there. The real, confirmed gap: `GalleryItem` had zero
write/manage endpoints anywhere in the codebase -- only the public read
(`GET /public/gallery`) and seed-time direct DB inserts existed. An Admin could not
publish a gallery item at all, violating `PUB-005-AC01`'s "Admin publishes via CMS" half.
Added `GET /cms/manage/gallery`, `POST /cms/gallery`, `PATCH /cms/gallery/{id}`,
mirroring the exact `posts` pattern (`require_editor` scoping, same audit-log shape). No
schema change needed -- every field the endpoints use already existed on the model.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import AuditLog, GalleryItem, User


async def _create_admin(db_session, *, division: str) -> User:
    admin = User(
        email=f"pub005-admin-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Test Admin",
        role="it_admin" if division == "it" else "overseas_admin",
        division=division,
        active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    return admin


async def _create_super_admin(db_session) -> User:
    admin = User(
        email=f"pub005-super-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Test Super Admin",
        role="super_admin",
        division="global",
        active=True,
    )
    db_session.add(admin)
    await db_session.commit()
    return admin


async def _login(client, email: str, division: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": division})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_creates_a_gallery_item_in_their_own_division(db_session, client):
    admin = await _create_admin(db_session, division="it")
    await _login(client, admin.email, "it")

    response = await client.post("/api/v1/cms/gallery", json={"division": "it", "title": "Placement Day", "image_url": "https://example.local/placement-day.jpg", "alt_text": "Students at placement day", "category": "Placement"})
    assert response.status_code == 201
    item_id = uuid.UUID(response.json()["id"])

    item = await db_session.get(GalleryItem, item_id)
    assert item.division == "it"
    assert item.published is True
    log = await db_session.scalar(select(AuditLog).where(AuditLog.action == "cms.gallery.create", AuditLog.entity_id == str(item_id)))
    assert log is not None


@pytest.mark.asyncio
async def test_admin_cannot_create_a_gallery_item_in_another_division(db_session, client):
    admin = await _create_admin(db_session, division="it")
    await _login(client, admin.email, "it")

    response = await client.post("/api/v1/cms/gallery", json={"division": "overseas", "title": "Study Abroad Fair", "image_url": "https://example.local/fair.jpg"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_creates_a_gallery_item_in_any_division(db_session, client):
    admin = await _create_super_admin(db_session)
    await _login(client, admin.email, "global")

    response = await client.post("/api/v1/cms/gallery", json={"division": "overseas", "title": "Counseling Session", "image_url": "https://example.local/counseling.jpg"})
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_admin_updates_a_gallery_item_toggling_published(db_session, client):
    admin = await _create_admin(db_session, division="it")
    item = GalleryItem(division="it", title="Draft Photo", image_url="https://example.local/draft.jpg", alt_text="Draft photo", category="General", published=False)
    db_session.add(item)
    await db_session.commit()

    await _login(client, admin.email, "it")
    response = await client.patch(f"/api/v1/cms/gallery/{item.id}", json={"published": True})
    assert response.status_code == 200

    await db_session.refresh(item)
    assert item.published is True


@pytest.mark.asyncio
async def test_updating_an_unknown_gallery_item_404s(db_session, client):
    admin = await _create_admin(db_session, division="it")
    await _login(client, admin.email, "it")
    response = await client.patch(f"/api/v1/cms/gallery/{uuid.uuid4()}", json={"published": False})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_non_admin_role_cannot_create_a_gallery_item(db_session, client):
    student = User(
        email=f"pub005-student-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Test Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.commit()

    await _login(client, student.email, "it")
    response = await client.post("/api/v1/cms/gallery", json={"division": "it", "title": "Unauthorized", "image_url": "https://example.local/x.jpg"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_creating_a_gallery_item_requires_authentication(client):
    response = await client.post("/api/v1/cms/gallery", json={"division": "it", "title": "Anon", "image_url": "https://example.local/x.jpg"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_manage_gallery_lists_unpublished_items_the_public_endpoint_hides(db_session, client):
    admin = await _create_admin(db_session, division="it")
    item = GalleryItem(division="it", title="Unpublished Draft", image_url="https://example.local/unpublished.jpg", alt_text="Draft", category="General", published=False)
    db_session.add(item)
    await db_session.commit()

    await _login(client, admin.email, "it")
    manage = await client.get("/api/v1/cms/manage/gallery")
    assert manage.status_code == 200
    assert any(row["id"] == str(item.id) for row in manage.json())

    public = await client.get("/api/v1/public/gallery")
    assert public.status_code == 200
    assert not any(row.get("id") == str(item.id) for row in public.json())


@pytest.mark.asyncio
async def test_manage_gallery_requires_admin_role(db_session, client):
    student = User(
        email=f"pub005-student2-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name="Test Student",
        role="it_student",
        division="it",
        active=True,
    )
    db_session.add(student)
    await db_session.commit()

    await _login(client, student.email, "it")
    response = await client.get("/api/v1/cms/manage/gallery")
    assert response.status_code == 403
