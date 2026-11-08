"""pob-028 -- the Placement Officer dashboard (DEC-SCOPE-437; design docs/superpowers/specs/2026-11-08-pob-028-po-dashboard-design.md).
A sixth hrc-033 board, `po`: every figure is one predicate, so it ties out to its drill-down (AC). The database is shared and never
truncated, so exact figures are read through this test's own employer filter."""

import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event

from app.core.database import engine
from app.models import (
    InstitutionVacancyShare,
    JobOffer,
    Placement,
    ProfileShare,
    ProfileShareItem,
    RecruiterFollowUp,
    RecruiterInvoice,
    RecruiterPayment,
)
from app.services import recruitment_dashboards as svc
from app.services.bdm_appointments import today_ist
from tests.bdm015_helpers import org_row
from tests.rec001_helpers import as_role, login, make_recruiter, make_user
from tests.test_hrc_033_dashboards import URL, _ago, _apply, _board, _company, _drill, _interview, _job, _values
from tests.test_rec_017_tracking import _candidate

BOARD = "po"


async def _follow_up(db, company, creator, due_at, *, status="open", reason="new_requirement") -> RecruiterFollowUp:
    done = {"completed_at": _ago(), "completed_by_user_id": creator.id} if status == "done" else {}
    row = RecruiterFollowUp(company_id=company.id, reason=reason, due_at=due_at, status=status, created_by_user_id=creator.id, **done)
    db.add(row)
    await db.commit()
    return row


async def _placement(db, application, job, candidate, creator, *, invoice: str = "none", paid: Decimal | None = None, **extra) -> Placement:
    offer = JobOffer(application_id=application.id, status="accepted", joining_status="joined")
    db.add(offer)
    await db.flush()
    fields = {}
    if invoice == "issued":
        bill = RecruiterInvoice(job_id=job.id, invoice_number=f"INV-{offer.id.hex[:8]}", invoice_date=_ago(days=40).date(), due_date=_ago(days=10).date(),
                                amount=Decimal("1000"), created_by_user_id=creator.id)  # fmt: skip
        db.add(bill)
        await db.flush()
        if paid:
            db.add(RecruiterPayment(invoice_id=bill.id, received_on=_ago().date(), amount=paid, created_by_user_id=creator.id))
        fields = {"invoice_status": "issued", "invoice_id": bill.id, "draft_due_date": bill.due_date}
    elif invoice == "draft":
        fields = {"invoice_status": "draft", "draft_due_date": _ago(days=-20).date(), "draft_amount": Decimal("500")}
    row = Placement(offer_id=offer.id, application_id=application.id, job_id=job.id, candidate_id=candidate.id, company_id=job.company_id, role="Engineer", **fields, **extra)
    db.add(row)
    await db.commit()
    return row


async def _plant(db):
    """One employer with a row behind every section of the board."""
    creator = await make_user(db, "placement_team", "it")
    company = await _company(db)
    job = await _job(db, company)
    await _job(db, company, status="on_hold")
    await _follow_up(db, company, creator, _ago(hours=-1))  # due later today, or tomorrow just after midnight IST
    await _follow_up(db, company, creator, _ago(days=2))  # overdue
    await _follow_up(db, company, creator, _ago(days=3), status="done")  # never counted
    people = [await _candidate(db, creator) for _ in range(4)]
    sourced = await _apply(db, people[0], job, "sourced")
    shortlisted = await _apply(db, people[1], job, "sourced", "shortlisted")
    interviewing = await _apply(db, people[2], job, "sourced", "shortlisted", "interview")
    joined = await _apply(db, people[3], job, "sourced", "selected", "joined")
    share = ProfileShare(job_id=job.id, company_id=company.id, channel="other", shared_by_user_id=creator.id)
    db.add(share)
    await db.flush()
    db.add(ProfileShareItem(share_id=share.id, candidate_id=people[2].id, application_id=interviewing.id))
    await db.commit()
    await _interview(db, interviewing, "scheduled", _ago(days=-1))
    await _interview(db, interviewing, "rescheduled", _ago(days=-2))
    await _interview(db, interviewing, "no_show", _ago(hours=3))
    await _placement(db, joined, job, people[3], creator, invoice="issued")
    return {"creator": creator, "company": company, "job": job, "sourced": sourced, "shortlisted": shortlisted}


