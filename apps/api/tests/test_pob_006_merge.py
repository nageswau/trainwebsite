"""pob-006 (DEC-SCOPE-418 M1-M8, C1-C6, AC3): company merge and contact merge -- every related row moves, nothing is orphaned, the refusals hold,
both merges are audited. `test_every_reference_is_handled` fails when a later item adds a foreign key to a company or contact without deciding
what its merge does."""

import csv
import io
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import (
    AuditLog,
    Base,
    Company,
    CompanyBranch,
    CompanyContact,
    CompanyDocument,
    CompanySkillDemand,
    CompanyStageHistory,
    EmployerProfile,
    Job,
    JobDescription,
    ProfileShare,
    RecCampaign,
    RecLeadSource,
    RecruiterCall,
    RecruiterContract,
    RecruiterFollowUp,
    RecruiterMeeting,
    RecruiterMeetingParticipant,
    RecruiterMessage,
    RecruitmentDrive,
    Skill,
    UserPermissionOverride,
)
from app.services import company_merge
from tests.rec001_helpers import login, make_pm, make_recruiter, make_user
from tests.rec038_helpers import make_job
from tests.test_rec_009_candidates import mail, mobile

pytestmark = pytest.mark.asyncio
COMPANIES = "/api/v1/recruiter/companies"
CONTACTS = "/api/v1/recruiter/contacts"
IMPORTS = "/api/v1/recruiter/company-imports"
NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def unique(prefix: str = "Merge Co") -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


async def _team(client, db):
    """A manager (holds crm.merge by default) with one recruiter; signed in as the manager. Their unassigned and team companies are in scope."""
    manager = await make_pm(db)
    recruiter = await make_recruiter(db, manager)
    await login(client, manager)
    return manager, recruiter


async def _company(db, *, recruiter=None, **fields) -> Company:
    company = Company(name=fields.pop("name", unique()), assigned_recruiter_user_id=recruiter.id if recruiter else None, **fields)
    db.add(company)
    await db.commit()
    return company


async def _contact(db, company, **fields) -> CompanyContact:
    contact = CompanyContact(company_id=company.id, name=fields.pop("name", unique("Person")), **fields)
    db.add(contact)
    await db.commit()
    return contact


async def _merge(client, survivor, victim, **body):
    return await client.post(f"{COMPANIES}/{survivor.id}/merge", json={"victim_code": victim.company_code} | body)


async def _contact_merge(client, survivor, victim, **body):
    return await client.post(f"{CONTACTS}/{survivor.id}/merge", json={"victim_id": str(victim.id)} | body)


async def _world(db, manager, company, contact) -> None:
    """One row of everything that hangs off a company and a contact."""
    job = await make_job(db, company, manager)
    job.decision_maker_contact_id = contact.id
    db.add(JobDescription(job_id=job.id, jd_number=uuid.uuid4().hex[:10], version=1, is_current=True, role="Role", contact_id=contact.id, created_by_user_id=manager.id))
    db.add(RecruiterFollowUp(company_id=company.id, contact_id=contact.id, reason="jd", due_at=NOW + timedelta(days=30), created_by_user_id=manager.id))
    db.add(RecruiterCall(company_id=company.id, contact_id=contact.id, caller_user_id=manager.id, outcome="no_answer", direction="outgoing", occurred_at=NOW))
    message = RecruiterMessage(company_id=company.id, contact_id=contact.id, sender_user_id=manager.id, channel="whatsapp", body="Hello", sent_at=NOW)
    db.add(message)
    await db.flush()
    meeting = RecruiterMeeting(
        meeting_code=uuid.uuid4().hex[:10], company_id=company.id, contact_id=contact.id, meeting_type="company_meeting", starts_at=NOW, mode="Online", created_by_user_id=manager.id
    )
    db.add(meeting)
    await db.flush()
    db.add(RecruiterMeetingParticipant(meeting_id=meeting.id, contact_id=contact.id))
    db.add(RecruiterContract(company_id=company.id, created_by_user_id=manager.id, status="discussion"))
    db.add(CompanyDocument(company_id=company.id, kind="company_profile", content_type="application/pdf", size_bytes=1, storage_key=uuid.uuid4().hex, uploaded_by_user_id=manager.id))
    db.add(ProfileShare(job_id=job.id, company_id=company.id, contact_id=contact.id, channel="whatsapp", message_id=message.id, shared_by_user_id=manager.id))
    db.add(
        RecruitmentDrive(drive_code=uuid.uuid4().hex[:10], company_id=company.id, drive_date=date(2026, 12, 1), job_role="Role", vacancies=1, college_name="A College", created_by_user_id=manager.id)
    )
    db.add(CompanyStageHistory(company_id=company.id, event="move", from_stage="new_lead", to_stage="new_lead", actor_user_id=manager.id))
    await db.commit()


