"""rec-038 matrix rows: the activity group -- follow-ups (rec-024), calls (rec-025), templates and messages (rec-026), the timeline (rec-027),
meetings (rec-028), campus drives (rec-029), contracts (rec-030), revenue and invoices (rec-031) and the dashboards (rec-032..035).

Company-scoped records follow rec-003 `caller_scope` (RBAC_MATRIX §2.47): the assigned recruiter, the manager's team, super_admin and the
company's assigned BDM read (R10); out of scope is 404. Writes need the company's `can_edit` -- the assigned recruiter or super_admin -- so a
manager and the assigned BDM are refused 403 after the scope check (§2.57/§2.59/§2.60/§2.82/§2.104)."""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from app.models import (
    Company,
    DriveRequirement,
    RecruiterCall,
    RecruiterContract,
    RecruiterFollowUp,
    RecruiterInvoice,
    RecruiterMeeting,
    RecruiterMessageTemplate,
    RecruitmentDrive,
)
from app.services import recruiter_contracts as contracts
from tests.rec038_helpers import PDF, R, add, allow, now, tag

IN_SCOPE = ("rec", "mgr", "super", "bdm")  # rec-003 caller_scope readers of the world's company (R10: the assigned BDM)
OUT = ("rec_out", "mgr_out", "bdm_out")  # the same roles without the company in scope: 404, as an unknown id (RM4)
LISTERS = (*IN_SCOPE, *OUT)  # the scoped lists: every scope role reads its own (maybe empty) slice
EDITORS = ("rec", "super")  # rec-003 `can_edit`: the assigned recruiter or super_admin; mgr and bdm 403 after the scope check
POOL_READERS = ("rec", "rec_out", "mgr", "mgr_out", "super", "hr")  # candidates.READERS (R11, the whole pool; hr_team reads)
CREATORS = ("rec", "rec_out", "mgr", "mgr_out", "super")  # rec-003 `require_creator`: the pickers (MT5, DR2)
TEMPLATE_WRITERS = ("mgr", "mgr_out", "super")  # MS3 / R13: the placement manager's global library
REVENUE = ("rec", "mgr", "super")  # rec-031 READERS with the requirement in scope; bdm 403 first (RV10)
REVENUE_OUT = ("rec_out", "mgr_out")  # a revenue reader without the requirement in scope: 404
METRICS = ("mgr", "mgr_out", "super", "it_admin")  # rec-033 PF1 / rec-035 MG1 (it_admin reads: recruiters are IT staff)

PATH_VALUES = {"activity_kind": "contract"}
_DOC: dict[str, str] = {}  # one stored PDF reused by every world's contract (only its key is per row)


def _soon(days: int = 1) -> str:
    return (now() + timedelta(days=days)).isoformat()


def _upload(_w):
    return {}, {"file": ("signed.pdf", PDF, "application/pdf")}


def _meeting(_w) -> dict:
    return {"meeting_type": "contract_discussion", "starts_at": _soon(), "mode": "Online"}


def _drive(w) -> dict:
    return {"company_id": w["company"], "college_name": "ABC College", "requirement_ids": [w["requirement"]], "drive_date": w["tomorrow"],
            "job_role": "Graduate Engineer Trainee", "vacancies": 10}  # fmt: skip


def _invoice(w) -> dict:
    return {"requirement_id": w["requirement"], "invoice_number": tag("INV-"), "invoice_date": w["today"], "due_date": w["tomorrow"], "amount": "150000"}


