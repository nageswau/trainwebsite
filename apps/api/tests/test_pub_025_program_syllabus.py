"""PUB-025 (DEC-SCOPE-334): IT course card image (S3) and one syllabus source per course -- manual modules, a link or a PDF (S1) -- public
with no enquiry gate (S2)."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.models import AuditLog, Program
from app.services import program_media
from app.services.storage import storage
from tests.test_nehn_035_university_logos import jpeg, png, webp
from tests.upc001_helpers import as_role

ADMIN = "/api/v1/admin/programs"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
MODULES = [{"title": "Module 1: Python Basics", "topics": ["Variables", "  ", "Loops"]}, {"title": "Module 2: Django", "topics": []}]


@pytest_asyncio.fixture
async def program(db_session):
    tag = uuid.uuid4().hex[:10]
    item = Program(
        slug=f"pub025-{tag}", category="Software Development", title=f"Pub025 Course {tag}", summary="s", duration="12 weeks",
        eligibility="e", fees=1000, certification="c", curriculum=["Old topic"], placement_assistance="p", trainer_name="t", active=True,
    )
    db_session.add(item)
    await db_session.commit()
    program_id = item.id  # captured: a test may roll the session back, expiring `item`
    yield item
    await db_session.rollback()
    await db_session.execute(delete(Program).where(Program.id == program_id))
    await db_session.commit()


async def _admin(client, db, role="it_admin", division="it"):
    return await as_role(client, db, role, division)


async def _public(client, slug):
    return (await client.get(f"/api/v1/public/programs/{slug}")).json()


def _stored(url: str) -> bool:
    try:
        storage.read_bytes(f"{program_media.PREFIX}/{program_media.file_name(url)}")
        return True
    except Exception:
        return False


# --- defaults ---


@pytest.mark.asyncio
async def test_a_course_starts_with_no_image_and_no_syllabus(client, program):
    body = await _public(client, program.slug)
    assert body["image_url"] is None and body["syllabus"] is None
    assert body["curriculum"] == ["Old topic"]  # the page falls back to it
    listed = next(p for p in (await client.get("/api/v1/public/programs")).json() if p["slug"] == program.slug)
    assert listed["syllabus"] is None and listed["image_url"] is None


# --- S1 manual ---


@pytest.mark.asyncio
async def test_manual_modules_are_saved_cleaned_and_public(client, db_session, program):
    await _admin(client, db_session)
    response = await client.put(f"{ADMIN}/{program.id}/syllabus", json={"source": "manual", "modules": MODULES})
    assert response.status_code == 200, response.text
    expected = [{"title": "Module 1: Python Basics", "topics": ["Variables", "Loops"]}, {"title": "Module 2: Django", "topics": []}]
    assert response.json()["syllabus"] == {"source": "manual", "modules": expected}
    client.cookies.clear()
    assert (await _public(client, program.slug))["syllabus"] == {"source": "manual", "modules": expected}
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(program.id), AuditLog.action == "program.syllabus"))
    assert audit is not None and audit.metadata_json["modules"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("modules", [None, [], [{"title": "  ", "topics": []}], [{"title": "x", "topics": "not a list"}], ["x"],
                                     [{"title": "x" * 161}], [{"title": "m", "topics": ["t"] * 41}], [{"title": f"m{i}"} for i in range(41)]])
async def test_invalid_modules_are_422(client, db_session, program, modules):
    await _admin(client, db_session)
    response = await client.put(f"{ADMIN}/{program.id}/syllabus", json={"source": "manual", "modules": modules})
    assert response.status_code == 422


# --- S1 link ---


@pytest.mark.asyncio
async def test_a_drive_link_is_saved_and_public(client, db_session, program):
    await _admin(client, db_session)
    url = "https://drive.google.com/file/d/1AbC/view?usp=sharing"
    response = await client.put(f"{ADMIN}/{program.id}/syllabus", json={"source": "link", "url": f"  {url} "})
    assert response.status_code == 200, response.text
    assert (await _public(client, program.slug))["syllabus"] == {"source": "link", "url": url}


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [None, "", "http://drive.google.com/x", "javascript:alert(1)", "drive.google.com/x", "https://", "https://a b.com/x",
                                 "https://drive.google.com/" + "x" * 500])
async def test_bad_links_are_422(client, db_session, program, url):
    await _admin(client, db_session)
    assert (await client.put(f"{ADMIN}/{program.id}/syllabus", json={"source": "link", "url": url})).status_code == 422


@pytest.mark.asyncio
async def test_unknown_source_is_422(client, db_session, program):
    await _admin(client, db_session)
    assert (await client.put(f"{ADMIN}/{program.id}/syllabus", json={"source": "pdf"})).status_code == 422
    assert (await client.put(f"{ADMIN}/{program.id}/syllabus", json={"source": "word"})).status_code == 422


# --- S1 PDF + S2 public, no gate ---


@pytest.mark.asyncio
async def test_a_pdf_is_uploaded_and_served_publicly_inline(client, db_session, program):
    await _admin(client, db_session)
    response = await client.put(f"{ADMIN}/{program.id}/syllabus/pdf", files={"file": ("syllabus.pdf", PDF, "application/pdf")})
    assert response.status_code == 200, response.text
    syllabus = response.json()["syllabus"]
    assert syllabus["source"] == "pdf" and syllabus["url"].startswith(program_media.URL_PREFIX) and syllabus["url"].endswith(".pdf")
    client.cookies.clear()  # S2: no session, no enquiry
    served = await client.get(syllabus["url"])
    assert served.status_code == 200 and served.content == PDF
    assert served.headers["content-type"] == "application/pdf" and served.headers["x-content-type-options"] == "nosniff"
    assert served.headers["content-disposition"] == f'inline; filename="{program.slug}-syllabus.pdf"'


@pytest.mark.asyncio
@pytest.mark.parametrize(("data", "content_type", "status"), [(b"MZ\x90\x00 not a pdf", "application/pdf", 415), (PDF, "application/msword", 415),
                                                                (png(), "image/png", 415)])
async def test_non_pdf_syllabus_is_refused(client, db_session, program, data, content_type, status):
    await _admin(client, db_session)
    response = await client.put(f"{ADMIN}/{program.id}/syllabus/pdf", files={"file": ("x.pdf", data, content_type)})
    assert response.status_code == status


@pytest.mark.asyncio
async def test_a_pdf_over_10_mb_is_413(client, db_session, program):
    await _admin(client, db_session)
    big = PDF + b"0" * (10 * 1024 * 1024)
    assert (await client.put(f"{ADMIN}/{program.id}/syllabus/pdf", files={"file": ("x.pdf", big, "application/pdf")})).status_code == 413


@pytest.mark.asyncio
async def test_one_source_switching_away_from_pdf_deletes_it_and_clears_the_rest(client, db_session, program):
    await _admin(client, db_session)
    await client.put(f"{ADMIN}/{program.id}/syllabus", json={"source": "manual", "modules": MODULES})
    pdf_url = (await client.put(f"{ADMIN}/{program.id}/syllabus/pdf", files={"file": ("s.pdf", PDF, "application/pdf")})).json()["syllabus"]["url"]
    await db_session.refresh(program)
    assert program.syllabus_modules == [] and program.syllabus_url is None  # the PDF replaced the modules
    assert _stored(pdf_url)
    response = await client.put(f"{ADMIN}/{program.id}/syllabus", json={"source": "link", "url": "https://example.com/s"})
    assert response.json()["syllabus"] == {"source": "link", "url": "https://example.com/s"}
    assert not _stored(pdf_url)
    assert (await client.get(pdf_url)).status_code == 404
    cleared = await client.put(f"{ADMIN}/{program.id}/syllabus", json={"source": None})
    assert cleared.status_code == 200 and cleared.json()["syllabus"] is None


@pytest.mark.asyncio
async def test_replacing_a_pdf_deletes_the_previous_one(client, db_session, program):
    await _admin(client, db_session)
    first = (await client.put(f"{ADMIN}/{program.id}/syllabus/pdf", files={"file": ("a.pdf", PDF, "application/pdf")})).json()["syllabus"]["url"]
    second = (await client.put(f"{ADMIN}/{program.id}/syllabus/pdf", files={"file": ("b.pdf", PDF, "application/pdf")})).json()["syllabus"]["url"]
    assert first != second and not _stored(first) and _stored(second)


# --- S3 image ---


@pytest.mark.asyncio
@pytest.mark.parametrize(("data", "content_type", "ext"), [(png(400, 240, text=b"Comment\x00secret"), "image/png", ".png"),
                                                            (jpeg(400, 240), "image/jpeg", ".jpg"), (webp(400, 240), "image/webp", ".webp")])
async def test_an_image_is_uploaded_and_served(client, db_session, program, data, content_type, ext):
    await _admin(client, db_session)
    response = await client.put(f"{ADMIN}/{program.id}/image", files={"file": (f"c{ext}", data, content_type)})
    assert response.status_code == 200, response.text
    image_url = response.json()["image_url"]
    assert image_url.startswith(program_media.URL_PREFIX) and image_url.endswith(ext)
    client.cookies.clear()
    assert (await _public(client, program.slug))["image_url"] == image_url
    served = await client.get(image_url)
    assert served.status_code == 200 and served.headers["content-type"] == content_type and b"secret" not in served.content
    assert "content-disposition" not in served.headers


@pytest.mark.asyncio
async def test_image_rules(client, db_session, program):
    await _admin(client, db_session)
    put = lambda data, ct="image/png": client.put(f"{ADMIN}/{program.id}/image", files={"file": ("c.png", data, ct)})  # noqa: E731
    assert (await put(png(64, 64))).status_code == 422  # below 120 px
    assert (await put(b"<svg onload=alert(1)>", "image/svg+xml")).status_code == 415
    assert (await put(PDF, "application/pdf")).status_code == 415
    assert (await put(png() + b"0" * (2 * 1024 * 1024))).status_code == 413


@pytest.mark.asyncio
async def test_replacing_and_removing_an_image_deletes_the_files(client, db_session, program):
    await _admin(client, db_session)
    first = (await client.put(f"{ADMIN}/{program.id}/image", files={"file": ("a.png", png(200, 200), "image/png")})).json()["image_url"]
    second = (await client.put(f"{ADMIN}/{program.id}/image", files={"file": ("b.png", png(200, 200), "image/png")})).json()["image_url"]
    assert not _stored(first) and _stored(second)
    removed = await client.delete(f"{ADMIN}/{program.id}/image")
    assert removed.status_code == 200 and removed.json()["image_url"] is None and not _stored(second)


# --- public route ---


@pytest.mark.asyncio
async def test_files_of_an_inactive_course_are_not_served(client, db_session, program):
    await _admin(client, db_session)
    url = (await client.put(f"{ADMIN}/{program.id}/image", files={"file": ("a.png", png(200, 200), "image/png")})).json()["image_url"]
    program.active = False
    await db_session.commit()
    assert (await client.get(url)).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["x.png", "../../etc/passwd", f"{'a' * 32}.svg", f"{'A' * 32}.png", f"{uuid.uuid4().hex}.pdf"])
async def test_public_route_404s_bad_or_unowned_names(client, name):
    assert (await client.get(f"{program_media.URL_PREFIX}{name}")).status_code == 404


# --- RBAC ---


@pytest.mark.asyncio
async def test_media_detail_for_the_editor(client, db_session, program):
    await _admin(client, db_session, "super_admin", "it")
    response = await client.get(f"{ADMIN}/{program.id}/media")
    assert response.status_code == 200 and response.json() == {"id": str(program.id), "slug": program.slug, "title": program.title,
                                                               "image_url": None, "syllabus": None}
    assert (await client.get(f"{ADMIN}/{uuid.uuid4()}/media")).status_code == 404
    assert (await client.put(f"{ADMIN}/{uuid.uuid4()}/syllabus", json={"source": None})).status_code == 404


@pytest.mark.asyncio
async def test_needs_a_session(client, program):
    assert (await client.put(f"{ADMIN}/{program.id}/syllabus", json={"source": None})).status_code == 401
    assert (await client.put(f"{ADMIN}/{program.id}/image", files={"file": ("a.png", png(200, 200), "image/png")})).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("overseas_admin", "overseas"), ("trainer", "it"), ("it_student", "it")])
async def test_other_roles_get_403(client, db_session, program, role, division):
    await _admin(client, db_session, role, division)
    calls = [
        client.get(f"{ADMIN}/{program.id}/media"),
        client.put(f"{ADMIN}/{program.id}/syllabus", json={"source": None}),
        client.put(f"{ADMIN}/{program.id}/syllabus/pdf", files={"file": ("s.pdf", PDF, "application/pdf")}),
        client.put(f"{ADMIN}/{program.id}/image", files={"file": ("a.png", png(200, 200), "image/png")}),
        client.delete(f"{ADMIN}/{program.id}/image"),
    ]
    for call in calls:
        assert (await call).status_code == 403
    await db_session.refresh(program)
    assert program.syllabus_source is None and program.image_url is None


# --- migration 0220 ---


@pytest.mark.asyncio
async def test_the_database_refuses_an_unknown_syllabus_source(db_session, program):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    program_id = program.id
    with pytest.raises(IntegrityError):
        await db_session.execute(text("UPDATE programs SET syllabus_source = 'word' WHERE id = :id"), {"id": program_id})
    await db_session.rollback()
    modules = await db_session.scalar(text("SELECT syllabus_modules FROM programs WHERE id = :id"), {"id": program_id})
    assert modules == []
