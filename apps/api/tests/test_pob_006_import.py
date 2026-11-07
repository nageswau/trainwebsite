"""pob-006 (DEC-SCOPE-418 G1-G3, I1-I11): the company and contact import -- a read-only preview, a commit that creates or matches each row and
never changes a known record, a safe retry, a per-row report and the `crm.import` grant. The shared test database is never truncated, so every
value is unique per test."""

import csv
import io
import time
import uuid
from uuid import UUID

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select

from app.models import AuditLog, Company, CompanyContact, CrmImportBatch, RecIndustry, UserPermissionOverride
from tests.rec001_helpers import login, make_pm, make_recruiter, make_user
from tests.test_rec_009_candidates import mail, mobile

pytestmark = pytest.mark.asyncio
IMPORTS = "/api/v1/recruiter/company-imports"
COMPANIES = "/api/v1/recruiter/companies"
COLUMNS = ("company_name", "website", "industry", "priority", "contact_name", "contact_mobile", "contact_email", "contact_source", "contact_decision_maker")


def unique(prefix: str = "Import Co") -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


def _csv(rows: list[dict], columns: tuple[str, ...] = COLUMNS) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(c, "") for c in columns])
    return buffer.getvalue().encode()


async def _preview(client, raw: bytes, name: str = "companies.csv"):
    return await client.post(f"{IMPORTS}/preview", files={"file": (name, raw, "text/csv")})


async def _commit(client, raw: bytes, key: str | None = None, name: str = "companies.csv"):
    return await client.post(IMPORTS, files={"file": (name, raw, "text/csv")}, headers={"Idempotency-Key": key or uuid.uuid4().hex})


async def _company(client, name: str | None = None, **over) -> dict:
    response = await client.post(COMPANIES, json={"name": name or unique("Known Co")} | over)
    assert response.status_code == 201, response.text
    return response.json()["company"]


async def _contacts(db, company_id) -> list[CompanyContact]:
    db.expire_all()
    return list((await db.scalars(select(CompanyContact).where(CompanyContact.company_id == UUID(str(company_id))))).all())


async def _by_name(db, name: str) -> Company | None:
    db.expire_all()
    return await db.scalar(select(Company).where(Company.name == name))


async def _manager(client, db):
    manager = await make_pm(db)
    await login(client, manager)
    return manager


async def _allowed_recruiter(client, db, manager=None):
    recruiter = await make_recruiter(db, manager or await make_pm(db))
    db.add(UserPermissionOverride(user_id=recruiter.id, resource="crm", action="import", effect="allow", reason="pob-006 test"))
    await db.commit()
    await login(client, recruiter)
    return recruiter


# --- G1-G3 grants ---------------------------------------------------------------------------------------------------------------------


async def test_a_manager_holds_the_grant_and_a_plain_recruiter_does_not(client, db_session):
    await _manager(client, db_session)
    assert (await client.get(f"{IMPORTS}/template")).status_code == 200
    await login(client, await make_recruiter(db_session, await make_pm(db_session)))
    response = await _preview(client, _csv([{"company_name": unique()}]))
    assert response.status_code == 403
    assert (await client.get(IMPORTS)).status_code == 403


async def test_an_allowed_recruiter_may_import_and_a_denied_manager_may_not(client, db_session):
    await _allowed_recruiter(client, db_session)
    assert (await _preview(client, _csv([{"company_name": unique()}]))).status_code == 200
    manager = await make_pm(db_session)
    db_session.add(UserPermissionOverride(user_id=manager.id, resource="crm", action="import", effect="deny", reason="pob-006 test"))
    await db_session.commit()
    await login(client, manager)
    assert (await _preview(client, _csv([{"company_name": unique()}]))).status_code == 403


async def test_a_grant_never_lets_another_role_in(client, db_session):
    """G2: an allow override on a role outside the recruiter gate changes nothing."""
    outsider = await make_user(db_session, "hr_team", "it")
    db_session.add(UserPermissionOverride(user_id=outsider.id, resource="crm", action="import", effect="allow", reason="pob-006 test"))
    await db_session.commit()
    await login(client, outsider)
    assert (await _preview(client, _csv([{"company_name": unique()}]))).status_code == 403


async def test_signed_out_is_refused(client):
    assert (await client.get(IMPORTS)).status_code == 401


# --- I1-I3 the file ---------------------------------------------------------------------------------------------------------------------


