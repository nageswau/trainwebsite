"""hrc-013 (DEC-SCOPE-391, spec docs/superpowers/specs/2026-11-04-hrc-013-candidate-bulk-import-design.md): a CSV/XLSX candidate import
with a read-only preview (I5), a commit that creates new people and matches known ones without changing them (I6/I7, AC2), a safe retry
(I8, AC3), a 1,000-row cap (Q-13, AC1), the `candidates.import` grant (I1) and a formula-safe report (I11)."""

import csv
import io
import random
import zipfile
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Candidate, CandidateImportBatch, CandidateImportRow, RecCandidateSource, UserPermissionOverride
from tests.rec038_helpers import _recruiter, _user, add, make_candidate, tag
from tests.tel026_helpers import headers

pytestmark = pytest.mark.asyncio
IMPORTS = "/api/v1/recruiter/candidate-imports"


def _mobile() -> str:
    return "9" + "".join(random.choices("0123456789", k=9))


def _csv(rows: list[dict], columns: tuple[str, ...] = ("name", "mobile", "email")) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(c, "") for c in columns])
    return buffer.getvalue().encode()


def _xlsx(rows: list[list[str]]) -> bytes:
    """A minimal one-sheet workbook with inline strings."""

    def cell(ref, value):
        return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'

    sheet = "".join(f'<row r="{i}">' + "".join(cell(f"{chr(65 + j)}{i}", v) for j, v in enumerate(r)) + "</row>" for i, r in enumerate(rows, start=1))
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rels = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    pkg = "http://schemas.openxmlformats.org/package/2006/relationships"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')  # fmt: skip
        z.writestr("_rels/.rels", f'<?xml version="1.0"?><Relationships xmlns="{pkg}"><Relationship Id="rId1" Type="{rels}/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", f'<?xml version="1.0"?><workbook xmlns="{main}" xmlns:r="{rels}"><sheets><sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", f'<?xml version="1.0"?><Relationships xmlns="{pkg}"><Relationship Id="rId1" Type="{rels}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", f'<?xml version="1.0"?><worksheet xmlns="{main}"><sheetData>{sheet}</sheetData></worksheet>')
    return buffer.getvalue()


async def _source(db, name: str = "Referral") -> str:
    return str(await db.scalar(select(RecCandidateSource.id).where(RecCandidateSource.name == name)))


async def _team(db):
    manager = await _user(db, "placement_manager", "global")
    recruiter = await _recruiter(db, manager)
    await db.commit()
    return manager, recruiter


async def _send(client, db, user, raw: bytes, *, preview=False, key: str | None = None, name="people.csv", source=None):
    data = {"source_id": source or await _source(db)}
    files = {"file": (name, raw, "text/csv")}
    hdrs = headers(user) | ({"Idempotency-Key": key} if key else {})
    return await client.post(f"{IMPORTS}/preview" if preview else IMPORTS, data=data, files=files, headers=hdrs)


async def _count(db) -> int:
    return await db.scalar(select(func.count()).select_from(Candidate))


async def test_template_lists_the_columns(client, db_session):
    _, recruiter = await _team(db_session)
    response = await client.get(f"{IMPORTS}/template", headers=headers(recruiter))
    assert response.status_code == 200, response.text
    header = response.text.splitlines()[0].split(",")
    assert header[:3] == ["name", "mobile", "email"] and "preferred_locations" in header and "current_salary" not in header
    assert response.headers["cache-control"] == "private, no-store"


async def test_preview_reports_every_row_and_writes_nothing(client, db_session):
    _, recruiter = await _team(db_session)
    known = await make_candidate(db_session, recruiter, mobile=f"+91{_mobile()}")
    await db_session.commit()
    fresh = _mobile()
    raw = _csv([
        {"name": "New Person", "mobile": fresh},
        {"name": "Known Person", "email": known.email},
        {"name": "Same Again", "mobile": f"+91 {fresh}"},
        {"name": "No Contact"},
        {"name": "Bad Mail", "email": "not-an-email"},
    ])  # fmt: skip
    before = await _count(db_session)
    response = await _send(client, db_session, recruiter, raw, preview=True)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["total_rows"], body["new_count"], body["matched_count"], body["error_count"]) == (5, 1, 2, 2)
    rows = {r["row_number"]: r for r in body["rows"]}
    assert rows[2]["status"] == "new" and rows[2]["name"] == "New Person"
    assert rows[3]["status"] == "matched" and rows[3]["candidate"]["candidate_code"] == known.candidate_code
    assert rows[4]["status"] == "matched" and rows[4]["same_as_row"] == 2 and rows[4]["candidate"] is None
    assert rows[5]["status"] == "error" and "mobile" in rows[5]["reason"].lower()
    assert rows[6]["status"] == "error" and "email" in rows[6]["reason"].lower()
    assert await _count(db_session) == before
    assert await db_session.scalar(select(func.count()).select_from(CandidateImportBatch).where(CandidateImportBatch.uploaded_by_user_id == recruiter.id)) == 0


