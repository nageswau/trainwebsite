"""pob-030 -- the share gate (DEC-SCOPE-440 G1-G8; AC1 route inventory, AC2 no share without consent on any path, +/-/E a permission
withdrawn after a submission). The shared test database is never truncated, so every value is unique per test."""

import inspect
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.api import employer as employer_api
from app.api import recruiter_shares
from app.main import app
from app.models import AuditLog, BdmOrganization, Candidate, InstitutionDataPermission, RecruiterMessage
from app.services import bdm_organizations as orgs
from app.services import interview_panel, profile_sharing, share_gate
from tests.rec001_helpers import login, make_user
from tests.test_hrc_029_interview_panel import MINE, _assign, _resume, _world
from tests.test_pob_011_vendor_requirements import _setup as _vendor_setup
from tests.test_pob_011_vendor_requirements import _vendor_body
from tests.test_rec_017_tracking import _candidate
from tests.test_rec_019_shares import EMPLOYER, PDF, PUBLIC, SHARES, SUBMIT, _body, _employer, _links, _setup, _upload, published, smtp_on  # noqa: F401

# AC1: the routes that can carry candidate data out of the team -- every one must be classified in share_gate.OUTWARD
OUTWARD_SHAPE = re.compile(r"^/api/v1/(public/shared-|employer/shared-|interviewer/interviews|recruiter/shares$|recruiter/candidates/.*(export|/resume/))")
# where each gated route's check lives (the endpoint or the service it delegates to)
GATED_IN = {
    ("POST", "/api/v1/recruiter/shares"): (profile_sharing.create, ("share_gate.request", "share_gate.people")),
    ("GET", "/api/v1/public/shared-resume/{token}"): (recruiter_shares.shared_resume, ("share_gate.deliverable",)),
    ("GET", "/api/v1/employer/shared-profiles/{item_id}/resume"): (employer_api.shared_profile_resume, ("share_gate.deliverable",)),
    ("GET", "/api/v1/interviewer/interviews/{interview_id}/resume"): (interview_panel.resume, ("_shareable(",)),
}
DELEGATES = ((interview_panel._shareable, "share_gate.deliverable_ids"), (interview_panel._resume_open, "shareable"))


def _outward_routes() -> set[tuple[str, str]]:
    """From the OpenAPI document: on this FastAPI version `app.routes` does not flatten included routers (the ccrm-041 way)."""
    return {(m.upper(), path) for path, ops in app.openapi()["paths"].items() if OUTWARD_SHAPE.search(path) for m in ops if m in ("get", "post", "patch")}


def test_ac1_every_outward_route_is_classified_and_every_gated_one_calls_the_gate():
    routes = _outward_routes()
    assert routes - set(share_gate.OUTWARD) == set(), "a new outward route needs a share_gate.OUTWARD entry"
    assert set(share_gate.OUTWARD) - routes == set(), "a share_gate.OUTWARD entry names a route that no longer exists"
    gated = {key for key, kind in share_gate.OUTWARD.items() if kind in ("share", "delivery")}
    assert gated == set(GATED_IN)
    for fn, calls in GATED_IN.values():
        source = inspect.getsource(fn)
        assert all(call in source for call in calls), f"{fn.__qualname__} must call {calls}"
    for fn, call in DELEGATES:
        assert call in inspect.getsource(fn), f"{fn.__qualname__} must use {call}"


# --- AC2: without consent, no path shares ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["email", "whatsapp", "portal", "other"])
async def test_ac2_a_client_share_without_consent_fails_on_every_channel(client, db_session, smtp_on, published, channel):  # noqa: F811
    s = await _setup(client, db_session, n=1)
    if channel == "portal":
        await _employer(db_session, s["job"].company_id)
    refused = await client.post(SHARES, json=_body(s, channel, interest_confirmed=True))
    assert refused.status_code == 409 and "consent" in refused.json()["detail"].lower()
    s["candidates"][0].outreach_status = "declined"
    s["candidates"][0].outreach_permission_method = s["candidates"][0].outreach_permission_on = s["candidates"][0].outreach_permission_by_user_id = None
    await db_session.commit()
    unpermitted = await client.post(SHARES, json=_body(s, channel, **SUBMIT))
    assert unpermitted.status_code == 422 and "permission to be represented" in unpermitted.json()["detail"]


@pytest.mark.asyncio
async def test_ac2_a_vendor_share_needs_consent_and_the_nda(client, db_session, smtp_on, published):  # noqa: F811
    s = await _vendor_setup(client, db_session, n=1)
    bare = await client.post(SHARES, json=_vendor_body(s, consent_confirmed=False, consent_reference=None))
    assert bare.status_code == 409 and "consent" in bare.json()["detail"].lower()
    t = await _vendor_setup(client, db_session, n=1, nda=False)
    no_nda = await client.post(SHARES, json=_vendor_body(t))
    assert no_nda.status_code == 409 and no_nda.json()["detail"] == share_gate.VENDOR_NO_NDA


# --- +/-/E: consent withdrawn after a submission ---------------------------------------------------------------------------------------
async def _withdraw(db, candidate: Candidate) -> None:
    await db.execute(update(Candidate).where(Candidate.id == candidate.id).values(outreach_status="declined", outreach_permission_method=None,
                                                                                    outreach_permission_on=None, outreach_permission_by_user_id=None))  # fmt: skip
    await db.commit()