ROWS = [
    # rec-024 follow-ups (§2.57): reads by scope, writes by `can_edit`
    R("get", "/recruiter/follow-ups", **allow(200, *LISTERS)),
    R("get", "/recruiter/companies/{company}/follow-ups", **allow(200, *IN_SCOPE), **allow(404, *OUT)),
    R("post", "/recruiter/companies/{company}/follow-ups", lambda w: {"due_at": _soon(), "reason": "jd"}, **allow(201, *EDITORS), **allow(404, *OUT)),
    R("patch", "/recruiter/follow-ups/{activity_fu}", lambda w: {"notes": f"Call HR {tag()}"}, **allow(200, *EDITORS), **allow(404, *OUT)),
    R("post", "/recruiter/follow-ups/{activity_fu}/complete", {}, **allow(200, *EDITORS), **allow(404, *OUT)),
    R("post", "/recruiter/follow-ups/{activity_fu}/cancel", {"reason": "Company paused hiring"}, **allow(200, *EDITORS), **allow(404, *OUT)),
    # rec-025 calls (§2.59): a contact call is the company's; only its caller edits / deletes it (super_admin 403 CALLER_ONLY on rec's call)
    R("post", "/recruiter/calls", lambda w: {"contact_id": w["contact"], "outcome": "connected"}, **allow(201, *EDITORS), **allow(404, *OUT)),
    R("patch", "/recruiter/calls/{activity_call}", {"notes": "Discussed fees"}, rec=200, **allow(404, *OUT)),
    R("delete", "/recruiter/calls/{activity_call}", rec=204, **allow(404, *OUT)),
    R("get", "/recruiter/companies/{company}/calls", **allow(200, *IN_SCOPE), **allow(404, *OUT)),
    R("get", "/recruiter/candidates/{candidate}/calls", **allow(200, *POOL_READERS)),
    # rec-026 templates (MS3, R13: the manager's library; recruiters read active ones) and messages (§2.61)
    R("get", "/recruiter/templates", **allow(200, *CREATORS)),
    R("post", "/recruiter/templates", lambda w: {"channel": "whatsapp", "kind": "follow_up", "name": tag("R38 T "), "body": "Hi {name}"}, **allow(201, *TEMPLATE_WRITERS)),
    R("patch", "/recruiter/templates/{activity_template}", {"body": "Hello {name}, {recruiter} here."}, **allow(200, *TEMPLATE_WRITERS)),
    R("get", "/recruiter/templates/{activity_template}/preview", **allow(200, *CREATORS)),
    R("post", "/recruiter/messages", lambda w: {"channel": "whatsapp", "contact_id": w["contact"], "body": "Hi"}, **allow(201, *EDITORS), **allow(404, *OUT)),
    # §2.61 / RM6: render is a template read -- the template readers' role first (the BDMs 403), then the contact's company scope (404)
    R("get", "/recruiter/messages/render?template_id={activity_template}&contact_id={contact}", **allow(200, "rec", "mgr", "super"), **allow(404, "rec_out", "mgr_out")),
    R("get", "/recruiter/companies/{company}/messages", **allow(200, *IN_SCOPE), **allow(404, *OUT)),
    R("get", "/recruiter/candidates/{candidate}/messages", **allow(200, *POOL_READERS)),
    # rec-027 timeline (§2.107): the company's by scope (hr 403), the candidate's by the pool (bdm 403)
    R("get", "/recruiter/companies/{company}/timeline", **allow(200, *IN_SCOPE), **allow(404, *OUT)),
    R("get", "/recruiter/candidates/{candidate}/timeline", **allow(200, *POOL_READERS)),
    # rec-028 meetings (§2.60): the picker is the company creators'; outcome needs a started meeting (the world's started 1 h ago)
    R("get", "/recruiter/meetings", **allow(200, *LISTERS)),
    R("get", "/recruiter/meetings/recruiter-options", **allow(200, *CREATORS)),
    R("get", "/recruiter/meetings/{activity_meeting}", **allow(200, *IN_SCOPE), **allow(404, *OUT)),
    R("patch", "/recruiter/meetings/{activity_meeting}", lambda w: {"purpose": f"Fees {tag()}"}, **allow(200, *EDITORS), **allow(404, *OUT)),
    R("post", "/recruiter/meetings/{activity_meeting}/cancel", {"reason": "Client postponed"}, **allow(200, *EDITORS), **allow(404, *OUT)),
    R("post", "/recruiter/meetings/{activity_meeting}/outcome", {"outcome": "Agreed on the fee"}, **allow(200, *EDITORS), **allow(404, *OUT)),
    R("get", "/recruiter/companies/{company}/meetings", **allow(200, *IN_SCOPE), **allow(404, *OUT)),
    R("post", "/recruiter/companies/{company}/meetings", _meeting, **allow(201, *EDITORS), **allow(404, *OUT)),
    # rec-029 campus drives (§2.104)
    R("get", "/recruiter/drives", **allow(200, *LISTERS)),
    R("post", "/recruiter/drives", _drive, **allow(201, *EDITORS), **allow(404, *OUT)),
    R("get", "/recruiter/drives/college-options", **allow(200, *CREATORS)),
    R("get", "/recruiter/drives/{activity_drive}", **allow(200, *IN_SCOPE), **allow(404, *OUT)),
    R("patch", "/recruiter/drives/{activity_drive}", lambda w: {"job_role": f"SDE Trainee {tag()}"}, **allow(200, *EDITORS), **allow(404, *OUT)),
    R("get", "/recruiter/drives/{activity_drive}/candidates", **allow(200, *IN_SCOPE), **allow(404, *OUT)),
    R("get", "/recruiter/drives/{activity_drive}/funnel", **allow(200, *IN_SCOPE), **allow(404, *OUT)),
    # rec-030 contracts (§2.82): `company` has none (a first contract); `activity_contract_company` (also rec's, same BDM) has a draft one
    R("get", "/recruiter/companies/{activity_contract_company}/contracts", **allow(200, *IN_SCOPE), **allow(404, *OUT)),
    R("post", "/recruiter/companies/{company}/contracts", {}, **allow(201, *EDITORS), **allow(404, *OUT)),
    R("patch", "/recruiter/companies/{activity_contract_company}/contracts", lambda w: {"payment_terms": f"Net 30 {tag()}"}, **allow(200, *EDITORS), **allow(404, *OUT)),
    R("put", "/recruiter/companies/{activity_contract_company}/contracts/document?kind=mou", form=_upload, **allow(200, *EDITORS), **allow(404, *OUT)),
    R("get", "/recruiter/contracts/{activity_contract}/documents/{activity_kind}", **allow(200, *IN_SCOPE), **allow(404, *OUT)),
    R("get", "/recruiter/contracts/{activity_contract}/history", **allow(200, *IN_SCOPE), **allow(404, *OUT)),
    # rec-031 revenue (§2.102): the role first (bdm 403), then the requirement's scope (404); the fee override is the manager's (RV10) --
    # `rec` reaches it in scope and gets 403, `rec_out` is out of scope first (404, as an unknown id)
    R("get", "/recruiter/companies/{company}/revenue", **allow(200, *REVENUE), **allow(404, *REVENUE_OUT)),
    R("get", "/recruiter/requirements/{requirement}/revenue", **allow(200, *REVENUE), **allow(404, *REVENUE_OUT)),
    R("put", "/recruiter/requirements/{requirement}/fee", {"fee_basis": "fixed", "fee_value": "60000"}, **allow(200, "mgr", "super"), **allow(404, *REVENUE_OUT)),
    R("get", "/recruiter/invoices", **allow(200, *REVENUE, *REVENUE_OUT)),
    R("post", "/recruiter/invoices", _invoice, **allow(201, *REVENUE), **allow(404, *REVENUE_OUT)),
    R("post", "/recruiter/invoices/{activity_invoice}/cancel", {"reason": "Raised in error"}, **allow(200, *REVENUE), **allow(404, *REVENUE_OUT)),
    R("post", "/recruiter/invoices/{activity_invoice}/payments", lambda w: {"received_on": w["today"], "amount": "1000"}, **allow(201, *REVENUE), **allow(404, *REVENUE_OUT)),
    # rec-032 dashboard (§2.106), narrowed to `rec`: another recruiter naming them 403; a manager's non-report 404
    R("get", "/recruiter/dashboard?recruiter={rec_id}", **allow(200, "rec", "mgr", "super"), rec_out=403, mgr_out=404),
    # rec-033 performance (§2.108, PF1) and its CSV, rec-034 per recruiter (§2.109, own row only; it_admin 403), rec-035 management (§2.110)
    R("get", "/recruiter/performance?recruiter={rec_id}", **allow(200, "mgr", "super", "it_admin"), mgr_out=404),
    R("get", "/recruiter/performance.csv", **allow(200, *METRICS)),
    R("get", "/recruiter/performance/by-recruiter?recruiter={rec_id}", **allow(200, "rec", "mgr", "super"), rec_out=403, mgr_out=404),
    R("get", "/recruiter/management", **allow(200, *METRICS)),
]


