"""AGN-012 AC1-AC7, AC12 -- an agency starts and runs a visa case (spec §4); refusals write nothing; logs and audit stay clean."""

import logging
from datetime import date

import pytest
import pytest_asyncio

from app.models import OverseasApplication, VisaCase
from tests.agn001_helpers import client_for
from tests.agn008_helpers import APPS, mk_application
from tests.agn009_helpers import mk_doc
from tests.agn012_helpers import VISA, case_of, count_cases, mk_case, verified, visa_audits, visa_world


@pytest_asyncio.fixture
async def world(db_session):
    return await visa_world(db_session)


async def _start(c, app_id, **body):
    return await c.post(VISA.format(app_id), json={"expected_status": "offer", **body})


async def _patch(c, app_id, **body):
    return await c.patch(VISA.format(app_id), json=body)


@pytest.mark.asyncio
async def test_the_detail_has_no_visa_block_until_a_case_starts(world):
    async with client_for(world["master"].email) as c:
        assert (await c.get(f"{APPS}/{world['app'].id}")).json()["application"]["visa"] is None


@pytest.mark.asyncio
async def test_full_flow_to_an_approved_decision(db_session, world):
    async with client_for(world["master"].email) as c:
        r = await _start(c, world["app"].id, checklist=["Passport", "Financial documents"], visa_application_date="2027-05-01")
        assert r.status_code == 201, r.text
        v = r.json()["application"]["visa"]
        assert (v["stage"], v["visa_application_date"], v["decision"]) == ("checklist", "2027-05-01", None)
        assert v["checklist"] == [{"item": "Passport", "verification_status": "not_uploaded"}, {"item": "Financial documents", "verification_status": "not_uploaded"}]
        assert v["disclaimer"].startswith("Visa decisions are made by")
        await verified(db_session, world, "Passport", "Financial documents")
        for old, new in (("checklist", "documentation"), ("documentation", "interview_prep")):
            r = await _patch(c, world["app"].id, expected_stage=old, to_stage=new)
            assert r.status_code == 200, r.text
        r = await _patch(c, world["app"].id, expected_stage="interview_prep", interview_date="2027-05-20", appointment_date="2027-05-10")
        assert r.status_code == 200 and r.json()["application"]["visa"]["interview_date"] == "2027-05-20"
        assert (await _patch(c, world["app"].id, expected_stage="interview_prep", to_stage="decision")).status_code == 200  # a skip
        r = await _patch(c, world["app"].id, expected_stage="decision", decision="approved")
        assert r.status_code == 200, r.text
        a = r.json()["application"]
    assert (a["visa"]["decision"], a["status"]) == ("approved", "offer")  # V5: the application stage never moves
    assert a["visa"]["decided_at"]
    actions = [(row.action, row.metadata_json) for row in await visa_audits(db_session, world["app"])]
    assert actions == [
        ("overseas.application.visa_start", {"checklist_items": 2}),
        ("overseas.application.visa_advance", {"from_stage": "checklist", "to_stage": "documentation"}),
        ("overseas.application.visa_advance", {"from_stage": "documentation", "to_stage": "interview_prep"}),
        ("overseas.application.visa_update", {"fields": ["appointment_date", "interview_date"]}),
        ("overseas.application.visa_advance", {"from_stage": "interview_prep", "to_stage": "decision"}),
        ("overseas.application.visa_decision", {"decision": "approved"}),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["offer", "visa_documentation", "status_tracking"])
