"""nehn-035 (DEC-SCOPE-331): university logo upload (L1-L5) and the public catalogue's richer card payload (L6)."""

import struct
import uuid
import zlib

import pytest
from sqlalchemy import select

from app.models import AuditLog, Country, OverseasCourse, University
from app.services.image_metadata import image_size
from app.services.storage import storage
from tests.test_ovs_001_discovery import _make_country, _make_university
from tests.test_pub_023_country_flags import _cleanup
from tests.upc001_helpers import as_role, login
from tests.upc003_helpers import BASE, create, make_head, make_pm

PUBLIC = "/api/v1/public/university-logos"


def png(width: int = 64, height: int = 64, *, text: bytes = b"") -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    idat = zlib.compress(b"".join(b"\x00" + b"\xff" * width for _ in range(min(height, 4))))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + (chunk(b"tEXt", text) if text else b"") + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def jpeg(width: int = 80, height: int = 40) -> bytes:
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + sof + b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x00\xff\xd9"


def webp(width: int = 100, height: int = 50) -> bytes:
    body = b"VP8X" + struct.pack("<I", 10) + b"\x00\x00\x00\x00" + (width - 1).to_bytes(3, "little") + (height - 1).to_bytes(3, "little")
    return b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WEBP" + body


async def _country(db) -> Country:
    """Internal (not in the public catalogue): the shared test database is never truncated, and public debris pushes seeded countries off
    the first page that other suites' e2e read."""
    tag = uuid.uuid4().hex[:8]
    country = Country(
        slug=f"nehn035-{tag}",
        name=f"Logoland {tag}",
        catalogue_visible=False,
        overview="",
        tuition="",
        living_expenses="",
        visa_process=[],
        work_opportunities="",
        post_study_work="",
        pr_opportunities="",
        faq=[],
    )
    db.add(country)
    await db.commit()
    return country


async def _uni(client, db):
    await as_role(client, db, "super_admin", "overseas")
    return await create(client, (await _country(db)).id)


def _put(client, university_id, data: bytes, content_type: str = "image/png", name: str = "logo.png"):
    return client.put(f"{BASE}/{university_id}/logo", files={"file": (name, data, content_type)})


# --- image_size (L2): read from the header, never decoded ---


def test_image_size_reads_png_jpeg_and_webp_headers():
    assert image_size(png(120, 30), "image/png") == (120, 30)
    assert image_size(jpeg(80, 40), "image/jpeg") == (80, 40)
    assert image_size(webp(100, 50), "image/webp") == (100, 50)


def test_image_size_reads_lossy_and_lossless_webp():
    lossy = b"RIFF" + b"\x00" * 4 + b"WEBPVP8 " + b"\x00" * 4 + b"\x00\x00\x00\x9d\x01\x2a" + (300).to_bytes(2, "little") + (150).to_bytes(2, "little")
    bits = (300 - 1) | ((150 - 1) << 14)
    lossless = b"RIFF" + b"\x00" * 4 + b"WEBPVP8L" + b"\x00" * 4 + b"\x2f" + bits.to_bytes(4, "little") + b"\x00" * 5
    assert image_size(lossy, "image/webp") == (300, 150)
    assert image_size(lossless, "image/webp") == (300, 150)


def test_image_size_is_none_for_a_header_it_cannot_read():
    assert image_size(b"\x89PNG\r\n\x1a\n", "image/png") is None
    assert image_size(b"\xff\xd8\xff\xd9", "image/jpeg") is None
    assert image_size(b"RIFF\x00\x00\x00\x00WEBPXXXX", "image/webp") is None


# --- upload (L1-L4) ---


@pytest.mark.asyncio
async def test_admin_uploads_a_png_and_it_is_served_publicly(client, db_session):  # AC1
    uni = await _uni(client, db_session)
    response = await _put(client, uni["id"], png(text=b"Comment\x00secret"))
    assert response.status_code == 200, response.text
    logo_url = response.json()["university"]["logo_url"]
    assert logo_url.startswith(f"{PUBLIC}/") and logo_url.endswith(".png")
    client.cookies.clear()  # the read needs no session
    served = await client.get(logo_url)
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png" and served.headers["x-content-type-options"] == "nosniff"
    assert "immutable" in served.headers["cache-control"]
    assert served.content.startswith(b"\x89PNG") and b"secret" not in served.content  # metadata stripped
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == uni["id"], AuditLog.action == "university.logo"))
    assert audit is not None and audit.metadata_json["content_type"] == "image/png"


