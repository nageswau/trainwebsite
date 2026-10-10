"""upc-033 -- the commission sweep, the confidentiality net for EVID-020 line 1129 ("Commissions should not be seen by anyone", U2; spec
docs/superpowers/specs/2026-10-10-upc-033-permission-matrix-design.md PX6/PX8, RBAC_MATRIX §2.100).

The world plants a sentinel in every commission column (upc033_helpers.SENTINELS). Every endpoint that can return university, course, agreement
or performance data -- each inventoried GET of the matrix plus the public catalogue and the other roles' university/course reads -- is called as
every non-commission role. Whatever the status, the body must hold no key naming commission, no health `factors` breakdown and no sentinel.
A positive control proves the sentinels are really reachable (by the commission roles), so the sweep cannot pass by looking at nothing."""

import json
import re
from pathlib import Path

import pytest

from tests.test_upc_033_matrix import MATRIX, _fill
from tests.upc033_helpers import OTHER_ROLES, SENTINELS, headers, world

API = "/api/v1"
REPORTS = ("pipeline", "expected", "performance", "agreements", "targets")  # upc-031 RP1

# The other roles' university / course / application reads outside the inventoried prefixes (PX6; "the public endpoints are included").
OUTSIDE = [
    "/public/universities?q={uni_name}",
    "/public/universities/{slug}",
    "/public/overseas-courses?category={category}",
    "/public/search?q={uni_name}",
    "/public/countries/{country_slug}",
    "/universities/{uni}/view/documents/{secret_doc}/file",
    "/partnership/universities/{uni}/documents/{secret_doc}/file",
    "/admin/universities",
    "/workflows/overseas/applications",
    "/lookups/overseas-applications",
    "/portal/overseas/university/dashboard",
    "/portal/overseas/university/applications",
    "/portal/overseas/university/offer-letters",
    "/portal/overseas/admin/universities",
    "/portal/overseas/admin/applications",
    "/portal/overseas/counselor/applications",
    "/portal/overseas/student/applications",
]
INVENTORIED = [row.path.replace("{report}", kind) for row in MATRIX if row.method == "get" for kind in (REPORTS if "{report}" in row.path else ("",))]
SWEEP = [*INVENTORIED, *OUTSIDE]

# PX6 positive control: where a commission role does see each sentinel (each one is planted, and each is reachable).
CONTROL = [
    ("pm", "/partnership/universities/{uni}/courses", ("course_percent", "course_amount")),
    ("head", "/partnership/agreements/{agreement}", ("term_percent", "text")),
    ("pm_out", "/partnership/commission-terms", ("term_percent",)),
    ("super", "/partnership/universities/{uni}/commission", ("receipt_amount", "text")),
    ("pm", "/partnership/universities/{uni}/documents", ("text",)),
]


def _keys(value) -> list[str]:
    if isinstance(value, dict):
        return [*value, *(k for v in value.values() for k in _keys(v))]
    if isinstance(value, list):
        return [k for v in value for k in _keys(v)]
    return []


def _leaks(response) -> list[str]:
    body = response.text
    found = [f"sentinel {name}={value}" for name, value in SENTINELS.items() if value in body]
    if response.headers.get("content-type", "").startswith("application/json"):
        found += [f"key {k}" for k in _keys(json.loads(body)) if "commission" in k.lower() or k == "factors"]
    return found


@pytest.mark.asyncio
@pytest.mark.parametrize("path", SWEEP)
async def test_no_commission_reaches_a_non_commission_role(client, db_session, path):
    """AC2 / U2: every non-commission role, every endpoint, any status: no commission key, no health factors, no planted value."""
    w = await world(client, db_session)
    leaks = []
    for role in OTHER_ROLES:
        response = await client.get(API + _fill(path, w), headers=headers(None if role == "anon" else w["users"][role]))
        leaks += [f"{role} ({response.status_code}): {leak}" for leak in _leaks(response)]
    assert not leaks, " | ".join(leaks)


