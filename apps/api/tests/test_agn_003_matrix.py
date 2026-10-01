"""AGN-003-AC01/AC02 -- the EVID-015 §6 matrix as built (spec §3). Staff have both optional toggles OFF here; the toggles' ON side
is tested in test_agn_003_permissions.py and test_agn_003_verify.py. Rows with no route for any agent (Edit/Delete/Assign Student,
Edit Application, Change Application Status, Staff Performance, CRM Settings) are N/A in spec §3 and have nothing to call.
Two Master cells are proven elsewhere: a Master deactivating another Master (tests/test_agn_001_team.py::
test_a_pending_invitee_can_still_be_deactivated_by_an_accepted_master, plus test_a_master_may_deactivate_themselves_once_another_master_has_accepted)
and a Master claiming a commission (tests/test_agn_001_tenancy.py::test_a_second_master_sees_and_claims_what_the_first_created)."""

import pytest

from app.models import AgentOrgMember, StudentDocument, User
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn002_helpers import STAFF, mk_staff
from tests.agn003_helpers import agency_document, mk_university

TEAM = "/api/v1/workflows/overseas/agent/team"
VERIFY = "/api/v1/workflows/overseas/documents/{document}/verify"
PORTAL = "/api/v1/portal/overseas/agent"
ALL_ON = {"can_verify_documents": True, "can_view_reports": True}

# (§6 row, method, path, json body, expected detail). "{name}" placeholders are filled from the world built for each test.
STAFF_REFUSED = [
    ("Staff Management", "get", STAFF, None, "Only an agency Master can manage the team"),
    ("Staff Management", "patch", STAFF + "/{other_staff}", {"full_name": "Renamed"}, "Only an agency Master can manage the team"),
    ("Staff Management", "put", STAFF + "/{other_staff}/permissions", ALL_ON, "Only an agency Master can manage the team"),
    ("Staff Management", "get", TEAM, None, "Only an agency Master can manage the team"),
    ("Staff Management", "get", PORTAL + "/team", None, "Only an agency Master can open this page"),
    ("Staff Management", "post", TEAM + "/masters", {"full_name": "New Master", "email": "{fresh_email}"}, "Only an agency Master can manage the team"),
    ("Staff Management", "post", TEAM + "/masters/{master_member}/deactivate", None, "Only an agency Master can manage the team"),
    ("Create Staff Login", "post", STAFF, {"full_name": "New Staff", "email": "{fresh_email}"}, "Only an agency Master can manage the team"),
    ("Create Staff Login", "post", STAFF + "/{other_staff}/reset", None, "Only an agency Master can manage the team"),
    ("Deactivate Staff", "post", STAFF + "/{other_staff}/deactivate", None, "Only an agency Master can manage the team"),
    ("Deactivate Staff", "post", STAFF + "/{other_staff}/reactivate", None, "Only an agency Master can manage the team"),
    ("Verify Documents", "patch", VERIFY, {"verification_status": "verified"}, "Your agency Master hasn't given you permission to verify documents"),
    ("Reject Documents", "patch", VERIFY, {"verification_status": "rejected"}, "Your agency Master hasn't given you permission to verify documents"),
    ("Reject Documents", "patch", VERIFY, {"verification_status": "changes_required"}, "Your agency Master hasn't given you permission to verify documents"),
    ("Reports", "get", PORTAL + "/reports", None, "Your agency Master hasn't given you access to reports"),
    ("Commission", "get", "/api/v1/workflows/overseas/agent/commissions", None, "Only an agency Master can view commissions"),
    ("Commission", "post", "/api/v1/workflows/overseas/agent/commissions/{zero}/claim", None, "Only an agency Master can view commissions"),
    ("Commission", "get", PORTAL + "/commissions", None, "Only an agency Master can open this page"),
    ("Add University", "post", "/api/v1/admin/universities", {}, "Admin role required"),
]

# (§6 row, method, path, json body, expected status) -- succeeds for staff AND for a Master.
BOTH_ALLOWED = [
    ("Dashboard", "get", PORTAL + "/dashboard", None, 200),
    ("Create Student", "post", "/api/v1/workflows/overseas/agent/students", {"student_id": "{unlinked_student}"}, 201),
    ("View Students", "get", "/api/v1/workflows/overseas/agent/students", None, 200),
    ("View Students", "get", PORTAL + "/students", None, 200),
    ("View Students", "get", "/api/v1/lookups/overseas-students", None, 200),
    # A second university: the student already has an application at `{university}`, and the API refuses a duplicate (409).
    ("Create Application", "post", "/api/v1/workflows/overseas/applications", {"university_id": "{other_university}", "student_id": "{student}"}, 201),
    ("View Applications", "get", "/api/v1/workflows/overseas/applications", None, 200),
    ("View Applications", "get", PORTAL + "/applications", None, 200),
    ("View Applications", "get", "/api/v1/lookups/overseas-applications", None, 200),
    ("Upload Documents", "post", "/api/v1/workflows/overseas/documents", {"student_id": "{student}", "application_id": "{application}", "document_type": "Transcript", "file_url": "uploads/agn003-transcript.pdf"}, 201),
    ("Upload Documents", "get", PORTAL + "/documents", None, 200),
    ("University Database", "get", "/api/v1/public/universities", None, 200),
    ("University Database", "get", "/api/v1/public/universities/{university_slug}", None, 200),
]

