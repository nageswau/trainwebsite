"""upc-005 -- University CSV import (spec §1 IM1-IM12; AC1-AC5)."""

import csv
import io
import time
import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, University, UniversityImportBatch
from tests.upc003_helpers import BASE, as_role, catalogue_country, create, internal_country, login, make_head, url

IMPORT = f"{BASE}/import"
IMPORTS = f"{BASE}/imports"
HEADER = "name,country,city,institution_type"


def _tag() -> str:
    return uuid.uuid4().hex[:8]


def _csv(*rows: str, header: str = HEADER, bom: bool = False) -> bytes:
    text = "\n".join([header, *rows]) + "\n"
    return (("﻿" if bom else "") + text).encode()


async def _upload(client, content: bytes, key: str | None = None):
    headers = {"Idempotency-Key": key or f"k-{_tag()}"}
    return await client.post(IMPORT, files={"file": ("universities.csv", content, "text/csv")}, headers=headers)


async def _ok(client, content: bytes, key: str | None = None) -> dict:
    response = await _upload(client, content, key)
    assert response.status_code == 201, response.text
    return response.json()


async def _head(client, db):
    head = await make_head(db)
    await login(client, head)
    return head


# --- template + happy path (IM1, IM2, IM3, IM4, IM11) ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_template_lists_the_columns_and_needs_an_importer(client, db_session):
    await _head(client, db_session)
    response = await client.get(f"{IMPORTS}/template")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    header = next(csv.reader(io.StringIO(response.text)))
    assert header[:4] == ["name", "country", "city", "institution_type"] and "overview" in header and "rankings" not in header
    await as_role(client, db_session, "counselor", "overseas")
    assert (await client.get(f"{IMPORTS}/template")).status_code == 403


@pytest.mark.asyncio
async def test_rows_are_created_unowned_internal_and_audited(client, db_session):
    head = await _head(client, db_session)
    gb, jp = await catalogue_country(db_session), await internal_country(db_session)
    tag = _tag()
    header = f"{HEADER},ownership_type,priority,partnership_potential,course_levels,popular_programs,existing_relationship,website,overview"
    content = _csv(
        f"Alpha {tag} University,gb,London,University,Public,a,HIGH,ug; phd,Business; Law,New,alpha.ac.uk,An overview",
        f"Beta {tag} School,{jp.name.upper()},Tokyo,language school,,,,,,,,",
        header=header,
    )
    report = await _ok(client, content)
    assert (report["total_rows"], report["created_count"], report["duplicate_count"], report["invalid_count"]) == (2, 2, 0, 0)
    assert report["uploaded_by"]["id"] == str(head.id)
    alpha, beta = report["rows"]
    assert alpha["row_number"] == 2 and alpha["status"] == "created" and alpha["university_code"].startswith("UNV-")
    assert alpha["name"] == f"Alpha {tag} University" and alpha["country"] == "gb" and alpha["reason"] is None
    uni = await db_session.get(University, uuid.UUID(alpha["university_id"]))
    await db_session.refresh(uni)
    assert (uni.country_id, uni.city, uni.institution_type, uni.ownership_type, uni.priority, uni.partnership_potential) == (gb.id, "London", "university", "public", "A", "high")
    assert uni.course_levels == ["UG", "PhD"] and uni.popular_programs == ["Business", "Law"] and uni.existing_relationship == "new"
    assert uni.website and uni.overview == "An overview"
    assert (uni.primary_manager_user_id, uni.backup_manager_user_id, uni.catalogue_visible, uni.active) == (None, None, False, True)
    assert uni.stage == "target_university"  # IM4: upc-007's first stage, as for a manual create
    second = await db_session.get(University, uuid.UUID(beta["university_id"]))
    await db_session.refresh(second)
    assert second.country_id == jp.id and second.institution_type == "language_school"
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id.in_([alpha["university_id"], report["id"]])))).all()
    actions = {a.action: a.metadata_json for a in audits}
    assert actions["university.create"] == {"code": alpha["university_code"], "import_batch_id": report["id"]}
    assert actions["university.import"]["created"] == 2 and "file_sha256" in actions["university.import"]