def _contract(company, manager, status: str) -> RecruiterContract:
    """`expired_by_date` is an active contract whose end date has passed; `signed` and `active` need a document, `active` a window (the CHECKs)."""
    lapsed = status == "expired_by_date"
    effective = status in ("signed", "active") or lapsed
    return RecruiterContract(
        company_id=company.id, created_by_user_id=manager.id, status="active" if lapsed else status, start_date=date(2020, 1, 1) if effective else None,
        end_date=date(2020, 12, 31) if lapsed else (date(2099, 1, 1) if effective else None), contract_document_key=uuid.uuid4().hex if effective else None,
        contract_document_content_type="application/pdf" if effective else None,
    )  # fmt: skip


def _references(table_name: str) -> list[tuple]:
    return [(t, c) for t in Base.metadata.tables.values() for c in t.columns for fk in c.foreign_keys if fk.target_fullname == f"{table_name}.id" and c.name != "merged_into_id"]


async def test_every_reference_is_handled():
    """A new foreign key to a company or contact must be moved by the merge, or be listed as handled by a rule."""
    companies = {t.name for t, _ in _references("companies")}
    assert companies == {m.__tablename__ for m in company_merge.MOVED.values()} | {m.__tablename__ for m in company_merge.HANDLED}
    contacts = {(t.name, c.name) for t, c in _references("company_contacts")}
    assert contacts == {(m.__tablename__, column) for m, column in company_merge.CONTACT_MOVED.values()} | {("recruiter_meeting_participants", "contact_id")}


async def test_ac3_a_company_merge_leaves_no_orphaned_rows_and_is_audited(client, db_session):
    manager, _ = await _team(client, db_session)
    survivor, victim = await _company(db_session), await _company(db_session)
    kept = await _contact(db_session, survivor, is_primary=True)
    moved = await _contact(db_session, victim, is_primary=True)
    await _world(db_session, manager, victim, moved)
    response = await _merge(client, survivor, victim, reason="Same firm")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["victim_code"] == victim.company_code
    assert body["moved"]["contacts"] == 1 and body["moved"]["requirements"] == 1 and body["moved"]["drives"] == 1
    for table, column in _references("companies"):
        rows = await db_session.scalar(select(func.count()).select_from(table).where(column == victim.id))
        if table.name not in ("company_branches", "company_skill_demand"):
            assert rows == 0, f"{table.name}.{column.name} still points at the victim"
    for model, count in (
        (RecruiterFollowUp, 1),
        (RecruiterCall, 1),
        (RecruiterMessage, 1),
        (RecruiterMeeting, 1),
        (ProfileShare, 1),
        (RecruitmentDrive, 1),
        (CompanyDocument, 1),
        (RecruiterContract, 1),
        (Job, 1),
        (CompanyContact, 2),
    ):
        assert await db_session.scalar(select(func.count()).select_from(model).where(model.company_id == survivor.id)) == count, model.__tablename__

    stored = await db_session.get(Company, victim.id, populate_existing=True)
    assert stored.merged_into_id == survivor.id and stored.archived_at is not None and stored.merged_at is not None and stored.merged_by_user_id == manager.id
    # the survivor keeps its one primary
    assert [c.id for c in (await db_session.scalars(select(CompanyContact).where(CompanyContact.company_id == survivor.id, CompanyContact.is_primary))).all()] == [kept.id]
    # its last contact follows the moved call and message
    assert (await db_session.get(Company, survivor.id, populate_existing=True)).last_contacted_at == NOW

    merge_audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_company.merge", AuditLog.entity_id == str(survivor.id)))
    assert merge_audit.user_id == manager.id and merge_audit.metadata_json["victim_id"] == str(victim.id) and merge_audit.metadata_json["moved"]["calls"] == 1
    into = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_company.merged_into", AuditLog.entity_id == str(victim.id)))
    assert into.metadata_json["survivor_id"] == str(survivor.id) and into.metadata_json["reason"] == "Same firm"