@pytest.mark.asyncio
async def test_a_withdrawn_permission_blocks_future_shares_and_deliveries_and_past_shares_stay_logged(client, db_session, smtp_on, published):  # noqa: F811
    s = await _setup(client, db_session, n=1)
    employer = await _employer(db_session, s["job"].company_id)
    await _upload(client, s["candidates"][0].id)
    emailed = (await client.post(SHARES, json=_body(s, "email", **SUBMIT))).json()["share"]
    portal = (await client.post(SHARES, json=_body(s, "portal", repeat=True, **SUBMIT))).json()["share"]
    (token,) = _links((await db_session.get(RecruiterMessage, uuid.UUID(emailed["message"]["id"]))).body)
    await _withdraw(db_session, s["candidates"][0])

    again = await client.post(SHARES, json=_body(s, "other", repeat=True, **SUBMIT))
    assert again.status_code == 422 and s["candidates"][0].candidate_code in again.json()["detail"]
    client.cookies.clear()
    assert (await client.get(f"{PUBLIC}/{token}")).status_code == 404
    await login(client, employer)
    listed = next(i for i in (await client.get(EMPLOYER)).json()["items"] if i["id"] == portal["items"][0]["id"])
    assert listed["has_resume"] is False  # no dead Download link
    responded = await client.patch(f"{EMPLOYER}/{listed['id']}", json={"response": "interested"})
    assert responded.status_code == 200 and responded.json()["has_resume"] is False
    assert (await client.get(f"{EMPLOYER}/{portal['items'][0]['id']}/resume")).status_code == 404
    logged = await db_session.scalar(select(AuditLog.id).where(AuditLog.action == "profile_share.create", AuditLog.entity_id.in_([emailed["id"], portal["id"]])).limit(1))
    assert logged is not None  # past shares remain logged
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.action == "profile_share.resume_download", AuditLog.entity_id == portal["items"][0]["id"])) is None


@pytest.mark.asyncio
async def test_a_permitted_candidate_still_downloads(client, db_session, smtp_on, published):  # noqa: F811
    s = await _setup(client, db_session, n=1)
    await _upload(client, s["candidates"][0].id)
    emailed = (await client.post(SHARES, json=_body(s, "email", **SUBMIT))).json()["share"]
    (token,) = _links((await db_session.get(RecruiterMessage, uuid.UUID(emailed["message"]["id"]))).body)
    client.cookies.clear()
    download = await client.get(f"{PUBLIC}/{token}")
    assert download.status_code == 200 and download.content == PDF


@pytest.mark.asyncio
async def test_an_employer_panel_member_loses_the_resume_when_permission_is_withdrawn_an_internal_one_keeps_it(client, db_session):
    s = await _world(client, db_session)
    await _resume(db_session, s["candidate"].id, s["recruiter"].id)
    assert (await _assign(client, s["item"]["id"], s["employer"], s["interviewer"])).status_code == 200
    candidate = await db_session.get(Candidate, s["candidate"].id)
    await _withdraw(db_session, candidate)
    await login(client, s["employer"])
    assert (await client.get(f"{MINE}/{s['item']['id']}")).json()["has_resume"] is False
    assert (await client.get(MINE)).json()["items"][0]["has_resume"] is False
    assert (await client.get(f"{MINE}/{s['item']['id']}/resume")).status_code == 404
    await login(client, s["interviewer"])
    assert (await client.get(f"{MINE}/{s['item']['id']}")).json()["has_resume"] is True
    assert (await client.get(f"{MINE}/{s['item']['id']}/resume")).status_code == 200


# --- deliverable() --------------------------------------------------------------------------------------------------------------------------
async def _permission(db, bdm, purposes) -> InstitutionDataPermission:
    name, city = f"P30 College {uuid.uuid4().hex[:8]}", "Pune"
    keys = orgs.org_keys(name, city)
    org = BdmOrganization(code=await orgs.next_code(db), org_type="college", bdm_type="college", name=name, name_key=keys[0], city=city, city_key=keys[1],
                          assigned_bdm_user_id=bdm.id, created_by_user_id=bdm.id)  # fmt: skip
    db.add(org)
    await db.flush()
    today = datetime.now(UTC).date()
    permission = InstitutionDataPermission(organization_id=org.id, agreement_reference="MoU P30", purposes=purposes, valid_from=today - timedelta(days=1),
                                           expires_on=today + timedelta(days=90), created_by_user_id=bdm.id)  # fmt: skip
    db.add(permission)
    await db.commit()
    return permission


@pytest.mark.asyncio
async def test_deliverable_follows_the_institution_permission(db_session):
    bdm = await make_user(db_session, "bdm", "it")
    permission = await _permission(db_session, bdm, ["placement"])
    person = await _candidate(db_session, bdm, institution_permission_id=permission.id, institution_org_id=permission.organization_id)
    assert await share_gate.deliverable(db_session, person) is True
    await db_session.execute(update(InstitutionDataPermission).where(InstitutionDataPermission.id == permission.id).values(revoked_at=datetime.now(UTC)))
    await db_session.commit()
    assert await share_gate.deliverable(db_session, person) is False
    training = await _permission(db_session, bdm, ["training"])
    trained = await _candidate(db_session, bdm, institution_permission_id=training.id, institution_org_id=training.organization_id)
    assert await share_gate.deliverable(db_session, trained) is False
    person.archived_at = datetime.now(UTC)
    assert await share_gate.deliverable(db_session, person) is False