@pytest.mark.asyncio
@pytest.mark.parametrize(("data", "content_type", "ext"), [(jpeg(), "image/jpeg", ".jpg"), (webp(), "image/webp", ".webp")])
async def test_jpeg_and_webp_are_accepted(client, db_session, data, content_type, ext):
    uni = await _uni(client, db_session)
    response = await _put(client, uni["id"], data, content_type, f"logo{ext}")
    assert response.status_code == 200, response.text
    logo_url = response.json()["university"]["logo_url"]
    assert logo_url.endswith(ext)
    assert (await client.get(logo_url)).headers["content-type"] == content_type


@pytest.mark.asyncio
async def test_an_svg_with_a_script_is_rejected(client, db_session):  # AC5
    uni = await _uni(client, db_session)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    assert (await _put(client, uni["id"], svg, "image/svg+xml", "logo.svg")).status_code == 415
    assert (await _put(client, uni["id"], svg, "image/png", "logo.png")).status_code == 415  # renamed: the bytes do not match
    assert (await client.get(f"{BASE}/{uni['id']}")).json()["university"]["logo_url"] is None


@pytest.mark.asyncio
async def test_a_10_mb_upload_is_rejected(client, db_session):
    uni = await _uni(client, db_session)
    assert (await _put(client, uni["id"], png() + b"\x00" * (10 * 1024 * 1024))).status_code == 413


@pytest.mark.asyncio
@pytest.mark.parametrize(("width", "height"), [(16, 64), (64, 16), (4000, 64), (64, 3000)])
async def test_dimensions_outside_32_to_2048_are_rejected(client, db_session, width, height):
    uni = await _uni(client, db_session)
    response = await _put(client, uni["id"], png(width, height))
    assert response.status_code == 422 and "32" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_logo_whose_header_cannot_be_read_is_rejected(client, db_session):
    uni = await _uni(client, db_session)
    assert (await _put(client, uni["id"], b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)).status_code == 422


@pytest.mark.asyncio
async def test_replacing_a_logo_deletes_the_previous_upload(client, db_session):
    uni = await _uni(client, db_session)
    first = (await _put(client, uni["id"], png())).json()["university"]["logo_url"]
    second = (await _put(client, uni["id"], png(100, 100))).json()["university"]["logo_url"]
    assert first != second
    assert (await client.get(first)).status_code == 404
    assert (await client.get(second)).status_code == 200


@pytest.mark.asyncio
async def test_clearing_or_changing_an_uploaded_logo_in_the_form_deletes_the_file(client, db_session):  # QA-02
    uni = await _uni(client, db_session)
    first = (await _put(client, uni["id"], png())).json()["university"]["logo_url"]
    assert (await client.patch(f"{BASE}/{uni['id']}", json={"logo_url": "https://cdn.example.com/l.png"})).status_code == 200
    assert (await client.get(first)).status_code == 404
    second = (await _put(client, uni["id"], png())).json()["university"]["logo_url"]
    assert (await client.patch(f"{BASE}/{uni['id']}", json={"logo_url": None})).status_code == 200
    assert (await client.get(second)).status_code == 404


@pytest.mark.asyncio
async def test_a_logo_another_university_still_uses_is_kept(client, db_session):  # QA-02: the form accepts a copied uploaded URL
    uni = await _uni(client, db_session)
    other = await create(client, (await _country(db_session)).id)
    shared = (await _put(client, uni["id"], png())).json()["university"]["logo_url"]
    assert (await client.patch(f"{BASE}/{other['id']}", json={"logo_url": shared})).status_code == 200
    await _put(client, uni["id"], png(100, 100))
    assert (await client.get(shared)).status_code == 200
    await client.patch(f"{BASE}/{other['id']}", json={"logo_url": None})
    assert (await client.get(shared)).status_code == 404  # its last user let it go


@pytest.mark.asyncio
async def test_replacing_a_bundled_logo_leaves_it_alone(client, db_session):
    uni = await _uni(client, db_session)
    await client.patch(f"{BASE}/{uni['id']}", json={"logo_url": "/universities/logos/x.png"})
    assert (await _put(client, uni["id"], png())).status_code == 200


@pytest.mark.asyncio
async def test_upload_needs_a_session(client, db_session):
    uni = await _uni(client, db_session)
    client.cookies.clear()
    assert (await _put(client, uni["id"], png())).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["overseas_student", "counselor", "agent"])