async def test_commit_creates_new_people_and_matches_known_ones_unchanged(client, db_session):
    _, recruiter = await _team(db_session)
    known = await make_candidate(db_session, recruiter, location="Pune")
    await db_session.commit()
    fresh, mail = _mobile(), f"{tag('h13-')}@example.com"
    columns = ("name", "mobile", "email", "city", "preferred_locations", "experience_months", "source_detail")
    raw = _csv([
        {"name": "Kiran Rao", "mobile": fresh, "email": mail, "city": "Chennai", "preferred_locations": "Chennai; Bengaluru", "experience_months": "18", "source_detail": "Job fair"},
        {"name": "Renamed Known", "email": known.email.upper(), "city": "Delhi"},
        {"name": "Kiran Again", "email": mail},
        {"name": "Bad Year", "mobile": _mobile(), "experience_months": "lots"},
    ], columns)  # fmt: skip
    response = await _send(client, db_session, recruiter, raw, key=tag("k-"))
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["total_rows"], body["created_count"], body["matched_count"], body["error_count"], body["replayed"]) == (4, 1, 2, 1, False), body["rows"]
    rows = {r["row_number"]: r for r in body["rows"]}
    created = await db_session.get(Candidate, UUID(rows[2]["candidate"]["id"]))
    await db_session.refresh(created)
    assert created.name == "Kiran Rao" and created.email == mail and created.mobile_normalized == f"+91{fresh}"
    assert created.preferred_locations == ["Chennai", "Bengaluru"] and created.experience_months == 18 and created.city == "Chennai"
    assert created.source_detail == "Job fair" and str(created.source_id) == await _source(db_session) and created.status == "available"
    assert created.created_by_user_id == recruiter.id and created.owner_user_id == recruiter.id  # I10: hrc-012 O7
    assert rows[3]["status"] == "matched" and rows[3]["candidate"]["candidate_code"] == known.candidate_code
    assert rows[4]["status"] == "matched" and rows[4]["candidate"]["id"] == rows[2]["candidate"]["id"]  # AC2: the in-file repeat
    assert rows[5]["status"] == "error" and rows[5]["candidate"] is None
    # browser QA-02/03: the stored report keeps why a row matched, and a type error reads like the form
    assert (rows[3]["reason"], rows[4]["reason"]) == ("Already a candidate", "Same person as row 2")
    assert rows[5]["reason"] == "Total experience (months) must be a whole number"
    replay = (await client.get(f"{IMPORTS}/{body['id']}", headers=headers(recruiter))).json()
    assert [r["reason"] for r in replay["rows"]] == [r["reason"] for r in body["rows"]]
    await db_session.refresh(known)
    assert known.name != "Renamed Known" and known.location == "Pune"  # I7: nothing on a matched candidate changes
    batch_id = body["id"]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "candidate.create", AuditLog.entity_id == str(created.id)))
    assert audit.metadata_json["import_batch_id"] == batch_id
    batch_audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "candidate.import", AuditLog.entity_id == batch_id))
    assert batch_audit.metadata_json["created"] == 1 and batch_audit.metadata_json["error"] == 1
    stored = (await db_session.scalars(select(CandidateImportRow).where(CandidateImportRow.batch_id == UUID(batch_id)))).all()
    assert len(stored) == 4  # I9: rows keep status, candidate and reason -- never the file's name, mobile or email
    assert not {"name", "mobile", "email"} & set(CandidateImportRow.__table__.columns.keys())


