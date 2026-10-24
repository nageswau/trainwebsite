"""ccrm-026 (DEC-SCOPE-254, VC1-VC4) -- the counselor records the full visa lifecycle on direct and agency applications: Appendix A
statuses mapped onto stage / decision / sub-status, the checklist gate, refused -> visa_refused outcome, the restricted refusal reason,
the V2 decision lock with an admin correction, the stale check, the visa template, CC5 notices and the read views."""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import ApplicationOutcome, AuditLog, DocumentChecklistTemplate, DocumentChecklistTemplateItem, VisaCase
from tests.agn001_helpers import client_for
from tests.agn008_helpers import APPS
from tests.agn009_helpers import mk_doc
from tests.agn023_helpers import ASSIGN, PORTAL, assign_world, fresh, notices

CASES = "/api/v1/workflows/overseas/visa"
LIFECYCLE = CASES + "/{}/lifecycle"
CHECKLIST = "/api/v1/workflows/overseas/applications/{}/visa-checklist"
STATUS = "/api/v1/workflows/overseas/applications/{}/visa-status"
TODAY = date.today()
SECRET = "Insufficient funds shown for the first year"


@pytest_asyncio.fixture
async def world(db_session):
    w = await assign_world(db_session, status="offer")
    async with client_for(w["admin"].email) as c:
        for app in (w["app"], w["direct_app"]):
            assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
    for app in (w["app"], w["direct_app"]):
        case = VisaCase(application_id=app.id, status="checklist", checklist=[])
        db_session.add(case)
        await db_session.commit()
        w[f"case_{'direct' if app is w['direct_app'] else 'agency'}"] = case
    return w


async def _case(db, case) -> VisaCase:
    return await db.get(VisaCase, case.id, populate_existing=True)


async def _patch(user, case, **body):
    async with client_for(user.email) as c:
        return await c.patch(LIFECYCLE.format(case.id), json=body)


async def _walk(user, case, *statuses, **extra):
    """Move a case through `statuses`, each from the previous one."""
    current = "not_started"
    for target in statuses:
        r = await _patch(user, case, expected_visa_status=current, visa_status=target, **extra.get(target, {}))
        assert r.status_code == 200, (target, r.text)
        current = target
    return r


@pytest.mark.asyncio
async def test_the_counselor_records_the_lifecycle_fields_on_a_direct_case(db_session, world):  # AC01
    case = world["case_direct"]
    r = await _patch(
        world["counselor"], case, expected_visa_status="not_started", visa_category="Student (Tier 4)", readiness_review_date=TODAY.isoformat(),
        appointment_place="VFS Chennai", next_steps="Book the biometrics slot",
    )  # fmt: skip
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["visa_status"] == "not_started" and data["visa_status_label"] == "Not started"
    assert (data["visa_category"], data["appointment_place"], data["next_steps"]) == ("Student (Tier 4)", "VFS Chennai", "Book the biometrics slot")
    row = await _case(db_session, case)
    assert (row.visa_category, row.readiness_review_date, row.appointment_place) == ("Student (Tier 4)", TODAY, "VFS Chennai")


@pytest.mark.asyncio
async def test_status_moves_map_onto_stage_and_application_sub_status(db_session, world):  # AC03, Appendix B "Visa application is submitted"
    case, app = world["case_direct"], world["direct_app"]
    submitted = (TODAY - timedelta(days=1)).isoformat()
    await _walk(
        world["counselor"], case, "preparing", "appointment_booked", "submitted",
        appointment_booked={"appointment_date": TODAY.isoformat(), "appointment_place": "VFS Chennai"},
        submitted={"submission_date": submitted, "tracking_reference": "GWF0123456", "expected_decision_date": (TODAY + timedelta(days=20)).isoformat()},
    )  # fmt: skip
    row, item = await _case(db_session, case), await fresh(db_session, app)
    assert (row.visa_status, row.status, row.decision) == ("submitted", "tracking", None)
    assert (row.visa_application_date, row.tracking_reference) == (TODAY - timedelta(days=1), "GWF0123456")
    assert (item.status, item.sub_status) == ("visa_documentation", "visa_applied")
    r = await _patch(world["counselor"], case, expected_visa_status="submitted", visa_status="decision_pending")
    assert r.status_code == 200
    assert ((await fresh(db_session, app)).status, (await fresh(db_session, app)).sub_status) == ("status_tracking", "visa_decision_pending")
    # Additional information requested <-> Decision pending is the one way back.
    assert (await _patch(world["counselor"], case, expected_visa_status="decision_pending", visa_status="additional_info_requested")).status_code == 200
    assert (await fresh(db_session, app)).sub_status == "visa_decision_pending"  # the application never moves back
    assert (await _patch(world["counselor"], case, expected_visa_status="additional_info_requested", visa_status="preparing")).status_code == 422


