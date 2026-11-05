"""pob-002 (DEC-SCOPE-407) -- requirement revisions (R1-R5), the hiring process (R6), per-requirement terms behind pob-001's gate (R7/R8)
and the backup owner (R9). Names are unique per test (the database is shared and never truncated)."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, select

from app.models import AuditLog, CompanyContact, Job, JobRevision, RecruiterContract, UserPermissionOverride
from tests.rec001_helpers import as_role, login, make_pm, make_recruiter
from tests.test_rec_007_requirements import BASE, _company

REFUSED_TERMS = "Your role cannot view or change client commercial terms"
COMMERCIAL = {"fee_basis", "fee_value", "payment_trigger", "payment_days", "payment_terms", "replacement_terms"}


def _tag() -> str:
    return uuid.uuid4().hex[:8]


async def _world(client, db, **body) -> dict:
    """A manager's recruiter `primary` (signed in) with a company, a current contract and a requirement of 2 vacancies; `mate` is a
    teammate, `outsider` is in another team."""
    manager = await make_pm(db)
    tag = _tag()
    primary = await make_recruiter(db, manager, name=f"Primary {tag}")
    mate = await make_recruiter(db, manager, name=f"Mate {tag}")
    outsider = await make_recruiter(db, await make_pm(db), name=f"Outsider {tag}")
    company = await _company(db, primary)
    db.add(RecruiterContract(company_id=company.id, created_by_user_id=primary.id, status="discussion", fee_basis="fixed", fee_value=Decimal("50000"),
                             payment_terms="30 days from invoice", replacement_policy="90 days free replacement", is_current=True))  # fmt: skip
    await db.commit()
    await login(client, primary)
    response = await client.post(BASE, json={"company_id": str(company.id), "title": f"Revised {tag}", "location": "Pune", "vacancies": 2, **body})
    assert response.status_code == 201, response.text
    return {"manager": manager, "primary": primary, "mate": mate, "outsider": outsider, "company": company, "req": response.json()["requirement"], "tag": tag}


async def _patch(client, w, expected: int = 200, **body) -> dict:
    response = await client.patch(f"{BASE}/{w['req']['id']}", json=body)
    assert response.status_code == expected, response.text
    return response.json()


async def _revisions(client, job_id) -> dict:
    response = await client.get(f"{BASE}/{job_id}/revisions")
    assert response.status_code == 200, response.text
    assert "no-store" in response.headers["cache-control"]
    return response.json()


async def _revision(client, job_id, n, **params) -> dict:
    response = await client.get(f"{BASE}/{job_id}/revisions/{n}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _value(revision: dict, field: str):
    return next(v["value"] for v in revision["values"] if v["field"] == field)


async def _contact(db, company_id, *, active=True) -> CompanyContact:
    contact = CompanyContact(company_id=company_id, name=f"Decider {_tag()}", designation="VP Engineering", active=active)
    db.add(contact)
    await db.commit()
    return contact


async def _deny(db, user, *actions: str) -> None:
    for action in actions:
        db.add(UserPermissionOverride(user_id=user.id, resource="commercials.client", action=action, effect="deny", reason="pob-002 test"))
    await db.commit()


# --- R1-R5: revisions -----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_writes_revision_1(client, db_session):
    w = await _world(client, db_session)
    page = await _revisions(client, w["req"]["id"])
    assert page["total"] == 1 and page["items"][0]["revision"] == 1 and page["items"][0]["author"]["id"] == str(w["primary"].id)
    first = await _revision(client, w["req"]["id"], 1)
    assert _value(first, "vacancies") == 2 and _value(first, "title") == w["req"]["title"] and first["changes"] is None


@pytest.mark.asyncio
async def test_headcount_2_to_3_writes_exactly_one_revision_with_its_diff(client, db_session):
    """AC1 / backlog +: revision 2 shows the diff; revision 1 stays readable."""
    w = await _world(client, db_session)
    await _patch(client, w, vacancies=3, revision_reason="Client added a seat")
    page = await _revisions(client, w["req"]["id"])
    assert [i["revision"] for i in page["items"]] == [2, 1]
    assert page["items"][0]["reason"] == "Client added a seat"
    assert page["items"][0]["changed_fields"] == [{"field": "vacancies", "label": "Number of vacancies"}]
    second = await _revision(client, w["req"]["id"], 2)
    assert second["compared_to"] == 1
    assert second["changes"] == [{"field": "vacancies", "label": "Number of vacancies", "before": 2, "after": 3}]
    assert _value(await _revision(client, w["req"]["id"], 1), "vacancies") == 2


@pytest.mark.asyncio
async def test_a_save_without_a_change_writes_no_revision(client, db_session):
    """Backlog −: the same values, or nothing at all."""
    w = await _world(client, db_session)
    await _patch(client, w, vacancies=2, title=w["req"]["title"])
    await _patch(client, w)
    assert (await _revisions(client, w["req"]["id"]))["total"] == 1


@pytest.mark.asyncio
async def test_a_skills_only_change_and_two_edits_number_in_order(client, db_session):
    w = await _world(client, db_session)
    await _patch(client, w, required_skills=["Python"])
    await _patch(client, w, vacancies=4)
    page = await _revisions(client, w["req"]["id"])
    assert [i["revision"] for i in page["items"]] == [3, 2, 1]
    assert page["items"][1]["changed_fields"] == [{"field": "required_skills", "label": "Required skills"}]
    compared = await _revision(client, w["req"]["id"], 3, compare_to=1)
    assert {c["field"] for c in compared["changes"]} == {"vacancies", "required_skills"}
    assert (await _revision(client, w["req"]["id"], 3, compare_to=3))["changes"] == []


@pytest.mark.asyncio
async def test_unknown_revisions_and_out_of_scope_callers_are_404(client, db_session):
    w = await _world(client, db_session)
    assert (await client.get(f"{BASE}/{w['req']['id']}/revisions/9")).status_code == 404
    assert (await client.get(f"{BASE}/{w['req']['id']}/revisions/1", params={"compare_to": 9})).status_code == 404
    await login(client, w["outsider"])
    assert (await client.get(f"{BASE}/{w['req']['id']}/revisions")).status_code == 404
    assert (await client.get(f"{BASE}/{w['req']['id']}/revisions/1")).status_code == 404


@pytest.mark.asyncio
async def test_a_job_from_before_revisions_gets_a_baseline_then_its_edit(client, db_session):
    """R3: revision 1 holds the stored values (no author), revision 2 the edit."""
    w = await _world(client, db_session)
    await db_session.execute(delete(JobRevision).where(JobRevision.job_id == uuid.UUID(w["req"]["id"])))
    await db_session.commit()
    await _patch(client, w, vacancies=5)
    page = await _revisions(client, w["req"]["id"])
    assert [(i["revision"], i["author"], i["reason"]) for i in page["items"]] == [
        (2, {"id": str(w["primary"].id), "full_name": w["primary"].full_name}, None),
        (1, None, "Recorded before revisions were kept"),
    ]
    assert (await _revision(client, w["req"]["id"], 2))["changes"][0]["before"] == 2


@pytest.mark.asyncio
async def test_the_managers_fee_override_writes_a_revision(client, db_session):
    w = await _world(client, db_session)
    await login(client, w["manager"])
    response = await client.put(f"/api/v1/recruiter/requirements/{w['req']['id']}/fee", json={"fee_basis": "fixed", "fee_value": "65000"})
    assert response.status_code == 200, response.text
    second = await _revision(client, w["req"]["id"], 2)
    assert second["changes"] == [{"field": "fee_basis", "label": "Fee basis", "before": None, "after": "fixed"},
                                 {"field": "fee_value", "label": "Fee", "before": None, "after": "65000.00"}]  # fmt: skip


# --- R6: the hiring process -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_hiring_process_round_trips_and_is_revised(client, db_session):
    w = await _world(client, db_session)
    contact = await _contact(db_session, w["company"].id)
    req = (await _patch(client, w, interview_rounds=["Technical", " ", "HR"], screening_steps=["Phone screen"], decision_maker_contact_id=str(contact.id),
                        expected_tat_days=21))["requirement"]  # fmt: skip
    assert req["interview_rounds"] == ["Technical", "HR"] and req["screening_steps"] == ["Phone screen"] and req["expected_tat_days"] == 21
    assert req["decision_maker"] == {"id": str(contact.id), "name": contact.name, "designation": "VP Engineering", "active": True}
    second = await _revision(client, w["req"]["id"], 2)
    assert _value(second, "interview_rounds") == "Technical; HR" and _value(second, "decision_maker_contact") == contact.name
    cleared = (await _patch(client, w, interview_rounds=[], decision_maker_contact_id=None))["requirement"]
    assert cleared["interview_rounds"] == [] and cleared["decision_maker"] is None


@pytest.mark.asyncio
async def test_the_decision_maker_is_an_active_contact_of_the_same_company(client, db_session):
    w = await _world(client, db_session)
    other = await _company(db_session, w["primary"])
    for contact in (await _contact(db_session, other.id), await _contact(db_session, w["company"].id, active=False)):
        body = await _patch(client, w, 422, decision_maker_contact_id=str(contact.id))
        assert body["detail"] == "Choose an active contact of this company as the decision-maker"
    assert (await _revisions(client, w["req"]["id"]))["total"] == 1


@pytest.mark.asyncio
async def test_hiring_process_limits_are_422(client, db_session):
    w = await _world(client, db_session)
    await _patch(client, w, 422, interview_rounds=[f"R{i}" for i in range(11)])
    await _patch(client, w, 422, interview_rounds=["x" * 121])
    await _patch(client, w, 422, expected_tat_days=0)
    await _patch(client, w, 422, screening_steps=["bad\x07step"])


# --- R9: the backup owner -------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_backup_owner_reads_edits_and_manages_the_owners(client, db_session):
    """AC3 (Q-02 = always): owner access without being the primary."""
    w = await _world(client, db_session)
    req = (await _patch(client, w, backup_owner_user_id=str(w["outsider"].id)))["requirement"]
    assert req["backup_owner"]["id"] == str(w["outsider"].id)
    await login(client, w["outsider"])  # another team's recruiter: in scope only as the backup
    read = await client.get(f"{BASE}/{w['req']['id']}")
    assert read.status_code == 200 and read.json()["requirement"]["permissions"]["can_manage_owners"] is True
    assert (await client.patch(f"{BASE}/{w['req']['id']}", json={"vacancies": 3})).status_code == 200
    assert (await client.post(f"{BASE}/{w['req']['id']}/assignments", json={"user_id": str(w["mate"].id), "role": "collaborator"})).status_code == 201
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == w["req"]["id"], AuditLog.action == "recruiter_requirement.update")
                                    .order_by(AuditLog.created_at).limit(1))  # fmt: skip
    assert audit.metadata_json["changes"]["backup_owner"] == [None, w["outsider"].full_name]


@pytest.mark.asyncio
async def test_only_owner_managers_set_the_backup_and_only_an_eligible_recruiter(client, db_session):
    w = await _world(client, db_session)
    assert (await client.post(f"{BASE}/{w['req']['id']}/assignments", json={"user_id": str(w["mate"].id), "role": "collaborator"})).status_code == 201
    options = await client.get(f"{BASE}/{w['req']['id']}/assignment-options", params={"role": "backup", "q": w["tag"]})
    assert options.status_code == 200 and {i["id"] for i in options.json()["items"]} == {str(w["mate"].id), str(w["outsider"].id)}  # a collaborator may be the backup
    await login(client, w["mate"])  # a collaborator edits the requirement, but not its owners
    body = await _patch(client, w, 403, backup_owner_user_id=str(w["mate"].id))
    assert body["detail"] == "Only the primary owner, the backup owner or a placement manager can change the backup owner"
    await login(client, w["primary"])
    assert (await _patch(client, w, 409, backup_owner_user_id=str(w["primary"].id)))["detail"] == "The primary owner cannot also be the backup owner"
    assert (await _patch(client, w, 422, backup_owner_user_id=str(w["manager"].id)))["detail"] == "Choose an active recruiter as the backup owner"
    inactive = await make_recruiter(db_session, w["manager"], active=False)
    await _patch(client, w, 422, backup_owner_user_id=str(inactive.id))
    await login(client, w["manager"])  # a placement manager reads but never edits a requirement's fields (rec-007 WRITERS)
    assert (await _patch(client, w, 403, backup_owner_user_id=str(w["mate"].id)))["detail"] == "Only the recruiter on this requirement can edit it"
    await as_role(client, db_session, "super_admin", "global")
    assert (await _patch(client, w, backup_owner_user_id=str(w["mate"].id)))["requirement"]["backup_owner"]["id"] == str(w["mate"].id)
    cleared = await _patch(client, w, backup_owner_user_id=None)
    assert cleared["requirement"]["backup_owner"] is None
    page = await _revisions(client, w["req"]["id"])
    assert [i["changed_fields"] for i in page["items"][:2]] == [[{"field": "backup_owner", "label": "Backup owner"}]] * 2


@pytest.mark.asyncio
async def test_promoting_or_deactivating_the_backup_clears_it(client, db_session):
    w = await _world(client, db_session)
    await _patch(client, w, backup_owner_user_id=str(w["mate"].id))
    await login(client, w["manager"])
    response = await client.post(f"{BASE}/{w['req']['id']}/assign", json={"recruiter_user_id": str(w["mate"].id)})
    assert response.status_code == 200 and response.json()["requirement"]["backup_owner"] is None
    response = await client.post(f"{BASE}/{w['req']['id']}/assign", json={"recruiter_user_id": str(w["primary"].id)})
    assert response.status_code == 200, response.text
    await login(client, w["primary"])
    await _patch(client, w, backup_owner_user_id=str(w["mate"].id))
    # `mate` primarily owns nothing open, so the deactivation goes through and releases the backup role
    admin = await as_role(client, db_session, "super_admin", "global")
    assert (await client.patch(f"/api/v1/admin/users/{w['mate'].id}", json={"active": False})).status_code == 200
    job = await db_session.get(Job, uuid.UUID(w["req"]["id"]), populate_existing=True)
    assert job.backup_owner_user_id is None
    released = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == w["req"]["id"], AuditLog.action == "recruiter_requirement.backup_released"))
    assert released.user_id == admin.id and released.metadata_json["changes"] == {"backup_owner": [w["mate"].full_name, None]}


# --- R7/R8: per-requirement terms -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_terms_inherit_from_the_contract_until_overridden(client, db_session):
    """AC2."""
    w = await _world(client, db_session)
    terms = w["req"]["commercial_terms"]
    assert terms["fee"] == {"basis": "fixed", "value": "50000.00", "inherited": True}
    assert terms["payment_terms"] == {"value": "30 days from invoice", "inherited": True}
    assert terms["replacement_terms"] == {"value": "90 days free replacement", "inherited": True}
    assert terms["payment_trigger"] is None and terms["can_edit"] is True
    req = (await _patch(client, w, payment_trigger="days_after_joining", payment_days=45, payment_terms="45 days after joining"))["requirement"]
    terms = req["commercial_terms"]
    assert terms["payment_trigger"] == "days_after_joining" and terms["payment_trigger_label"] == "Days after joining" and terms["payment_days"] == 45
    assert terms["payment_terms"] == {"value": "45 days after joining", "inherited": False}
    assert terms["replacement_terms"]["inherited"] is True
    assert _value(await _revision(client, w["req"]["id"], 2), "payment_days") == 45
    history = (await client.get(f"{BASE}/{w['req']['id']}/history")).json()["items"][0]["changes"]
    assert history["payment_terms"] == "changed" and history["payment_days"] == "changed"  # R12: the History card never shows terms


@pytest.mark.asyncio
async def test_payment_days_go_with_days_after_joining_only(client, db_session):
    w = await _world(client, db_session)
    for body in ({"payment_trigger": "days_after_joining"}, {"payment_days": 10}, {"payment_trigger": "on_joining", "payment_days": 10}):
        assert (await _patch(client, w, 422, **body))["detail"] == "Enter the number of days only when payment is due a number of days after joining"
    await _patch(client, w, payment_trigger="days_after_joining", payment_days=10)
    await _patch(client, w, 422, payment_trigger="on_invoice")
    await _patch(client, w, payment_trigger="on_invoice", payment_days=None)


@pytest.mark.asyncio
async def test_without_view_no_terms_and_no_commercial_values_in_revisions(client, db_session):
    """AC (R8): absent, not null; a hiring edit still saves; a terms PATCH is 403."""
    w = await _world(client, db_session)
    await _patch(client, w, payment_terms="Net 15", vacancies=3)
    await _deny(db_session, w["primary"], "view")
    read = (await client.get(f"{BASE}/{w['req']['id']}")).json()["requirement"]
    assert "commercial_terms" not in read
    second = await _revision(client, w["req"]["id"], 2)
    assert not COMMERCIAL & {v["field"] for v in second["values"]}
    assert [c["field"] for c in second["changes"]] == ["vacancies"]
    assert (await _revisions(client, w["req"]["id"]))["items"][0]["changed_fields"] == [{"field": "vacancies", "label": "Number of vacancies"}]
    for body in ({"payment_terms": "Net 1"}, {"replacement_terms": None}, {"payment_trigger": "on_invoice"}):
        assert (await _patch(client, w, 403, **body))["detail"] == REFUSED_TERMS, body
    assert (await _patch(client, w, expected_tat_days=10))["requirement"]["expected_tat_days"] == 10


@pytest.mark.asyncio
async def test_view_without_edit_reads_the_terms_but_cannot_change_them(client, db_session):
    w = await _world(client, db_session)
    await _deny(db_session, w["primary"], "edit")
    read = (await client.get(f"{BASE}/{w['req']['id']}")).json()["requirement"]
    assert read["commercial_terms"]["can_edit"] is False and read["commercial_terms"]["payment_terms"]["value"] == "30 days from invoice"
    await _patch(client, w, 403, payment_terms="Net 1")
    await login(client, w["manager"])  # the Team Lead sees the team's terms (and, not editing requirement fields, never edits them here)
    terms = (await client.get(f"{BASE}/{w['req']['id']}")).json()["requirement"]["commercial_terms"]
    assert terms["payment_terms"]["value"] == "30 days from invoice" and terms["can_edit"] is False
