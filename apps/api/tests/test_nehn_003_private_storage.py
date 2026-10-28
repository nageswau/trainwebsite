"""nehn-003 -- private, S3-compatible storage with per-purpose upload policy (DEC-SCOPE-279; spec
docs/superpowers/specs/2026-10-26-nehn-003-private-storage-design.md)."""

import io
import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import StoredFile
from app.services import upload_policy
from app.services.storage import StorageService, storage
from tests.agn001_helpers import client_for, mk_user

PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
EXE = b"MZ\x90\x00\x03\x00\x00\x00" + b"\x00" * 64


def _key(prefix: str = "uploads") -> str:
    return f"{prefix}/{uuid.uuid4().hex}-private.pdf"


# --- upload policy ------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        (PDF, "application/pdf"),
        (PNG, "image/png"),
        (b"\xff\xd8\xff\xe0" + b"\x00" * 16, "image/jpeg"),
        (b"PK\x03\x04" + b"\x00" * 26, "zip"),
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 8, "ole2"),
        (b"\x00\x00\x00\x18ftypheic" + b"\x00" * 8, "image/heic"),
        (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
        (b"name,email\nA,a@example.com\n", "text"),
        (EXE, None),
    ],
)
def test_sniff_recognises_the_magic_bytes(head, expected):
    assert upload_policy.sniff(head) == expected


def test_a_renamed_exe_is_rejected_by_the_sniffing_check():
    with pytest.raises(upload_policy.PolicyError) as refused:
        upload_policy.check("assignment_submission", "application/pdf", len(EXE), EXE)
    assert refused.value.status_code == 415


def test_the_submission_policy_rejects_5_1_mb_with_413():
    with pytest.raises(upload_policy.PolicyError) as refused:
        upload_policy.check("assignment_submission", "application/pdf", int(5.1 * 1024 * 1024), PDF)
    assert refused.value.status_code == 413
    upload_policy.check("assignment_submission", "application/pdf", 3 * 1024 * 1024, PDF)  # a 3 MB PDF is fine


def test_zero_bytes_and_unknown_purposes_are_refused():
    with pytest.raises(upload_policy.PolicyError) as empty:
        upload_policy.check("default", "application/pdf", 0, b"")
    assert empty.value.status_code == 413
    with pytest.raises(upload_policy.PolicyError) as unknown:
        upload_policy.check("nope", "application/pdf", 10, PDF)
    assert unknown.value.status_code == 422


def test_a_type_outside_the_purpose_is_415_even_when_the_bytes_match():
    with pytest.raises(upload_policy.PolicyError) as refused:
        upload_policy.check("signature", "application/pdf", len(PDF), PDF)
    assert refused.value.status_code == 415


# --- S3-compatible configuration ----------------------------------------------------------------------------------------------------


def test_the_s3_client_takes_the_endpoint_and_sse_is_configurable(monkeypatch):
    calls: list = []

    class FakeS3:
        def put_object(self, **kwargs):
            calls.append(kwargs)

    def fake_client(service, **kwargs):
        calls.append(kwargs)
        return FakeS3()

    monkeypatch.setattr("app.services.storage.boto3.client", fake_client)
    monkeypatch.setattr(settings, "aws_s3_bucket", "bucket")
    monkeypatch.setattr(settings, "s3_endpoint_url", "https://ams3.digitaloceanspaces.com")
    monkeypatch.setattr(settings, "s3_sse", "")
    StorageService().write_bytes("certificates/x.pdf", PDF, "application/pdf")
    assert calls[0] == {"region_name": settings.aws_region, "endpoint_url": "https://ams3.digitaloceanspaces.com"}
    assert "ServerSideEncryption" not in calls[1] and calls[1]["Bucket"] == "bucket"
    monkeypatch.setattr(settings, "s3_sse", "AES256")
    StorageService().write_bytes("certificates/x.pdf", PDF, "application/pdf")
    assert calls[3]["ServerSideEncryption"] == "AES256"


# --- private serving ----------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_private_key_is_404_on_local_files_without_a_session(client):
    key = _key()
    storage.write_bytes(key, PDF, "application/pdf")
    for path in (key, f"certificates/{uuid.uuid4().hex}.pdf", f"receipts/{uuid.uuid4().hex}.pdf"):
        storage.write_bytes(path, PDF, "application/pdf")
        assert (await client.get(f"/local-files/{path}")).status_code == 404