async def test_roles_that_cannot_edit_universities_get_403(client, db_session, role):
    uni = await _uni(client, db_session)
    await as_role(client, db_session, role, "overseas")
    assert (await _put(client, uni["id"], png())).status_code == 403


@pytest.mark.asyncio
async def test_overseas_admin_may_upload(client, db_session):
    uni = await _uni(client, db_session)
    await as_role(client, db_session, "overseas_admin", "overseas")
    assert (await _put(client, uni["id"], png())).status_code == 200


@pytest.mark.asyncio
async def test_a_manager_of_another_university_gets_403(client, db_session):
    uni = await _uni(client, db_session)
    head = await make_head(db_session)
    other_pm = await make_pm(db_session, head)
    uni_row = await db_session.get(University, uuid.UUID(uni["id"]))
    uni_row.primary_manager_user_id = (await make_pm(db_session, await make_head(db_session))).id
    await db_session.commit()
    await login(client, other_pm)
    assert (await _put(client, uni["id"], png())).status_code == 403


@pytest.mark.asyncio
async def test_the_universitys_own_manager_may_upload(client, db_session):
    uni = await _uni(client, db_session)
    pm = await make_pm(db_session, await make_head(db_session))
    uni_row = await db_session.get(University, uuid.UUID(uni["id"]))
    uni_row.primary_manager_user_id = pm.id
    await db_session.commit()
    await login(client, pm)
    assert (await _put(client, uni["id"], png())).status_code == 200


@pytest.mark.asyncio
async def test_unknown_university_is_404(client, db_session):
    await as_role(client, db_session, "super_admin", "overseas")
    assert (await _put(client, uuid.uuid4(), png())).status_code == 404


# --- validator (L5) and the public read ---


@pytest.mark.asyncio
async def test_the_form_can_resend_an_uploaded_logo_url(client, db_session):
    uni = await _uni(client, db_session)
    logo_url = (await _put(client, uni["id"], png())).json()["university"]["logo_url"]
    patched = await client.patch(f"{BASE}/{uni['id']}", json={"logo_url": logo_url, "city": "Leeds"})
    assert patched.status_code == 200, patched.text
    assert patched.json()["university"]["logo_url"] == logo_url


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [f"{PUBLIC}/../secret.png", f"{PUBLIC}/abc.png", f"{PUBLIC}/{'a' * 32}.svg", "/api/v1/files/x"])
async def test_other_api_paths_are_still_refused(client, db_session, bad):
    uni = await _uni(client, db_session)
    assert (await client.patch(f"{BASE}/{uni['id']}", json={"logo_url": bad})).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["abc.png", f"{'a' * 32}.svg", f"{'a' * 32}.png", f"{'A' * 32}.png"])
async def test_public_read_404s_bad_or_missing_names(client, name):
    assert (await client.get(f"{PUBLIC}/{name}")).status_code == 404


@pytest.mark.asyncio
async def test_public_read_never_serves_other_storage_keys(client):
    storage.write_bytes("public/elsewhere/" + "b" * 32 + ".png", png(), "image/png")
    assert (await client.get(f"{PUBLIC}/..%2Felsewhere%2F{'b' * 32}.png")).status_code == 404


# --- public card payload (L6) ---


@pytest.mark.asyncio
async def test_public_list_carries_programs_count_and_country(client, db_session):  # AC2
    country = await _make_country(db_session, iso2=None)
    try:
        with_courses = await _make_university(db_session, country.id, name="Counted University")
        await _make_university(db_session, country.id, name="Empty University")
        for active in (True, True, False):
            db_session.add(
                OverseasCourse(university_id=with_courses.id, title=f"MSc {uuid.uuid4().hex[:6]}", level="PG", category="Tech", duration="1 year", tuition_fee="", intake="Sep", active=active)
            )
        await db_session.commit()
        rows = {r["name"]: r for r in (await client.get("/api/v1/public/universities", params={"country": country.slug})).json()}
        assert rows["Counted University"]["programs_count"] == 2
        assert rows["Empty University"]["programs_count"] == 0
        assert rows["Counted University"]["country_name"] == country.name and rows["Counted University"]["country_slug"] == country.slug
        assert "country_iso2" in rows["Counted University"]
    finally:
        await _cleanup(db_session, country)
