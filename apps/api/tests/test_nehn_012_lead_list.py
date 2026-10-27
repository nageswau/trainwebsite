"""nehn-012 (DEC-SCOPE-296): the admin and telecaller lead lists' India-time date range and counselor filters, and their filtered Excel
export -- the same rows as the list (all pages), each download audited (filters, rows) and throttled. The shared database is never
truncated, so every test narrows to rows it created (a unique `q`)."""

import io
import uuid
from datetime import UTC, datetime, timedelta

import openpyxl
import pytest
from sqlalchemy import select

from app.api import crm_exports
from app.api.agent_reports import EXPORT_LIMIT
from app.models import AuditLog, Enquiry, LeadCall, LeadFollowUp, User
from app.services.tabular import XLSX_TYPE
from tests.bdm001_helpers import make_user
from tests.bdm017_helpers import ADMIN_LEADS, as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager

ADMIN_XLSX = "/api/v1/admin/leads.xlsx"
TEL_LEADS = "/api/v1/telecaller/leads"
TEL_XLSX = "/api/v1/telecaller/leads.xlsx"
HEADER = ["Lead ID", "Name", "Phone", "Email", "Source", "Course interest", "Stage", "Telecaller", "Counselor", "Created", "Last contact", "Next follow-up"]
# 2026-10-20 23:59 and 2026-10-21 00:01 India time (UTC+05:30)
LATE = datetime(2026, 10, 20, 18, 29, tzinfo=UTC)
EARLY = datetime(2026, 10, 20, 18, 31, tzinfo=UTC)


def tag() -> str:
    return f"n12{uuid.uuid4().hex[:10]}"


async def lead(db, name: str, **over) -> Enquiry:
    values = {"division": "it", "name": name, "email": f"{uuid.uuid4().hex[:8]}@example.local", "phone": "9876543210", "subject": "Python", "message": "Hello there", "source": "website"} | over
    row = Enquiry(**values)
    db.add(row)
    await db.commit()
    return row


def names(data: dict) -> list[str]:
    return [item["name"] for item in data["items"]]


def sheet(response) -> list[list]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == XLSX_TYPE
    assert response.headers["cache-control"] == "private, no-store"
    rows = list(openpyxl.load_workbook(io.BytesIO(response.content)).active.iter_rows(values_only=True))
    return [list(row) for row in rows]


async def exports(db, user: User) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "crm.export").order_by(AuditLog.created_at)
    return list((await db.scalars(stmt)).all())


# --- AC1 / AC2: the filters ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_created_day_is_the_india_calendar_day(client, db_session):
    t = tag()
    await lead(db_session, f"Late {t}", created_at=LATE)
    await lead(db_session, f"Early {t}", created_at=EARLY)
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    day = (await client.get(ADMIN_LEADS, params={"q": t, "created_from": "2026-10-20", "created_to": "2026-10-20"})).json()
    assert (names(day), day["total"]) == ([f"Late {t}"], 1)
    after = (await client.get(ADMIN_LEADS, params={"q": t, "created_from": "2026-10-21"})).json()
    assert names(after) == [f"Early {t}"]
    before = (await client.get(ADMIN_LEADS, params={"q": t, "created_to": "2026-10-21"})).json()
    assert names(before) == [f"Early {t}", f"Late {t}"]


@pytest.mark.asyncio
@pytest.mark.parametrize("params", [{"created_from": "2026-10-21", "created_to": "2026-10-20"}, {"created_from": "20-10-2026"}, {"owner_id": "x"}])
async def test_a_reversed_or_malformed_filter_is_422(client, db_session, params):
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.get(ADMIN_LEADS, params=params)).status_code == 422
    assert (await client.get(ADMIN_XLSX, params=params)).status_code == 422


@pytest.mark.asyncio
async def test_owner_id_filters_by_counselor(client, db_session):
    t = tag()
    counselor = await make_user(db_session, "counselor", "it")
    await lead(db_session, f"Mine {t}", owner_id=counselor.id)
    await lead(db_session, f"Other {t}")
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    assert names((await client.get(ADMIN_LEADS, params={"q": t, "owner_id": str(counselor.id)})).json()) == [f"Mine {t}"]