async def test_the_template_lists_every_column_and_needs_only_the_company_name(client, db_session):
    await _manager(client, db_session)
    response = await client.get(f"{IMPORTS}/template")
    header = next(csv.reader(io.StringIO(response.text)))
    assert header[0] == "company_name" and {"contact_name", "contact_mobile", "contact_email", "industry", "priority"} <= set(header)
    assert "attachment" in response.headers["content-disposition"]
    assert (await _preview(client, _csv([{"company_name": unique()}], ("company_name",)))).status_code == 200


async def test_a_bad_header_is_refused_before_any_row(client, db_session):
    await _manager(client, db_session)
    assert (await _preview(client, _csv([{"website": "x"}], ("website",)))).status_code == 422
    assert (await _preview(client, _csv([{"company_name": unique()}], ("company_name", "secret_column")))).status_code == 422
    assert (await _preview(client, _csv([], ("company_name",)))).status_code == 422


async def test_each_bad_row_gets_its_own_reason_and_the_good_rows_still_import(client, db_session):
    await _manager(client, db_session)
    good = unique()
    rows = [
        {"company_name": good},
        {"company_name": "", "website": "https://blank.example.com"},
        {"company_name": unique(), "contact_name": "Asha", "contact_email": "not-an-email"},
        {"company_name": unique(), "contact_email": mail()},
        {"company_name": unique(), "industry": "No Such Industry"},
        {"company_name": unique(), "priority": "urgent"},
        {"company_name": unique(), "contact_name": "Ravi", "contact_source": "carrier pigeon"},
    ]
    body = (await _commit(client, _csv(rows))).json()
    assert [r["status"] for r in body["rows"]] == ["created", "error", "error", "error", "error", "error", "error"]
    assert body["created_count"] == 1 and body["error_count"] == 6 and body["total_rows"] == 7
    assert all(r["reason"] for r in body["rows"][1:])
    assert "contact_name" in body["rows"][3]["reason"]
    assert "ndustry" in body["rows"][4]["reason"]
    assert await _by_name(db_session, good) is not None
    assert await _by_name(db_session, rows[4]["company_name"]) is None


async def test_catalogue_values_match_by_name_whatever_the_case(client, db_session):
    await _manager(client, db_session)
    industry = RecIndustry(name=unique("Industry"))
    db_session.add(industry)
    await db_session.commit()
    industry_id, industry_name = industry.id, industry.name
    name = unique()
    body = (
        await _commit(
            client, _csv([{"company_name": name, "industry": industry_name.upper(), "priority": "HOT", "contact_name": "Asha", "contact_source": "Company website", "contact_decision_maker": "Yes"}])
        )
    ).json()
    assert body["rows"][0]["status"] == "created", body
    company = await _by_name(db_session, name)
    assert company.industry_id == industry_id and company.priority == "hot"
    contact = (await _contacts(db_session, company.id))[0]
    assert contact.is_primary and contact.is_decision_maker and contact.source == "company_website" and contact.status == "not_contacted"


# --- I4/I5 preview, matching ---------------------------------------------------------------------------------------------------------


async def test_the_preview_writes_nothing(client, db_session):
    await _manager(client, db_session)
    name = unique()
    before = await db_session.scalar(select(func.count()).select_from(CrmImportBatch))
    body = (
        await _preview(client, _csv([{"company_name": name, "contact_name": "Asha", "contact_mobile": mobile()}, {"company_name": name, "contact_name": "Ravi", "contact_mobile": mobile()}]))
    ).json()
    assert [r["status"] for r in body["rows"]] == ["new", "new"]
    assert body["rows"][0]["company_outcome"] == "new" and body["rows"][0]["contact_outcome"] == "new"
    assert body["rows"][1]["company_outcome"] == "matched" and body["rows"][1]["same_as_row"] == 2
    assert body["new_count"] == 2
    assert await _by_name(db_session, name) is None
    assert await db_session.scalar(select(func.count()).select_from(CrmImportBatch)) == before


async def test_several_rows_build_one_company_with_several_contacts(client, db_session):
    await _manager(client, db_session)
    name = unique()
    first, second = mobile(), mail()
    rows = [{"company_name": name, "contact_name": "Asha", "contact_mobile": first}, {"company_name": f"  {name.upper()} ", "contact_name": "Ravi", "contact_email": second},
            {"company_name": name, "contact_name": "Asha again", "contact_mobile": first}]  # fmt: skip
    body = (await _commit(client, _csv(rows))).json()
    assert [r["status"] for r in body["rows"]] == ["created", "created", "matched"], body
    assert (body["companies_created"], body["contacts_created"]) == (1, 2)
    company = await _by_name(db_session, name)
    contacts = await _contacts(db_session, company.id)
    assert sorted(c.name for c in contacts) == ["Asha", "Ravi"]
    assert [c.name for c in contacts if c.is_primary] == ["Asha"]


