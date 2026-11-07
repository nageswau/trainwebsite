"""pob-015 -- vacancy sharing with institutions, the campus calendar and per-institution outcomes (DEC-SCOPE-426 V1-V12; AC1-AC3).
Shared database: every name is unique, and figures are read for this test's own college only."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import (
    AuditLog,
    BdmOrgPlacementBatch,
    BdmOrgPlacementEvent,
    Company,
    InstitutionDataPermission,
    InstitutionDataPermissionUser,
    Interview,
    JobApplication,
    JobOffer,
    RecruiterMessageTemplate,
    RecruitmentDrive,
)
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm
from tests.rec038_helpers import _recruiter, _user, add, make_candidate, make_job, tag
from tests.tel026_helpers import headers

pytestmark = pytest.mark.asyncio
COLLEGES = "/api/v1/recruiter/colleges"
CALENDAR = "/api/v1/recruiter/campus-calendar"
SUMMARY = "/api/v1/recruiter/campus-summary"


async def _world(client, db) -> dict:
    """A college (created by its BDM through the API), a placement manager with two recruiters, and `rec`'s company with an open job."""
    bdm = await make_bdm(db, await make_manager(db))
    await login(client, bdm)
    org = await create_org(client)
    client.cookies.clear()
    mgr = await _user(db, "placement_manager", "global")
    rec, other = await _recruiter(db, mgr), await _recruiter(db, mgr)
    company = await add(db, Company(name=f"P15 Co {tag()}", assigned_recruiter_user_id=rec.id, created_by_user_id=rec.id))
    job = await make_job(db, company, rec)
    await db.commit()
    await db.refresh(job)  # the server-made requirement code
    return {"oid": org["id"], "bdm": bdm, "mgr": mgr, "rec": rec, "other": other, "company": company, "job": job}


async def _outsider(db):
    """A role with no college scope, committed so the app's own session sees it."""
    user = await _user(db, "it_student", "it")
    await db.commit()
    return user


async def _template(db,*, category="college_tpo", owner=None, status="approved") -> RecruiterMessageTemplate:
    row = await add(db, RecruiterMessageTemplate(channel="whatsapp", kind="requirement_update", name=f"TPO {tag()}", body="New vacancy", category=category,
                                                 status=status, owner_user_id=owner))  # fmt: skip
    await db.commit()
    return row


def _share(job, **over) -> dict:
    return {"requirement_id": str(job.id), "channel": "email", **over}


async def _post(client, w, user, body):
    return await client.post(f"{COLLEGES}/{w['oid']}/vacancy-shares", json=body, headers=headers(user))


async def _view(client, w, user) -> dict:
    r = await client.get(f"{COLLEGES}/{w['oid']}/vacancies", headers=headers(user))
    assert r.status_code == 200, r.text
    return r.json()["vacancies"]