async def test_the_preview_shows_both_sides_and_what_would_move_without_writing(client, db_session):
    manager, _ = await _team(client, db_session)
    survivor, victim = await _company(db_session, city="Pune"), await _company(db_session, city="Mumbai", website="https://victim.example.com")
    contact = await _contact(db_session, victim)
    await _world(db_session, manager, victim, contact)
    response = await client.get(f"{COMPANIES}/{survivor.id}/merge", params={"victim": victim.company_code})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["survivor"]["code"] == survivor.company_code and body["victim"]["values"]["city"] == "Mumbai"
    assert body["moved"]["contacts"] == 1 and body["moved"]["requirements"] == 1 and body["blocked"] == []
    assert "city" in body["fields"]
    assert (await db_session.get(Company, victim.id, populate_existing=True)).merged_into_id is None


async def test_chosen_fields_are_taken_and_empty_ones_filled(client, db_session):
    await _team(client, db_session)
    source = await db_session.scalar(select(RecLeadSource).where(RecLeadSource.active.is_(True)).limit(1))
    campaign = RecCampaign(name=unique("Camp"), lead_source_id=source.id, start_date=date(2026, 1, 1))
    db_session.add(campaign)
    await db_session.commit()
    name = unique("Stays")
    survivor = await _company(db_session, name=name, city="Pune", state="MH", departments_hiring=[])
    victim = await _company(db_session, city="Mumbai", state="KA", website="https://w.example.com", lead_source_id=source.id, campaign_id=campaign.id, departments_hiring=["Sales"])
    assert (await _merge(client, survivor, victim, use_victim=["city"])).status_code == 200
    stored = await db_session.get(Company, survivor.id, populate_existing=True)
    assert stored.name == name
    assert (stored.city, stored.state, stored.website) == ("Mumbai", "MH", "https://w.example.com")
    assert (stored.lead_source_id, stored.campaign_id) == (source.id, campaign.id)
    assert stored.departments_hiring == ["Sales"]


async def test_an_unknown_field_is_refused(client, db_session):
    await _team(client, db_session)
    survivor, victim = await _company(db_session), await _company(db_session)
    assert (await _merge(client, survivor, victim, use_victim=["name"])).status_code == 422


async def test_an_unassigned_survivor_takes_the_victims_recruiter(client, db_session):
    _, recruiter = await _team(client, db_session)
    survivor, victim = await _company(db_session), await _company(db_session, recruiter=recruiter)
    assert (await _merge(client, survivor, victim)).status_code == 200
    assert (await db_session.get(Company, survivor.id, populate_existing=True)).assigned_recruiter_user_id == recruiter.id


async def test_branches_move_only_to_an_empty_survivor_and_skills_only_where_missing(client, db_session):
    await _team(client, db_session)
    skills = (await db_session.scalars(select(Skill).limit(2))).all()
    survivor, victim = await _company(db_session), await _company(db_session)
    other = await _company(db_session)
    db_session.add_all([
        CompanySkillDemand(company_id=survivor.id, skill_id=skills[0].id, position=0), CompanySkillDemand(company_id=victim.id, skill_id=skills[0].id, position=0),
        CompanySkillDemand(company_id=victim.id, skill_id=skills[1].id, position=1),
        CompanyBranch(company_id=victim.id, position=0, city="Goa"), CompanyBranch(company_id=other.id, position=0, city="Agra"), CompanyBranch(company_id=survivor.id, position=0, city="Pune"),
    ])  # fmt: skip
    await db_session.commit()
    assert (await _merge(client, survivor, victim)).status_code == 200
    assert set((await db_session.scalars(select(CompanySkillDemand.skill_id).where(CompanySkillDemand.company_id == survivor.id))).all()) == {skills[0].id, skills[1].id}
    assert (await db_session.scalars(select(CompanyBranch.city).where(CompanyBranch.company_id == survivor.id))).all() == ["Pune"]
    third = await _company(db_session)
    assert (await _merge(client, third, other)).status_code == 200
    assert (await db_session.scalars(select(CompanyBranch.city).where(CompanyBranch.company_id == third.id))).all() == ["Agra"]