async def test_a_known_company_is_matched_by_its_normalised_name_and_never_changed(client, db_session):
    await _manager(client, db_session)
    name = unique("Known  Spaced")
    known = await _company(client, name, website="https://kept.example.com")
    body = (await _commit(client, _csv([{"company_name": " ".join(name.split()).upper(), "website": "https://other.example.com"}]))).json()
    row = body["rows"][0]
    assert row["status"] == "matched" and row["company"]["id"] == known["id"] and row["company"]["in_scope"] is True
    assert (await _by_name(db_session, name)).website == "https://kept.example.com"


async def test_a_new_contact_joins_a_known_company_and_a_known_contact_is_matched_however_it_is_written(client, db_session):
    await _manager(client, db_session)
    company = await _company(client)
    number, address = mobile(), mail()
    db_session.add(CompanyContact(company_id=UUID(company["id"]), name="Known", mobile=number, email=address, is_primary=True))
    db_session.add(CompanyContact(company_id=UUID(company["id"]), name="No Details"))
    await db_session.commit()
    rows = [
        {"company_name": company["name"], "contact_name": "By Mobile", "contact_mobile": f"+91 {number}"},
        {"company_name": company["name"], "contact_name": "By Email", "contact_email": address.upper()},
        {"company_name": company["name"], "contact_name": "  no   details "},
        {"company_name": company["name"], "contact_name": "Brand New", "contact_mobile": mobile()},
    ]
    body = (await _commit(client, _csv(rows))).json()
    assert [(r["company_outcome"], r["contact_outcome"]) for r in body["rows"]] == [("matched", "matched")] * 3 + [("matched", "created")]
    contacts = await _contacts(db_session, company["id"])
    assert sorted(c.name for c in contacts) == ["Brand New", "Known", "No Details"]
    assert next(c for c in contacts if c.name == "Brand New").is_primary is False


async def test_the_same_person_at_another_company_is_added_and_noted(client, db_session):
    await _manager(client, db_session)
    number = mobile()
    first = await _company(client)
    db_session.add(CompanyContact(company_id=UUID(first["id"]), name="Moved", mobile=number))
    await db_session.commit()
    body = (await _commit(client, _csv([{"company_name": unique(), "contact_name": "Moved", "contact_mobile": number}]))).json()
    assert body["rows"][0]["status"] == "created"
    assert "another company" in body["rows"][0]["reason"]


async def test_a_company_at_the_contact_cap_reports_the_row(client, db_session):
    await _manager(client, db_session)
    company = await _company(client)
    db_session.add_all(CompanyContact(company_id=UUID(company["id"]), name=f"Person {i}", active=False) for i in range(50))
    await db_session.commit()
    body = (await _commit(client, _csv([{"company_name": company["name"], "contact_name": "One More", "contact_mobile": mobile()}]))).json()
    assert body["rows"][0]["status"] == "error" and "at most 50" in body["rows"][0]["reason"]


# --- I6/I7 scope and ownership ---------------------------------------------------------------------------------------------------------


async def test_a_recruiters_new_companies_are_their_own_and_a_managers_are_unassigned(client, db_session):
    manager = await make_pm(db_session)
    manager_id = manager.id
    recruiter = await _allowed_recruiter(client, db_session, manager)
    recruiter_id = recruiter.id
    mine = unique()
    await _commit(client, _csv([{"company_name": mine, "contact_name": "Asha"}]))
    assert (await _by_name(db_session, mine)).assigned_recruiter_user_id == recruiter_id
    await login(client, await db_session.get(type(manager), manager_id))
    theirs = unique()
    await _commit(client, _csv([{"company_name": theirs}]))
    assert (await _by_name(db_session, theirs)).assigned_recruiter_user_id is None


async def test_a_manager_may_add_a_contact_to_a_teams_company(client, db_session):
    """I6: the grant, not the manual route's recruiter-only rule, decides."""
    manager = await make_pm(db_session)
    recruiter = await make_recruiter(db_session, manager)
    await login(client, recruiter)
    company = await _company(client)
    await login(client, manager)
    body = (await _commit(client, _csv([{"company_name": company["name"], "contact_name": "Added By Lead", "contact_mobile": mobile()}]))).json()
    assert body["rows"][0]["contact_outcome"] == "created", body
    assert [c.name for c in await _contacts(db_session, company["id"])] == ["Added By Lead"]