@pytest.mark.asyncio
async def test_appointment_booked_and_submitted_need_their_dates(db_session, world):  # D2
    case = world["case_direct"]
    await _walk(world["counselor"], case, "preparing")
    r = await _patch(world["counselor"], case, expected_visa_status="preparing", visa_status="appointment_booked")
    assert r.status_code == 422 and "appointment date" in r.text
    r = await _patch(world["counselor"], case, expected_visa_status="preparing", visa_status="submitted")
    assert r.status_code == 422 and "submission date" in r.text
    r = await _patch(world["counselor"], case, expected_visa_status="preparing", submission_date=TODAY.isoformat(), interview_date=(TODAY - timedelta(days=3)).isoformat())
    assert r.status_code == 422 and "interview date" in r.text


@pytest.mark.asyncio
async def test_the_counselor_visa_table_shows_the_status_label(db_session, world):  # browser QA-01
    await _walk(world["counselor"], world["case_direct"], "preparing")
    async with client_for(world["counselor"].email) as c:
        rows = (await c.get(PORTAL.format("counselor", "visa"))).json()["rows"]
    row = next(r for r in rows if r["id"] == str(world["case_direct"].id))
    assert row["status"] == "Preparing"


@pytest.mark.asyncio
async def test_a_typed_year_slip_is_422(db_session, world):  # browser QA-02: the AGN-012 date range
    r = await _patch(world["counselor"], world["case_direct"], expected_visa_status="not_started", readiness_review_date="0202-11-05")
    assert r.status_code == 422 and "between 2000 and 2100" in r.text


@pytest.mark.asyncio
async def test_leaving_not_started_needs_every_checklist_item_verified(db_session, world):  # AC04
    case = world["case_direct"]
    case.checklist = ["Passport"]
    await db_session.commit()
    r = await _patch(world["counselor"], case, expected_visa_status="not_started", visa_status="preparing")
    assert r.status_code == 422 and "Passport" in r.text
    await mk_doc(db_session, student=world["direct_student"], application=world["direct_app"], status="verified")
    assert (await _patch(world["counselor"], case, expected_visa_status="not_started", visa_status="preparing")).status_code == 200


@pytest.mark.asyncio
async def test_refused_needs_a_reason_writes_the_outcome_and_the_reason_stays_restricted(db_session, world):  # AC05
    case, app = world["case_direct"], world["direct_app"]
    await _walk(world["counselor"], case, "preparing", "appointment_booked", "submitted",
                appointment_booked={"appointment_date": TODAY.isoformat()}, submitted={"submission_date": TODAY.isoformat()})  # fmt: skip
    r = await _patch(world["counselor"], case, expected_visa_status="submitted", visa_status="refused")
    assert r.status_code == 422 and "refusal reason" in r.text
    letter = await mk_doc(db_session, student=world["direct_student"], application=app, document_type="Visa refusal letter")
    r = await _patch(
        world["counselor"], case, expected_visa_status="submitted", visa_status="refused", refusal_reason=SECRET, outcome_document_id=str(letter.id), next_steps="Reapply with a sponsor letter"
    )
    assert r.status_code == 200, r.text
    assert r.json()["refusal_reason"] == SECRET
    row, item = await _case(db_session, case), await fresh(db_session, app)
    assert (row.visa_status, row.decision, row.decision_date, row.outcome_document_id) == ("refused", "refused", TODAY, letter.id)
    assert item.outcome == "visa_refused"
    event = await db_session.scalar(select(ApplicationOutcome).where(ApplicationOutcome.application_id == app.id))
    assert event.outcome == "visa_refused" and event.reason is None and event.next_steps == "Reapply with a sponsor letter"
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(case.id)))).all()
    assert audits and all(SECRET not in str(a.metadata_json) for a in audits)
    assert all(SECRET not in f"{n.title} {n.body}" for n in await notices(db_session, world["direct_student"]))
    async with client_for(world["direct_student"].email) as c:
        student_view = (await c.get(STATUS.format(app.id))).json()
        student_checklist = (await c.get(CHECKLIST.format(app.id))).json()
    assert student_view["visa_status_label"] == "Refused" and student_view["next_steps"] == "Reapply with a sponsor letter"
    assert SECRET not in str(student_view) and SECRET not in str(student_checklist)
    async with client_for(world["counselor"].email) as c:
        assert (await c.get(CHECKLIST.format(app.id))).json()["refusal_reason"] == SECRET