async def test_q06_both_with_a_contract_in_effect_are_refused(client, db_session):
    manager, _ = await _team(client, db_session)
    survivor, victim = await _company(db_session), await _company(db_session)
    for company in (survivor, victim):
        db_session.add(_contract(company, manager, "active"))
    await db_session.commit()
    preview = (await client.get(f"{COMPANIES}/{survivor.id}/merge", params={"victim": victim.company_code})).json()
    assert preview["blocked"] and "contract" in preview["blocked"][0]
    response = await _merge(client, survivor, victim)
    assert response.status_code == 409 and "contract" in response.json()["detail"]
    assert (await db_session.get(Company, victim.id, populate_existing=True)).merged_into_id is None


@pytest.mark.parametrize(
    ("survivor_status", "victim_status", "current"),
    [("discussion", "active", "victim"), ("active", "discussion", "survivor"), ("discussion", "discussion", "survivor"), ("signed", "expired_by_date", "survivor")],
)
async def test_one_current_contract_stays_when_only_one_is_in_effect(client, db_session, survivor_status, victim_status, current):
    manager, _ = await _team(client, db_session)
    survivor, victim = await _company(db_session), await _company(db_session)
    rows = {}
    for key, company, status in (("survivor", survivor, survivor_status), ("victim", victim, victim_status)):
        rows[key] = _contract(company, manager, status)
        db_session.add(rows[key])
    await db_session.commit()
    assert (await _merge(client, survivor, victim)).status_code == 200
    stored = (await db_session.scalars(select(RecruiterContract).where(RecruiterContract.company_id == survivor.id, RecruiterContract.is_current))).all()
    assert [c.id for c in stored] == [rows[current].id]
    assert await db_session.scalar(select(func.count()).select_from(RecruiterContract).where(RecruiterContract.company_id == survivor.id)) == 2


async def test_an_employers_company_cannot_be_the_victim_but_may_stay(client, db_session):
    await _team(client, db_session)
    employer = await make_user(db_session, "employer", "it")
    own = await _company(db_session, owner_type="employer", employer_user_id=employer.id)
    db_session.add(EmployerProfile(user_id=employer.id, company_id=own.id))
    await db_session.commit()
    plain = await _company(db_session)
    refused = await _merge(client, plain, own)
    assert refused.status_code == 409 and "instead" in refused.json()["detail"]
    assert (await _merge(client, own, plain)).status_code == 200
    assert (await db_session.get(Company, plain.id, populate_existing=True)).merged_into_id == own.id


async def test_the_refusals(client, db_session):
    await _team(client, db_session)
    survivor, victim = await _company(db_session), await _company(db_session)
    assert (await _merge(client, survivor, survivor)).status_code == 422
    archived = await _company(db_session, archived_at=NOW)
    assert (await _merge(client, archived, victim)).status_code == 409
    assert (await _merge(client, survivor, archived)).status_code == 409
    assert (await _merge(client, survivor, victim)).status_code == 200
    assert (await _merge(client, survivor, victim)).status_code == 409  # already merged
    assert (await client.post(f"{COMPANIES}/{survivor.id}/merge", json={"victim_code": "CMP-999999999"})).status_code == 404


