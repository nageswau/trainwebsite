"""tel-012 -- message templates API + preview (spec §4, §6; AC2, AC3, AC6). Brochure-linked templates are covered in
test_tel_012_assets.py (they need an uploaded asset)."""

import pytest
from sqlalchemy import select

from app.models import AuditLog
from tests.tel012_helpers import NON_READERS, READERS, WRITERS, as_role, product, uname

TEMPLATES = "/api/v1/telecaller/templates"


async def _wa(client, **body):
    return await client.post(TEMPLATES, json={"channel": "whatsapp", "kind": "welcome", "name": uname("WA"), "body": "Hi {name}", **body})


async def _email(client, **body):
    return await client.post(TEMPLATES, json={"channel": "email", "kind": "fee_proposal", "name": uname("EM"), "subject": "{product} fees", "body": "Dear {name}", **body})


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), WRITERS)
async def test_writers_create_both_channels(client, db_session, role, division):
    user = await as_role(client, db_session, role, division)
    prod = await product(db_session)
    name = uname("Hello")
    wa = await _wa(client, name=f"  {name}  ", body="Hi {name},\n\twelcome to {product}  ", product_id=str(prod.id))
    assert wa.status_code == 201, wa.text
    body = wa.json()
    assert body == {
        "id": body["id"],
        "channel": "whatsapp",
        "kind": "welcome",
        "name": name,
        "product": {"id": str(prod.id), "name": prod.name, "group": "it", "active": True},
        "asset": None,
        "subject": None,
        "body": "Hi {name},\n\twelcome to {product}",
        "active": True,
    }
    email = await _email(client)
    assert email.status_code == 201 and email.json()["subject"] == "{product} fees" and email.json()["product"] is None
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == body["id"]))
    assert (audit.action, audit.user_id, audit.metadata_json) == (
        "telecaller.template_create",
        user.id,
        {"fields": ["asset_id", "body", "channel", "kind", "name", "product_id", "subject"]},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("telecaller", "it"), *NON_READERS])
async def test_other_roles_cannot_write(client, db_session, role, division):
    await as_role(client, db_session)
    created = (await _wa(client)).json()
    await as_role(client, db_session, role, division)
    assert (await _wa(client)).status_code == 403
    assert (await client.patch(f"{TEMPLATES}/{created['id']}", json={"name": "X"})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), NON_READERS)
async def test_non_readers_cannot_read(client, db_session, role, division):
    await as_role(client, db_session)
    created = (await _wa(client)).json()
    await as_role(client, db_session, role, division)
    assert (await client.get(TEMPLATES)).status_code == 403
    assert (await client.get(f"{TEMPLATES}/{created['id']}/preview")).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("maker", "body", "detail"),
    [
        (_wa, {"body": "Hi {first_name}"}, "Unknown placeholder {first_name}. Use {name}, {product}, {brochure_link} or {appointment_time}"),
        (_email, {"subject": "{Name}"}, "Unknown placeholder {Name}. Use {name}, {product}, {brochure_link} or {appointment_time}"),
        (_wa, {"body": "Get it: {brochure_link}"}, "Attach a brochure to use {brochure_link}"),
        (_wa, {"subject": "Hi"}, "Only email templates have a subject"),
        (_email, {"subject": None}, "Subject is required"),
        (_email, {"subject": "Line one\r\nBcc: x@y.z"}, "Subject must be one line without control characters"),
        (_email, {"subject": "s" * 201}, "Subject must be at most 200 characters"),
        (_wa, {"kind": "fee_proposal"}, "Choose a WhatsApp template kind"),
        (_email, {"kind": "welcome"}, "Choose an email template kind"),
        (_wa, {"channel": "sms"}, "Channel: Input should be 'whatsapp' or 'email'"),
        (_wa, {"body": "a" * 1001}, "A WhatsApp message must be at most 1000 characters"),
        (_email, {"body": "a" * 5001}, "An email message must be at most 5000 characters"),
        (_wa, {"body": "  "}, "Message is required"),
        (_wa, {"body": "Hi\x07"}, "Message contains invalid characters"),
        (_wa, {"asset_id": "00000000-0000-0000-0000-000000000000"}, "Choose an active brochure"),
    ],
)
async def test_validation_sentences(client, db_session, maker, body, detail):
    await as_role(client, db_session)
    response = await maker(client, **body)
    assert response.status_code == 422, response.text
    assert response.json()["detail"] == detail