@pytest.mark.asyncio
async def test_evidence_must_be_a_document_of_this_application(db_session, world):  # D3
    case = world["case_direct"]
    elsewhere = await mk_doc(db_session, student=world["direct_student"], document_type="Visa letter")
    r = await _patch(world["counselor"], case, expected_visa_status="not_started", visa_status="withdrawn", outcome_document_id=str(elsewhere.id))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_a_decided_case_is_locked_and_only_the_admin_corrects_it(db_session, world):  # AC06, VC1
    case, app = world["case_direct"], world["direct_app"]
    await _walk(world["counselor"], case, "preparing", "appointment_booked", "submitted", "approved",
                appointment_booked={"appointment_date": TODAY.isoformat()}, submitted={"submission_date": TODAY.isoformat()})  # fmt: skip
    assert ((await fresh(db_session, app)).status, (await fresh(db_session, app)).sub_status) == ("status_tracking", "visa_approved")
    r = await _patch(world["counselor"], case, expected_visa_status="approved", next_steps="Book flights")
    assert r.status_code == 409 and "decision is recorded" in r.text
    r = await _patch(world["admin"], case, expected_visa_status="approved", visa_status="refused", refusal_reason=SECRET)
    assert r.status_code == 422 and "correction reason" in r.text
    r = await _patch(world["admin"], case, expected_visa_status="approved", visa_status="decision_pending", correction_reason="Recorded too early")
    assert r.status_code == 422  # a correction stays among the decisions
    r = await _patch(world["admin"], case, expected_visa_status="approved", visa_status="refused", refusal_reason=SECRET, correction_reason="Wrong case")
    assert r.status_code == 200, r.text
    assert (await fresh(db_session, app)).outcome == "visa_refused"
    # A refused application is closed, but the admin may still correct its visa decision (D7); a counselor may not.
    assert (await _patch(world["counselor"], case, expected_visa_status="refused", next_steps="x")).status_code == 409
    r = await _patch(world["admin"], case, expected_visa_status="refused", next_steps="Appeal lodged", correction_reason="Add next steps")
    assert r.status_code == 200, r.text
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(case.id), AuditLog.action == "visa.lifecycle").order_by(AuditLog.created_at.desc()).limit(1))
    assert audit.metadata_json["correction"] is True and SECRET not in str(audit.metadata_json)


@pytest.mark.asyncio
async def test_a_stale_expected_status_is_409_and_an_identical_save_writes_nothing(db_session, world):  # AC07
    case = world["case_direct"]
    r = await _patch(world["counselor"], case, expected_visa_status="preparing", visa_category="Student")
    assert r.status_code == 409
    assert (await _patch(world["counselor"], case, expected_visa_status="not_started", visa_category="Student")).status_code == 200
    before = len((await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(case.id)))).all())
    assert (await _patch(world["counselor"], case, expected_visa_status="not_started", visa_category="Student")).status_code == 200
    assert len((await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(case.id)))).all()) == before


@pytest.mark.asyncio
async def test_scope_and_roles(db_session, world):  # IDOR
    case = world["case_direct"]
    assert (await _patch(world["counselor2"], case, expected_visa_status="not_started", visa_category="x")).status_code == 403
    assert (await _patch(world["direct_student"], case, expected_visa_status="not_started", visa_category="x")).status_code == 403
    assert (await _patch(world["master"], case, expected_visa_status="not_started", visa_category="x")).status_code == 403
    r = await _patch(world["counselor"], case, expected_visa_status="not_started", decision="approved")
    assert r.status_code == 422  # an unknown key


