"""rec-038 -- the Recruiter CRM permission matrix as built (spec docs/superpowers/specs/2026-10-11-rec-038-permission-matrix-design.md,
RBAC_MATRIX §2.111). Every recruiter route is called as every matrix role (rec038_helpers.ROLES): a recruiter and a placement manager with
the world's records and each again on *another* team, super_admin, it_admin, overseas_admin, hr_team, the company's assigned BDM and another
BDM, the company's employer user, an opted-in IT student and nobody signed in.

A row lists only the cells that are not "refused": every unlisted signed-in role must get 403 and anonymous 401 (RM3). Refused cells and every
GET share one world per row; every other 2xx cell runs on its own fresh world, so one cell's write never changes what another sees (RM5).
The expectations are the owner-approved rules of each item (RBAC_MATRIX §2.42-§2.110). Out of scope is 404 in this module (RM4): a record
outside the caller's scope reads as missing."""

import re
import uuid

import pytest

from app.main import app
from tests import rec038_rows_activity, rec038_rows_candidates, rec038_rows_hiring, rec038_rows_profile
from tests.rec038_helpers import ROLES, Row, core, headers

API = "/api/v1"
OK = {200, 201, 204}
GROUPS = (rec038_rows_profile, rec038_rows_candidates, rec038_rows_hiring, rec038_rows_activity)
MATRIX = [row for group in GROUPS for row in group.ROWS]
PATH_VALUES = {key: value for group in GROUPS for key, value in group.PATH_VALUES.items()}  # the non-id path parameters
# RM1: every operation of the recruiter CRM -- `/recruiter/*`, the recruiter admin pickers (rec-001), the program skill tags (rec-036), the
# student's pool consent (rec-010) and offers (rec-022), the employer's shared profiles and the public shared resume (rec-019).
PREFIXES = ("/recruiter/", "/admin/recruiters", "/admin/placement-managers", "/admin/programs/skill-options", "/account/placement-pool",
            "/employer/shared-profiles", "/workflows/it/student/offers", "/public/shared-resume/")  # fmt: skip
EXACT = {"GET /admin/programs/{}/skills", "PUT /admin/programs/{}/skills"}


async def world(client, db) -> dict:
    w = await core(client, db)
    for group in GROUPS:
        await group.build(client, db, w)
    return w


def _fill(text: str, w: dict) -> str:
    return text.format(**PATH_VALUES, **w)


async def _call(client, row: Row, w: dict, role: str):
    url = API + _fill(row.path, w)
    kwargs = {"headers": headers(None if role == "anon" else w["users"][role])}
    if row.form:
        data, files = row.form(w)
        kwargs |= {"data": data, "files": files, "headers": kwargs["headers"] | {"Idempotency-Key": uuid.uuid4().hex}}
    elif row.method not in ("get", "delete"):
        kwargs["json"] = row.body(w) if callable(row.body) else (row.body if row.body is not None else {})
    return await client.request(row.method.upper(), url, **kwargs)


def _operations() -> set[str]:
    """Every registered operation as "METHOD /path" (included routers are not flattened into `app.routes`)."""
    return {f"{method.upper()} {path.removeprefix(API)}" for path, ops in app.openapi()["paths"].items() for method in ops}


def _template(key: str) -> str:
    """`GET /recruiter/companies/{company}/calls?x=1` -> `GET /recruiter/companies/{}/calls`: placeholders compare by position."""
    return re.sub(r"\{[^}]+\}", "{}", key.split("?")[0])


def test_every_recruiter_route_has_a_row():
    """AC / RM1: a recruiter route without a matrix row (or a stale row) fails here."""
    routes = {t for t in map(_template, _operations()) if t.split(" ", 1)[1].startswith(PREFIXES) or t in EXACT}
    rows = [_template(row.key) for row in MATRIX]
    assert len(rows) == len(set(rows)), "duplicate matrix rows"
    assert routes - set(rows) == set(), "routes without a matrix row"
    assert set(rows) - routes == set(), "matrix rows without a route"


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "party"), [("bdm", "contact"), ("hr", "candidate")])
async def test_render_refuses_a_role_that_cannot_read_templates(client, db_session, role, party):
    """RM6 (§2.61): the assigned BDM reads its company's contact messages and hr_team the pool's candidate messages, but templates are
    `403` to both -- rendering one for a party they can read must be refused too, as the preview is."""
    w = await world(client, db_session)
    url = f"{API}/recruiter/messages/render?template_id={w['activity_template']}&{party}_id={w[party]}"
    response = await client.get(url, headers=headers(w["users"][role]))
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("row", MATRIX, ids=lambda r: r.key)
async def test_matrix_row(client, db_session, row):
    """AC: every route x role cell. Refused cells and reads first on one world; then every other 2xx cell on its own fresh world."""
    shared = await world(client, db_session)
    wrong = []
    for role in ROLES:
        want = row.expected(role)
        if want in OK and row.method != "get":
            continue
        response = await _call(client, row, shared, role)
        if response.status_code != want:
            wrong.append(f"{role}: want {want}, got {response.status_code} {response.text[:160]}")
    for role in ROLES:
        want = row.expected(role)
        if want not in OK or row.method == "get":
            continue
        response = await _call(client, row, await world(client, db_session), role)
        if response.status_code != want:
            wrong.append(f"{role}: want {want}, got {response.status_code} {response.text[:200]}")
    assert not wrong, " | ".join(wrong)