@pytest.mark.asyncio
async def test_a_stored_local_files_url_still_resolves_for_a_signed_in_user(db_session):
    key = _key()
    storage.write_bytes(key, PDF, "application/pdf")
    user = await mk_user(db_session, role="it_student", division="it")
    async with client_for(user.email, "it") as c:
        response = await c.get(f"/local-files/{key}")
        assert response.status_code == 200 and response.content == PDF
        assert response.headers["x-content-type-options"] == "nosniff"
        assert (await c.get("/local-files/agent-kyc/x.pdf")).status_code == 404
        assert (await c.get("/local-files/../etc/passwd")).status_code == 404


@pytest.mark.asyncio
async def test_the_public_prefix_stays_public(client):
    key = f"public/{uuid.uuid4().hex}.png"
    storage.write_bytes(key, PNG, "image/png")
    response = await client.get(f"/local-files/{key}")
    assert response.status_code == 200 and response.content == PNG


@pytest.mark.asyncio
async def test_a_local_presigned_link_is_signed_short_lived_and_scoped_to_its_key(client, monkeypatch):
    key = _key("certificates")
    storage.write_bytes(key, PDF, "application/pdf")
    url = storage.presign_download(key)
    assert url.startswith("/api/v1/files/signed/") and key not in url
    response = await client.get(url)  # no session: the signature is the authorisation, like an S3 presigned URL
    assert response.status_code == 200 and response.content == PDF
    assert response.headers["content-type"].startswith("application/pdf")
    assert (await client.get(url[:-2] + ("aa" if not url.endswith("aa") else "bb"))).status_code == 404
    monkeypatch.setattr("app.services.storage.DOWNLOAD_TTL_SECONDS", -1)
    assert (await client.get(storage.presign_download(key))).status_code == 404


@pytest.mark.asyncio
async def test_plain_text_opens_inline_but_markup_is_only_ever_an_attachment(client):
    """QA-01: a .txt profile document opened in a new tab (as under the old static mount); HTML never renders in our origin."""
    text_key, html_key = f"uploads/{uuid.uuid4().hex}-notes.txt", f"uploads/{uuid.uuid4().hex}-page.html"
    storage.write_bytes(text_key, b"hello", "text/plain")
    storage.write_bytes(html_key, b"<script>alert(1)</script>", "text/plain")
    text = await client.get(storage.presign_download(text_key))
    assert text.status_code == 200 and text.headers["content-type"].startswith("text/plain") and "content-disposition" not in text.headers
    html = await client.get(storage.presign_download(html_key))
    assert html.headers["content-disposition"].startswith("attachment") and html.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_a_download_token_is_not_a_session(client):
    token = storage.presign_download(_key()).rsplit("/", 1)[1]
    client.cookies.set("edusphere_access", token)
    assert (await client.get("/api/v1/auth/me")).status_code == 401


# --- /files/upload + /files/{id} ----------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_by_purpose_then_owner_downloads_and_others_are_refused(client, db_session):
    owner = await mk_user(db_session, role="it_student", division="it")
    other = await mk_user(db_session, role="it_student", division="it")
    admin = await mk_user(db_session, role="super_admin", division="global")
    async with client_for(owner.email, "it") as c:
        created = await c.post("/api/v1/files/upload", params={"purpose": "assignment_submission"}, files={"file": ("Résumé final.pdf", PDF, "application/pdf")})
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["purpose"] == "assignment_submission" and body["size"] == len(PDF) and body["content_type"] == "application/pdf"
        assert body["filename"] == "Résumé final.pdf" and body["url"] == f"/api/v1/files/{body['id']}" and "key" not in body
        mine = await c.get(body["url"])
        assert mine.status_code == 200 and mine.content == PDF
        assert mine.headers["content-disposition"].startswith("attachment")
    row = await db_session.scalar(select(StoredFile).where(StoredFile.id == uuid.UUID(body["id"])))
    assert row.owner_id == owner.id and len(row.sha256) == 64 and (await client.get(f"/local-files/{row.key}")).status_code == 404
    assert (await client.get(body["url"])).status_code == 401
    async with client_for(other.email, "it") as c:
        assert (await c.get(body["url"])).status_code == 403
    async with client_for(admin.email, "global") as c:
        assert (await c.get(body["url"])).status_code == 200
    async with client_for(owner.email, "it") as c:
        assert (await c.get(f"/api/v1/files/{uuid.uuid4()}")).status_code == 404