@pytest.mark.asyncio
async def test_on_hold_refuses_a_status_change_but_not_a_field_edit(db_session, world):  # D7
    case, app = world["case_direct"], world["direct_app"]
    item = await fresh(db_session, app)
    item.outcome = "on_hold"
    await db_session.commit()
    assert (await _patch(world["counselor"], case, expected_visa_status="not_started", visa_status="preparing")).status_code == 409
    assert (await _patch(world["counselor"], case, expected_visa_status="not_started", visa_category="Student")).status_code == 200


@pytest.mark.asyncio
async def test_the_counselor_records_the_decision_on_an_agency_case_and_the_agency_is_told(db_session, world):  # AC02, VC2, VC3, CC5
    case, app = world["case_agency"], world["app"]
    agency_user = world["staff"]["user"]
    await _walk(world["counselor"], case, "preparing", "appointment_booked", "submitted", "approved",
                appointment_booked={"appointment_date": TODAY.isoformat(), "appointment_place": "VFS Mumbai"},
                submitted={"submission_date": TODAY.isoformat(), "tracking_reference": "GWF999"})  # fmt: skip
    assert any("Visa" in n.title for n in await notices(db_session, agency_user))
    async with client_for(agency_user.email) as c:
        visa = (await c.get(f"{APPS}/{app.id}")).json()["application"]["visa"]
    assert visa["visa_status"] == "approved" and visa["appointment_place"] == "VFS Mumbai" and visa["decision"] == "approved"
    assert "refusal_reason" not in visa
    # V2: the agency's own route now sees a decided case.
    async with client_for(agency_user.email) as c:
        r = await c.patch(f"{APPS}/{app.id}/visa", json={"expected_stage": "decision", "interview_date": TODAY.isoformat()})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_an_agency_stage_move_and_decision_keep_the_status_in_step_and_tell_the_counselor(db_session, world):  # VC4, CC5
    case, app = world["case_agency"], world["app"]
    agency_user = world["staff"]["user"]
    async with client_for(agency_user.email) as c:
        for stage in ("documentation", "interview_prep", "tracking", "decision"):
            current = (await _case(db_session, case)).status
            assert (await c.patch(f"{APPS}/{app.id}/visa", json={"expected_stage": current, "to_stage": stage})).status_code == 200
        assert (await _case(db_session, case)).visa_status == "decision_pending"
        assert (await c.patch(f"{APPS}/{app.id}/visa", json={"expected_stage": "decision", "decision": "refused"})).status_code == 200
    row = await _case(db_session, case)
    assert (row.visa_status, row.decision_date) == ("refused", TODAY)
    assert (await fresh(db_session, app)).outcome == "visa_refused"
    assert any("Visa" in n.title for n in await notices(db_session, world["counselor"]))


@pytest.mark.asyncio
async def test_the_legacy_patch_keeps_its_contract_and_the_status_follows_the_stage(db_session, world):  # AC10
    case = world["case_direct"]
    async with client_for(world["counselor"].email) as c:
        r = await c.patch(f"{CASES}/{case.id}", json={"status": "documentation"})
    assert r.status_code == 200 and r.json()["status"] == "documentation"
    assert (await _case(db_session, case)).visa_status == "preparing"


@pytest.mark.asyncio
async def test_a_visa_template_prefills_the_checklist(db_session, world):  # AC08, D5
    app = world["direct_app"]
    await db_session.delete(await _case(db_session, world["case_direct"]))
    template = DocumentChecklistTemplate(name="UK student visa", kind="visa", country_id=world["university"].country_id, gate_mode="block")
    db_session.add(template)
    await db_session.flush()
    for position, doc_type in enumerate(("Passport", "CAS letter"), start=1):
        db_session.add(DocumentChecklistTemplateItem(template_id=template.id, position=position, document_type=doc_type, required=True, allowed_statuses=["verified"]))
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        view = (await c.get(CHECKLIST.format(app.id))).json()
        assert view["exists"] is False and view["template"] == {"name": "UK student visa", "items": ["Passport", "CAS letter"]}
        r = await c.post(CASES, json={"application_id": str(app.id)})
        assert r.status_code == 201, r.text
        view = (await c.get(CHECKLIST.format(app.id))).json()
    assert [i["item"] for i in view["checklist"]] == ["Passport", "CAS letter"] and view["visa_status"] == "not_started"