@pytest.mark.asyncio
async def test_a_file_with_a_bom_and_crlf_imports(client, db_session):
    await _head(client, db_session)
    content = ("﻿" + HEADER + "\r\n" + f"Gamma {_tag()} College,GB,Leeds,college\r\n").encode()
    report = await _ok(client, content)
    assert report["created_count"] == 1


# --- invalid and duplicate rows (IM2, IM3, IM5) ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_invalid_rows_are_reported_with_their_reason(client, db_session):
    await _head(client, db_session)
    tag = _tag()
    content = _csv(
        f"Delta {tag},Atlantis,Paris,university",
        f"Epsilon {tag},GB,Leeds,castle",
        f"Zeta {tag},GB,,university",
        f"Eta {tag},GB,Leeds,university",
    )
    report = await _ok(client, content)
    assert (report["created_count"], report["invalid_count"]) == (1, 3)
    unknown, bad_type, no_city, ok = report["rows"]
    assert unknown["status"] == "invalid" and unknown["reason"] == "Unknown country: Atlantis"
    assert bad_type["status"] == "invalid" and bad_type["reason"].startswith("institution_type")
    assert no_city["status"] == "invalid" and no_city["reason"].startswith("city")
    assert ok["status"] == "created" and unknown["university_id"] is None


@pytest.mark.asyncio
async def test_duplicates_of_the_master_and_of_earlier_rows_are_reported_not_created(client, db_session):
    await _head(client, db_session)
    gb, jp = await catalogue_country(db_session), await internal_country(db_session)
    tag = _tag()
    existing = await create(client, gb.id, name=f"ABC {tag} University")
    inactive = await create(client, gb.id, name=f"Old {tag} College")
    assert (await client.post(url(inactive["id"], "deactivate"))).status_code == 200
    content = _csv(
        f"abc   {tag} UNIVERSITY,GB,London,university",
        f"old {tag} college,United Kingdom,London,college",
        f"New {tag} Institute,GB,Bath,institute",
        f"new {tag} institute,gb,Bath,institute",
        f"ABC {tag} University,JP,Osaka,university",
    )
    report = await _ok(client, content)
    assert (report["created_count"], report["duplicate_count"]) == (2, 3)
    master, old, first, repeat, other_country = report["rows"]
    assert master["status"] == "duplicate" and master["matches"] == [existing["university_code"]] and existing["university_code"] in master["reason"]
    assert old["status"] == "duplicate" and old["matches"] == [inactive["university_code"]]
    assert first["status"] == "created" and repeat["status"] == "duplicate" and repeat["reason"] == "Repeats row 4 of this file"
    assert other_country["status"] == "created"
    other = await db_session.get(University, uuid.UUID(other_country["university_id"]))
    assert other.country_id == jp.id


# --- file-level rejections (IM1, IM6, IM7) --------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("header", "message"),
    [
        ("name,country,city", "Missing required column: institution_type"),
        (f"{HEADER},rankings", "Unknown column: rankings"),
        (f"{HEADER},city", "Duplicate column: city"),
    ],
)
async def test_wrong_headers_reject_the_whole_file(client, db_session, header, message):
    await _head(client, db_session)
    tag = _tag()
    response = await _upload(client, _csv(f"Theta {tag},GB,York,university,x", header=header))
    assert response.status_code == 422 and response.json()["detail"] == message
    assert await db_session.scalar(select(University.id).where(University.name == f"Theta {tag}")) is None


@pytest.mark.asyncio
async def test_key_empty_file_and_row_cap_are_checked(client, db_session):
    await _head(client, db_session)
    no_key = await client.post(IMPORT, files={"file": ("u.csv", _csv("A,GB,York,university"), "text/csv")})
    assert no_key.status_code == 422 and "Idempotency-Key" in no_key.json()["detail"]
    assert (await _upload(client, _csv())).status_code == 422
    big = _csv(*(f"U{i},GB,York,university" for i in range(5001)))
    response = await _upload(client, big)
    assert response.status_code == 422 and response.json()["detail"] == "The file has more than 5000 filled-in rows"


