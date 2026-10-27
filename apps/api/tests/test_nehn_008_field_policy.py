"""nehn-008 (DEC-SCOPE-300) -- the field (column) policy: a report's tagged columns reach the caller only with `field.<class>.view`, in the
JSON and in the CSV/xlsx alike. The pilot is the partnership Performance report's commission columns (the only financial columns in any
report today)."""

import csv
import io
import uuid

import openpyxl
import pytest
from sqlalchemy import delete, select

from app.core import rbac
from app.models import RolePermission, UserPermissionOverride
from app.services import field_policy, permissions
from tests.test_upc_031_reports import KINDS, REPORTS, _team, _university
from tests.upc003_helpers import login, make_head, make_user

pytestmark = pytest.mark.asyncio
FINANCIAL = ("field.financial", "view")
COMMISSION = {"commission_expected", "commission_received"}


# --- catalogue and seed (AC1) ---------------------------------------------------------------------------------------------------------


async def test_financial_columns_are_a_catalogue_permission_seeded_to_the_commission_roles(db_session):
    assert rbac.CATALOGUE["field.financial"]["actions"] == ("view",)
    holders = {role for role, keys in rbac.DEFAULT_GRANTS.items() if "field.financial.view" in keys}
    assert holders == {"partnership_manager", "partnership_head"}  # today's U2 commission readers; super_admin is implicit
    seeded = set(await db_session.scalars(select(RolePermission.role).where(RolePermission.resource == "field.financial")))
    assert seeded == holders


@pytest.mark.parametrize("role", ["placement_team", "placement_manager", "hr_team", "it_admin", "overseas_admin", "telecaller_manager"])
async def test_recruiter_hr_and_division_roles_do_not_see_financial_columns(db_session, role):
    assert not await permissions.has_grant(db_session, role, *FINANCIAL)


async def test_super_admin_always_sees_financial_columns(db_session):
    assert await permissions.has_grant(db_session, "super_admin", *FINANCIAL)


# --- the policy itself (AC5) ----------------------------------------------------------------------------------------------------------


def _payload() -> dict:
    return {
        "title": "T",
        "columns": [{"key": "name", "label": "Name"}, {"key": "fee", "label": "Fee"}],
        "items": [{"name": "A", "fee": "INR 10"}],
        "totals": {"name": "Total", "fee": "INR 10"},
    }


async def test_strip_removes_a_denied_column_from_columns_items_and_totals(db_session):
    user = await make_user(db_session, "placement_team", "it")
    payload = _payload()
    out = await field_policy.strip(db_session, user, payload, {"fee": "financial"})
    assert out["columns"] == [{"key": "name", "label": "Name"}]
    assert out["items"] == [{"name": "A"}] and out["totals"] == {"name": "Total"}
    assert out["title"] == "T"
    assert payload == _payload()  # the input is not mutated


async def test_strip_keeps_a_granted_column_and_untagged_columns(db_session):
    head = await make_head(db_session)
    out = await field_policy.strip(db_session, head, _payload(), {"fee": "financial"})
    assert out == _payload()
    other = await make_user(db_session, "placement_team", "it")
    assert await field_policy.strip(db_session, other, _payload(), {}) == _payload()  # nothing tagged: nothing filtered


async def test_strip_handles_absent_totals(db_session):
    user = await make_user(db_session, "placement_team", "it")
    out = await field_policy.strip(db_session, user, {**_payload(), "totals": None}, {"fee": "financial"})
    assert out["totals"] is None and out["items"] == [{"name": "A"}]


# --- partnership reports: screen == download, and the grant decides (AC2-AC4) --------------------------------------------------------


def _csv_header(response) -> list[str]:
    return next(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))


def _xlsx_header(response) -> list[str]:
    return list(next(openpyxl.load_workbook(io.BytesIO(response.content)).active.iter_rows(values_only=True)))


async def _views(client, kind: str) -> tuple[dict, list[str], list[str]]:
    body = await client.get(f"{REPORTS}/{kind}")
    csv_file = await client.get(f"{REPORTS}/{kind}.csv")
    xlsx_file = await client.get(f"{REPORTS}/{kind}.xlsx")
    assert body.status_code == csv_file.status_code == xlsx_file.status_code == 200, (body.text, csv_file.text, xlsx_file.text)
    return body.json(), _csv_header(csv_file), _xlsx_header(xlsx_file)


def _keys(report: dict) -> set[str]:
    return {c["key"] for c in report["columns"]} | {k for row in [*report["items"], report["totals"] or {}] for k in row}


async def _deny(db, user) -> None:
    db.add(UserPermissionOverride(user_id=user.id, resource=FINANCIAL[0], action=FINANCIAL[1], effect="deny", reason="nehn-008 test"))
    await db.commit()


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("denied", [False, True])
@pytest.mark.parametrize("reader", ["partnership_head", "partnership_manager", "super_admin"])
async def test_the_json_columns_equal_the_download_columns_for_every_reader_and_kind(client, db_session, reader, denied, kind):
    head, manager = await _team(db_session)
    await _university(client, db_session, head, manager, stage="partner_activated")
    user = {"partnership_head": head, "partnership_manager": manager}.get(reader) or await make_user(db_session, "super_admin", "global")
    if denied:
        await _deny(db_session, user)
    await login(client, user)
    report, csv_header, xlsx_header = await _views(client, kind)
    labels = [c["label"] for c in report["columns"]]
    assert csv_header == labels and xlsx_header == labels  # AC3
    if kind == "performance":
        hidden = denied and reader != "super_admin"  # super_admin holds everything; an override never applies to them (nehn-007 U2)
        assert (COMMISSION & _keys(report)) == (set() if hidden else COMMISSION)  # AC2 (the seed keeps them), AC4 (a deny removes them)


async def test_revoking_the_role_grant_removes_commission_from_screen_and_files_until_restored(client, db_session):
    head, manager = await _team(db_session)
    await _university(client, db_session, head, manager, stage="partner_activated")
    await login(client, head)
    try:
        await db_session.execute(delete(RolePermission).where(RolePermission.role == "partnership_head", RolePermission.resource == FINANCIAL[0]))
        await db_session.commit()
        report, csv_header, xlsx_header = await _views(client, "performance")
        assert not COMMISSION & _keys(report)
        assert not {"Commission expected", "Commission received"} & {*csv_header, *xlsx_header}
    finally:
        db_session.add(RolePermission(role="partnership_head", resource=FINANCIAL[0], action=FINANCIAL[1]))
        await db_session.commit()
    report, csv_header, _ = await _views(client, "performance")  # the next request, no restart
    assert COMMISSION <= _keys(report) and "Commission expected" in csv_header


async def test_an_allow_override_cannot_widen_past_the_report_gate(client, db_session):
    """The field grant narrows only: a role that may not read the report still gets 403 with the grant."""
    user = await make_user(db_session, "placement_team", "it")
    db_session.add(UserPermissionOverride(user_id=user.id, resource=FINANCIAL[0], action=FINANCIAL[1], effect="allow", reason="nehn-008 test"))
    await db_session.commit()
    await login(client, user)
    for suffix in ("", ".csv", ".xlsx"):
        assert (await client.get(f"{REPORTS}/performance{suffix}")).status_code == 403


async def test_an_unknown_class_is_denied(db_session):
    head = await make_head(db_session)
    out = await field_policy.strip(db_session, head, _payload(), {"fee": f"nonsense{uuid.uuid4().hex[:4]}"})
    assert [c["key"] for c in out["columns"]] == ["name"]  # deny by default: a class outside the catalogue reaches nobody