async def test_a_chain_of_merges_stays_one_hop(client, db_session):
    await _team(client, db_session)
    a, b, c = await _company(db_session), await _company(db_session), await _company(db_session)
    assert (await _merge(client, b, a)).status_code == 200
    assert (await _merge(client, c, b)).status_code == 200
    assert (await db_session.get(Company, a.id, populate_existing=True)).merged_into_id == c.id


async def test_grant_and_scope_decide(client, db_session):
    _, recruiter = await _team(client, db_session)
    survivor, victim = await _company(db_session, recruiter=recruiter), await _company(db_session, recruiter=recruiter)
    outside = await _company(db_session, recruiter=await make_recruiter(db_session, await make_pm(db_session)))
    assert (await _merge(client, survivor, outside)).status_code == 404  # another team's
    assert (await _merge(client, outside, survivor)).status_code == 404
    assert (await client.get(f"{COMPANIES}/{survivor.id}/merge", params={"victim": outside.company_code})).status_code == 404
    await login(client, recruiter)
    assert (await _merge(client, survivor, victim)).status_code == 403  # no default grant
    db_session.add(UserPermissionOverride(user_id=recruiter.id, resource="crm", action="merge", effect="allow", reason="pob-006 test"))
    await db_session.commit()
    assert (await _merge(client, survivor, outside)).status_code == 404  # the grant does not widen scope (G3)
    assert (await _merge(client, survivor, victim)).status_code == 200
    outsider = await make_user(db_session, "hr_team", "it")
    db_session.add(UserPermissionOverride(user_id=outsider.id, resource="crm", action="merge", effect="allow", reason="pob-006 test"))
    await db_session.commit()
    await login(client, outsider)
    assert (await _merge(client, survivor, victim)).status_code == 403


async def test_a_merged_company_says_so_and_cannot_be_restored_or_edited(client, db_session):
    await _team(client, db_session)
    survivor, victim = await _company(db_session), await _company(db_session)
    assert (await _merge(client, survivor, victim)).status_code == 200
    read = (await client.get(f"{COMPANIES}/{victim.id}")).json()["company"]
    assert read["merged_into"] == {"id": str(survivor.id), "code": survivor.company_code, "name": survivor.name}
    assert not any(read["permissions"].values())
    refused = await client.post(f"{COMPANIES}/{victim.id}/restore")
    assert refused.status_code == 409 and "merged" in refused.json()["detail"]
    listed = (await client.get(COMPANIES, params={"q": victim.name})).json()
    assert listed["total"] == 0


async def test_a_job_created_by_a_merged_name_goes_to_the_survivor(client, db_session):
    _, recruiter = await _team(client, db_session)
    survivor, victim = await _company(db_session, recruiter=recruiter), await _company(db_session, recruiter=recruiter)
    assert (await _merge(client, survivor, victim)).status_code == 200
    await login(client, recruiter)
    response = await client.post("/api/v1/workflows/it/jobs", json={"company_name": victim.name, "title": "Role", "description": "Build things", "location": "Pune", "employment_type": "full_time"})
    assert response.status_code == 201, response.text
    assert await db_session.scalar(select(func.count()).select_from(Job).where(Job.company_id == survivor.id)) == 1


async def test_a_reimport_after_a_merge_lands_on_the_survivor(client, db_session):
    await _team(client, db_session)
    survivor, victim = await _company(db_session), await _company(db_session)
    number = mobile()
    await _contact(db_session, victim, mobile=number)
    assert (await _merge(client, survivor, victim)).status_code == 200
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerows([("company_name", "contact_name", "contact_mobile"), (victim.name, "Again", number)])
    body = (await client.post(IMPORTS, files={"file": ("c.csv", buffer.getvalue().encode(), "text/csv")}, headers={"Idempotency-Key": uuid.uuid4().hex})).json()
    assert body["rows"][0]["status"] == "matched" and body["rows"][0]["company"]["id"] == str(survivor.id), body


# --- contacts ---------------------------------------------------------------------------------------------------------------------------