async def test_a_case_starts_from_an_offer_onwards(db_session, stage):
    w = await visa_world(db_session, status=stage)
    async with client_for(w["master"].email) as c:
        assert (await _start(c, w["app"].id, expected_status=stage)).status_code == 201


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "expected", "archived", "code", "detail"),
    [
        ("enquiry", "enquiry", False, 422, "An offer is needed before a visa case"),
        ("University review", "University review", False, 422, "An offer is needed before a visa case"),  # legacy free text
        ("offer", "visa_documentation", False, 409, "This application changed since you opened it -- reload to see its current status"),
        ("withdrawn", "withdrawn", False, 409, "This application is withdrawn"),
        ("enrolled", "enrolled", False, 409, "This application is enrolled, so its visa case can no longer be changed"),
        ("offer", "offer", True, 409, "Unarchive this student first"),
    ],
)
async def test_start_refusals_write_nothing(db_session, world, status, expected, archived, code, detail):
    row = await db_session.get(OverseasApplication, world["app"].id)
    row.status = status
    if archived:
        world["record"].status = "archived"
        db_session.add(world["record"])
    await db_session.commit()
    async with client_for(world["master"].email) as c:
        r = await _start(c, world["app"].id, expected_status=expected)
    assert (r.status_code, r.json()["detail"]) == (code, detail)
    assert await count_cases(db_session, world["app"]) == 0 and await visa_audits(db_session, world["app"]) == []


@pytest.mark.asyncio
async def test_a_second_start_is_409(db_session, world):
    await mk_case(db_session, world["app"])
    async with client_for(world["master"].email) as c:
        r = await _start(c, world["app"].id)
    assert (r.status_code, r.json()["detail"]) == (409, "A visa case already exists for this application")
    assert await count_cases(db_session, world["app"]) == 1


@pytest.mark.asyncio
async def test_start_checks_the_date_order(db_session, world):
    async with client_for(world["master"].email) as c:
        r = await _start(c, world["app"].id, visa_application_date="2027-05-02", interview_date="2027-05-01")
    assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", "interview_date"]
    assert await count_cases(db_session, world["app"]) == 0


@pytest.mark.asyncio
async def test_the_gate_blocks_until_every_item_is_verified(db_session, world):
    await mk_case(db_session, world["app"], checklist=["Passport", "SOP"])
    await verified(db_session, world, "Passport")
    await verified(db_session, world, "SOP", status="pending")
    async with client_for(world["master"].email) as c:
        r = await _patch(c, world["app"].id, expected_stage="checklist", to_stage="tracking")
        assert (r.status_code, r.json()["detail"]) == (422, "Cannot advance past the checklist stage -- not yet verified: SOP.")
        assert (await case_of(db_session, world["app"])).status == "checklist"
        await verified(db_session, world, "SOP")
        assert (await _patch(c, world["app"].id, expected_stage="checklist", to_stage="tracking")).status_code == 200


@pytest.mark.asyncio
async def test_the_newest_document_of_a_type_decides(db_session, world):
    await mk_case(db_session, world["app"], checklist=["Passport"])
    await verified(db_session, world, "Passport")
    await verified(db_session, world, "Passport", status="pending")  # a newer upload, not yet reviewed
    async with client_for(world["master"].email) as c:
        r = await _patch(c, world["app"].id, expected_stage="checklist", to_stage="documentation")
    assert r.status_code == 422 and "Passport" in r.json()["detail"]


@pytest.mark.asyncio
async def test_documents_outside_the_application_do_not_count(db_session, world):
    await mk_case(db_session, world["app"], checklist=["Passport"])
    other_app = await mk_application(db_session, agent=world["master"], university=world["university"], record=world["record"], status="offer", intake="Jan 2028")
    await mk_doc(db_session, record=world["record"], application=other_app, status="verified")
    await mk_doc(db_session, record=world["record"], application=None, status="verified")
    async with client_for(world["master"].email) as c:
        r = await c.get(f"{APPS}/{world['app'].id}")
        assert r.json()["application"]["visa"]["checklist"] == [{"item": "Passport", "verification_status": "not_uploaded"}]
        assert (await _patch(c, world["app"].id, expected_stage="checklist", to_stage="documentation")).status_code == 422


