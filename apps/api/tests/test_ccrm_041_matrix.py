"""ccrm-041 -- the counselor CRM permission matrix (DEC-SCOPE-278 G1-G5, RBAC_MATRIX §2.192; spec
docs/superpowers/specs/2026-10-25-ccrm-041-go-live-verification-design.md). Source §2: "every role and permission should be tested before
go-live". Every route ccrm-001..040 added is called as every matrix role (ccrm041_helpers.ROLES): the overseas counselor who owns the
world's records, another overseas counselor, an IT counselor, both division admins, super_admin, the lead's telecaller and their manager,
the direct student, the agency Master, a management partner and nobody signed in.

A row lists only the cells that are not "refused": every unlisted signed-in role must get 403 and anonymous 401 (tel-026 PM3). The
expectations are each item's owner-approved rules (RBAC_MATRIX §2.153-§2.191), never what the code happens to return (G3). A write's 2xx
cell runs on a fresh world; reads and refused / hidden cells share one world (G5)."""

import re
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

import pytest

from app.main import app
from tests.ccrm041_helpers import ROLES, today, world
from tests.tel026_helpers import at, headers

API = "/api/v1"
OK = {200, 201, 204}
PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"


@dataclass
class Row:
    method: str
    path: str
    body: object = None  # a dict / callable(world) -> dict, sent as JSON
    form: bool = False  # a multipart upload of one PDF
    cells: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.method.upper()} {self.path}"

    def expected(self, role: str) -> int:
        return self.cells.get(role, 401 if role == "anon" else 403)


def R(method: str, path: str, body=None, *, form: bool = False, **cells) -> Row:
    return Row(method, path, body, form, cells)


def day(offset: int = 0) -> str:
    return (today() + timedelta(days=offset)).isoformat()


# The cells, by the rule of the item that added the route.
LEAD = {"cns_out": 404, "it_cns": 404}  # tel-017 counselor scope: owner + division, a lead outside it reads as missing (§2.157/2.158/2.173/2.174)
STUDENT = {"cns_out": 404}  # csc-001 visible students; the Overseas Admin any overseas student (§2.156/2.164/2.168/2.180/2.187/2.189)
SELF = {"cns": 200, "cns_out": 200}  # the session counselor's own work; the request names nobody (§2.183/2.188/2.191, ccrm-012/035)
STAFF_READ = {"cns": 200, "cns_out": 200, "ovs_admin": 200, "super": 200}  # §2.163 checklists, §2.165 task lists, §2.187 templates
ADMINS = {"ovs_admin": 200, "super": 200}  # §2.163/2.184/2.186/2.187 writes, the reminder rules, overdue by counselor
MANAGEMENT = {"partner": 200, "super": 200, "ovs_admin": 200}  # §2.181/2.182
TEL_NOTES = {"tel": 200, "mgr": 200, "super": 200}  # §2.157: the telecaller's own lead (also once handed over), the manager's team, all
LOST_READ = {"tel": 200, "mgr": 200, "super": 200, "cns": 200, "cns_out": 200, "it_cns": 200, "it_admin": 200, "ovs_admin": 200}  # §2.178
WHATSAPP = {"channel": "whatsapp", "body": "Please see the shortlist"}  # email is off in the test settings; WhatsApp needs no provider


def staff(code: int, **extra) -> dict:
    """An application route (§2.154/2.159/2.160/2.166/2.169-2.172/2.175/2.176/2.179): the counselor of the application, the Overseas Admin and
    -- G10 -- super_admin, whose overseas-workflow access every ccrm item kept (RBAC §1, DEC-SCOPE-263 SD3); another counselor 403."""
    return {"cns": code, "ovs_admin": code, "super": code, "cns_out": 403, **extra}