@pytest.mark.asyncio
async def test_update_rechecks_on_the_merged_row(client, db_session):
    await as_role(client, db_session)
    created = (await _email(client)).json()
    url = f"{TEMPLATES}/{created['id']}"
    assert (await client.patch(url, json={"channel": "whatsapp"})).json()["detail"] == "Channel cannot be changed"
    assert (await client.patch(url, json={"kind": "welcome"})).json()["detail"] == "Choose an email template kind"
    assert (await client.patch(url, json={"body": "Hi {nme}"})).status_code == 422
    assert (await client.patch(url, json={"subject": None})).json()["detail"] == "Subject is required"
    ok = await client.patch(url, json={"kind": "follow_up", "body": "Dear {name}, about {product}", "channel": "email"})
    assert ok.status_code == 200 and ok.json()["kind"] == "follow_up"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == created["id"], AuditLog.action == "telecaller.template_update"))
    assert audit.metadata_json == {"fields": ["body", "kind"]}


@pytest.mark.asyncio
async def test_duplicate_name_per_channel_is_409(client, db_session):
    await as_role(client, db_session)
    name = uname("Dup")
    assert (await _wa(client, name=name)).status_code == 201
    dup = await _wa(client, name=name.upper())
    assert dup.status_code == 409 and dup.json()["detail"] == f"A WhatsApp template named “{name.upper()}” already exists"
    assert (await _email(client, name=name)).status_code == 201  # same name, other channel


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), READERS)
async def test_filters_and_telecaller_active_only(client, db_session, role, division):
    prod = await product(db_session)
    await as_role(client, db_session)
    on = (await _wa(client, product_id=str(prod.id), kind="reminder")).json()
    off = (await _email(client, product_id=str(prod.id))).json()
    await client.patch(f"{TEMPLATES}/{off['id']}", json={"active": False})
    await as_role(client, db_session, role, division)
    listed = (await client.get(TEMPLATES, params={"product_id": str(prod.id)})).json()["items"]
    assert [i["id"] for i in listed] == ([on["id"]] if role == "telecaller" else [on["id"], off["id"]])  # WhatsApp before email
    by_kind = (await client.get(TEMPLATES, params={"product_id": str(prod.id), "channel": "whatsapp", "kind": "reminder"})).json()
    assert [i["id"] for i in by_kind["items"]] == [on["id"]]
    assert (await client.get(TEMPLATES, params={"q": on["name"]})).json()["items"][0]["id"] == on["id"]
    assert (await client.get(TEMPLATES, params={"channel": "fax"})).status_code == 422


@pytest.mark.asyncio
async def test_seeded_templates_are_listed(client, db_session):
    """AC1 through the API: a telecaller sees the generic seed templates."""
    await as_role(client, db_session, "telecaller", "it")
    page = (await client.get(TEMPLATES, params={"q": "Welcome message", "channel": "whatsapp"})).json()
    assert any(i["name"] == "Welcome message" and i["product"] is None for i in page["items"])


@pytest.mark.asyncio
async def test_preview_renders_sample_values(client, db_session):
    """AC2: placeholders filled; the template's product name when it has one, else the sample product."""
    prod = await product(db_session)
    await as_role(client, db_session)
    generic = (await _email(client, subject="{product} at {appointment_time}", body="Dear {name}")).json()
    linked = (await _wa(client, body="{name} likes {product}", product_id=str(prod.id))).json()
    await as_role(client, db_session, "telecaller", "it")
    preview = (await client.get(f"{TEMPLATES}/{generic['id']}/preview")).json()
    assert preview == {"subject": "Cyber Security at Mon 14 Sept 2026, 10:30 AM", "body": "Dear Priya Sharma", "brochure_link": None}
    assert (await client.get(f"{TEMPLATES}/{linked['id']}/preview")).json()["body"] == f"Priya Sharma likes {prod.name}"


@pytest.mark.asyncio
async def test_inactive_template_preview_is_404_for_a_telecaller(client, db_session):
    await as_role(client, db_session)
    created = (await _wa(client)).json()
    await client.patch(f"{TEMPLATES}/{created['id']}", json={"active": False})
    assert (await client.get(f"{TEMPLATES}/{created['id']}/preview")).status_code == 200  # the manager still previews it
    await as_role(client, db_session, "telecaller", "it")
    assert (await client.get(f"{TEMPLATES}/{created['id']}/preview")).status_code == 404
