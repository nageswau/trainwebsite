"""tel-026 -- the EVID-019 §22 permission matrix as built (spec docs/superpowers/specs/2026-10-07-tel-026-permission-matrix-design.md, RBAC_MATRIX
§2.41). Every route of the telecaller CRM is called as every matrix role (tel026_helpers.ROLES): a telecaller, a manager and a counselor
each with the world's records and each again *outside* them, both division admins, super_admin, a student and nobody signed in.

A row lists only the cells that are not "refused": every unlisted signed-in role must get 403 and anonymous 401 (PM3). A 2xx cell runs on
a fresh world, so one cell's write never changes what another sees; refused and hidden (404) cells share one world. The expectations are
the owner-approved rules of each item (RBAC_MATRIX §2.14-§2.40); PM2: super_admin is read-only on the telecaller's own work."""

import re
import uuid
from dataclasses import dataclass, field

import pytest

from app.main import app
from tests.tel026_helpers import ROLES, at, headers, world

API = "/api/v1"
OK = {200, 201, 204}


@dataclass
class Row:
    method: str
    path: str
    body: object = None  # a dict / callable(world) -> dict, sent as JSON
    form: object = None  # callable(world) -> (data, files), sent as multipart
    cells: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.method.upper()} {self.path}"

    def expected(self, role: str) -> int:
        return self.cells.get(role, 401 if role == "anon" else 403)


def R(method: str, path: str, body=None, *, form=None, **cells) -> Row:
    return Row(method, path, body, form, cells)


READ = {"tel": 200, "tel_out": 404, "mgr": 200, "mgr_out": 404, "super": 200}  # a lead read: §2.19 scope
TEL_WRITE = {"tel": 201, "tel_out": 404, "mgr": 403, "mgr_out": 404, "super": 403}  # F2 / CL / WA: the telecaller's own work
TEL_EDIT = TEL_WRITE | {"tel": 200}
SELF = {"tel": 200, "tel_out": 200}  # session-scoped, no id
TEAM_READ = {"tel": 200, "tel_out": 200, "mgr": 200, "mgr_out": 200, "super": 200}  # a list filtered by scope, or the global library
MANAGERS = {"mgr": 200, "mgr_out": 200, "super": 200}
CATALOGUE_READ = TEAM_READ | {"cns": 200, "cns_out": 200, "it_admin": 200, "ovs_admin": 200}
ADMINS = {"it_admin": 200, "ovs_admin": 200, "super": 200}
REPORTS = MANAGERS | {"it_admin": 200, "ovs_admin": 200}
COUNSELOR_READ = {"cns": 200, "cns_out": 404}
ACTION = {r: 404 for r in ROLES if r != "anon"}  # §2.23: an appointment action outside the session's scope reads as missing


def _mobile() -> str:
    return f"9{uuid.uuid4().int % 10**9:09d}"


def _csv(w):
    return {"campaign_id": w["campaign"]}, {"file": ("leads.csv", f"name,phone\nT26 Lead,{_mobile()}\n".encode(), "text/csv")}