MATRIX = [
    # ccrm-002 lead notes (§2.157)
    R("get", "/telecaller/leads/{lead}/notes", **TEL_NOTES),
    R("post", "/telecaller/leads/{lead}/notes", {"body": "Called back"}, tel=201, mgr=201, super=201),
    R("get", "/counselor/leads/{lead}/notes", cns=200, **LEAD),
    R("post", "/counselor/leads/{lead}/notes", {"body": "Prefers the UK"}, cns=201, **LEAD),
    R("get", "/admin/leads/{lead}/notes", ovs_admin=200, super=200),
    R("post", "/admin/leads/{lead}/notes", {"body": "Checked"}, ovs_admin=201, super=201),
    # ccrm-003 counselor lead actions (§2.158)
    R("post", "/counselor/leads/{lead}/stage", lambda w: {"to_stage": "follow_up", "next_action": "Call back", "next_action_due": day(2)}, cns=200, **LEAD),
    R("put", "/counselor/leads/{lead}/next-action", lambda w: {"next_action": "Share the shortlist", "next_action_due": day(2)}, cns=200, **LEAD),
    R("get", "/counselor/leads/{lead}/follow-ups", cns=200, **LEAD),
    R("post", "/counselor/leads/{lead}/follow-ups", lambda w: {"due_at": at(days=2), "reason": "course_details"}, cns=201, **LEAD),
    R("patch", "/counselor/follow-ups/{follow_up}", {"notes": "Moved"}, cns=200, **LEAD),
    R("post", "/counselor/follow-ups/{follow_up}/complete", cns=200, **LEAD),
    R("post", "/counselor/follow-ups/{follow_up}/cancel", {"reason": "Lead asked"}, cns=200, **LEAD),
    R("get", "/counselor/follow-ups", cns=200, cns_out=200, it_cns=200),  # §2.165: any counselor, their own leads
    # ccrm-004 calls, messages, meetings (§2.173)
    R("get", "/counselor/leads/{lead}/calls", cns=200, **LEAD),
    R("post", "/counselor/leads/{lead}/calls", {"duration_seconds": 120, "call_type": "outgoing", "outcome": "interested"}, cns=201, **LEAD),
    R("patch", "/counselor/calls/{call}", {"remarks": "Late"}, cns=200, **LEAD),
    R("delete", "/counselor/calls/{call}", cns=204, **LEAD),
    R("get", "/counselor/leads/{lead}/render?template_id={tel_template}", cns=200, **LEAD),
    R("get", "/counselor/leads/{lead}/messages", cns=200, **LEAD),
    R("post", "/counselor/leads/{lead}/messages", WHATSAPP, cns=201, **LEAD),
    R("delete", "/counselor/messages/{message}", cns=204, **LEAD),
    R("get", "/counselor/leads/{lead}/meetings", cns=200, **LEAD),
    R("post", "/counselor/leads/{lead}/meetings", lambda w: {"occurred_at": at(days=-1), "mode": "Online", "notes": "Discussed intakes"}, cns=201, **LEAD),
    # ccrm-005 lead data fields (§2.174)
    R("patch", "/counselor/leads/{lead}", {"contact_preference": "email"}, cns=200, **LEAD),
    R("get", "/counselor/leads/{lead}/qualification", cns=200, **LEAD),
    R("put", "/counselor/leads/{lead}/qualification", {"qualification": "B.Tech", "city": "Pune"}, cns=200, **LEAD),
    # ccrm-006 lost reasons (§2.178)
    R("get", "/telecaller/lost-reasons", **LOST_READ),
    R("post", "/telecaller/lost-reasons", lambda w: {"name": f"C41 {uuid.uuid4().hex[:8]}"}, mgr=201, super=201),
    R("patch", "/telecaller/lost-reasons/{lost_reason}", {"active": False}, mgr=200, super=200),
    # ccrm-008 convert (§2.167): an IT counselor is refused on the role before the scope
    R("post", "/counselor/leads/{lead}/convert", lambda w: {"full_name": "Converted Student", "email": f"c41-conv-{uuid.uuid4().hex[:8]}@example.local"}, cns=201, cns_out=404),
    # ccrm-007 structured profile (§2.164)
    R("get", "/counselor/students/{student}/profile", cns=200, ovs_admin=200, **STUDENT),
    R("put", "/counselor/students/{student}/profile", {"city": "Pune"}, cns=200, ovs_admin=200, **STUDENT),
    R("get", "/overseas/me/profile", student=200),
    R("put", "/overseas/me/profile", {"city": "Chennai"}, student=200),
    R("get", "/workflows/overseas/agent/crm/students/{record}/profile", agent=200),
    # ccrm-009 student 360 (§2.168), ccrm-010 notes (§2.156), ccrm-039 finance (§2.189)
    R("get", "/counselor/students/{student}/overview", cns=200, ovs_admin=200, **STUDENT),
    R("get", "/counselor/students/{student}/documents", cns=200, ovs_admin=200, **STUDENT),
    R("get", "/counselor/students/{student}/activities", cns=200, ovs_admin=200, **STUDENT),
    R("get", "/counselor/students/{student}/history", cns=200, ovs_admin=200, **STUDENT),
    R("get", "/counselor/students/{student}/notes", cns=200, ovs_admin=200, **STUDENT),
    R("post", "/counselor/students/{student}/notes", {"body": "Shortlist sent"}, cns=201, ovs_admin=201, **STUDENT),
    R("get", "/counselor/students/{student}/finance", cns=200, ovs_admin=200, **STUDENT),
    # ccrm-020 document requests (§2.180)
    R("get", "/counselor/students/{student}/document-requests", cns=200, ovs_admin=200, **STUDENT),
    R("post", "/counselor/students/{student}/document-requests", lambda w: {"due_date": day(5), "document_type": "CV"}, cns=201, ovs_admin=201, **STUDENT),
    R("post", "/counselor/students/{student}/document-requests/{request}/cancel", cns=200, ovs_admin=200, **STUDENT),
    R("get", "/overseas/me/document-requests", student=200),
    R("post", "/overseas/me/document-requests/{request}/upload", form=True, student=201),
    # ccrm-011 / ccrm-012 quick search (§2.161)
    R("get", "/counselor/search?q=Lead", **SELF),
    # ccrm-013 application details (§2.171)
    R("get", "/workflows/overseas/applications/{app}/details", **staff(200)),
    R("patch", "/workflows/overseas/applications/{app}/details", {"faculty": "Engineering"}, **staff(200)),
    # ccrm-014 sub-status (§2.154)
    R("post", "/workflows/overseas/applications/{app}/sub-status", {"sub_status": "unconditional_offer"}, **staff(200)),
    R("post", "/workflows/overseas/agent/crm/applications/{agency_app}/sub-status", {"sub_status": "documents_pending"}, agent=200),
    # ccrm-015 outcomes (§2.159)
    R("post", "/workflows/overseas/applications/{app}/outcome", {"outcome": "rejected", "reason": "Grades below the cut-off"}, **staff(200)),
    R("post", "/workflows/overseas/applications/{held}/outcome/reopen", {"reason": "Funds arrived"}, **staff(200)),
    # ccrm-018 checklist templates (§2.163)
    R("get", "/overseas-admin/checklists", **STAFF_READ),
    R("get", "/overseas-admin/checklists/{checklist_template}", **STAFF_READ),
    R(
        "post",
        "/overseas-admin/checklists",
        lambda w: {"name": f"C41 {uuid.uuid4().hex[:8]}", "kind": "admission", "country_id": w["country"], "gate_mode": "warn", "items": [{"document_type": "Passport", "required": True}]},
        ovs_admin=201,
        super=201,
    ),
    R(
        "put",
        "/overseas-admin/checklists/{checklist_template}",
        lambda w: {
            "name": f"C41 {uuid.uuid4().hex[:8]}",
            "kind": "visa",
            "country_id": w["country"],
            "gate_mode": "warn",
            "items": [{"document_type": "Passport", "required": True}],
            "version": 1,
            "active": True,
        },
        **ADMINS,
    ),
    R("get", "/overseas-admin/checklists/resolve?application_id={app}&kind=visa", **staff(200)),
    # ccrm-019 application checklist (§2.172)
    R("get", "/workflows/overseas/applications/{app}/checklist", **staff(200, student=200)),
    R("post", "/workflows/overseas/applications/{agency_app}/checklist", **staff(201)),  # one with no checklist yet
    R("post", "/workflows/overseas/applications/{app}/checklist/items", {"document_type": "SOP", "required": False}, **staff(201)),
    R("patch", "/workflows/overseas/applications/{app}/checklist/items/{item}", {"mark": "requested"}, **staff(200)),
    R("delete", "/workflows/overseas/applications/{app}/checklist/items/{item}", **staff(200)),
    R("put", "/workflows/overseas/applications/{app}/checklist/items/{item}/documents/{document}", **staff(200)),
    R("delete", "/workflows/overseas/applications/{app}/checklist/items/{item}/documents/{document}", **staff(200)),
    # ccrm-021 document versions (§2.166)
    R("post", "/workflows/overseas/documents/{document}/versions", form=True, **staff(201)),
    # ccrm-023 offers (§2.160), ccrm-024 conditions (§2.175), ccrm-025 decision + deposit (§2.170)
    R("get", "/workflows/overseas/applications/{app}/offers", **staff(200, student=200)),
    R("post", "/workflows/overseas/applications/{app}/offer-letters", form=True, **staff(201)),
    R("post", "/workflows/overseas/applications/{app}/offers", lambda w: {"offer_type": "unconditional", "issue_date": day(-1), "offer_document_id": w["letter"]}, **staff(201)),
    R("post", "/workflows/overseas/applications/{app}/offers/{offer}/withdraw", {"status": "withdrawn_by_university", "reason": "Course closed"}, **staff(200)),
    R("post", "/workflows/overseas/applications/{app}/offers/{offer}/conditions", {"description": "Pay the deposit", "owner": "student"}, **staff(201)),
    R("patch", "/workflows/overseas/applications/{app}/offers/{offer}/conditions/{condition}", lambda w: {"due_date": day(25)}, **staff(200)),
    R("post", "/workflows/overseas/applications/{app}/condition-evidence", form=True, **staff(201)),
    R("post", "/workflows/overseas/applications/{app}/offers/{offer}/decision", {"decision": "accepted"}, **staff(200)),
    R("get", "/workflows/overseas/applications/{app}/deposit", **staff(200, student=200)),
    R("put", "/workflows/overseas/applications/{app}/deposit", lambda w: {"required": True, "payment_status": "pending", "amount": "3000", "currency": "GBP", "due_date": day(14)}, **staff(200)),
    R("post", "/workflows/overseas/applications/{app}/deposit-receipts", form=True, **staff(201)),
    # ccrm-026 visa lifecycle (§2.169)
    R("patch", "/workflows/overseas/visa/{visa}/lifecycle", {"expected_visa_status": "not_started", "visa_category": "Student"}, **staff(200)),
    # ccrm-027 enrolment (§2.176), ccrm-028 arrival (§2.179)
    R("get", "/workflows/overseas/applications/{app}/enrollment", **staff(200, student=200)),
    R("post", "/workflows/overseas/applications/{app}/enrollment-documents", form=True, **staff(201)),
    R(
        "put",
        "/workflows/overseas/applications/{app}/enrollment",
        lambda w: {"expected_status": "offer", "enrollment_date": day(), "enrollment_document_id": w["enrol_doc"], "pre_enrollment_checklist_complete": True},
        **staff(200),
    ),
    R("get", "/workflows/overseas/applications/{app}/arrival", **staff(200, student=200)),
    R("put", "/workflows/overseas/applications/{enrolled}/arrival", {"notes": "Flight booked"}, **staff(200)),  # recorded after enrolment
    # ccrm-029 tasks (§2.165), ccrm-031 overdue escalation (§2.186)
    R("get", "/counselor/tasks", **STAFF_READ),
    R("get", "/counselor/tasks/options", **STAFF_READ),
    R("get", "/counselor/tasks/{task}", cns=200, cns_out=404, ovs_admin=200, super=200),
    R("post", "/counselor/tasks", lambda w: {"title": "Chase the transcript", "due_on": day(1), "counselor_user_id": w["cns_id"]}, cns=201, ovs_admin=201, super=201),
    R("patch", "/counselor/tasks/{task}", {"status": "done"}, cns=200, cns_out=404, ovs_admin=200, super=200),
    R("get", "/counselor/tasks/overdue-by-counselor", **ADMINS),
    # ccrm-030 reminder rules (§2.184): the values written are RM1's defaults, so the shared database keeps them
    R("get", "/overseas-admin/reminder-rules", **ADMINS),
    R("put", "/overseas-admin/reminder-rules/{rule}", {"enabled": True, "offset_days": 3, "notify_student": True}, **ADMINS),
    R("post", "/overseas-admin/reminder-rules/run", **ADMINS),
    R("get", "/overseas-admin/reminder-rules/log", **ADMINS),
    # ccrm-032 dashboard (§2.191), ccrm-036 performance (§2.183), ccrm-035 exports (§2.182), ccrm-034 reports (§2.181)
    R("get", "/counselor/dashboard", **SELF),
    R("get", "/counselor/performance", **SELF),
    R("get", "/counselor/exports/applications", **SELF),
    R("get", "/counselor/exports/leads", **SELF),
    R("get", "/management/crm-reports", **MANAGEMENT),
    R("get", "/management/crm-reports/export?report=ageing", **MANAGEMENT),
    R("get", "/management/crm-reports/universities/{university}/applications", **MANAGEMENT),  # ccrm-052 (§2.181)
    # ccrm-037 templates and the student message log (§2.187)
    R("get", "/counselor/templates", **STAFF_READ),
    R("get", "/counselor/templates/{template}/preview", **STAFF_READ),
    R("post", "/counselor/templates", lambda w: {"channel": "email", "name": f"C41 {uuid.uuid4().hex[:8]}", "subject": "Hello", "body": "Hi"}, ovs_admin=201, super=201),
    R("patch", "/counselor/templates/{template}", {"active": False}, **ADMINS),
    R("get", "/counselor/students/{student}/messages", cns=200, ovs_admin=200, **STUDENT),
    R("get", "/counselor/students/{student}/messages/render?template_id={template}", cns=200, **STUDENT),
    R("post", "/counselor/students/{student}/messages", WHATSAPP, cns=201, **STUDENT),
    R("post", "/counselor/students/{student}/replies", {"channel": "whatsapp", "body": "Thanks"}, cns=201, **STUDENT),
    # ccrm-038 calendar feed (§2.188): the session's own feed; the .ics is public and its token the credential, a bad one is 404 for all
    R("get", "/counselor/calendar-feed", **SELF),
    R("post", "/counselor/calendar-feed", cns=201, cns_out=201),
    R("delete", "/counselor/calendar-feed", cns=204, cns_out=204),
    R("get", "/calendar/feeds/{bad_token}.ics", **{r: 404 for r in ROLES}),
    # ccrm-040 archive and consent (§2.190)
    R("post", "/counselor/students/{lonely}/archive", {"reason": "Studying locally instead"}, cns=200, ovs_admin=200, **STUDENT),
    R("post", "/counselor/students/{archived}/restore", ovs_admin=200),
    R("get", "/counselor/students/archived", cns=200, cns_out=200, ovs_admin=200),
    R("get", "/overseas/me/consents", student=200),
    R("post", "/overseas/me/consents/{agreement}/accept", student=201),
]