async def test_ac3_a_contact_merge_leaves_no_orphaned_rows_and_is_audited(client, db_session):
    manager, _ = await _team(client, db_session)
    company = await _company(db_session)
    survivor, victim = await _contact(db_session, company, is_primary=True), await _contact(db_session, company, mobile=mobile())
    await _world(db_session, manager, company, victim)
    response = await _contact_merge(client, survivor, victim, reason="Same person")
    assert response.status_code == 200, response.text
    assert response.json()["moved"]["calls"] == 1 and response.json()["moved"]["meeting_participants"] == 1
    for table, column in _references("company_contacts"):
        assert await db_session.scalar(select(func.count()).select_from(table).where(column == victim.id)) == 0, f"{table.name}.{column.name} still points at the victim"
    stored = await db_session.get(CompanyContact, victim.id, populate_existing=True)
    assert stored.merged_into_id == survivor.id and stored.active is False and stored.merged_by_user_id == manager.id
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_company.contact_merge", AuditLog.entity_id == str(company.id)).order_by(AuditLog.created_at.desc()))
    assert audit.user_id == manager.id and audit.metadata_json["victim_id"] == str(victim.id) and audit.metadata_json["reason"] == "Same person"
    assert stored.mobile not in str(audit.metadata_json)


async def test_a_meeting_both_attend_keeps_one_participant(client, db_session):
    manager, _ = await _team(client, db_session)
    company = await _company(db_session)
    survivor, victim = await _contact(db_session, company), await _contact(db_session, company)
    meeting = RecruiterMeeting(meeting_code=uuid.uuid4().hex[:10], company_id=company.id, meeting_type="company_meeting", starts_at=NOW, mode="Online", created_by_user_id=manager.id)
    db_session.add(meeting)
    await db_session.flush()
    db_session.add_all([RecruiterMeetingParticipant(meeting_id=meeting.id, contact_id=survivor.id), RecruiterMeetingParticipant(meeting_id=meeting.id, contact_id=victim.id)])
    await db_session.commit()
    assert (await _contact_merge(client, survivor, victim)).status_code == 200
    assert (await db_session.scalars(select(RecruiterMeetingParticipant.contact_id).where(RecruiterMeetingParticipant.meeting_id == meeting.id))).all() == [survivor.id]


async def test_do_not_contact_decision_maker_and_primary_carry_over(client, db_session):
    await _team(client, db_session)
    company = await _company(db_session)
    survivor = await _contact(db_session, company, status="replied")
    victim = await _contact(db_session, company, status="do_not_contact", is_decision_maker=True, is_primary=True)
    assert (await _contact_merge(client, survivor, victim)).status_code == 200
    stored = await db_session.get(CompanyContact, survivor.id, populate_existing=True)
    assert stored.status == "do_not_contact" and stored.is_decision_maker and stored.is_primary
    gone = await db_session.get(CompanyContact, victim.id, populate_existing=True)
    assert not gone.is_primary and not gone.active
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "recruiter_company.contact_status", AuditLog.entity_id == str(company.id)))
    assert audit.metadata_json["cause"] == "merge" and audit.metadata_json["to"] == "do_not_contact"


async def test_a_contact_merge_picks_and_fills_fields(client, db_session):
    await _team(client, db_session)
    company = await _company(db_session)
    number = mobile()
    survivor = await _contact(db_session, company, name="Stays", designation="Lead", department="HR")
    victim = await _contact(db_session, company, name="Merges", designation="Head", department="Ops", mobile=number)
    preview = (await client.get(f"{CONTACTS}/{survivor.id}/merge", params={"victim": str(victim.id)})).json()
    assert preview["victim"]["values"]["designation"] == "Head" and "designation" in preview["fields"]
    assert (await _contact_merge(client, survivor, victim, use_victim=["department"])).status_code == 200
    stored = await db_session.get(CompanyContact, survivor.id, populate_existing=True)
    assert (stored.name, stored.designation, stored.department, stored.mobile) == ("Stays", "Lead", "Ops", number)
    assert stored.mobile_normalized is not None