async def test_ac1_a_shared_vacancy_appears_on_the_college_timeline_and_takes_a_response(client, db_session):
    w = await _world(client, db_session)
    template = await _template(db_session)
    r = await _post(client, w, w["rec"], _share(w["job"], template_id=str(template.id), notes="Sent the JD to the TPO", shared_on=str(date.today() - timedelta(days=1))))
    assert r.status_code == 201, r.text
    view = r.json()["vacancies"]
    assert view["share_total"] == 1 and view["can_share"] is True
    share = view["shares"][0]
    assert share["requirement"] == {"id": str(w["job"].id), "code": w["job"].requirement_code, "title": w["job"].title}
    assert (share["channel"], share["response"], share["template"]["name"], share["shared_by_name"]) == ("email", "awaiting", template.name, w["rec"].full_name)
    assert (await db_session.get(RecruiterMessageTemplate, template.id, populate_existing=True)).last_used_at is not None  # V4: marked used

    later = await _post(client, w, w["rec"], _share(w["job"], channel="whatsapp"))
    assert later.status_code == 201
    assert [s["channel"] for s in later.json()["vacancies"]["shares"]] == ["whatsapp", "email"]  # newest first

    url = f"{COLLEGES}/{w['oid']}/vacancy-shares/{share['id']}"
    r = await client.patch(url, json={"response": "interested", "response_note": "40 students will apply"}, headers=headers(w["rec"]))
    assert r.status_code == 200, r.text
    answered = next(s for s in r.json()["vacancies"]["shares"] if s["id"] == share["id"])
    assert (answered["response"], answered["response_note"], answered["responded_by_name"]) == ("interested", "40 students will apply", w["rec"].full_name)
    assert answered["responded_at"]
    again = await client.patch(url, json={"response": "interested", "response_note": "40 students will apply"}, headers=headers(w["rec"]))
    assert again.status_code == 200
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == w["oid"], AuditLog.action.like("bdm_organization.placement_vacancy%")))).all()
    assert sorted(actions) == ["bdm_organization.placement_vacancy_response", "bdm_organization.placement_vacancy_share", "bdm_organization.placement_vacancy_share"]

    # every college reader sees the timeline; the BDM and the manager read only
    for reader in (w["bdm"], w["mgr"]):
        assert (await _view(client, w, reader))["share_total"] == 2
    assert (await _view(client, w, w["mgr"]))["can_share"] is False


async def test_only_open_vacancies_that_are_not_internal_and_in_the_callers_scope_can_be_shared(client, db_session):
    w = await _world(client, db_session)
    job = w["job"]
    job.visibility = "internal"
    await db_session.commit()
    r = await _post(client, w, w["rec"], _share(job))
    assert r.status_code == 422 and "not internal" in r.json()["detail"]
    job.visibility, job.status = "portal", "closed"
    await db_session.commit()
    assert (await _post(client, w, w["rec"], _share(job))).status_code == 422
    job.status = "sourcing"
    await db_session.commit()
    # another recruiter's requirement is missing to them (no existence oracle), a manager is read only, other roles are refused
    assert (await _post(client, w, w["other"], _share(job))).status_code == 404
    assert (await _post(client, w, w["mgr"], _share(job))).status_code == 403
    assert (await _post(client, w, await _outsider(db_session), _share(job))).status_code == 403
    assert (await client.post(f"{COLLEGES}/{uuid4()}/vacancy-shares", json=_share(job), headers=headers(w["rec"]))).status_code == 404
    assert (await _post(client, w, w["rec"], _share(job))).status_code == 201


async def test_template_date_and_duplicate_rules(client, db_session):
    w = await _world(client, db_session)
    company_template = await _template(db_session, category="company")
    r = await _post(client, w, w["rec"], _share(w["job"], template_id=str(company_template.id)))
    assert r.status_code == 422 and "College/TPO" in r.json()["detail"]
    someone_elses = await _template(db_session, owner=w["other"].id, status="draft")
    assert (await _post(client, w, w["rec"], _share(w["job"], template_id=str(someone_elses.id)))).status_code == 404
    tomorrow = str(date.today() + timedelta(days=2))
    assert (await _post(client, w, w["rec"], _share(w["job"], shared_on=tomorrow))).status_code == 422
    assert (await _post(client, w, w["rec"], _share(w["job"], channel="fax"))).status_code == 422
    assert (await _post(client, w, w["rec"], _share(w["job"]))).status_code == 201
    duplicate = await _post(client, w, w["rec"], _share(w["job"]))
    assert duplicate.status_code == 409 and "already recorded" in duplicate.json()["detail"]


async def test_a_share_of_another_college_reads_as_missing(client, db_session):
    w = await _world(client, db_session)
    share = (await _post(client, w, w["rec"], _share(w["job"]))).json()["vacancies"]["shares"][0]
    await login(client, w["bdm"])
    other_org = await create_org(client)
    client.cookies.clear()
    r = await client.patch(f"{COLLEGES}/{other_org['id']}/vacancy-shares/{share['id']}", json={"response": "declined"}, headers=headers(w["rec"]))
    assert r.status_code == 404
    bad = await client.patch(f"{COLLEGES}/{w['oid']}/vacancy-shares/{share['id']}", json={"response": "maybe"}, headers=headers(w["rec"]))
    assert bad.status_code == 422