@pytest.mark.asyncio
async def test_the_telecaller_list_takes_the_same_filters_inside_its_scope(client, db_session):
    t = tag()
    manager = await make_tl_manager(db_session)
    caller = await make_telecaller(db_session, manager)
    counselor = await make_user(db_session, "counselor", "it")
    await lead(db_session, f"Day {t}", created_at=LATE, telecaller_user_id=caller.id, owner_id=counselor.id)
    await lead(db_session, f"Next {t}", created_at=EARLY, telecaller_user_id=caller.id)
    await lead(db_session, f"Stranger {t}", created_at=LATE)  # unassigned: never in a telecaller's own scope
    await as_user(client, caller)
    day = (await client.get(TEL_LEADS, params={"q": t, "created_from": "2026-10-20", "created_to": "2026-10-20"})).json()
    assert names(day) == [f"Day {t}"]
    assert names((await client.get(TEL_LEADS, params={"q": t, "owner_id": str(counselor.id)})).json()) == [f"Day {t}"]
    assert (await client.get(TEL_LEADS, params={"created_from": "2026-10-21", "created_to": "2026-10-20"})).status_code == 422


# --- AC3 / AC5: the admin export -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_admin_export_holds_every_filtered_row_with_the_fixed_columns_and_is_audited(client, db_session):
    t = tag()
    caller = await make_user(db_session, "telecaller", "it", name=f"Caller {t}")
    counselor = await make_user(db_session, "counselor", "it", name=f"Counselor {t}")
    first = await lead(db_session, f"First {t}", created_at=LATE - timedelta(hours=1), telecaller_user_id=caller.id, owner_id=counselor.id, source="instagram", status="contacted")
    for i in range(3):
        await lead(db_session, f"Filler {i} {t}", created_at=LATE - timedelta(minutes=i))
    await lead(db_session, f"Outside {t}", created_at=EARLY)
    called = datetime(2026, 10, 22, 6, 30, tzinfo=UTC)
    db_session.add(LeadCall(lead_id=first.id, caller_user_id=caller.id, occurred_at=called, duration_seconds=60, call_type="outgoing", outcome="interested"))
    due = datetime(2026, 10, 25, 4, 30, tzinfo=UTC)
    for at, status in ((due, "open"), (due - timedelta(days=2), "open"), (due - timedelta(days=4), "cancelled")):
        db_session.add(
            LeadFollowUp(
                lead_id=first.id, due_at=at, reason="fee_details", status=status, created_by_user_id=caller.id, **({"cancelled_at": called, "cancel_reason": "x"} if status == "cancelled" else {})
            )
        )
    await db_session.commit()
    admin = await make_user(db_session, "it_admin", "it")
    await as_user(client, admin)
    params = {"q": t, "created_from": "2026-10-20", "created_to": "2026-10-20", "limit": 2, "offset": 2}  # paging is ignored
    listed = (await client.get(ADMIN_LEADS, params={"q": t, "created_from": "2026-10-20", "created_to": "2026-10-20", "limit": 100})).json()
    response = await client.get(ADMIN_XLSX, params=params)
    rows = sheet(response)
    assert 'filename="leads-' in response.headers["content-disposition"] and response.headers["content-disposition"].endswith('.xlsx"')
    assert rows[0] == HEADER
    assert [row[1] for row in rows[1:]] == names(listed) and len(rows) == 5  # AC3: the list's rows, all pages, the list's order
    by_name = {row[1]: row for row in rows[1:]}
    row = by_name[f"First {t}"]
    assert row[:9] == [first.lead_code, f"First {t}", "9876543210", first.email, "Instagram", "Python", "Contacted", f"Caller {t}", f"Counselor {t}"]
    assert row[9] == datetime(2026, 10, 20, 22, 59)  # India time
    assert row[10] == datetime(2026, 10, 22, 12, 0)
    assert row[11] == datetime(2026, 10, 23, 10, 0)  # the earliest OPEN follow-up
    assert by_name[f"Filler 0 {t}"][7:] == ["", "", datetime(2026, 10, 20, 23, 59), "", ""]  # to_xlsx writes an unset value as an empty cell
    [audit] = await exports(db_session, admin)
    assert (audit.entity_type, audit.entity_id) == ("lead_list", "admin")
    assert audit.metadata_json == {"format": "xlsx", "filters": {"q": True, "created_from": "2026-10-20", "created_to": "2026-10-20"}, "rows": 4}


