"""upc-033 -- the University Partnership CRM permission matrix as built (spec docs/superpowers/specs/2026-10-10-upc-033-permission-matrix-design.md,
RBAC_MATRIX §2.100). Every route under the partnership prefixes is called as every matrix role (upc033_helpers.ROLES): a partnership manager and a
head with the world's universities and each again on *another* team, super_admin, overseas_admin, it_admin, a college BDM, an overseas counselor,
the world university's rep, an agent, an overseas student and nobody signed in.

A row lists only the cells that are not "refused": every unlisted signed-in role must get 403 and anonymous 401 (PX3). Refused cells and every
GET share one world per row; every other 2xx cell runs on its own fresh world, so one cell's write never changes what another sees (PX5).
The expectations are the owner-approved rules of each item (RBAC_MATRIX §2.44-§2.99). Out of scope is 403 in this module (PX4): reads are
not team-filtered and a write outside the team is refused with "This university belongs to another partnership team"."""

import re
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

import pytest

from app.main import app
from tests.upc033_helpers import PDF, ROLES, headers, today, world

API = "/api/v1"
OK = {200, 201, 204}
PREFIXES = ("/partnership/", "/admin/partnership-", "/universities/")  # PX1


@dataclass
class Row:
    method: str
    path: str
    body: object = None  # a dict / callable(world) -> dict, sent as JSON
    form: object = None  # callable(world) -> (data, files), sent as multipart (with an Idempotency-Key)
    cells: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.method.upper()} {self.path}"

    def expected(self, role: str) -> int:
        return self.cells.get(role, 401 if role == "anon" else 403)


def R(method: str, path: str, body=None, *, form=None, **cells) -> Row:
    return Row(method, path, body, form, cells)


def _all(status: int, *roles: str) -> dict:
    return dict.fromkeys(roles, status)


STAFF = ("pm", "pm_out", "head", "head_out", "super")  # the partnership staff + super_admin (= the commission roles)
READERS = (*STAFF, "ovs_admin")  # upc-003 `require_reader`: the master and its read-only slices
OWNERS = ("pm", "head", "super")  # the university's manager, their head, super_admin: `can_edit_contacts` / `can_move_stage` / agreements
EDITORS = (*OWNERS, "ovs_admin")  # upc-003 `can_edit`: the master's fields and courses (upc-017)
CATALOGUE = ("head", "super", "ovs_admin")  # upc-003 UM5/UM7/UM8: publish, (de)activate; on any of the head's own or unowned universities
IMPORTERS = ("head", "head_out", "super", "ovs_admin")  # upc-005: the catalogue roles, every head on its own batches
TEMPLATE_EDITORS = ("head", "head_out", "super")  # upc-012: the global template library
RECEIPTS = ("head", "head_out", "super")  # upc-019 CL9 / Q-20: heads and super_admin record receipts (no team rule, PX9)


def _day(days: int) -> str:
    return (today() + timedelta(days=days)).isoformat()


def _u() -> str:
    return uuid.uuid4().hex[:8]


def _pdf(_w):
    return {"kind": "brochure", "title": f"U33 brochure {_u()}"}, {"file": ("b.pdf", PDF, "application/pdf")}


def _pdf_version(_w):
    return {}, {"file": ("v2.pdf", PDF, "application/pdf")}


def _universities_csv(_w):
    return {}, {"file": ("u.csv", f"name,country,city,institution_type\nU33 Import {_u()},GB,York,university\n".encode(), "text/csv")}


def _courses_csv(_w):
    header = "title,level,category,duration,intakes,tuition_amount,tuition_currency,english_test,english_score,deadline,active"
    return {}, {"file": ("c.csv", f"{header}\nMSc U33 Import {_u()},PG,Tech,1 year,,,,,,,\n".encode(), "text/csv")}