@pytest.mark.asyncio
async def test_the_gate_reads_the_checklist_sent_with_the_move(world):
    async with client_for(world["master"].email) as c:
        assert (await _start(c, world["app"].id, checklist=["Passport"])).status_code == 201
        r = await _patch(c, world["app"].id, expected_stage="checklist", checklist=[], to_stage="documentation")
    assert r.status_code == 200 and r.json()["application"]["visa"]["checklist"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stage", "body", "detail"),
    [
        ("documentation", {"to_stage": "checklist"}, "A visa case can only move forward"),
        ("documentation", {"to_stage": "documentation"}, "A visa case can only move forward"),
        ("documentation", {"checklist": ["Passport"]}, "The checklist can only be changed at the checklist stage"),
        ("tracking", {"decision": "approved"}, "Move the case to the decision stage before recording a decision"),
        ("tracking", {"to_stage": "decision", "decision": "approved"}, "Move the case to the decision stage before recording a decision"),
    ],
)
async def test_rule_refusals_are_422_and_write_nothing(db_session, world, stage, body, detail):
    await mk_case(db_session, world["app"], status=stage)
    async with client_for(world["master"].email) as c:
        r = await _patch(c, world["app"].id, expected_stage=stage, **body)
    assert (r.status_code, r.json()["detail"]) == (422, detail)
    case = await case_of(db_session, world["app"])
    assert (case.status, case.checklist, case.decision) == (stage, [], None)
    assert await visa_audits(db_session, world["app"]) == []


@pytest.mark.asyncio
async def test_a_recorded_decision_is_final(db_session, world):
    await mk_case(db_session, world["app"], status="decision", decision="refused")
    async with client_for(world["master"].email) as c:
        for body in ({"decision": "approved"}, {"interview_date": "2027-06-01"}):
            r = await _patch(c, world["app"].id, expected_stage="decision", **body)
            assert (r.status_code, r.json()["detail"]) == (409, "The visa decision is recorded, so this case can no longer be changed")
    case = await case_of(db_session, world["app"])
    assert (case.decision, case.interview_date) == ("refused", None)


@pytest.mark.asyncio
async def test_stale_stage_and_missing_case_are_409(db_session, world):
    async with client_for(world["master"].email) as c:
        r = await _patch(c, world["app"].id, expected_stage="checklist", interview_date="2027-06-01")
        assert (r.status_code, r.json()["detail"]) == (409, "This visa case changed since you opened it -- reload to see its current stage")
        await mk_case(db_session, world["app"], status="documentation")
        assert (await _patch(c, world["app"].id, expected_stage="checklist", to_stage="tracking")).status_code == 409
    assert (await case_of(db_session, world["app"])).status == "documentation"


@pytest.mark.asyncio
async def test_date_order_uses_stored_values(db_session, world):
    await mk_case(db_session, world["app"], status="documentation", interview_date=date(2027, 5, 10))
    async with client_for(world["master"].email) as c:
        r = await _patch(c, world["app"].id, expected_stage="documentation", visa_application_date="2027-05-11")
        assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body", "interview_date"]
        assert (await _patch(c, world["app"].id, expected_stage="documentation", visa_application_date="2027-05-10")).status_code == 200  # same day
        r = await _patch(c, world["app"].id, expected_stage="documentation", interview_date=None, appointment_date=None)
    assert r.status_code == 200 and r.json()["application"]["visa"]["interview_date"] is None
    assert (await case_of(db_session, world["app"])).visa_application_date == date(2027, 5, 10)


@pytest.mark.asyncio
async def test_an_unchanged_patch_writes_nothing(db_session, world):
    await mk_case(db_session, world["app"], checklist=["Passport"])
    async with client_for(world["master"].email) as c:
        r = await _patch(c, world["app"].id, expected_stage="checklist", checklist=["Passport"], interview_date=None)
    assert r.status_code == 200 and await visa_audits(db_session, world["app"]) == []