async def test_a_company_outside_the_callers_scope_is_never_written_or_linked(client, db_session):
    other = await make_recruiter(db_session, await make_pm(db_session))
    await login(client, other)
    company = await _company(client)
    secret = unique("Secret Person")
    await client.post(f"{COMPANIES}/{company['id']}/contacts", json={"name": secret, "mobile": mobile()})
    await _allowed_recruiter(client, db_session)
    rows = [{"company_name": company["name"]}, {"company_name": company["name"], "contact_name": "Sneaky", "contact_mobile": mobile()}]
    body = (await _commit(client, _csv(rows))).json()
    assert body["rows"][0]["status"] == "matched" and body["rows"][0]["company"]["in_scope"] is False
    assert body["rows"][1]["status"] == "error" and "another recruiter" in body["rows"][1]["reason"]
    assert [c.name for c in await _contacts(db_session, company["id"])] == [secret]
    assert secret not in str(body)


async def test_an_archived_company_takes_no_contact(client, db_session):
    recruiter = await make_recruiter(db_session, await make_pm(db_session))
    await login(client, recruiter)
    company = await _company(client)
    assert (await client.post(f"{COMPANIES}/{company['id']}/archive")).status_code == 200
    db_session.add(UserPermissionOverride(user_id=recruiter.id, resource="crm", action="import", effect="allow", reason="pob-006 test"))
    await db_session.commit()
    body = (await _commit(client, _csv([{"company_name": company["name"]}, {"company_name": company["name"], "contact_name": "Late"}]))).json()
    assert body["rows"][0]["status"] == "matched" and "archived" in body["rows"][0]["reason"]
    assert body["rows"][1]["status"] == "error" and "archived" in body["rows"][1]["reason"]


# --- I8 retry; AC1, AC2 ---------------------------------------------------------------------------------------------------------------


async def test_ac1_500_companies_import_with_a_report(client, db_session):
    await _manager(client, db_session)
    stem = uuid.uuid4().hex[:8]
    rows = [{"company_name": f"Bulk {stem} {i}", "contact_name": f"Person {i}", "contact_mobile": mobile()} for i in range(500)]
    started = time.monotonic()
    body = (await _commit(client, _csv(rows))).json()
    elapsed = time.monotonic() - started
    assert (body["total_rows"], body["created_count"], body["companies_created"], body["contacts_created"], body["error_count"]) == (500, 500, 500, 500, 0)
    assert len(body["rows"]) == 500 and elapsed < 60, elapsed
    report = (await client.get(f"{IMPORTS}/{body['id']}")).json()
    assert len(report["rows"]) == 500 and report["rows"][0]["company"]["name"] == f"Bulk {stem} 0"


async def test_ac2_a_reimport_creates_no_duplicates(client, db_session):
    await _manager(client, db_session)
    names = [unique() for _ in range(3)]
    rows = [{"company_name": n, "contact_name": "Asha", "contact_mobile": mobile()} for n in names]
    await _commit(client, _csv(rows))
    # the same people in a re-saved (different) file: another hash, so it runs again and must match every row
    body = (await _commit(client, _csv(rows + [{"company_name": names[0]}]), name="resaved.csv")).json()
    assert body["replayed"] is False and body["created_count"] == 0 and body["matched_count"] == 4
    for name in names:
        company = await _by_name(db_session, name)
        assert len(await _contacts(db_session, company.id)) == 1
    db_session.expire_all()
    assert await db_session.scalar(select(func.count()).select_from(Company).where(Company.name.in_(names))) == 3


async def test_the_same_key_or_the_same_file_replays_the_first_report(client, db_session):
    await _manager(client, db_session)
    raw = _csv([{"company_name": unique()}])
    key = uuid.uuid4().hex
    first = await _commit(client, raw, key)
    assert first.status_code == 201 and first.json()["replayed"] is False
    again = await _commit(client, raw, key)
    assert again.json()["replayed"] is True and again.json()["id"] == first.json()["id"]
    other_key = await _commit(client, raw)
    assert other_key.json()["replayed"] is True and other_key.json()["id"] == first.json()["id"]
    assert (await _commit(client, _csv([{"company_name": unique()}]), key)).status_code == 422