async def _apply(db, job, candidate, status, *, drive=None):
    return await add(db, JobApplication(job_id=job.id, candidate_id=candidate.id, status=status, drive_id=drive.id if drive else None))


async def test_ac2_outcomes_count_the_institutions_external_candidates_once_and_only_for_permitted_viewers(client, db_session):
    w = await _world(client, db_session)
    org_id, rec, job = w["oid"], w["rec"], w["job"]
    permission = await add(db_session, InstitutionDataPermission(organization_id=org_id, agreement_reference=f"MoU {tag()}", purposes=["placement"],
                                                                 valid_from=date.today() - timedelta(days=1), expires_on=date.today() + timedelta(days=90),
                                                                 created_by_user_id=w["mgr"].id))  # fmt: skip
    await add(db_session, InstitutionDataPermissionUser(permission_id=permission.id, user_id=rec.id, added_by_user_id=w["mgr"].id))
    drive = await add(db_session, RecruitmentDrive(drive_code=tag("D15-")[:20], company_id=w["company"].id, college_org_id=org_id, drive_date=date.today(),
                                                   job_role="Java", vacancies=5, created_by_user_id=rec.id))  # fmt: skip
    student = dict(institution_org_id=org_id, institution_permission_id=permission.id, institution_notice_status="consented")
    joined = await _apply(db_session, job, await make_candidate(db_session, rec, **student), "joined")  # imported, joined
    await add(db_session, JobOffer(application_id=joined.id))
    both = await _apply(db_session, job, await make_candidate(db_session, rec, **student), "shortlisted", drive=drive)  # imported AND via the drive
    await add(db_session, Interview(application_id=both.id, scheduled_at=datetime.now(UTC) - timedelta(days=1), status="completed"))
    await _apply(db_session, job, await make_candidate(db_session, rec), "sourced", drive=drive)  # an ordinary candidate through the drive
    await _apply(db_session, job, await make_candidate(db_session, rec), "joined")  # someone else's student: not this college's
    await db_session.commit()

    outcomes = (await _view(client, w, rec))["outcomes"]
    assert outcomes == {"applications": 3, "students": 3, "shortlisted": 2, "interviewed": 1, "offered": 1, "joined": 1, "external": 3}
    # a reader outside the agreement never counts the institution's students -- only the drive's ordinary applicant
    assert (await _view(client, w, w["other"]))["outcomes"] == {"applications": 1, "students": 1, "shortlisted": 0, "interviewed": 0, "offered": 0,
                                                               "joined": 0, "external": 1}  # fmt: skip