# G1: the counselor CRM surface. A route under these prefixes needs a row here, or is one of the routes that predate ccrm (EARLIER), whose
# roles their own items pin. The ccrm routes under tel-026's prefixes are named one by one.
PREFIXES = (
    "/counselor/",
    "/overseas-admin/checklists",
    "/overseas-admin/reminder-rules",
    "/overseas/me/",
    "/calendar/feeds/",
    "/management/crm-reports",
    "/workflows/overseas/applications/{}/",
    "/workflows/overseas/documents/{}/versions",
    "/workflows/overseas/visa/{}/lifecycle",
)
NAMED = {
    "GET /telecaller/leads/{}/notes",
    "POST /telecaller/leads/{}/notes",
    "GET /admin/leads/{}/notes",
    "POST /admin/leads/{}/notes",
    "GET /telecaller/lost-reasons",
    "POST /telecaller/lost-reasons",
    "PATCH /telecaller/lost-reasons/{}",
    "POST /workflows/overseas/agent/crm/applications/{}/sub-status",
    "GET /workflows/overseas/agent/crm/students/{}/profile",
}
EARLIER = {  # before ccrm-001 (OpenAPI at 37f087fa): tel-018 / tel-016 (test_tel_026_matrix.py), csc-001..005, AGN-008/012, the overseas workflow
    "GET /counselor/appointments",
    "GET /counselor/leads",
    "GET /counselor/leads/{}",
    "GET /counselor/leads/{}/timeline",
    "GET /counselor/leads/{}/link-suggestions",
    "POST /counselor/leads/{}/return",
    "POST /counselor/leads/{}/student-link",
    "DELETE /counselor/leads/{}/student-link",
    "GET /counselor/students",
    "POST /counselor/students",
    "PATCH /counselor/students/{}",
    "POST /counselor/students/{}/welcome-links",
    "GET /counselor/walk-in-leads/duplicate-check",
    "POST /counselor/walk-in-leads",
    "POST /counselor/walk-in-leads/{}/enquiries",
    "PATCH /workflows/overseas/applications/{}",
    "POST /workflows/overseas/applications/{}/advance",
    "PUT /workflows/overseas/applications/{}/counselor",
    "GET /workflows/overseas/applications/{}/status",
    "GET /workflows/overseas/applications/{}/visa-checklist",
    "GET /workflows/overseas/applications/{}/visa-status",
}

