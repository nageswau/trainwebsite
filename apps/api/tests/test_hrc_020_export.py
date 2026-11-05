"""hrc-020 -- the Find Candidates export (DEC-SCOPE-401 X8-X12): the `candidates.export` grant (AC2), the audit row (AC3), the columns
by field grant, the formula guard and the row cap. Candidates hold this test's own skills, so only they can match."""

import csv
import io
import zipfile

import pytest
from sqlalchemy import select

from app.api import crm_exports
from app.core import rbac
from app.models import AuditLog, UserPermissionOverride
from tests.rec038_helpers import _user, add
from tests.tel026_helpers import headers
from tests.test_rec_013_find_candidates import _world

pytestmark = pytest.mark.asyncio
EXPORT = "/api/v1/recruiter/candidates/search/export"


def _rows(response) -> list[list[str]]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    return list(csv.reader(io.StringIO(response.text.lstrip("﻿"))))


async def _grant(db, user, effect="allow"):
    await add(db, UserPermissionOverride(user_id=user.id, resource="candidates", action="export", effect=effect, reason="hrc-020 test"))
    await db.commit()


async def test_default_holders():
    """X12: placement managers by default; super_admin implicitly; nobody else."""
    holders = {role for role, keys in rbac.DEFAULT_GRANTS.items() if "candidates.export" in keys}
    assert holders == {"placement_manager"}


async def test_export_without_the_grant_is_403(client, db_session):
    """AC2: a recruiter (no default grant) and an explicit deny are refused, before the body is read; a non-reader too."""
    w = await _world(client, db_session)  # signs in a recruiter
    java = await w.skill("Java")
    await w.candidate(java)
    refused = await client.post(EXPORT, json={"all": [java.name]})
    assert refused.status_code == 403 and "export" in refused.json()["detail"].lower()
    assert (await client.post(EXPORT, json="junk")).status_code == 403
    bdm = await _user(db_session, "bdm", "it")
    await _grant(db_session, bdm)
    assert (await client.post(EXPORT, json={"all": [java.name]}, headers=headers(bdm))).status_code == 403
    pm = await _user(db_session, "placement_manager", "it")
    await _grant(db_session, pm, "deny")
    assert (await client.post(EXPORT, json={"all": [java.name]}, headers=headers(pm))).status_code == 403
    assert (await db_session.scalar(select(AuditLog.id).where(AuditLog.user_id == w.actor.id, AuditLog.action == crm_exports.EXPORT_ACTION))) is None


async def test_csv_follows_the_search_and_is_audited(client, db_session):
    """AC3 plus X10: the rows the search finds, in its order; the audit row holds the filters and the row count."""
    w = await _world(client, db_session, role="pm")
    java, go = await w.skill("Java"), await w.skill("Go")
    senior = await w.candidate(java, name='=HYPERLINK("http://x")', experience_months=60, location="Pune", expected_salary=900000)
    junior = await w.candidate(java, name="Junior Dev", experience_months=12)
    await w.candidate(go)
    body = {"all": [java.name], "sort": "experience"}
    rows = _rows(await client.post(f"{EXPORT}?format=csv", json=body))
    header = rows[0]
    assert header[:3] == ["Candidate ID", "Name", "Preferred role"] and "Expected salary (₹ a year)" in header
    assert "Email" not in header and "Mobile" not in header
    assert [r[0] for r in rows[1:]] == [senior.candidate_code, junior.candidate_code]
    first = dict(zip(header, rows[1], strict=True))
    assert first["Name"].startswith("'=")  # the formula guard
    assert first["Experience (years)"] == "5" and first["Location"] == "Pune" and java.name in first["Skills"]
    assert first["Expected salary (₹ a year)"] == "900000"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.user_id == w.actor.id, AuditLog.action == crm_exports.EXPORT_ACTION))
    assert audit.entity_type == "candidate_search" and audit.entity_id == "find_candidates"
    assert audit.metadata_json == {"format": "csv", "filters": body, "rows": 2}


async def test_compensation_column_and_filter_need_their_grant(client, db_session):
    """X10 / X5: without `candidates.compensation.view` the salary column is left out and a salary filter is a 403."""
    w = await _world(client, db_session)
    java = await w.skill("Java")
    await w.candidate(java, expected_salary=500000)
    await _grant(db_session, w.actor)
    await add(db_session, UserPermissionOverride(user_id=w.actor.id, resource="candidates.compensation", action="view", effect="deny", reason="hrc-020 test"))
    await db_session.commit()
    rows = _rows(await client.post(EXPORT, json={"all": [java.name]}))
    assert all("salary" not in label.lower() for label in rows[0]) and len(rows) == 2
    assert (await client.post(EXPORT, json={"all": [java.name], "salary_min": 100000})).status_code == 403


async def test_xlsx_bad_body_and_format(client, db_session):
    w = await _world(client, db_session, role="pm")
    java = await w.skill("Java")
    await w.candidate(java, name="Xlsx Person")
    response = await client.post(f"{EXPORT}?format=xlsx", json={"all": [java.name]})
    assert response.status_code == 200 and response.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert 'filename="candidates.xlsx"' in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as book:
        assert "Xlsx Person" in book.read("xl/worksheets/sheet1.xml").decode()
    assert (await client.post(f"{EXPORT}?format=pdf", json={"all": [java.name]})).status_code == 422
    assert (await client.post(EXPORT, json={"experience_min_months": 12})).status_code == 422


async def test_over_the_cap_is_422_and_writes_nothing(client, db_session, monkeypatch):
    """X9: more rows than the cap -> narrow the filters; no audit row, no file."""
    monkeypatch.setattr(crm_exports, "ROW_CAP", 1)
    w = await _world(client, db_session, role="pm")
    java = await w.skill("Java")
    await w.candidate(java)
    await w.candidate(java)
    over = await client.post(EXPORT, json={"all": [java.name]})
    assert over.status_code == 422 and "narrow" in over.json()["detail"].lower()
    assert (await db_session.scalar(select(AuditLog.id).where(AuditLog.user_id == w.actor.id, AuditLog.action == crm_exports.EXPORT_ACTION))) is None


async def test_an_override_allow_lets_a_recruiter_export(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    await w.candidate(java)
    await _grant(db_session, w.actor)
    assert len(_rows(await client.post(EXPORT, json={"all": [java.name]}))) == 2
