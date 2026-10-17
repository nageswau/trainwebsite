"""AGN-024 -- agent self-registration carries the three KYC documents (spec §4.2; DEC-SCOPE-224 K1/K2/K8; AC01-AC03)."""

import pytest
from sqlalchemy import func, select

from app.models import AgentOrgKycDocument, AuditLog, User
from app.services import agent_kyc as kyc
from app.services.storage import storage
from tests.agn001_helpers import PASSWORD, uniq
from tests.agn009_helpers import PDF, PNG
from tests.agn024_helpers import KYC_FIELDS, REGISTER, agent_form, ip_headers, kyc_files, kyc_rows, org_for, register_kyc_agent


async def _users_with(db, email: str) -> int:
    return await db.scalar(select(func.count()).select_from(User).where(User.email == email.lower()))


@pytest.mark.asyncio
async def test_agent_signup_stores_three_pending_documents(client, db_session):
    body = await register_kyc_agent(client, files=kyc_files(aadhaar=PNG))
    org = await org_for(db_session, body["user"]["id"])
    assert org.status == "pending" and org.kyc_required is True
    rows = {r.doc_type: r for r in await kyc_rows(db_session, org.id)}
    assert set(rows) == set(kyc.DOC_TYPES) and {r.status for r in rows.values()} == {"pending"}
    assert rows["aadhaar"].doc_number == "1234" and rows["aadhaar"].content_type == "image/png"
    assert rows["pan"].doc_number == "ABCDE1234F" and rows["pan"].file_key.startswith("agent-kyc/")
    assert storage.read_bytes(rows["pan"].file_key) == PDF
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "auth.register", AuditLog.entity_id == body["user"]["id"]))
    assert audit.metadata_json["kyc_documents"] == 3 and "ABCDE1234F" not in str(audit.metadata_json)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["pan_number", "aadhaar_last4", "license_number", "pan_file", "aadhaar_file", "license_file"])
async def test_each_missing_item_is_422_and_creates_nothing(client, db_session, missing):
    form, files = agent_form(), kyc_files()
    form.pop(missing, None)
    files.pop(missing, None)
    response = await client.post(REGISTER, data=form, files=files, headers=ip_headers())
    assert response.status_code == 422 and response.json()["detail"] == kyc.REQUIRED
    assert await _users_with(db_session, form["email"]) == 0


@pytest.mark.asyncio
async def test_json_agent_signup_is_refused_but_json_student_signup_still_works(client, db_session):
    email = f"{uniq('json')}@example.local"
    response = await client.post(REGISTER, json={"email": email, "password": PASSWORD, "full_name": "Json Agent", "division": "overseas", "account_type": "agent"})
    assert response.status_code == 422 and response.json()["detail"] == kyc.REQUIRED
    student = await client.post(REGISTER, json={"email": f"{uniq('stu')}@example.local", "password": PASSWORD, "full_name": "Json Student", "division": "overseas"})
    assert student.status_code == 201 and student.json()["user"]["role"] == "overseas_student"


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("pan_number", "ABC1234567"), ("aadhaar_last4", "123412341234"), ("license_number", "x")])
async def test_bad_numbers_are_422(client, db_session, field, value):
    form = agent_form(**{field: value})
    response = await client.post(REGISTER, data=form, files=kyc_files(), headers=ip_headers())
    assert response.status_code == 422 and value not in response.text
    assert await _users_with(db_session, form["email"]) == 0


@pytest.mark.asyncio
async def test_oversize_or_wrong_type_file_creates_nothing_and_stores_nothing(client, db_session, monkeypatch):
    written: list[str] = []
    real_write = storage.write_bytes
    monkeypatch.setattr(storage, "write_bytes", lambda key, data, ct: (written.append(key), real_write(key, data, ct))[1])
    form = agent_form()
    big = await client.post(REGISTER, data=form, files=kyc_files(license=PDF + b"0" * kyc.MAX_BYTES), headers=ip_headers())
    assert big.status_code == 413 and big.json()["detail"].startswith("Business licence: ")
    exe = await client.post(REGISTER, data=form, files=kyc_files(license=b"MZ\x90\x00binary"), headers=ip_headers())
    assert exe.status_code == 415 and exe.json()["detail"].startswith("Business licence: ")
    assert await _users_with(db_session, form["email"]) == 0 and written == []