async def test_a_retry_creates_nothing_new(client, db_session):
    """AC3 / I8: the same key replays; the same file under a new key replays too; another file under a used key is refused."""
    _, recruiter = await _team(db_session)
    raw = _csv([{"name": "Retry One", "mobile": _mobile()}, {"name": "Retry Two", "email": f"{tag('h13-')}@example.com"}])
    key = tag("k-")
    first = await _send(client, db_session, recruiter, raw, key=key)
    assert first.status_code == 201 and first.json()["created_count"] == 2
    before = await _count(db_session)
    again = await _send(client, db_session, recruiter, raw, key=key)
    assert again.status_code == 201 and again.json()["id"] == first.json()["id"] and again.json()["replayed"] is True
    reload = await _send(client, db_session, recruiter, raw, key=tag("k-"))
    assert reload.status_code == 201 and reload.json()["id"] == first.json()["id"] and reload.json()["replayed"] is True
    assert await _count(db_session) == before
    other = await _send(client, db_session, recruiter, _csv([{"name": "Other", "mobile": _mobile()}]), key=key)
    assert other.status_code == 422 and "Idempotency-Key" in other.json()["detail"]
    missing = await _send(client, db_session, recruiter, raw)
    assert missing.status_code == 422


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (b"name,phone_number\nA,9876543210\n", "Unknown column: phone_number"),
        (b"mobile,email\n9876543210,\n", "Missing required column: name"),
        (b"name,name,email\nA,B,a@example.com\n", "Duplicate column: name"),
        ("name,email\nJosé,j@example.com\n".encode("latin-1"), "not a valid UTF-8 CSV"),
        (b"name,email\n,\n", "The file has no candidate rows"),  # browser QA-01: a header-only file
    ],
)
async def test_a_bad_file_is_422_before_any_row(client, db_session, raw, message):
    _, recruiter = await _team(db_session)
    before = await _count(db_session)
    for preview in (True, False):
        response = await _send(client, db_session, recruiter, raw, preview=preview, key=tag("k-"))
        assert response.status_code == 422, response.text
        assert message in str(response.json()["detail"])
    assert await _count(db_session) == before


async def test_file_type_size_and_row_cap(client, db_session):
    _, recruiter = await _team(db_session)
    assert (await _send(client, db_session, recruiter, b"name\n", preview=True, name="people.txt")).status_code == 415
    assert (await _send(client, db_session, recruiter, b"name,email\n" + b"x" * (1024 * 1024), preview=True)).status_code == 413
    over = _csv([{"name": f"P{i}", "mobile": f"9{i:09d}"} for i in range(1001)])
    response = await _send(client, db_session, recruiter, over, preview=True)
    assert response.status_code == 422 and "1,000 rows" in str(response.json()["detail"])


async def test_an_xlsx_file_imports(client, db_session):
    _, recruiter = await _team(db_session)
    mail = f"{tag('h13-')}@example.com"
    raw = _xlsx([["Name", "Email", "Willing_to_relocate", "Available_from"], ["Xl Person", mail, "yes", "2026-12-01"]])
    response = await _send(client, db_session, recruiter, raw, key=tag("k-"), name="people.xlsx")
    assert response.status_code == 201, response.text
    created = await db_session.scalar(select(Candidate).where(Candidate.email == mail))
    assert created.willing_to_relocate is True and str(created.available_from) == "2026-12-01"


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        ("available_from", "01/12/2026", "Available from must be a date (YYYY-MM-DD)"),
        ("willing_to_relocate", "maybe", "Willing to relocate must be Yes or No"),
        ("passing_year", "20x4", "Passing year must be a whole number"),
    ],
)
async def test_a_type_error_reads_like_the_form(client, db_session, column, value, message):
    """Browser QA-02: no parser jargon in a row's reason."""
    _, recruiter = await _team(db_session)
    raw = _csv([{"name": "Typed", "email": f"{tag('h13-')}@example.com", column: value}], ("name", "email", column))
    body = (await _send(client, db_session, recruiter, raw, preview=True)).json()
    assert body["rows"][0]["reason"] == message