def _pdf(w):
    return {"name": f"T26 {uuid.uuid4().hex[:6]}", "kind": "brochure"}, {"file": ("b.pdf", b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n", "application/pdf")}


MATRIX = [
    # tel-001 profile and team
    R("get", "/telecaller/me", **SELF),
    R("patch", "/telecaller/profile", {"phone": "+91 90000 00002"}, **SELF),
    R("get", "/telecaller/manager/team", **MANAGERS),
    R("get", "/admin/telecallers", **ADMINS),
    R("get", "/admin/telecaller-managers", **ADMINS),
    # tel-002 catalogue
    R("get", "/telecaller/products", **CATALOGUE_READ),
    R("post", "/telecaller/products", lambda w: {"group": "it", "name": f"T26 {uuid.uuid4().hex[:8]}", "team": "it"},
      mgr=201, mgr_out=201, super=201),
    R("patch", "/telecaller/products/{product}", {"sort_order": 1001}, **MANAGERS),
    R("get", "/telecaller/campaigns", **CATALOGUE_READ),
    R("post", "/telecaller/campaigns", lambda w: {"name": f"T26 {uuid.uuid4().hex[:8]}", "source": "instagram", "product_id": w["product"],
                                                  "start_date": "2026-09-01"}, mgr=201, mgr_out=201, super=201),
    R("patch", "/telecaller/campaigns/{campaign}", {"source": "walk_in"}, **MANAGERS),
    # tel-003 / tel-004 / tel-005 / tel-008 / tel-009 / tel-015 the lead workspace
    R("get", "/telecaller/leads", **TEAM_READ),
    R("get", "/telecaller/leads/duplicate-check?phone=9876500000", **TEAM_READ),
    R("post", "/telecaller/leads", lambda w: {"name": "T26 Lead", "phone": _mobile(), "product_id": w["product"], "source": "instagram"},
      tel=201, tel_out=201, mgr=201, mgr_out=201, super=201),
    # tel-005 I5 (DEC-SCOPE-088): "Add enquiry to this lead" from the duplicate panel works on ANY lead -- append-only, it grants no read.
    R("post", "/telecaller/leads/{lead}/enquiries", {"subject": "Again", "source": "website"}, tel=201, tel_out=201, mgr=201, mgr_out=201, super=201),
    R("get", "/telecaller/leads/{lead}", **READ),
    R("patch", "/telecaller/leads/{lead}", {"priority": "hot"}, **READ),
    R("get", "/telecaller/leads/{lead}/timeline", **READ),
    R("get", "/telecaller/leads/{lead}/qualification", **READ),
    R("put", "/telecaller/leads/{lead}/qualification", {"qualification": "B.Tech", "city": "Chennai"}, **READ),
    R("post", "/telecaller/leads/{lead}/stage", {"to_stage": "interested"}, **READ),
    R("get", "/telecaller/leads/{lead}/stage-history", **READ),
    # tel-006 import
    R("get", "/telecaller/imports/template", **MANAGERS),
    R("post", "/telecaller/imports", form=_csv, mgr=201, mgr_out=201, super=201),
    R("get", "/telecaller/imports", **MANAGERS),
    R("get", "/telecaller/imports/{batch}", mgr=200, mgr_out=404, super=200),  # R11: the uploader's own imports
    # tel-007 distribution and assignment
    R("get", "/telecaller/distribution-rules", **MANAGERS),
    R("post", "/telecaller/distribution-rules", lambda w: {"team": "it", "kind": "city", "city": f"City {uuid.uuid4().hex[:8]}",
                                                         "telecaller_user_id": w["tel_id"]}, mgr=201, super=201),
    R("patch", "/telecaller/distribution-rules/{rule}", lambda w: {"telecaller_user_id": w["spare_id"]}, mgr=200, super=200),
    R("delete", "/telecaller/distribution-rules/{rule}", mgr=204, super=204),
    R("get", "/telecaller/leads/unassigned", **MANAGERS),
    R("get", "/telecaller/leads/assigned", **MANAGERS),
    R("post", "/telecaller/leads/assign", lambda w: {"lead_ids": [w["lead"]], "telecaller_user_id": w["spare_id"]}, mgr=200, mgr_out=404, super=200),
    # tel-010 calls
    R("get", "/telecaller/calls/day-counts", **TEAM_READ),
    R("get", "/telecaller/leads/{lead}/calls", **READ),
    R("post", "/telecaller/leads/{lead}/calls", {"duration_seconds": 60, "call_type": "outgoing", "outcome": "interested"}, **TEL_WRITE),
    R("patch", "/telecaller/calls/{call}", {"remarks": "late"}, **TEL_EDIT),
    R("delete", "/telecaller/calls/{call}", **(TEL_WRITE | {"tel": 204})),
    # tel-011 follow-ups
    R("get", "/telecaller/follow-ups", **TEAM_READ),
    R("get", "/telecaller/leads/{lead}/follow-ups", **READ),
    R("post", "/telecaller/leads/{lead}/follow-ups", lambda w: {"due_at": at(days=2), "reason": "course_details"}, **TEL_WRITE),
    R("patch", "/telecaller/follow-ups/{follow_up}", {"notes": "x"}, **TEL_EDIT),
    R("post", "/telecaller/follow-ups/{follow_up}/complete", {}, **TEL_EDIT),
    R("post", "/telecaller/follow-ups/{follow_up}/cancel", {"reason": "Lead asked"}, **TEL_EDIT),
    # tel-012 content library
    R("get", "/telecaller/scripts", **TEAM_READ),
    R("post", "/telecaller/scripts", lambda w: {"product_id": w["bare_product"], "name": f"T26 {uuid.uuid4().hex[:8]}",
                                                "steps": [{"title": "Open"}]}, mgr=201, mgr_out=201, super=201),
    R("patch", "/telecaller/scripts/{script}", {"active": False}, **MANAGERS),
    R("get", "/telecaller/templates", **TEAM_READ),
    R("post", "/telecaller/templates", lambda w: {"channel": "whatsapp", "kind": "welcome", "name": f"T26 {uuid.uuid4().hex[:8]}", "body": "Hi {name}"},
      mgr=201, mgr_out=201, super=201),
    R("patch", "/telecaller/templates/{template}", {"active": False}, **MANAGERS),
    R("get", "/telecaller/templates/{template}/preview", **TEAM_READ),
    R("get", "/telecaller/assets", **TEAM_READ),
    R("post", "/telecaller/assets", form=_pdf, mgr=201, mgr_out=201, super=201),
    R("patch", "/telecaller/assets/{asset}", {"active": False}, **MANAGERS),
    R("post", "/telecaller/assets/{asset}/link", {}, **TEAM_READ),
    R("get", "/public/telecaller-assets/{bad_token}", **{r: 404 for r in ROLES}),  # public: no sign-in needed, a bad token is 404
    # tel-013 / tel-014 messages
    R("get", "/telecaller/leads/{lead}/render?template_id={template}", **READ),
    R("get", "/telecaller/leads/{lead}/messages", **READ),
    R("post", "/telecaller/leads/{lead}/messages", {"channel": "whatsapp", "body": "Hello"}, **TEL_WRITE),
    R("delete", "/telecaller/messages/{message}", **(TEL_WRITE | {"tel": 204})),
    # tel-016 lead appointments
    R("get", "/telecaller/leads/{lead}/appointment-options", **READ),
    R("get", "/telecaller/leads/{lead}/appointments", **READ),
    # `{fresh}` has no open appointment (one per lead). §2.23: a manager's booking is refused on the role before the scope (403, no oracle).
    R("post", "/telecaller/leads/{fresh}/appointments", lambda w: {"appointment_type": "it_course_counselling", "counselor_id": w["cns_id"],
                                                                   "scheduled_at": at(days=4), "mode": "Online", "purpose": "Course fit"},
      **(TEL_WRITE | {"mgr_out": 403})),
    R("get", "/counselor/appointments", cns=200, cns_out=200),
    R("post", "/lead-appointments/{appointment}/confirm", **(ACTION | {"cns": 200, "tel": 403})),
    R("post", "/lead-appointments/{appointment}/complete", **(ACTION | {"cns": 200, "tel": 403})),
    R("post", "/lead-appointments/{appointment}/no-show", **(ACTION | {"cns": 200, "tel": 403})),
    R("post", "/lead-appointments/{appointment}/cancel", {"reason": "Lead asked"}, **(ACTION | {"cns": 200, "tel": 200})),
    R("post", "/lead-appointments/{appointment}/reschedule", lambda w: {"scheduled_at": at(days=5)}, **(ACTION | {"cns": 200, "tel": 200})),
    # tel-018 handover, return, student link
    R("post", "/telecaller/leads/{lead}/handover", lambda w: {"counselor_id": w["cns_id"]}, **READ),
    R("get", "/counselor/leads", cns=200, cns_out=200),
    R("get", "/counselor/leads/{handed}", **COUNSELOR_READ),
    R("get", "/counselor/leads/{handed}/timeline", **COUNSELOR_READ),
    R("post", "/counselor/leads/{handed}/return", {"reason": "Wrong course"}, **COUNSELOR_READ),
    R("get", "/counselor/leads/{handed}/link-suggestions", **COUNSELOR_READ),
    R("post", "/counselor/leads/{handed}/student-link", lambda w: {"student_id": w["student_id"]}, **COUNSELOR_READ),
    R("delete", "/counselor/leads/{linked}/student-link", **COUNSELOR_READ),
    R("get", "/admin/leads", **ADMINS),
    R("patch", "/admin/leads/{lead}", {"priority": "warm"}, it_admin=200, super=200),
    R("post", "/admin/leads/{lead}/conversion", lambda w: {"student_email": w["student_email"]}, it_admin=200, super=200),
    R("delete", "/admin/leads/{linked}/conversion", it_admin=200, super=200),
    R("get", "/admin/leads/{lead}/stage-history", it_admin=200, super=200),
    R("get", "/admin/leads/{lead}/timeline", it_admin=200, super=200),
    # tel-019 BDM meeting requests (the BDM side's own roles are tel-019's tests; here: who of the matrix reaches it)
    R("get", "/telecaller/meeting-requests/options", **SELF),
    R("post", "/telecaller/meeting-requests", lambda w: {"request_type": "college", "organization_name": "Govt College", "person_name": "Dr Rao",
                                                         "contact_phone": "+91 98765 43210", "proposed_at": at(days=2), "mode": "In person",
                                                         "purpose": "Partnership"}, tel=201, tel_out=201),
    R("get", "/telecaller/meeting-requests", **SELF),
    R("get", "/bdm/meeting-requests", super=200),
    R("get", "/bdm/meeting-requests/{request}", super=200),
    R("post", "/bdm/meeting-requests/{request}/accept", lambda w: {"organization_id": w["lead"], "contact_id": w["lead"], "starts_at": at(days=3),
                                                                   "appointment_type": "college_meeting"}),
    R("post", "/bdm/meeting-requests/{request}/decline", {"reason": "Not my territory"}),
    # tel-020 alert settings
    R("get", "/telecaller/settings", **MANAGERS),
    R("put", "/telecaller/settings/{team}", {"not_contacted_hours": 24, "hot_pending_hours": 4}, **MANAGERS),
    # tel-021 dashboard and daily activity, tel-023 performance
    R("get", "/telecaller/dashboard", **SELF),
    R("get", "/telecaller/activity", **SELF, mgr=422, mgr_out=422, super=422),  # a manager must name the telecaller (`user_id`)
    R("get", "/telecaller/activity?user_id={tel_id}", tel=200, tel_out=403, mgr=200, mgr_out=404, super=200),
    R("get", "/telecaller/manager/performance", **REPORTS),
    R("get", "/telecaller/manager/performance.csv", **REPORTS),
    # tel-022 targets
    R("post", "/telecaller/targets", {"scope": "team", "team": "it", "period": "daily", "values": {"calls": 80}}, **MANAGERS),
    R("get", "/telecaller/targets", **MANAGERS),
    R("get", "/telecaller/targets/effective", **SELF, mgr=422, mgr_out=422, super=422),  # a manager names a telecaller or a team
    R("get", "/telecaller/targets/effective?user_id={tel_id}", tel=200, tel_out=403, mgr=200, mgr_out=404, super=200),
    # tel-024 reports
    R("get", "/telecaller/reports/{kind}", **REPORTS),
    R("get", "/telecaller/reports/{kind}.csv", **REPORTS),
    # tel-025 lifecycle
    R("get", "/admin/telecallers/{spare_id}/open-work", it_admin=200, super=200),
    R("post", "/admin/telecallers/{spare_id}/deactivate", {}, it_admin=200, super=200),
    R("post", "/admin/telecallers/{gone_id}/handover", {"target": "queue"}, it_admin=200, super=200),
    R("post", "/admin/telecallers/{spare_id}/move-team", {"team": "overseas"}, super=200),
    R("post", "/admin/telecaller-managers/{spare_mgr_id}/deactivate", {}, super=200),
]

# AC2: each EVID-019 §22 "Telecaller should not" line, as the routes that would do it (PM5). A telecaller with work in the world must be refused
# (403) on every one; `{nobody}` is a random id, so a 403 here is the role gate, never a missing row. "Delete leads" is
# test_no_lead_delete_route plus the 405 below.
DENIED_22 = [
    ("Edit financial records", "post", "/admin/payments", lambda w: {"user_id": w["student_id"], "amount": 1000}),
    ("Edit financial records", "post", "/admin/payments/{nobody}/discount", {"amount": 100}),
    ("Edit financial records", "post", "/admin/payments/emi-schedule", {}),
    ("Modify application documents", "post", "/workflows/overseas/documents", lambda w: {"student_id": w["student_id"], "document_type": "Transcript",
                                                                                         "file_url": "uploads/t26.pdf"}),
    ("Modify application documents", "patch", "/workflows/overseas/documents/{nobody}/verify", {"verification_status": "verified"}),
    ("Change university application status", "patch", "/workflows/overseas/applications/{nobody}", {"status": "offer"}),
    ("Change university application status", "post", "/workflows/overseas/applications/{nobody}/advance", {"to_status": "offer"}),
    ("Change university application status", "post", "/workflows/overseas/agent/crm/applications/{nobody}/status", {"to_status": "offer"}),
    ("Change counselor records", "patch", "/admin/users/{cns_id}", {"full_name": "Renamed"}),
    ("Change counselor records", "put", "/workflows/overseas/applications/{nobody}/counselor", lambda w: {"counselor_id": w["cns_id"]}),
    ("Change counselor records", "post", "/counselor/leads/{handed}/return", {"reason": "Wrong course"}),
    ("Change counselor records", "post", "/counselor/leads/{handed}/student-link", lambda w: {"student_id": w["student_id"]}),
    ("Change counselor records", "post", "/lead-appointments/{appointment}/confirm", {}),
    ("Change counselor records", "post", "/lead-appointments/{appointment}/complete", {}),
    ("View confidential management reports", "get", "/telecaller/reports/{kind}", None),
    ("View confidential management reports", "get", "/telecaller/reports/{kind}.csv", None),
    ("View confidential management reports", "get", "/telecaller/manager/performance", None),
    ("View confidential management reports", "get", "/telecaller/manager/performance.csv", None),
    ("Modify employee targets", "post", "/telecaller/targets", {"scope": "team", "team": "it", "period": "daily", "values": {"calls": 1}}),
    ("Modify employee targets", "post", "/telecaller/targets", lambda w: {"scope": "user", "user_id": w["tel_id"], "period": "daily",
                                                                          "values": {"calls": 1}}),
    ("Modify employee targets", "get", "/telecaller/targets", None),
]

PREFIXES = ("/telecaller/", "/counselor/leads", "/counselor/appointments", "/lead-appointments/", "/admin/telecaller",
            "/admin/leads", "/bdm/meeting-requests", "/public/telecaller-assets/")


PATH_VALUES = {"kind": "source", "team": "it", "bad_token": "not-a-token", "nobody": str(uuid.uuid4())}  # the non-id path parameters


def _fill(text: str, w: dict) -> str:
    return text.format(**PATH_VALUES, **w)


async def _call(client, row: Row, w: dict, role: str):
    url = API + _fill(row.path, w)
    user = None if role == "anon" else w["users"][role]
    kwargs = {"headers": headers(user)}
    if row.form:
        data, files = row.form(w)
        kwargs |= {"data": data, "files": files, "headers": kwargs["headers"] | {"Idempotency-Key": uuid.uuid4().hex}}
    elif row.method != "get" and row.method != "delete":
        kwargs["json"] = row.body(w) if callable(row.body) else (row.body if row.body is not None else {})
    return await client.request(row.method.upper(), url, **kwargs)


def _operations() -> set[str]:
    """Every registered operation as "METHOD /path" (this FastAPI version does not flatten included routers into `app.routes`)."""
    return {f"{method.upper()} {path.removeprefix(API)}" for path, ops in app.openapi()["paths"].items() for method in ops}


def _template(key: str) -> str:
    """`GET /telecaller/leads/{lead}/calls?x=1` -> `GET /telecaller/leads/{}/calls`: placeholders compare by position only."""
    return re.sub(r"\{[^}]+\}", "{}", key.split("?")[0])


def test_every_telecaller_crm_route_has_a_row():
    """AC1 / PM1: a route added under the telecaller CRM prefixes without a matrix row (or a stale row) fails here."""
    routes = {_template(k) for k in _operations() if k.split(" ", 1)[1].startswith(PREFIXES)}
    rows = {_template(row.key) for row in MATRIX}
    assert routes - rows == set(), "routes without a matrix row"
    assert rows - routes == set(), "matrix rows without a route"


def test_no_lead_delete_route():
    """AC3 / §22 "should not delete leads": no DELETE anywhere in the API removes a lead (`.../leads/{id}` or `.../enquiries/{id}`)."""
    lead_deletes = [k for k in _operations() if re.fullmatch(r"DELETE .*/(leads|enquiries)/\{[^}]+\}", k)]
    assert lead_deletes == []


@pytest.mark.asyncio
@pytest.mark.parametrize("row", MATRIX, ids=lambda r: r.key)
async def test_matrix_row(client, db_session, row):
    """AC1: every route x role cell. Refused / hidden cells first on one world; then every 2xx cell on its own fresh world."""
    shared = await world(db_session)
    wrong = []
    for role in ROLES:
        want = row.expected(role)
        if want in OK:
            continue
        got = (await _call(client, row, shared, role)).status_code
        if got != want:
            wrong.append(f"{role}: want {want}, got {got}")
    for role in ROLES:
        want = row.expected(role)
        if want not in OK:
            continue
        response = await _call(client, row, await world(db_session), role)
        if response.status_code != want:
            wrong.append(f"{role}: want {want}, got {response.status_code} {response.text[:200]}")
    assert not wrong, " | ".join(wrong)


@pytest.mark.asyncio
@pytest.mark.parametrize(("line", "method", "path", "body"), DENIED_22, ids=[f"{d[0]}: {d[1].upper()} {d[2]}" for d in DENIED_22])
async def test_section_22_denied(client, db_session, line, method, path, body):
    """AC2: a telecaller (with leads, calls and an appointment of their own) is refused every §22 "should not" capability."""
    response = await _call(client, Row(method, path, body), await world(db_session), "tel")
    assert response.status_code == 403, f"{line}: {response.status_code} {response.text[:200]}"


@pytest.mark.asyncio
async def test_a_lead_cannot_be_deleted_through_its_routes(client, db_session):
    """AC3 / §22 "Delete leads": the lead paths take no DELETE for any role (405), and the lead is still there."""
    w = await world(db_session)
    for role in ("tel", "mgr", "super"):
        for path in ("/telecaller/leads/{lead}", "/admin/leads/{lead}", "/counselor/leads/{handed}"):
            assert (await _call(client, Row("delete", path), w, role)).status_code == 405
    assert (await _call(client, Row("get", "/telecaller/leads/{lead}"), w, "tel")).status_code == 200