# Master-only cells that succeed for a Master.
MASTER_ALLOWED = [
    ("Staff Management", "get", STAFF, None, 200),
    ("Staff Management", "get", TEAM, None, 200),
    ("Staff Management", "get", PORTAL + "/team", None, 200),
    ("Staff Management", "put", STAFF + "/{other_staff}/permissions", ALL_ON, 200),
    ("Create Staff Login", "post", STAFF, {"full_name": "New Staff", "email": "{fresh_email}"}, 201),
    ("Deactivate Staff", "post", STAFF + "/{other_staff}/deactivate", None, 200),
    ("Verify Documents", "patch", VERIFY, {"verification_status": "verified"}, 200),
    ("Reject Documents", "patch", VERIFY, {"verification_status": "rejected"}, 200),
    ("Reports", "get", PORTAL + "/reports", None, 200),
    ("Commission", "get", "/api/v1/workflows/overseas/agent/commissions", None, 200),
    ("Commission", "get", PORTAL + "/commissions", None, 200),
    ("Staff Management", "patch", STAFF + "/{other_staff}", {"full_name": "Renamed"}, 200),
    ("Staff Management", "post", TEAM + "/masters", {"full_name": "New Master", "email": "{fresh_email}"}, 201),
    ("Create Staff Login", "post", STAFF + "/{other_staff}/reset", None, 200),
    ("Deactivate Staff", "post", STAFF + "/{deactivated_staff}/reactivate", None, 200),
    ("Reject Documents", "patch", VERIFY, {"verification_status": "changes_required"}, 200),
]


def _fill(value, ids: dict):
    if isinstance(value, str):
        return value.format(**ids)
    if isinstance(value, dict):
        return {k: _fill(v, ids) for k, v in value.items()}
    return value


async def _world(db_session) -> tuple[dict, dict, dict]:
    ctx = await mk_active_org(db_session, name=f"Matrix {uniq()}")
    caller = await mk_staff(db_session, ctx["org"], full_name="Caller Staff")
    other = await mk_staff(db_session, ctx["org"], full_name="Other Staff")
    away = await mk_staff(db_session, ctx["org"], full_name="Away Staff", active=False)
    world = await agency_document(db_session, ctx)
    unlinked = await mk_user(db_session, role="overseas_student", full_name="Unlinked Student")
    other_university = await mk_university(db_session)
    ids = {
        "other_staff": other["member"].id, "master_member": ctx["member"].id, "document": world["document"].id,
        "student": world["student"].id, "application": world["application"].id, "university": world["university"].id,
        "other_university": other_university.id, "university_slug": world["university"].slug, "deactivated_staff": away["member"].id,
        "unlinked_student": unlinked.id, "zero": "00000000-0000-0000-0000-000000000000", "fresh_email": f"{uniq('fresh')}@example.local",
    }
    return ctx, caller, ids


async def _call(client, method: str, path: str, body, ids: dict):
    kwargs = {} if body is None else {"json": _fill(body, ids)}
    return await getattr(client, method)(_fill(path, ids), **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize(("row", "method", "path", "body", "detail"), STAFF_REFUSED, ids=[f"{r[0]}-{r[1]}-{r[2]}" for r in STAFF_REFUSED])
async def test_staff_refused(db_session, row, method, path, body, detail):  # AGN-003-AC01
    _, caller, ids = await _world(db_session)
    async with client_for(caller["user"].email) as c:
        response = await _call(c, method, path, body, ids)
    assert response.status_code == 403, f"{row}: {response.status_code} {response.text}"
    assert response.json()["detail"] == detail, f"{row}: refused by the wrong gate: {response.text}"
    # A refused call changes nothing.
    document = await db_session.get(StudentDocument, ids["document"], populate_existing=True)
    other = await db_session.get(AgentOrgMember, ids["other_staff"], populate_existing=True)
    other_user = await db_session.get(User, other.user_id, populate_existing=True)
    assert document.verification_status == "pending"
    assert (other.status, other.can_verify_documents, other.can_view_reports) == ("active", False, False)
    assert other_user.full_name == "Other Staff"


@pytest.mark.asyncio
@pytest.mark.parametrize(("row", "method", "path", "body", "status"), BOTH_ALLOWED, ids=[f"{r[0]}-{r[1]}-{r[2]}" for r in BOTH_ALLOWED])
async def test_staff_allowed(db_session, row, method, path, body, status):  # AGN-003-AC02
    _, caller, ids = await _world(db_session)
    async with client_for(caller["user"].email) as c:
        response = await _call(c, method, path, body, ids)
    assert response.status_code == status, f"{row}: {response.status_code} {response.text}"


@pytest.mark.asyncio
@pytest.mark.parametrize(("row", "method", "path", "body", "status"), BOTH_ALLOWED + MASTER_ALLOWED, ids=[f"{r[0]}-{r[1]}-{r[2]}" for r in BOTH_ALLOWED + MASTER_ALLOWED])
async def test_master_allowed(db_session, row, method, path, body, status):  # AGN-003-AC02
    ctx, _, ids = await _world(db_session)
    async with client_for(ctx["master"].email) as m:
        response = await _call(m, method, path, body, ids)
    assert response.status_code == status, f"{row}: {response.status_code} {response.text}"


@pytest.mark.asyncio
async def test_add_university_is_refused_to_masters_too(db_session):  # spec §3: deliberate departure from §6's Master ✅ (P3)
    ctx, _, ids = await _world(db_session)
    async with client_for(ctx["master"].email) as m:
        response = await _call(m, "post", "/api/v1/admin/universities", {}, ids)
    assert response.status_code == 403