async def test_an_excel_file_imports_like_a_csv(client, db_session):
    await _manager(client, db_session)
    name = unique()
    book = Workbook()
    book.active.append(["company_name", "contact_name", "contact_email"])
    book.active.append([name, "Asha", mail()])
    buffer = io.BytesIO()
    book.save(buffer)
    files = {"file": ("companies.xlsx", buffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    response = await client.post(IMPORTS, files=files, headers={"Idempotency-Key": uuid.uuid4().hex})
    assert response.status_code == 201, response.text
    assert response.json()["companies_created"] == 1 and response.json()["contacts_created"] == 1
    company = await _by_name(db_session, name)
    assert [c.name for c in await _contacts(db_session, company.id)] == ["Asha"]


async def test_a_file_that_had_errors_can_run_again_once_they_are_fixed(client, db_session):
    """The preview promises the rows a fixed catalogue now allows, so the commit must not answer with the old report. The key still replays (a dropped connection)."""
    await _manager(client, db_session)
    industry, name = unique("Late Industry"), unique()
    raw = _csv([{"company_name": name, "industry": industry}])
    key = uuid.uuid4().hex
    first = (await _commit(client, raw, key)).json()
    assert first["error_count"] == 1 and await _by_name(db_session, name) is None
    db_session.add(RecIndustry(name=industry))
    await db_session.commit()
    assert (await _preview(client, raw)).json()["new_count"] == 1
    assert (await _commit(client, raw, key)).json()["replayed"] is True
    second = (await _commit(client, raw)).json()
    assert second["replayed"] is False and second["id"] != first["id"] and second["companies_created"] == 1
    assert await _by_name(db_session, name) is not None
    third = (await _commit(client, raw)).json()
    assert third["replayed"] is True and third["id"] == second["id"]


async def test_the_commit_needs_a_valid_key(client, db_session):
    await _manager(client, db_session)
    raw = _csv([{"company_name": unique()}])
    assert (await client.post(IMPORTS, files={"file": ("c.csv", raw, "text/csv")})).status_code == 422
    assert (await _commit(client, raw, "bad key!")).status_code == 422


# --- I9-I11 stored data, history, report ---------------------------------------------------------------------------------------------


async def test_nothing_from_the_file_reaches_the_audit_row(client, db_session):
    manager = await _manager(client, db_session)
    name, person = unique(), unique("Private")
    body = (await _commit(client, _csv([{"company_name": name, "contact_name": person}]))).json()
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "crm.import", AuditLog.entity_id == body["id"]))
    assert audit.user_id == manager.id and audit.metadata_json["companies_created"] == 1
    assert name not in str(audit.metadata_json) and person not in str(audit.metadata_json)


async def test_history_is_your_own_and_your_teams_only(client, db_session):
    manager = await make_pm(db_session)
    recruiter = await _allowed_recruiter(client, db_session, manager)
    body = (await _commit(client, _csv([{"company_name": unique(), "contact_name": "Team Person"}]))).json()
    await login(client, manager)
    assert body["id"] in [b["id"] for b in (await client.get(IMPORTS, params={"limit": 100})).json()["items"]]
    assert (await client.get(f"{IMPORTS}/{body['id']}")).status_code == 200
    await login(client, await make_pm(db_session))
    assert body["id"] not in [b["id"] for b in (await client.get(IMPORTS, params={"limit": 100})).json()["items"]]
    assert (await client.get(f"{IMPORTS}/{body['id']}")).status_code == 404
    assert (await client.get(f"{IMPORTS}/{body['id']}/report.csv")).status_code == 404
    await login(client, recruiter)
    assert (await client.get(f"{IMPORTS}/{body['id']}")).status_code == 200


async def test_a_report_read_later_hides_contacts_that_left_the_callers_scope(client, db_session):
    manager = await make_pm(db_session)
    recruiter = await _allowed_recruiter(client, db_session, manager)
    person = unique("Scoped Person")
    body = (await _commit(client, _csv([{"company_name": unique(), "contact_name": person}]))).json()
    await login(client, manager)
    new_owner = await make_recruiter(db_session, await make_pm(db_session))
    company = await db_session.get(Company, UUID(body["rows"][0]["company"]["id"]))
    company.assigned_recruiter_user_id = new_owner.id
    await db_session.commit()
    await login(client, recruiter)
    report = (await client.get(f"{IMPORTS}/{body['id']}")).json()
    assert report["rows"][0]["company"]["in_scope"] is False and report["rows"][0]["contact"] is None
    assert person not in (await client.get(f"{IMPORTS}/{body['id']}/report.csv")).text


async def test_the_report_csv_never_runs_a_formula(client, db_session):
    await _manager(client, db_session)
    formula = f"=HYPERLINK(1) {uuid.uuid4().hex[:8]}"
    body = (await _commit(client, _csv([{"company_name": formula, "contact_name": "@SUM(1)"}]))).json()
    assert body["rows"][0]["status"] == "created", body
    response = await client.get(f"{IMPORTS}/{body['id']}/report.csv")
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == ["row_number", "status", "company_code", "company_name", "contact_name", "reason"]
    assert rows[1][3].startswith("'=") and rows[1][4].startswith("'@")