@pytest.mark.asyncio
async def test_the_sentinels_are_reachable_by_the_commission_roles(client, db_session):
    """PX6: the control -- each planted commission value is visible where its item shows it, so the sweep is not vacuous."""
    w = await world(client, db_session)
    for role, path, needles in CONTROL:
        response = await client.get(API + _fill(path, w), headers=headers(w["users"][role]))
        assert response.status_code == 200, f"{role} {path}: {response.status_code}"
        for name in needles:
            assert SENTINELS[name] in response.text, f"{role} {path}: {name} not shown"
    stripped = await client.get(API + _fill("/partnership/universities/{uni}/courses", w), headers=headers(w["users"]["ovs_admin"]))
    assert len(stripped.json()["items"]) == 2  # overseas_admin sees both courses -- without their commission


# PX8 / AC2: every module that emits university commission data, mapped to the sweep endpoints that exercise it. A new emitter (or a
# moved one) fails `test_every_commission_serializer_is_swept` until it is mapped here -- and so swept.
EMITS = re.compile(r"strip_commission|can_see_commission|commission_terms|UniversityCommission(Term|Receipt)|commission_expected|commission_received"
                   r"|COMMISSION_FIELDS|[\"']commission[\"']\s*[]:]")  # fmt: skip
SERIALIZERS = {
    "app/api/partnership_global_dashboard.py": ["/partnership/global-dashboard"],
    "app/api/partnership_performance.py": ["/partnership/performance", "/partnership/universities/{uni}/performance"],
    "app/api/university_commission.py": ["/partnership/agreements/{agreement}/commission-terms", "/partnership/commission-terms", "/partnership/universities/{uni}/commission"],
    "app/api/university_courses.py": ["/partnership/universities/{uni}/courses", "/partnership/courses"],
    "app/services/partnership_access.py": ["/partnership/universities/{uni}/courses", "/partnership/agreements/{agreement}"],
    "app/services/partnership_metrics.py": ["/partnership/performance", "/partnership/universities/{uni}/performance"],  # health factors
    "app/services/partnership_reports.py": ["/partnership/reports/performance", "/partnership/reports/performance.csv"],
    "app/services/university_agreements.py": ["/partnership/universities/{uni}/agreements", "/partnership/agreements", "/partnership/agreements/{agreement}"],
    "app/services/university_commission.py": ["/partnership/universities/{uni}/commission", "/partnership/commission-terms"],
    "app/services/university_courses.py": ["/partnership/universities/{uni}/courses", "/partnership/courses", "/universities/{uni}/view"],
    "app/services/university_documents.py": [
        "/partnership/universities/{uni}/documents",
        "/partnership/documents",
        "/partnership/universities/{uni}/documents/{secret_doc}/file",
        "/universities/{uni}/view/documents/{secret_doc}/file",
    ],
    "app/services/university_search.py": ["/partnership/universities/search", "/partnership/universities/map"],
    "app/services/university_view.py": ["/universities/{uni}/view"],
}
# Agent commission (EduSphere pays the agent, DEC-SCOPE-005/051/054) is another confidential figure with its own rules -- not U2's.
AGENT_COMMISSION = {"app/services/agent_dashboard.py", "app/services/agent_network.py"}
APP = Path(__file__).resolve().parents[1]


def test_every_commission_serializer_is_swept():
    """AC2 / PX8: the sweep covers every serializer that includes commission."""
    emitters = {p.relative_to(APP).as_posix() for d in ("app/api", "app/services") for p in (APP / d).rglob("*.py") if EMITS.search(p.read_text("utf-8"))}
    assert emitters - AGENT_COMMISSION == set(SERIALIZERS), "a commission emitter without a sweep mapping (or a stale mapping)"
    swept = {path.split("?")[0] for path in SWEEP}
    unswept = {(f, e) for f, endpoints in SERIALIZERS.items() for e in endpoints if e not in swept}
    assert not unswept, unswept
