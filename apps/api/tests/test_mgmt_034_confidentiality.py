"""mgmt-034 -- the confidentiality sweep (spec docs/superpowers/specs/2026-10-14-mgmt-034-confidentiality-sweep-design.md CS1/CS7/CS8;
RBAC_MATRIX §2.146). AC2: "the sweep fails on any extra field".

CS7, the delta sweep: every management read of the matrix is taken as each management tier, then partner-only data (an investment, a
capital entry, a university commission receipt) or finance data (an approved income line, a department salary month) is planted, today,
directly in the database (no audit row), and every read is repeated. A tier that may not see the plant must get a byte-identical body,
so a leak inside a total fails as surely as an extra key. A positive control proves each plant is really reachable.

CS8, the assignee slices (M14): the owner's own task, decision and meeting lines carry exactly their documented keys, and nobody else's list
holds them."""

import pytest
import pytest_asyncio

from tests.mgmt034_helpers import MANAGEMENT, headers, plant_finance, plant_partner_only, retire_departments, world
from tests.test_mgmt_034_matrix import API, MATRIX, _fill

BINARY = ("/receipt", "/attachments/", "/pdf")  # files, not JSON figures
READS = [row.path for row in MATRIX if row.method == "get" and not any(part in row.path for part in BINARY)]


@pytest_asyncio.fixture(autouse=True)
async def _retire_departments(db_session):
    yield
    await retire_departments(db_session)


async def _read_all(client, w: dict, role: str) -> dict[str, tuple[int, object]]:
    """Each read's status and body; the only thing removed is the dashboards' `as_of` read clock (CS7)."""
    out = {}
    for path in READS:
        response = await client.get(API + _fill(path, w), headers=headers(w["users"][role]))
        body = response.json()
        if isinstance(body, dict):
            body.pop("as_of", None)
        out[path] = (response.status_code, body)
    return out


def _changed(before: dict, after: dict) -> list[str]:
    return [path for path in READS if before[path] != after[path]]


@pytest.mark.asyncio
async def test_partner_only_data_reaches_no_one_but_the_partners(client, db_session):
    """M2/M3/M13: investments, capital accounts and university commission change nothing the accountant or super_admin can read."""
    w = await world(client, db_session)
    before = {role: await _read_all(client, w, role) for role in MANAGEMENT}
    await plant_partner_only(db_session, w)
    after = {role: await _read_all(client, w, role) for role in MANAGEMENT}

    assert (leaks := _changed(before["accountant"], after["accountant"])) == [], f"the accountant sees partner-only data: {leaks}"
    assert (leaks := _changed(before["super"], after["super"])) == [], f"super_admin sees partner-only data: {leaks}"
    seen = _changed(before["partner"], after["partner"])  # positive control: each plant is reachable
    assert {"/management/investments", "/management/capital", "/management/ledger?include=auto"} <= set(seen), seen


@pytest.mark.asyncio
async def test_finance_data_reaches_no_one_outside_the_finance_tier(client, db_session):
    """M13: an income line and a salary month change nothing super_admin can read (no finance figures, salaries or ledger)."""
    w = await world(client, db_session)
    before = {role: await _read_all(client, w, role) for role in MANAGEMENT}
    await plant_finance(db_session, w)
    after = {role: await _read_all(client, w, role) for role in MANAGEMENT}

    assert (leaks := _changed(before["super"], after["super"])) == [], f"super_admin sees finance data: {leaks}"
    for role in ("partner", "accountant"):  # positive control
        seen = _changed(before[role], after[role])
        assert {"/management/ledger?include=auto", "/management/salaries"} <= set(seen), (role, seen)


@pytest.mark.asyncio
async def test_the_accountant_reads_no_university_commission_on_the_accounts_dashboard(client, db_session):
    """CS1 (M3): the receivable is never read for the accountant (null, out of the total); the partner keeps it."""
    w = await world(client, db_session)
    mine = (await client.get(f"{API}/management/accounts", headers=headers(w["users"]["accountant"]))).json()
    assert mine["commission_visible"] is False and mine["receivables"]["university"] is None
    assert all(row["kind"] != "university" for row in mine["receivables"]["not_counted"])
    r = mine["receivables"]
    assert float(r["total"]) == float(r["fees"]) + float(r["recruitment"])
    theirs = (await client.get(f"{API}/management/accounts", headers=headers(w["users"]["partner"]))).json()
    assert theirs["commission_visible"] is True and theirs["receivables"]["university"] is not None


# --- CS8: the assignee slices (M14) ------------------------------------------------------------------------------------------
SLICES = {
    "/me/management-tasks": ("task", {"id", "title", "priority", "deadline", "status", "band", "updated_at"}),
    "/me/management-decisions": ("discussion", {"id", "decision", "deadline", "status", "attachments", "updated_at"}),
    "/me/management-meetings": ("meeting", {"id", "title", "kind", "starts_at", "mode", "location", "meeting_url", "agenda", "status"}),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", SLICES)
async def test_the_owner_sees_only_their_line_and_no_one_else_sees_it(client, db_session, path):
    w = await world(client, db_session)
    record, keys = SLICES[path]
    mine = (await client.get(API + path, headers=headers(w["users"]["owner"]))).json()["items"]
    line = next(item for item in mine if item["id"] == w[record])
    assert set(line) == keys, f"extra or missing keys: {set(line) ^ keys}"
    if path == "/me/management-decisions":
        assert [set(a) for a in line["attachments"]] == [{"id", "name", "content_type"}]
    for role in ("partner", "accountant", "super", "counselor", "trainer", "student"):
        theirs = (await client.get(API + path, headers=headers(w["users"][role]))).json()["items"]
        assert w[record] not in {item["id"] for item in theirs}, f"{role} sees the owner's line"