@pytest.mark.asyncio
async def test_every_po_figure_equals_its_drill_down_count(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    planted = await _plant(db_session)
    params = {"employer": str(planted["company"].id)}
    payload = await _board(client, BOARD, **params)
    assert [s["key"] for s in payload["sections"]] == ["bd", "follow_ups", "requirements", "sourcing", "actions", "tpo", "interviews", "placements", "guarantee", "invoicing"]
    for section in payload["sections"]:
        assert section["figures"], section["key"]
        for figure in section["figures"]:
            drill = await _drill(client, BOARD, figure["key"], **params)
            assert drill["total"] == figure["value"], figure["key"]
            assert len(drill["items"]) == min(figure["value"], 100), figure["key"]
            assert figure["definition"]


@pytest.mark.asyncio
async def test_bd_pipeline_groups_the_stages_and_leaves_out_lost_inactive_and_vendors(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    company = await _company(db_session)
    company.stage, company.client_status = "meeting_scheduled", "active_client"
    await db_session.commit()
    values = _values(await _board(client, BOARD, employer=str(company.id)))
    assert (values["bd_targets"], values["bd_meetings"], values["bd_clients"]) == (0, 1, 1)

    company.lost_at, company.lost_reason = _ago(), "no_requirement"
    await db_session.commit()
    values = _values(await _board(client, BOARD, employer=str(company.id)))
    assert (values["bd_meetings"], values["bd_clients"]) == (0, 0)


@pytest.mark.asyncio
async def test_follow_ups_split_due_today_and_overdue(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    planted = await _plant(db_session)
    company, creator = planted["company"], planted["creator"]
    today_start = datetime.combine(svc.today_ist(datetime.now(UTC)), datetime.min.time(), tzinfo=svc.IST)
    await _follow_up(db_session, company, creator, today_start + timedelta(days=3))  # later: neither
    await _follow_up(db_session, company, creator, today_start - timedelta(minutes=1), reason="cadence_step")  # yesterday: overdue outreach
    values = _values(await _board(client, BOARD, employer=str(company.id)))
    assert values["follow_ups_overdue"] == 2  # _plant's two days ago and yesterday; its "in an hour" one is later today (or tomorrow)
    assert values["follow_ups_today"] + values["follow_ups_overdue"] == values["follow_ups_open_due"]
    assert values["follow_ups_outreach"] == 1


@pytest.mark.asyncio
async def test_candidate_action_queues(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    planted = await _plant(db_session)
    values = _values(await _board(client, BOARD, employer=str(planted["company"].id)))
    assert values["awaiting_screening"] == 1  # the sourced application
    assert values["awaiting_submission"] == 1  # shortlisted, never submitted
    assert values["awaiting_interview_confirmation"] == 2  # scheduled and rescheduled, in the future
    assert values["awaiting_contact"] == 3  # nobody was called or messaged; the joined candidate is no longer active


@pytest.mark.asyncio
async def test_tpo_counts_vacancies_shared_with_institutions(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    planted = await _plant(db_session)
    bdm = await make_user(db_session, "bdm", "it")
    org = await org_row(db_session, bdm.id)
    db_session.add(InstitutionVacancyShare(organization_id=org.id, job_id=planted["job"].id, shared_on=_ago().date(), channel="email", shared_by_user_id=planted["creator"].id))
    await db_session.commit()
    values = _values(await _board(client, BOARD, employer=str(planted["company"].id)))
    assert (values["tpo_shared"], values["tpo_awaiting"]) == (1, 1)


@pytest.mark.asyncio
async def test_invoicing_counts_overdue_and_collected(client, db_session):
    await as_role(client, db_session, "super_admin", "global")
    planted = await _plant(db_session)
    job, creator = planted["job"], planted["creator"]
    paid_person = await _candidate(db_session, creator)
    paid_app = await _apply(db_session, paid_person, job, "sourced", "selected", "joined")
    await _placement(db_session, paid_app, job, paid_person, creator, invoice="issued", paid=Decimal("1000"))
    draft_person = await _candidate(db_session, creator)
    draft_app = await _apply(db_session, draft_person, job, "sourced", "selected", "joined")
    await _placement(db_session, draft_app, job, draft_person, creator, invoice="draft")
    values = _values(await _board(client, BOARD, employer=str(planted["company"].id)))
    assert (values["placements"], values["invoice_pending"], values["invoices_issued"], values["invoices_overdue"], values["invoices_collected"]) == (3, 1, 2, 1, 1)


@pytest.mark.asyncio
async def test_guarantee_counts_expiring_and_owed_replacements(client, db_session):
    """pob-025 G10/G11: ending today..+7 with no dropout; a dropout on or before the end with no replacement filled."""
    await as_role(client, db_session, "super_admin", "global")
    planted = await _plant(db_session)
    job, creator = planted["job"], planted["creator"]
    today = today_ist(_ago())
    cases = [
        {"guarantee_end_date": today + timedelta(days=3)},  # expiring
        {"guarantee_end_date": today + timedelta(days=10)},  # later
        {"guarantee_end_date": today - timedelta(days=1)},  # already past
        {"guarantee_end_date": today + timedelta(days=5), "dropout_on": today - timedelta(days=2), "dropout_reason": "Left"},  # owed
        {"guarantee_end_date": today - timedelta(days=4), "dropout_on": today - timedelta(days=2), "dropout_reason": "Left"},  # after the end
    ]
    for extra in cases:
        person = await _candidate(db_session, creator)
        application = await _apply(db_session, person, job, "sourced", "selected", "joined")
        await _placement(db_session, application, job, person, creator, guarantee_days=30, **extra)
    values = _values(await _board(client, BOARD, employer=str(planted["company"].id)))
    assert (values["guarantee_expiring"], values["replacements_owed"]) == (1, 1)


@pytest.mark.asyncio
async def test_the_invoicing_section_is_for_the_revenue_gate_only(client, db_session):
    planted = await _plant(db_session)
    await as_role(client, db_session, "hr_manager", "it")
    payload = await _board(client, BOARD, employer=str(planted["company"].id))
    assert "invoicing" not in [s["key"] for s in payload["sections"]] and "placements" in [s["key"] for s in payload["sections"]]
    refused = await client.get(f"{URL}/{BOARD}/drill/invoices_overdue")
    assert refused.status_code == 403
    exported = await client.get(f"{URL}/{BOARD}.csv", params={"employer": str(planted["company"].id)})
    assert exported.status_code == 200 and "Invoices overdue" not in exported.text


@pytest.mark.asyncio
async def test_a_po_with_no_activity_sees_zeros_not_errors(client, db_session):
    recruiter = await make_recruiter(db_session)
    await login(client, recruiter)
    payload = await _board(client, BOARD)
    assert all(value == 0 for value in _values(payload).values())
    for key in _values(payload):
        assert (await _drill(client, BOARD, key))["items"] == [], key


@pytest.mark.asyncio
async def test_a_po_reads_only_their_own_companies(client, db_session):
    recruiter = await make_recruiter(db_session)
    mine, theirs = await _company(db_session, recruiter), await _company(db_session)
    for company in (mine, theirs):
        company.stage = "contacted"
    await db_session.commit()
    await login(client, recruiter)
    assert _values(await _board(client, BOARD, employer=str(mine.id)))["bd_outreach"] == 1
    assert _values(await _board(client, BOARD, employer=str(theirs.id)))["bd_outreach"] == 0


@pytest.mark.asyncio
async def test_the_employer_filter_lists_the_pos_prospects(client, db_session):
    """A BD prospect has no requirement yet, so the PO board takes its employer choices from the company scope."""
    recruiter = await make_recruiter(db_session)
    mine, theirs = await _company(db_session, recruiter), await _company(db_session)
    await login(client, recruiter)
    employers = {option["id"] for option in (await _board(client, BOARD, employer=str(mine.id)))["options"]["employers"]}
    assert str(mine.id) in employers
    assert str(theirs.id) not in employers


@pytest.mark.asyncio
async def test_the_po_board_query_count_does_not_grow_with_the_data(client, db_session):
    await as_role(client, db_session, "super_admin", "global")

    async def statements() -> int:
        seen: list[str] = []
        listener = lambda *args: seen.append(args[2])  # noqa: E731
        event.listen(engine.sync_engine, "before_cursor_execute", listener)
        try:
            await _board(client, BOARD)
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", listener)
        return len(seen)

    before = await statements()
    await _plant(db_session)
    assert await statements() == before


def test_the_service_imports_in_a_fresh_interpreter():
    """pob-016 lesson: a cycle hidden by conftest's `import app.main` breaks the worker and the seed."""
    result = subprocess.run([sys.executable, "-c", "import app.services.recruitment_dashboards"], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