async def build(client, db, w) -> None:
    """A follow-up, a call (rec's, today), a template, a started meeting and a drive on `company`; a second company of rec's (same BDM) with a
    draft contract carrying a contract document; an unpaid invoice on `requirement`."""
    users, company_id, contact_id, job_id = w["users"], UUID(w["company"]), UUID(w["contact"]), UUID(w["requirement"])
    rec = users["rec"]
    fu = await add(db, RecruiterFollowUp(company_id=company_id, due_at=now() + timedelta(days=1), reason="offer_status", created_by_user_id=rec.id))
    call = await add(db, RecruiterCall(company_id=company_id, contact_id=contact_id, caller_user_id=rec.id, occurred_at=now(), direction="outgoing",
                                       outcome="connected"))  # fmt: skip
    template = await add(db, RecruiterMessageTemplate(channel="whatsapp", kind="follow_up", name=tag("R38 T "), body="Hi {name}, {recruiter} here.", active=True))
    meeting = await add(db, RecruiterMeeting(meeting_code=tag("MTG-"), company_id=company_id, meeting_type="contract_discussion",
                                             starts_at=now() - timedelta(hours=1), mode="Online", created_by_user_id=rec.id))  # fmt: skip
    drive = await add(db, RecruitmentDrive(drive_code=tag("DRV-"), company_id=company_id, college_name="ABC College", drive_date=now().date() + timedelta(days=1),
                                           job_role="Graduate Engineer Trainee", vacancies=10, created_by_user_id=rec.id))  # fmt: skip
    await add(db, DriveRequirement(drive_id=drive.id, job_id=job_id))
    second = await add(db, Company(name=f"R38 Co {tag()}", assigned_recruiter_user_id=rec.id, assigned_bdm_user_id=users["bdm"].id, created_by_user_id=rec.id))
    if "key" not in _DOC:
        _DOC["key"] = contracts.store(PDF, "application/pdf")
    contract = await add(db, RecruiterContract(company_id=second.id, created_by_user_id=rec.id, contract_document_key=_DOC["key"],
                                               contract_document_content_type="application/pdf", contract_document_name="signed.pdf",
                                               contract_document_uploaded_at=now()))  # fmt: skip
    invoice = await add(db, RecruiterInvoice(job_id=job_id, invoice_number=tag("INV-"), invoice_date=now().date() - timedelta(days=1),
                                             due_date=now().date() + timedelta(days=30), amount=Decimal("150000.00"), created_by_user_id=rec.id))  # fmt: skip
    await db.commit()
    w.update({
        "activity_fu": str(fu.id), "activity_call": str(call.id), "activity_template": str(template.id), "activity_meeting": str(meeting.id),
        "activity_drive": str(drive.id), "activity_contract_company": str(second.id), "activity_contract": str(contract.id), "activity_invoice": str(invoice.id),
    })  # fmt: skip