async def test_a_merged_contact_leaves_the_list_the_duplicate_warning_and_the_edit_routes(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(db_session, recruiter=recruiter)
    address = mail()
    survivor, victim = await _contact(db_session, company), await _contact(db_session, company, email=address)
    assert (await _contact_merge(client, survivor, victim)).status_code == 200
    await login(client, recruiter)
    items = (await client.get(f"{COMPANIES}/{company.id}/contacts")).json()["items"]
    assert [c["id"] for c in items] == [str(survivor.id)]
    duplicates = (await client.get(f"{COMPANIES}/{company.id}/contacts/duplicates", params={"email": "x" + address, "exclude": str(survivor.id)})).json()
    assert duplicates["matches"] == []
    same = (await client.get(f"{COMPANIES}/{company.id}/contacts/duplicates", params={"email": address, "exclude": str(survivor.id)})).json()
    assert str(victim.id) not in [m["id"] for m in same["matches"]]
    assert (await client.patch(f"{CONTACTS}/{victim.id}", json={"name": "Back"})).status_code == 404


async def test_the_survivors_timeline_keeps_the_victims_status_changes(client, db_session):
    _, recruiter = await _team(client, db_session)
    company = await _company(db_session, recruiter=recruiter)
    survivor, victim = await _contact(db_session, company), await _contact(db_session, company)
    await login(client, recruiter)
    assert (await client.patch(f"{CONTACTS}/{victim.id}", json={"status": "replied"})).status_code == 200
    db_session.add(UserPermissionOverride(user_id=recruiter.id, resource="crm", action="merge", effect="allow", reason="pob-006 test"))
    await db_session.commit()
    assert (await _contact_merge(client, survivor, victim)).status_code == 200
    timeline = (await client.get(f"{COMPANIES}/{company.id}/timeline", params={"contact_id": str(survivor.id), "limit": 50})).json()
    assert any(row.get("kind") == "contact_status" and row.get("to_value") == "replied" for row in timeline["items"]), timeline


async def test_contact_merge_refusals_and_scope(client, db_session):
    manager, recruiter = await _team(client, db_session)
    company, other = await _company(db_session, recruiter=recruiter), await _company(db_session, recruiter=recruiter)
    survivor, victim = await _contact(db_session, company), await _contact(db_session, company)
    elsewhere = await _contact(db_session, other)
    assert (await _contact_merge(client, survivor, survivor)).status_code == 422
    assert (await _contact_merge(client, survivor, elsewhere)).status_code == 404  # within one company only
    outside_company = await _company(db_session, recruiter=await make_recruiter(db_session, await make_pm(db_session)))
    outside = await _contact(db_session, outside_company)
    assert (await _contact_merge(client, outside, await _contact(db_session, outside_company))).status_code == 404
    assert (await client.get(f"{CONTACTS}/{outside.id}/merge", params={"victim": str(outside.id)})).status_code == 404
    await login(client, recruiter)
    assert (await _contact_merge(client, survivor, victim)).status_code == 403  # no default grant
    await login(client, manager)
    archived = await _company(db_session, archived_at=NOW)
    first, second = await _contact(db_session, archived), await _contact(db_session, archived)
    assert (await _contact_merge(client, first, second)).status_code == 409
    assert (await _contact_merge(client, survivor, victim)).status_code == 200
    assert (await _contact_merge(client, survivor, victim)).status_code == 409  # already merged


async def test_a_company_merge_never_reaches_a_contact_of_a_third_company(client, db_session):
    await _team(client, db_session)
    survivor, victim, third = await _company(db_session), await _company(db_session), await _company(db_session)
    other = await _contact(db_session, third, is_primary=True)
    assert (await _merge(client, survivor, victim)).status_code == 200
    stored = await db_session.get(CompanyContact, other.id, populate_existing=True)
    assert stored.company_id == third.id and stored.is_primary


async def test_the_catalogue_holds_both_keys_for_the_manager_only(client, db_session):
    from app.core.rbac import CATALOGUE, DEFAULT_GRANTS

    assert set(CATALOGUE["crm"]["actions"]) == {"import", "merge"}
    holders = {role for role, keys in DEFAULT_GRANTS.items() if "crm.import" in keys or "crm.merge" in keys}
    assert holders == {"placement_manager"}