@pytest.mark.asyncio
async def test_commit_failure_discards_stored_files(client, db_session, monkeypatch):
    from app.api import auth as auth_api

    discarded: list[str] = []
    monkeypatch.setattr(auth_api.kyc, "discard", lambda key: discarded.append(key))

    async def boom(*args, **kwargs):
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(auth_api, "_sync_role_assignment", boom)
    form = agent_form()
    with pytest.raises(RuntimeError):
        await client.post(REGISTER, data=form, files=kyc_files(), headers=ip_headers())
    assert len(discarded) == 3 and all(k.startswith("agent-kyc/") for k in discarded)
    assert await _users_with(db_session, form["email"]) == 0


@pytest.mark.asyncio
async def test_duplicate_email_is_409_before_any_file_is_stored(client, db_session, monkeypatch):
    body = await register_kyc_agent(client)
    written: list[str] = []
    monkeypatch.setattr(storage, "write_bytes", lambda key, data, ct: written.append(key))
    again = await client.post(REGISTER, data=agent_form(email=body["user"]["email"]), files=kyc_files(), headers=ip_headers())
    assert again.status_code == 409 and written == []


@pytest.mark.asyncio
async def test_multipart_student_signup_ignores_kyc(client, db_session):
    response = await client.post(REGISTER, data={"email": f"{uniq('mstu')}@example.local", "password": PASSWORD, "full_name": "Multipart Student", "division": "overseas", **KYC_FIELDS})
    assert response.status_code == 201 and response.json()["user"]["role"] == "overseas_student"
    assert await db_session.scalar(select(func.count()).select_from(AgentOrgKycDocument).where(AgentOrgKycDocument.uploaded_by_user_id == response.json()["user"]["id"])) == 0


@pytest.mark.asyncio
async def test_validation_errors_do_not_echo_the_submitted_form(client, db_session):
    form = agent_form()
    form.pop("full_name")
    response = await client.post(REGISTER, data=form, files=kyc_files(), headers=ip_headers())
    assert response.status_code == 422
    for secret in (PASSWORD, "ABCDE1234F", "LIC-2026/001"):
        assert secret not in response.text
    js = await client.post(REGISTER, json={"email": f"{uniq('j')}@example.local", "password": PASSWORD, "division": "overseas"})
    assert js.status_code == 422 and PASSWORD not in js.text


@pytest.mark.asyncio
async def test_cross_site_form_registration_is_refused(client, db_session):
    from app.core.config import settings

    form = agent_form()
    evil = await client.post(REGISTER, data=form, files=kyc_files(), headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403 and await _users_with(db_session, form["email"]) == 0
    referer = await client.post(REGISTER, data=form, files=kyc_files(), headers={"Referer": "https://evil.example/x"})
    assert referer.status_code == 403 and await _users_with(db_session, form["email"]) == 0
    ok = await client.post(REGISTER, data=form, files=kyc_files(), headers=ip_headers(Origin=settings.frontend_url.rstrip("/") + "/"))
    assert ok.status_code == 201


@pytest.mark.asyncio
async def test_oversize_registration_body_is_refused_before_it_is_read(client, db_session):
    from app.api.auth import MAX_REGISTRATION_BYTES

    form = agent_form()
    big = await client.post(REGISTER, data=form, files=kyc_files(), headers=ip_headers(**{"Content-Length": str(MAX_REGISTRATION_BYTES + 1)}))
    assert big.status_code == 413 and await _users_with(db_session, form["email"]) == 0