@pytest.mark.asyncio
async def test_legacy_admin_case_is_readable_and_moves_forward_only_through_the_gate(db_session, world):
    await mk_case(db_session, world["app"], status="not_started", checklist=["Passport", "Visa form"])
    async with client_for(world["master"].email) as c:
        v = (await c.get(f"{APPS}/{world['app'].id}")).json()["application"]["visa"]
        assert v["stage"] == "not_started" and v["checklist"][1] == {"item": "Visa form", "verification_status": "not_uploaded"}
        assert (await _patch(c, world["app"].id, expected_stage="not_started", to_stage="documentation")).status_code == 422  # the gate
        assert (await _patch(c, world["app"].id, expected_stage="not_started", to_stage="checklist")).status_code == 200
        r = await _patch(c, world["app"].id, expected_stage="checklist", checklist=["Passport"])
    assert r.status_code == 200 and [i["item"] for i in r.json()["application"]["visa"]["checklist"]] == ["Passport"]


@pytest.mark.asyncio
async def test_list_items_carry_no_visa_block(db_session, world):
    await mk_case(db_session, world["app"])
    async with client_for(world["master"].email) as c:
        items = (await c.get(APPS, params={"status": "all"})).json()["items"]
    assert items and all("visa" not in item for item in items)


@pytest.mark.asyncio
async def test_a_failed_write_leaves_nothing_behind(db_session, world, monkeypatch):
    from app.api import agent_applications

    def broken(*args, **kwargs):
        raise RuntimeError("audit store unavailable")

    monkeypatch.setattr(agent_applications, "_audit", broken)
    async with client_for(world["master"].email) as c:
        with pytest.raises(RuntimeError):
            await _start(c, world["app"].id, checklist=["Passport"])
    assert await count_cases(db_session, world["app"]) == 0  # one transaction: no case without its audit row


@pytest.mark.asyncio
async def test_logs_carry_no_decision_or_dates(db_session, world, caplog):
    logging.getLogger("app.agent_applications").disabled = False  # alembic's fileConfig disables loggers (AGN-004 precedent)
    caplog.set_level(logging.INFO, logger="app.agent_applications")
    async with client_for(world["master"].email) as c:
        assert (await _start(c, world["app"].id, visa_application_date="2027-05-01")).status_code == 201
        assert (await _patch(c, world["app"].id, expected_stage="checklist", to_stage="documentation")).status_code == 200
        assert (await _patch(c, world["app"].id, expected_stage="documentation", interview_date="2027-05-21")).status_code == 200
        await db_session.execute(VisaCase.__table__.update().where(VisaCase.application_id == world["app"].id).values(status="decision"))
        await db_session.commit()
        assert (await _patch(c, world["app"].id, expected_stage="decision", decision="refused")).status_code == 200
    records = [r for r in caplog.records if r.name == "app.agent_applications"]
    assert [r.msg for r in records] == ["agent_visa_started", "agent_visa_advanced", "agent_visa_updated", "agent_visa_decided"]
    text = " ".join(str(r.extra_fields) for r in records)
    assert "refused" not in text and "2027-05" not in text
    assert records[1].extra_fields["to_stage"] == "documentation" and records[2].extra_fields["fields"] == ["interview_date"]


@pytest.mark.asyncio
async def test_a_blocked_gate_is_logged_without_document_names(world, caplog):
    logging.getLogger("app.agent_applications").disabled = False
    caplog.set_level(logging.INFO, logger="app.agent_applications")
    async with client_for(world["master"].email) as c:
        assert (await _start(c, world["app"].id, checklist=["Passport"])).status_code == 201
        assert (await _patch(c, world["app"].id, expected_stage="checklist", to_stage="documentation")).status_code == 422
    (blocked,) = [r for r in caplog.records if r.msg == "agent_visa_gate_blocked"]
    assert blocked.levelno == logging.WARNING and blocked.extra_fields["unverified_items"] == 1 and "Passport" not in str(blocked.extra_fields)