async def test_a_thousand_rows_import_with_a_report(client, db_session):
    """AC1."""
    _, recruiter = await _team(db_session)
    base = random.randint(10**8, 9 * 10**8)
    raw = _csv([{"name": f"Bulk {i}", "email": f"bulk{base}-{i}@example.com"} for i in range(1000)])
    response = await _send(client, db_session, recruiter, raw, key=tag("k-"))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["total_rows"] == 1000 and body["created_count"] == 1000 and len(body["rows"]) == 1000


async def test_the_inactive_source_is_refused(client, db_session):
    _, recruiter = await _team(db_session)
    source = await add(db_session, RecCandidateSource(name=tag("Old "), active=False))
    await db_session.commit()
    response = await _send(client, db_session, recruiter, _csv([{"name": "A", "mobile": _mobile()}]), preview=True, source=str(source.id))
    assert response.status_code == 422 and "source" in response.json()["detail"].lower()


async def test_who_may_import(client, db_session):
    """I1: candidate writers holding `candidates.import`; recruiters and placement managers hold it by default; a reader role never."""
    manager, recruiter = await _team(db_session)
    hr = await _user(db_session, "hr_team", "it")
    sup = await _user(db_session, "super_admin", "global")
    bdm = await _user(db_session, "bdm", "it")
    await db_session.commit()
    raw = _csv([{"name": "Grant Check", "mobile": _mobile()}])
    for user in (recruiter, manager, sup):
        assert (await _send(client, db_session, user, raw, preview=True)).status_code == 200, user.role
    for user in (hr, bdm):
        assert (await client.get(f"{IMPORTS}/template", headers=headers(user))).status_code == 403
        assert (await _send(client, db_session, user, raw, preview=True)).status_code == 403
    await add(db_session, UserPermissionOverride(user_id=hr.id, resource="candidates", action="import", effect="allow", reason="hrc-013 test"))
    await add(db_session, UserPermissionOverride(user_id=recruiter.id, resource="candidates", action="import", effect="deny", reason="hrc-013 test"))
    await db_session.commit()
    assert (await _send(client, db_session, hr, raw, preview=True)).status_code == 403
    response = await _send(client, db_session, recruiter, raw, preview=True)
    assert response.status_code == 403 and "import" in response.json()["detail"].lower()
    assert (await client.get(IMPORTS, headers=headers(recruiter))).status_code == 403
    assert (await client.get(f"{IMPORTS}/template")).status_code == 401


async def test_history_and_report_are_scoped(client, db_session):
    manager, recruiter = await _team(db_session)
    other = await _recruiter(db_session, manager)
    await db_session.commit()
    raw = _csv([{"name": '=HYPERLINK("http://x")', "mobile": _mobile()}, {"name": "Err", "email": "bad"}])
    body = (await _send(client, db_session, recruiter, raw, key=tag("k-"), name="campus.csv")).json()
    mine = (await client.get(IMPORTS, headers=headers(recruiter))).json()
    assert mine["items"][0]["id"] == body["id"] and mine["items"][0]["file_name"] == "campus.csv" and mine["items"][0]["error_count"] == 1
    assert body["id"] not in [i["id"] for i in (await client.get(IMPORTS, headers=headers(other))).json()["items"]]
    assert (await client.get(f"{IMPORTS}/{body['id']}", headers=headers(other))).status_code == 404
    assert (await client.get(f"{IMPORTS}/{uuid4()}", headers=headers(recruiter))).status_code == 404
    seen = await client.get(f"{IMPORTS}/{body['id']}", headers=headers(manager))
    assert seen.status_code == 200 and len(seen.json()["rows"]) == 2 and seen.json()["replayed"] is False
    report = await client.get(f"{IMPORTS}/{body['id']}/report.csv", headers=headers(recruiter))
    assert report.status_code == 200 and report.headers["content-type"].startswith("text/csv")
    lines = list(csv.reader(io.StringIO(report.text)))
    assert lines[0] == ["row_number", "status", "candidate_code", "name", "reason"]
    assert lines[1][3].startswith("'=")  # I11: formula-escaped
    assert lines[2][1] == "error" and lines[2][2] == ""
    assert (await client.get(f"{IMPORTS}/{body['id']}/report.csv", headers=headers(other))).status_code == 404
