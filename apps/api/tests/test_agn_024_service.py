"""AGN-024 -- services.agent_kyc rules (spec §4.2, §4.4, §4.5; DEC-SCOPE-224 K2/K3/K8)."""

import io

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import select

from app.models import AgentOrgKycDocument, Notification
from app.services import agent_kyc as kyc
from tests.agn001_helpers import mk_active_org, uniq
from tests.agn009_helpers import PDF, PNG


def upload(data: bytes, name: str = "doc.pdf") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name)


@pytest.mark.parametrize("raw,expected", [("abcde1234f", "ABCDE1234F"), (" ABCDE1234F ", "ABCDE1234F")])
def test_pan_is_upper_cased_and_validated(raw, expected):
    assert kyc.clean_number("pan", raw) == expected


@pytest.mark.parametrize("doc_type,raw", [("pan", "ABCD1234FF"), ("pan", ""), ("aadhaar", "12345"), ("aadhaar", "123412341234"), ("aadhaar", "12a4"), ("business_license", "ab"), ("business_license", "x" * 65), ("business_license", "LIC<1>")])
def test_bad_numbers_are_422_without_echoing_the_value(doc_type, raw):
    with pytest.raises(HTTPException) as exc:
        kyc.clean_number(doc_type, raw)
    assert exc.value.status_code == 422 and (not raw or raw not in exc.value.detail)


def test_clean_numbers_requires_all_three():
    with pytest.raises(HTTPException) as exc:
        kyc.clean_numbers({"pan_number": "ABCDE1234F", "aadhaar_last4": "1234"})
    assert exc.value.status_code == 422 and exc.value.detail == kyc.REQUIRED
    assert kyc.clean_numbers({"pan_number": "abcde1234f", "aadhaar_last4": "1234", "license_number": "LIC-2026/001"}) == {
        "pan": "ABCDE1234F", "aadhaar": "1234", "business_license": "LIC-2026/001"}  # fmt: skip


def test_require_files_needs_three_non_empty_uploads():
    with pytest.raises(HTTPException) as exc:
        kyc.require_files({"pan_file": upload(PDF), "aadhaar_file": upload(PDF)})
    assert exc.value.detail == kyc.REQUIRED
    files = kyc.require_files({"pan_file": upload(PDF), "aadhaar_file": upload(PDF), "license_file": upload(PDF)})
    assert set(files) == set(kyc.DOC_TYPES)


@pytest.mark.asyncio
async def test_read_kyc_file_names_the_document_on_error():
    with pytest.raises(HTTPException) as exc:
        await kyc.read_kyc_file("aadhaar", upload(b"MZ\x90\x00 not a pdf", "evil.pdf"))
    assert exc.value.status_code == 415 and exc.value.detail.startswith("Aadhaar card: ")
    with pytest.raises(HTTPException) as exc:
        await kyc.read_kyc_file("pan", upload(PDF + b"0" * kyc.MAX_BYTES))
    assert exc.value.status_code == 413 and exc.value.detail == "PAN card: The file must be at most 5 MB"
    data, content_type, name = await kyc.read_kyc_file("pan", upload(PNG, "pan.png"))
    assert content_type == "image/png" and name == "pan.png" and b"tEXt" not in data


def test_masking():
    assert kyc.mask("pan", "ABCDE1234F") == "ABCDE****F"
    assert kyc.mask("aadhaar", "1234") == "XXXX XXXX 1234"
    assert kyc.mask("business_license", "LIC-1") == "LIC-1"


def test_store_and_discard_only_touch_kyc_keys():
    key = kyc.store(PDF, "application/pdf")
    assert key.startswith("agent-kyc/") and len(key) == len("agent-kyc/") + 32
    kyc.discard("agent-documents/not-mine")  # refused, logged, no exception
    kyc.discard(key)


async def _org_with_docs(db, statuses: dict[str, str], *, kyc_required: bool = True):
    ctx = await mk_active_org(db, name=f"KYC {uniq()}")
    org = ctx["org"]
    org.status, org.kyc_required = "pending", kyc_required
    for doc_type, status in statuses.items():
        db.add(AgentOrgKycDocument(org_id=org.id, doc_type=doc_type, doc_number="1234" if doc_type == "aadhaar" else "ABCDE1234F", file_key=f"agent-kyc/{uniq()}",
                                   content_type="application/pdf", file_size=10, status=status, rejection_reason="Blurry" if status == "rejected" else None,
                                   uploaded_by_user_id=ctx["master"].id))  # fmt: skip
    await db.commit()
    return ctx


@pytest.mark.asyncio
@pytest.mark.parametrize("statuses", [{}, {"pan": "verified", "aadhaar": "verified"}, {"pan": "verified", "aadhaar": "verified", "business_license": "pending"}, {"pan": "verified", "aadhaar": "rejected", "business_license": "verified"}])
async def test_assert_complete_refuses_until_all_three_verified(db_session, statuses):
    ctx = await _org_with_docs(db_session, statuses)
    with pytest.raises(HTTPException) as exc:
        await kyc.assert_complete(db_session, ctx["org"])
    assert exc.value.status_code == 409 and exc.value.detail == kyc.NOT_VERIFIED


@pytest.mark.asyncio
async def test_assert_complete_passes_when_verified_or_not_required(db_session):
    ok = await _org_with_docs(db_session, {t: "verified" for t in kyc.DOC_TYPES})
    await kyc.assert_complete(db_session, ok["org"])
    legacy = await _org_with_docs(db_session, {}, kyc_required=False)
    await kyc.assert_complete(db_session, legacy["org"])


@pytest.mark.asyncio
async def test_views_summaries_and_rejection_notice(db_session):
    ctx = await _org_with_docs(db_session, {"pan": "verified", "aadhaar": "rejected", "business_license": "pending"})
    docs = await kyc.documents(db_session, ctx["org"].id)
    assert [d.doc_type for d in docs] == ["pan", "aadhaar", "business_license"]
    assert kyc.agent_view(docs[0])["doc_number_display"] == "ABCDE****F" and "doc_number" not in kyc.agent_view(docs[0])
    assert kyc.admin_view(docs[0])["doc_number"] == "ABCDE1234F" and "file_key" not in kyc.admin_view(docs[0])
    assert (await kyc.summaries(db_session, [ctx["org"].id]))[ctx["org"].id] == {"verified": 1, "rejected": 1, "pending": 1}
    await kyc.notify_rejected(db_session, ctx["org"].id, docs[1])
    await db_session.commit()
    note = await db_session.scalar(select(Notification).where(Notification.user_id == ctx["master"].id).order_by(Notification.created_at.desc()))
    assert note.title == "Verification document rejected" and "Aadhaar card" in note.body and "Blurry" in note.body and "1234" not in note.body
    assert note.action_url == kyc.STATUS_URL