MATRIX = [
    # upc-001 roles: own profile, the head's team, the admin pickers; upc-032 reassignment
    R("get", "/partnership/me", **_all(200, "pm", "pm_out")),
    R("patch", "/partnership/profile", {"phone": "+91 90000 00009"}, **_all(200, "pm", "pm_out")),
    R("get", "/partnership/head/team", **_all(200, "head", "head_out", "super")),
    R("post", "/partnership/head/reassign", lambda w: {"from_user_id": w["pm_id"], "to_user_id": w["pm2_id"]}, **_all(200, "head", "super")),
    R("get", "/admin/partnership-managers", **_all(200, "super", "ovs_admin")),
    R("get", "/admin/partnership-heads", **_all(200, "super", "ovs_admin")),
    # upc-003 the Global University Master, upc-004 duplicates, upc-024 search, upc-025 map
    R("get", "/partnership/universities", **_all(200, *READERS)),
    R("get", "/partnership/universities/search?q=U33", **_all(200, *READERS)),
    R("get", "/partnership/universities/map", **_all(200, *READERS)),
    R("post", "/partnership/universities", lambda w: {"name": f"U33 New {_u()}", "country_id": w["country"], "city": "York"}, **_all(201, "head", "head_out", "super", "ovs_admin")),
    R("get", "/partnership/universities/duplicates?name=U33", **_all(200, *READERS)),
    R("get", "/partnership/universities/manager-options", **_all(200, "head", "head_out", "super")),
    R("get", "/partnership/universities/{uni}", **_all(200, *READERS)),
    R("patch", "/partnership/universities/{uni}", {"city": "Manchester"}, **_all(200, *EDITORS)),
    R("post", "/partnership/universities/{uni}/assign", lambda w: {"primary_manager_user_id": w["pm2_id"], "backup_manager_user_id": None}, **_all(200, "head", "super")),
    R("post", "/partnership/universities/{internal}/publish", **_all(200, *CATALOGUE)),
    R("post", "/partnership/universities/{uni}/unpublish", **_all(200, *CATALOGUE)),
    R("post", "/partnership/universities/{uni}/deactivate", {"confirm": True}, **_all(200, *CATALOGUE)),
    R("post", "/partnership/universities/{inactive}/reactivate", **_all(200, *CATALOGUE)),
    # upc-005 university CSV import (R11 precedent: another uploader's batch is hidden)
    R("get", "/partnership/universities/imports/template", **_all(200, *IMPORTERS)),
    R("post", "/partnership/universities/import", form=_universities_csv, **_all(201, *IMPORTERS)),
    R("get", "/partnership/universities/imports", **_all(200, *IMPORTERS)),
    R("get", "/partnership/universities/imports/{batch}", head=200, super=200, head_out=404, ovs_admin=404),
    R("get", "/partnership/universities/imports/{batch}/report.csv", head=200, super=200, head_out=404, ovs_admin=404),
    # upc-006 contacts (overseas_admin reads the shareable slice)
    R("get", "/partnership/contact-roles", **_all(200, *READERS)),
    R("get", "/partnership/universities/{uni}/contacts", **_all(200, *READERS)),
    R("post", "/partnership/universities/{uni}/contacts", lambda w: {"name": f"U33 Contact {_u()}"}, **_all(201, *OWNERS)),
    R("patch", "/partnership/contacts/{contact}", {"designation": "Director"}, **_all(200, *OWNERS)),
    R("delete", "/partnership/contacts/{spare_contact}", **_all(204, *OWNERS)),
    # upc-007 stage engine
    R("post", "/partnership/universities/{uni}/stage", {"from_stage": "target_university", "to_stage": "researching"}, **_all(200, *OWNERS)),
    R("post", "/partnership/universities/{uni}/lost", {"reason": "No response after 3 follow-ups"}, **_all(200, *OWNERS)),
    R("post", "/partnership/universities/{lost}/reopen", {"reason": "Dean re-engaged"}, **_all(200, "head", "super")),
    R("get", "/partnership/universities/{uni}/stage-history", **_all(200, *READERS)),
    R("get", "/partnership/pipeline", **_all(200, *READERS)),
    # upc-008 expected timeline + milestones, upc-023 probability, upc-027 onboarding
    R("get", "/partnership/universities/{uni}/milestones", **_all(200, *READERS)),
    R("patch", "/partnership/universities/{uni}/milestones/{milestone}", lambda w: {"target_date": _day(30)}, **_all(200, *OWNERS)),
    R("patch", "/partnership/universities/{uni}/expected", {"expected_intake": "Sep 2027"}, **_all(200, *OWNERS)),
    R("get", "/partnership/expected", **_all(200, *STAFF)),
    R("put", "/partnership/universities/{uni}/probability", {"probability": 55, "reason": "Strong interest"}, **_all(200, *OWNERS)),
    R("get", "/partnership/universities/{uni}/onboarding", **_all(200, *READERS)),
    R("patch", "/partnership/universities/{uni}/onboarding/{onboarding}", {"status": "in_progress"}, **_all(200, *OWNERS)),
    # upc-026 documents (overseas_admin reads the shareable slice)
    R("get", "/partnership/universities/{uni}/documents", **_all(200, *READERS)),
    R("get", "/partnership/documents", **_all(200, *READERS)),
    R("post", "/partnership/universities/{uni}/documents", form=_pdf, **_all(201, *OWNERS)),
    R("post", "/partnership/universities/{uni}/documents/{doc}/versions", form=_pdf_version, **_all(201, *OWNERS)),
    R("patch", "/partnership/universities/{uni}/documents/{doc}", lambda w: {"title": f"Fees U33 {_u()}"}, **_all(200, *OWNERS)),
    R("get", "/partnership/universities/{uni}/documents/{doc}/file", **_all(200, *READERS)),
    # upc-014 agreements (AG13: the partnership staff read every agreement)
    R("get", "/partnership/universities/{uni}/agreements", **_all(200, *STAFF)),
    R("get", "/partnership/universities/{uni}/agreement-options", **_all(200, *OWNERS)),
    R("get", "/partnership/agreement-signatories", **_all(200, *STAFF)),
    R("get", "/partnership/agreements", **_all(200, *STAFF)),
    R("get", "/partnership/agreements/{agreement}", **_all(200, *STAFF)),
    R(
        "post",
        "/partnership/universities/{uni}/agreements",
        lambda w: {"agreement_type": "partnership_agreement", "start_date": _day(-5), "expiry_date": _day(900), "exclusivity": "non_exclusive"},
        **_all(201, *OWNERS),
    ),
    R("patch", "/partnership/agreements/{agreement}", {"territory": "United Kingdom"}, **_all(200, *OWNERS)),
    R("post", "/partnership/agreements/{agreement}/status", {"from_status": "draft", "to_status": "sent"}, **_all(200, *OWNERS)),
    R("post", "/partnership/agreements/{signed}/renew", lambda w: {"start_date": _day(701), "expiry_date": _day(1800)}, **_all(201, *OWNERS)),
    # upc-016 commission terms (restricted, U2: the commission roles only)
    R("get", "/partnership/agreements/{agreement}/commission-terms", **_all(200, *STAFF)),
    R("post", "/partnership/agreements/{agreement}/commission-terms", {"fixed_amount": "500", "currency": "GBP", "trigger": "enrolment"}, **_all(201, *OWNERS)),
    R("patch", "/partnership/agreements/{agreement}/commission-terms/{term}", {"conditions": "Paid in two parts"}, **_all(200, *OWNERS)),
    R("delete", "/partnership/agreements/{agreement}/commission-terms/{term}", **_all(204, *OWNERS)),
    R("get", "/partnership/commission-terms", **_all(200, *STAFF)),
    # upc-019 commission ledger (restricted)
    R("get", "/partnership/universities/{uni}/commission", **_all(200, *STAFF)),
    R("post", "/partnership/universities/{uni}/commission/receipts", lambda w: {"amount": "120.00", "currency": "GBP", "received_on": w["today"], "reference": f"REM-{_u()}"}, **_all(201, *RECEIPTS)),
    R("delete", "/partnership/universities/{uni}/commission/receipts/{receipt}", **_all(204, *RECEIPTS)),
    # upc-017 courses (overseas_admin edits courses, never their commission: CO2)
    R("get", "/partnership/universities/{uni}/courses", **_all(200, *READERS)),
    R("get", "/partnership/universities/{uni}/course-options", **_all(200, *EDITORS)),
    R("post", "/partnership/universities/{uni}/courses", lambda w: {"title": f"MA U33 {_u()}", "level": "PG", "category": "Arts", "duration": "1 year"}, **_all(201, *EDITORS)),
    R("patch", "/partnership/universities/{uni}/courses/{course}", {"duration": "2 years"}, **_all(200, *EDITORS)),
    R("get", "/partnership/courses", **_all(200, *READERS)),
    R("get", "/partnership/universities/{uni}/courses/imports/template", **_all(200, *EDITORS)),
    R("post", "/partnership/universities/{uni}/courses/import", form=_courses_csv, **_all(201, *EDITORS)),
    # upc-012 templates, messages, calls; upc-013 timeline
    R("get", "/partnership/templates", **_all(200, *STAFF)),
    R("post", "/partnership/templates", lambda w: {"channel": "whatsapp", "name": f"U33 {_u()}", "body": "Dear {name}"}, **_all(201, *TEMPLATE_EDITORS)),
    R("patch", "/partnership/templates/{template}", {"active": False}, **_all(200, *TEMPLATE_EDITORS)),
    R("get", "/partnership/templates/{template}/preview", **_all(200, *STAFF)),
    R("get", "/partnership/messages/render?template_id={template}&contact_id={contact}", **_all(200, *STAFF)),
    R("post", "/partnership/messages", lambda w: {"contact_id": w["contact"], "channel": "whatsapp", "body": "Hello"}, **_all(201, *OWNERS)),
    R("post", "/partnership/calls", lambda w: {"contact_id": w["contact"], "outcome": "connected"}, **_all(201, *OWNERS)),
    R("get", "/partnership/universities/{uni}/calls", **_all(200, *STAFF)),
    R("get", "/partnership/universities/{uni}/messages", **_all(200, *STAFF)),
    R("get", "/partnership/universities/{uni}/timeline", **_all(200, *STAFF)),
    # upc-009 meetings (MG14/MG15: the responsible manager or creator acts; super_admin reads)
    R("get", "/partnership/meetings", **_all(200, *STAFF)),
    R("post", "/partnership/meetings", lambda w: {"university_id": w["uni"], "meeting_type": "mou_discussion", "starts_at": f"{_day(3)}T10:00:00+05:30", "mode": "offline"}, **_all(201, "pm", "head")),
    R("get", "/partnership/meetings/{meeting}", **_all(200, *STAFF)),
    R("patch", "/partnership/meetings/{meeting}", {"agenda": "Fees and intakes"}, pm=200),
    R("post", "/partnership/meetings/{meeting}/complete", {"notes": "Met the dean"}, pm=200),
    R("post", "/partnership/meetings/{meeting}/cancel", {"reason": "Clash"}, pm=200),
    # upc-010 visits (VS6/VS7: the lead acts; the lead's head approves)
    R("get", "/partnership/visits", **_all(200, *STAFF)),
    R("get", "/partnership/visits/approvals", **_all(200, "head", "head_out", "super")),
    R("get", "/partnership/visits/university-options", **_all(200, "pm", "pm_out", "head", "head_out")),
    R("get", "/partnership/visits/lead-options", **_all(200, "pm", "pm_out", "head", "head_out")),
    R("get", "/partnership/visits/employee-options", **_all(200, *STAFF)),
    R("post", "/partnership/visits", lambda w: {"university_id": w["uni"], "purpose": "Discuss MoU", "proposed_date": _day(10)}, **_all(201, "pm", "head")),
    R("get", "/partnership/visits/{draft_visit}", **_all(200, *STAFF)),
    R("patch", "/partnership/visits/{draft_visit}", {"purpose": "Discuss the renewal"}, pm=200),
    R("post", "/partnership/visits/{draft_visit}/submit", pm=200),
    R("post", "/partnership/visits/{waiting_visit}/approve", head=200),
    R("post", "/partnership/visits/{waiting_visit}/reject", {"reason": "Fix the dates"}, head=200),
    R("post", "/partnership/visits/{approved_visit}/book", pm=200),
    R("post", "/partnership/visits/{booked_visit}/complete", lambda w: {"follow_up_date": _day(7)}, pm=200),
    R("post", "/partnership/visits/{done_visit}/follow-up", pm=200),
    R("post", "/partnership/visits/{draft_visit}/close", {"reason": "Called off"}, pm=200),
    # upc-011 events + calendar
    R("post", "/partnership/events", lambda w: {"kind": "education_fair", "title": "QS Fair", "starts_on": _day(5), "ends_on": _day(7)}, **_all(201, "pm", "pm_out", "head", "head_out")),
    R("get", "/partnership/events/{event}", **_all(200, *STAFF)),
    R("patch", "/partnership/events/{event}", {"title": "QS Fair (moved)"}, pm=200),
    R("post", "/partnership/events/{event}/cancel", {"reason": "Postponed"}, pm=200),
    R("get", "/partnership/calendar?date_from={today}&date_to={today}", **_all(200, *STAFF)),
    R("get", "/partnership/calendar/employees", **_all(200, *STAFF)),
    # upc-020 tasks (TK8/TK9: the assignee or the assignee's head acts)
    R("get", "/partnership/tasks", **_all(200, *STAFF)),
    R("get", "/partnership/tasks/catalogue", **_all(200, *STAFF)),
    R("post", "/partnership/tasks", lambda w: {"university_id": w["uni"], "kind": "follow_up", "title": "Follow-up call", "due_on": _day(2)}, **_all(201, "pm", "head")),
    R("patch", "/partnership/tasks/{task}", {"title": "Call the dean"}, **_all(200, "pm", "head")),
    R("post", "/partnership/tasks/{task}/reschedule", lambda w: {"due_on": _day(5)}, **_all(200, "pm", "head")),
    R("post", "/partnership/tasks/{task}/complete", **_all(200, "pm", "head")),
    R("post", "/partnership/tasks/{task}/cancel", {"reason": "Not needed"}, **_all(200, "pm", "head")),
    # upc-015 alerts, upc-022 dashboard, upc-029 global dashboard, upc-018 performance, upc-031 reports
    R("get", "/partnership/alerts", **_all(200, *STAFF)),
    R("get", "/partnership/dashboard", **_all(200, *STAFF)),
    R("get", "/partnership/global-dashboard", **_all(200, "head", "head_out", "super")),
    R("get", "/partnership/performance", **_all(200, *READERS)),
    R("get", "/partnership/universities/{uni}/performance", **_all(200, *READERS)),
    R("get", "/partnership/reports/{report}", **_all(200, *STAFF)),
    R("get", "/partnership/reports/{report}.csv", **_all(200, *STAFF)),
    # upc-021 targets (another manager's sheet is hidden)
    R("get", "/partnership/targets", **_all(200, *STAFF)),
    R("get", "/partnership/targets/{pm_id}", pm=200, pm_out=404, head=200, head_out=404, super=200),
    R("put", "/partnership/targets", lambda w: {"month": w["month"], "items": [{"manager_user_id": w["pm_id"], "kpi_key": "meetings", "target": 5}]}, head=200, head_out=404, super=200),
    # upc-030 the University 360 view for the other roles (U14 slices; never the partnership roles)
    R("get", "/universities/{uni}/view", **_all(200, "ovs_admin", "bdm", "cns", "rep")),
    R("get", "/universities/{uni}/view/documents/{doc}/file", **_all(200, "ovs_admin", "cns")),
]