PATH_VALUES = {"bad_token": "not-a-token", "rule": "offer_deadline"}  # the non-id path parameters


def _fill(text: str, w: dict) -> str:
    return text.format(**PATH_VALUES, **w)


async def _call(client, row: Row, w: dict, role: str):
    url = API + _fill(row.path, w)
    user = None if role == "anon" else w["users"][role]
    kwargs = {"headers": headers(user)}
    if row.form:
        kwargs["files"] = {"file": ("c41.pdf", PDF, "application/pdf")}
    elif row.method not in ("get", "delete"):
        body = row.body(w) if callable(row.body) else row.body
        if body is not None:
            kwargs["json"] = body
    return await client.request(row.method.upper(), url, **kwargs)


def _template(key: str) -> str:
    """`GET /counselor/leads/{lead}/render?x=1` -> `GET /counselor/leads/{}/render`: placeholders compare by position only."""
    return re.sub(r"\{[^}]+\}", "{}", key.split("?")[0])


def operations() -> set[str]:
    """Every registered operation as a placeholder template ("METHOD /path/{}")."""
    return {_template(f"{method.upper()} {path.removeprefix(API)}") for path, ops in app.openapi()["paths"].items() for method in ops}


CCRM_ROUTES = {_template(row.key) for row in MATRIX}  # tel-026's inventory leaves these to this matrix (G4)