@pytest.mark.asyncio
async def test_upload_refusals(client, db_session):
    user = await mk_user(db_session, role="it_student", division="it")
    assert (await client.post("/api/v1/files/upload", params={"purpose": "default"}, files={"file": ("a.pdf", PDF, "application/pdf")})).status_code == 401
    async with client_for(user.email, "it") as c:
        spoofed = await c.post("/api/v1/files/upload", params={"purpose": "assignment_submission"}, files={"file": ("x.pdf", EXE, "application/pdf")})
        assert spoofed.status_code == 415
        big = io.BytesIO(PDF + b"0" * (5 * 1024 * 1024))
        assert (await c.post("/api/v1/files/upload", params={"purpose": "assignment_submission"}, files={"file": ("big.pdf", big, "application/pdf")})).status_code == 413
        assert (await c.post("/api/v1/files/upload", params={"purpose": "nope"}, files={"file": ("a.pdf", PDF, "application/pdf")})).status_code == 422
        assert (await c.post("/api/v1/files/upload", params={"purpose": "default"}, files={"file": ("e.pdf", b"", "application/pdf")})).status_code == 413


@pytest.mark.asyncio
async def test_local_upload_keeps_its_shape_and_now_sniffs(db_session):
    user = await mk_user(db_session, role="it_student", division="it")
    async with client_for(user.email, "it") as c:
        ok = await c.post("/api/v1/files/local-upload", files={"file": ("my cv.pdf", PDF, "application/pdf")})
        assert ok.status_code == 200 and ok.json()["url"].startswith("/local-files/uploads/") and ok.json()["url"].endswith("-my-cv.pdf")
        assert storage.read_bytes(ok.json()["url"].removeprefix("/local-files/")) == PDF
        assert (await c.post("/api/v1/files/local-upload", files={"file": ("x.pdf", EXE, "application/pdf")})).status_code == 415


@pytest.mark.asyncio
async def test_career_upload_goes_through_storage_and_sniffs(client):
    ok = await client.post("/api/v1/public/career-upload", files={"file": ("cv.pdf", PDF, "application/pdf")})
    assert ok.status_code == 201 and storage.read_bytes(ok.json()["url"].removeprefix("/local-files/")) == PDF
    assert (await client.get(ok.json()["url"])).status_code == 404  # resumes are private
    assert (await client.post("/api/v1/public/career-upload", files={"file": ("x.pdf", EXE, "application/pdf")})).status_code == 415


def test_certificates_receipts_and_invoices_are_written_through_storage(monkeypatch):
    from datetime import date

    from app.services import billing_documents, certificates

    written: list[tuple[str, str]] = []
    monkeypatch.setattr(storage, "write_bytes", lambda key, data, content_type: written.append((key, data[:5].decode())))
    cert = certificates.generate_certificate_pdf(certificate_no="CERT-NEHN-1", student_name="Ada", program_title="Python", issued_on=date(2026, 10, 26), verification_code="V1", signatories=[])
    receipt = billing_documents.generate_receipt_pdf(receipt_no="RCT-NEHN-1", issued_on=date(2026, 10, 26), lines=[("Receipt No", "RCT-NEHN-1")])
    invoice = billing_documents.generate_invoice_pdf(invoice_no="INV-NEHN-1", payer_name="Ada", amount=10, currency="INR", issued_on=date(2026, 10, 26), reference_type="course")
    assert written == [("certificates/CERT-NEHN-1.pdf", "%PDF-"), ("receipts/RCT-NEHN-1.pdf", "%PDF-"), ("invoices/INV-NEHN-1.pdf", "%PDF-")]
    assert (cert, receipt, invoice) == ("/local-files/certificates/CERT-NEHN-1.pdf", "/local-files/receipts/RCT-NEHN-1.pdf", "/local-files/invoices/INV-NEHN-1.pdf")