PATH_VALUES = {"milestone": "meeting", "onboarding": "counselor_training", "report": "performance"}  # the non-id path parameters


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
    """`GET /partnership/universities/{uni}/calls?x=1` -> `GET /partnership/universities/{}/calls`: placeholders compare by position."""
    return re.sub(r"\{[^}]+\}", "{}", key.split("?")[0])


def test_every_partnership_route_has_a_row():
    """AC1 / PX1: a route added under the partnership prefixes without a matrix row (or a stale row) fails here."""
    routes = {_template(k) for k in _operations() if k.split(" ", 1)[1].startswith(PREFIXES)}
    rows = [_template(row.key) for row in MATRIX]
    assert len(rows) == len(set(rows)), "duplicate matrix rows"
    assert routes - set(rows) == set(), "routes without a matrix row"
    assert set(rows) - routes == set(), "matrix rows without a route"


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["cns", "rep", "agent", "it_admin"])
@pytest.mark.parametrize("upload", ["no key", "not a csv", "unknown column"])
async def test_a_refused_role_gets_403_before_the_course_upload_is_read(client, db_session, role, upload):
    """PX7: the course import (upc-017) refuses the role before it reads the file, as upc-005's university import does -- never a 422 that
    reveals how the upload was judged."""
    w = await world(client, db_session)
    content = {"no key": b"title,level,category,duration\nMSc,PG,Tech,1 year\n", "not a csv": b"\x00\xff\x00",
               "unknown column": b"title,level,category,duration,commission\nMSc,PG,Tech,1 year,10\n"}[upload]  # fmt: skip
    key = {} if upload == "no key" else {"Idempotency-Key": uuid.uuid4().hex}
    response = await client.post(f"{API}/partnership/universities/{w['uni']}/courses/import", headers=headers(w["users"][role]) | key,
                                 files={"file": ("c.csv", content, "text/csv")})  # fmt: skip
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("row", MATRIX, ids=lambda r: r.key)
async def test_matrix_row(client, db_session, row):
    """AC1: every route x role cell. Refused cells and reads first on one world; then every other 2xx cell on its own fresh world."""
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