async def test_ac3_the_campus_calendar_shows_drives_batches_and_calendar_entries(client, db_session):
    w = await _world(client, db_session)
    org_id, rec = w["oid"], w["rec"]
    day = date.today() + timedelta(days=3)
    await add(db_session, RecruitmentDrive(drive_code=tag("D15-")[:20], company_id=w["company"].id, college_org_id=org_id, drive_date=day, job_role="Java dev",
                                           vacancies=5, created_by_user_id=rec.id))  # fmt: skip
    await add(db_session, BdmOrgPlacementBatch(organization_id=org_id, pass_out_year=day.year, pass_out_date=day, student_count=120, created_by_user_id=rec.id))
    await add(db_session, BdmOrgPlacementEvent(organization_id=org_id, title="Pre-placement talk", kind="pre_placement_talk", starts_on=day - timedelta(days=10),
                                               ends_on=day, created_by_user_id=rec.id))  # fmt: skip
    await add(db_session, BdmOrgPlacementEvent(organization_id=org_id, title="Far away", kind="exam", starts_on=day + timedelta(days=200), created_by_user_id=rec.id))
    await db_session.commit()
    window = {"from": str(day - timedelta(days=1)), "to": str(day + timedelta(days=1)), "college_id": org_id}
    r = await client.get(CALENDAR, params=window, headers=headers(rec))
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert sorted(i["kind"] for i in items) == ["batch", "drive", "event"]  # the event started before the window and overlaps it
    assert all(i["college"]["id"] == org_id for i in items) and r.json()["truncated"] is False
    drive = next(i for i in items if i["kind"] == "drive")
    assert drive["title"] == "Java dev" and drive["date"] == str(day) and "company" not in drive
    # the BDM reads it too; the window is bounded; other roles are refused
    assert len((await client.get(CALENDAR, params=window, headers=headers(w["bdm"]))).json()["items"]) == 3
    assert (await client.get(CALENDAR, params={"from": "2026-01-01", "to": "2026-12-31"}, headers=headers(rec))).status_code == 422
    assert (await client.get(CALENDAR, params={"from": "2026-02-01", "to": "2026-01-01"}, headers=headers(rec))).status_code == 422
    assert (await client.get(CALENDAR, params=window, headers=headers(await _outsider(db_session)))).status_code == 403

    ics = await client.get(f"{CALENDAR}.ics", params=window, headers=headers(rec))
    assert ics.status_code == 200 and ics.headers["content-type"].startswith("text/calendar")
    assert "attachment" in ics.headers["content-disposition"]
    body = ics.text
    assert body.startswith("BEGIN:VCALENDAR") and body.count("BEGIN:VEVENT") == 3 and "SUMMARY:Campus drive: Java dev" in body


async def test_the_tpo_widget_sums_the_callers_colleges(client, db_session):
    w = await _world(client, db_session)
    assert (await _post(client, w, w["rec"], _share(w["job"]))).status_code == 201
    r = await client.get(SUMMARY, headers=headers(w["rec"]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["colleges"] >= 1 and body["shared_30d"] >= 1 and body["awaiting"] >= 1
    assert set(body["outcomes"]) == {"applications", "students", "shortlisted", "interviewed", "offered", "joined", "external"}
    assert (await client.get(SUMMARY, headers=headers(await _outsider(db_session)))).status_code == 403
    total = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == w["oid"]))
    assert total >= 1


async def test_vacancy_options_lists_only_shareable_requirements_in_scope(client, db_session):
    w = await _world(client, db_session)
    hidden = await make_job(db_session, w["company"], w["rec"])
    hidden.visibility = "internal"
    await db_session.commit()
    r = await client.get(f"{COLLEGES}/{w['oid']}/vacancy-options", params={"q": w["job"].title}, headers=headers(w["rec"]))
    assert r.status_code == 200, r.text
    assert [i["id"] for i in r.json()["items"]] == [str(w["job"].id)] and r.json()["items"][0]["company_name"] == w["company"].name
    assert (await client.get(f"{COLLEGES}/{w['oid']}/vacancy-options", params={"q": hidden.title}, headers=headers(w["rec"]))).json()["items"] == []
    assert (await client.get(f"{COLLEGES}/{w['oid']}/vacancy-options", headers=headers(w["mgr"]))).status_code == 403


async def test_vacancy_options_carry_the_callers_college_tpo_templates_for_every_writer(client, db_session):
    """QA-02: the picker's templates come with the options, so a college's BDM (no template-library access) gets them without a 403."""
    w = await _world(client, db_session)
    tpo, company = await _template(db_session), await _template(db_session, category="company")
    for writer in (w["rec"], w["bdm"]):
        r = await client.get(f"{COLLEGES}/{w['oid']}/vacancy-options", headers=headers(writer))
        assert r.status_code == 200, r.text
        names = {t["name"] for t in r.json()["templates"]}
        assert tpo.name in names and company.name not in names