@pytest.mark.asyncio
async def test_the_admin_export_keeps_the_division_scope(client, db_session):
    t = tag()
    await lead(db_session, f"It {t}")
    await lead(db_session, f"Overseas {t}", division="overseas")
    await as_user(client, await make_user(db_session, "overseas_admin", "overseas"))
    assert [row[1] for row in sheet(await client.get(ADMIN_XLSX, params={"q": t, "division": "it"}))[1:]] == [f"Overseas {t}"]
    await as_user(client, await make_user(db_session, "super_admin", "global"))
    assert [row[1] for row in sheet(await client.get(ADMIN_XLSX, params={"q": t, "division": "it"}))[1:]] == [f"It {t}"]


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("telecaller", "it"), ("counselor", "it"), ("it_student", "it"), ("telecaller_manager", "it")])
async def test_other_roles_cannot_use_the_admin_export_and_nothing_is_audited(client, db_session, role, division):
    actor = await make_user(db_session, role, division)
    await as_user(client, actor)
    assert (await client.get(ADMIN_XLSX)).status_code == 403
    assert await exports(db_session, actor) == []


@pytest.mark.asyncio
async def test_the_export_is_throttled_and_capped(client, db_session, monkeypatch):
    t = tag()
    await lead(db_session, f"A {t}")
    await lead(db_session, f"B {t}")
    admin = await make_user(db_session, "it_admin", "it")
    await as_user(client, admin)
    monkeypatch.setattr(crm_exports, "ROW_CAP", 1)
    assert (await client.get(ADMIN_XLSX, params={"q": t})).status_code == 422
    monkeypatch.setattr(crm_exports, "ROW_CAP", 5000)
    for _ in range(EXPORT_LIMIT):
        assert (await client.get(ADMIN_XLSX, params={"q": t})).status_code == 200
    refused = await client.get(ADMIN_XLSX, params={"q": t})
    assert refused.status_code == 429 and int(refused.headers["retry-after"]) >= 1
    assert len(await exports(db_session, admin)) == EXPORT_LIMIT


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(ADMIN_XLSX)).status_code == 401
    assert (await client.get(TEL_XLSX)).status_code == 401


# --- AC4: the telecaller manager's export ----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_managers_export_holds_only_their_scope(client, db_session):
    t = tag()
    manager = await make_tl_manager(db_session)
    caller = await make_telecaller(db_session, manager)
    other = await make_telecaller(db_session, await make_tl_manager(db_session))
    await lead(db_session, f"Report {t}", telecaller_user_id=caller.id)
    await lead(db_session, f"Elsewhere {t}", telecaller_user_id=other.id)
    await as_user(client, manager)
    response = await client.get(TEL_XLSX, params={"q": t})
    assert [row[1] for row in sheet(response)[1:]] == [f"Report {t}"]
    [audit] = await exports(db_session, manager)
    assert (audit.entity_type, audit.entity_id, audit.metadata_json) == ("lead_list", "telecaller", {"format": "xlsx", "filters": {"q": True}, "rows": 1})


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("it_admin", "it"), ("counselor", "it")])
async def test_a_telecaller_or_another_role_cannot_use_the_manager_export(client, db_session, role, division):
    manager = await make_tl_manager(db_session)
    actors = [await make_telecaller(db_session, manager), await make_user(db_session, role, division)]
    for actor in actors:
        await as_user(client, actor)
        assert (await client.get(TEL_XLSX)).status_code == 403
        assert await exports(db_session, actor) == []
