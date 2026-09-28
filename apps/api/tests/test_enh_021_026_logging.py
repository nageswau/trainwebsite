"""AC-R4 -- no response or log line carries storage keys or sensitive free text (spec §11.3 S9/S10)."""
import logging

import pytest
from enh005_helpers import login, mk_school, mk_staff

from app.services.storage import storage

SECRET = "ZZ-sensitive-ZZ"


@pytest.fixture(autouse=True)
def _local_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "bucket", "")
    monkeypatch.setattr(storage, "local_dir", tmp_path)


@pytest.mark.asyncio
async def test_logs_and_responses_carry_no_sensitive_values(client, db_session, caplog):
    ctx = await mk_school(db_session, label="E21-Log")
    counselor = await mk_staff(db_session, ctx["school"], ctx["admin"], role="career_counselor")
    caplog.set_level(logging.DEBUG)
    await login(client, counselor.email)
    r = await client.post("/api/v1/school/career-counselor/records", json={"school_student_id": str(ctx["students"][0].id), "record_type": "counselling_note", "notes": SECRET, "weak_areas": [SECRET]})
    assert r.status_code == 201, r.text
    await client.patch(f"/api/v1/school/career-counselor/records/{r.json()['id']}", json={"academic_strengths": [SECRET], "status": "follow_up_required", "next_follow_up_date": "2099-01-01"})
    await login(client, ctx["coordinator"].email)
    sid = ctx["students"][0].id
    entry = await client.post(f"/api/v1/school/students/{sid}/portfolio/entries", json={"section": "internship", "title": "T", "organization": "Acme", "date_to": "2026-06-01", "completion_status": "completed", "mentor_name": SECRET, "feedback": SECRET})
    assert entry.status_code == 201, entry.text
    url = f"/api/v1/school/students/{sid}/portfolio/entries/{entry.json()['id']}/certificate"
    put = await client.put(url, files={"file": (f"{SECRET}.pdf", b"%PDF-1.4\n%%EOF\n", "application/pdf")})
    assert put.status_code == 200
    await client.get(url)
    await client.delete(url)
    responses = [r.text, entry.text, put.text, (await client.get(f"/api/v1/school/students/{sid}/portfolio")).text]
    assert not any("portfolio-certificates" in body for body in responses)
    logged = "\n".join(f"{rec.getMessage()} {getattr(rec, 'extra_fields', '')}" for rec in caplog.records)
    assert SECRET not in logged
    assert "portfolio-certificates/" not in logged