@pytest.mark.asyncio
async def test_same_key_replays_and_a_new_key_creates_nothing_new(client, db_session):
    await _head(client, db_session)
    tag = _tag()
    content = _csv(f"Iota {tag} University,GB,York,university", f"Kappa {tag} University,GB,York,university")
    first = await _ok(client, content, key=f"same-{tag}")
    replay = await _ok(client, content, key=f"same-{tag}")
    assert replay == first
    reused = await _upload(client, _csv(f"Other {tag},GB,York,university"), key=f"same-{tag}")
    assert reused.status_code == 422 and reused.json()["detail"] == "Idempotency-Key was already used for a different file"
    again = await _ok(client, content)  # AC2: the same file, a new key
    assert (again["created_count"], again["duplicate_count"]) == (0, 2) and again["id"] != first["id"]
    names = (await db_session.scalars(select(University.name).where(University.name.like(f"% {tag} University")))).all()
    assert len(names) == 2


# --- roles, history and the report download (IM8, IM10) -------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "division", "status"),
    [
        ("partnership_manager", "overseas", 403),
        ("counselor", "overseas", 403),
        ("overseas_admin", "it", 403),
        ("overseas_admin", "overseas", 201),
        ("super_admin", "global", 201),
    ],
)
async def test_only_heads_overseas_admins_and_super_admins_import(client, db_session, role, division, status):
    await as_role(client, db_session, role, division)
    response = await _upload(client, _csv(f"Lambda {_tag()},GB,York,university"))
    assert response.status_code == status, response.text


@pytest.mark.asyncio
async def test_history_shows_own_imports_and_hides_others(client, db_session):
    await _head(client, db_session)
    mine = await _ok(client, _csv(f"Mu {_tag()},GB,York,university"))
    page = (await client.get(IMPORTS)).json()
    assert set(page) == {"items", "total", "limit", "offset"} and page["items"][0]["id"] == mine["id"]
    assert "rows" not in page["items"][0] and page["items"][0]["created_count"] == 1
    assert (await client.get(f"{IMPORTS}/{mine['id']}")).json() == mine
    await _head(client, db_session)  # another head
    assert all(item["id"] != mine["id"] for item in (await client.get(IMPORTS)).json()["items"])
    assert (await client.get(f"{IMPORTS}/{mine['id']}")).status_code == 404
    assert (await client.get(f"{IMPORTS}/{mine['id']}/report.csv")).status_code == 404
    await as_role(client, db_session, "super_admin", "global")
    assert (await client.get(f"{IMPORTS}/{mine['id']}")).status_code == 200


@pytest.mark.asyncio
async def test_report_csv_escapes_formula_cells(client, db_session):
    await _head(client, db_session)
    tag = _tag()
    report = await _ok(client, _csv(f"=HYPERLINK(1) {tag},GB,York,university", f"Nu {tag},@SUM(1),York,university"))
    response = await client.get(f"{IMPORTS}/{report['id']}/report.csv")
    assert response.status_code == 200 and "attachment" in response.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == ["row_number", "status", "name", "country", "university_code", "reason"]
    assert rows[1][2] == f"'=HYPERLINK(1) {tag}" and rows[2][3] == "'@SUM(1)" and rows[2][1] == "invalid"


# --- AC1: a 1,000-row file ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_thousand_row_file_imports_with_an_accurate_report(client, db_session):
    await _head(client, db_session)
    tag = _tag()
    rows = [f"Bulk {tag} University {i},GB,City {i},university" for i in range(985)]
    rows += [f"Bulk {tag} University {i},GB,City {i},university" for i in range(10)]  # 10 in-file duplicates
    rows += [f"Bad {tag} {i},Nowhere,City,university" for i in range(5)]  # 5 invalid
    started = time.monotonic()
    report = await _ok(client, _csv(*rows))
    assert (report["total_rows"], report["created_count"], report["duplicate_count"], report["invalid_count"]) == (1000, 985, 10, 5)
    assert [r["row_number"] for r in report["rows"]] == list(range(2, 1002))
    codes = [r["university_code"] for r in report["rows"] if r["status"] == "created"]
    assert len(set(codes)) == 985
    assert time.monotonic() - started < 30
    batch = await db_session.get(UniversityImportBatch, uuid.UUID(report["id"]))
    assert (batch.total_rows, batch.created_count, batch.duplicate_count, batch.invalid_count) == (1000, 985, 10, 5)