def test_every_counselor_crm_route_has_a_row():
    """G1: a route added to the counselor CRM surface without a matrix row (or a stale row) fails here."""
    surface = {k for k in operations() if k.split(" ", 1)[1].startswith(PREFIXES) or k in NAMED}
    assert surface - CCRM_ROUTES - EARLIER == set(), "routes without a matrix row"
    assert CCRM_ROUTES - surface == set(), "matrix rows without a route"
    assert len(MATRIX) == len(CCRM_ROUTES), "one row per route"


@pytest.mark.asyncio
@pytest.mark.parametrize("row", MATRIX, ids=lambda r: r.key)
async def test_matrix_row(client, db_session, row):
    """Every route x role cell: reads and refused / hidden cells on one world, then every 2xx write cell on its own fresh world."""
    shared = await world(db_session, client)
    wrong = []
    for role in ROLES:
        want = row.expected(role)
        if want in OK and row.method != "get":
            continue
        got = await _call(client, row, shared, role)
        if got.status_code != want:
            wrong.append(f"{role}: want {want}, got {got.status_code} {got.text[:160]}")
    for role in ROLES:
        want = row.expected(role)
        if want not in OK or row.method == "get":
            continue
        response = await _call(client, row, await world(db_session, client), role)
        if response.status_code != want:
            wrong.append(f"{role}: want {want}, got {response.status_code} {response.text[:200]}")
    assert not wrong, " | ".join(wrong)
