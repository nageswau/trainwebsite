"""rec-038 matrix rows: the activity group -- follow-ups (rec-024), calls (rec-025), templates and messages (rec-026), the timeline (rec-027),
meetings (rec-028), campus drives (rec-029), contracts (rec-030), revenue and invoices (rec-031) and the dashboards (rec-032..035).

Company-scoped records follow rec-003 `caller_scope` (RBAC_MATRIX §2.47): the assigned recruiter, the manager's team, super_admin and the
company's assigned BDM read (R10); out of scope is 404. Writes need the company's `can_edit` -- the assigned recruiter or super_admin -- so a
manager and the assigned BDM are refused 403 after the scope check (§2.57/§2.59/§2.60/§2.82/§2.104)."""

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

from app.models import (
    BdmOrganization,
    BdmOrganizationContact,
    BdmOrgCourse,
    BdmOrgPlacementBatch,
    BdmOrgPlacementEvent,
    Company,
    CompanyContact,
    CompanyDocument,
    DriveRequirement,
    InstitutionDataPermission,
    InstitutionVacancyShare,
    RecruiterCadence,
    RecruiterCall,
    RecruiterContactCadence,
    RecruiterContract,
    RecruiterFollowUp,
    RecruiterInvoice,
    RecruiterMeeting,
    RecruiterMessage,
    RecruiterMessageTemplate,
    RecruiterPlanItem,
    RecruiterTargetCompany,
    RecruitmentDrive,
    VendorBill,
)
from app.services import bdm_organizations as orgs
from app.services import recruiter_contracts as contracts
from app.services.bdm_appointments import today_ist
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
VENDOR_COMM = ("rec", "mgr", "super")  # pob-012 W4: `commercials.vendor` holders (bdm 403 first) with the vendor in the company scope
VENDOR_COMM_OUT = ("rec_out", "mgr_out")  # a holder without the vendor in scope: 404
METRICS = ("mgr", "mgr_out", "super", "it_admin")  # rec-033 PF1 / rec-035 MG1 (it_admin reads: recruiters are IT staff)
COLLEGE_READERS = ("rec", "rec_out", "mgr", "mgr_out", "super", "bdm", "bdm_out")  # pob-013 P3 (both BDMs are of the college module)
COLLEGE_WRITERS = ("rec", "rec_out", "super", "bdm")  # pob-013 P4: `bdm` is the college's assigned BDM
PERMISSION_WRITERS = ("mgr", "mgr_out", "super")  # pob-014 S4
POS = ("rec", "rec_out")  # pob-009 T1: a PO's own targets, plan and reports
TEAM_LEADS = ("mgr", "super")  # pob-009 T1: `rec` reports to `mgr`; `mgr_out` names a PO outside their team (404)


def _po_targets(w) -> dict:
    return {"month": w["po_month"], "items": [{"recruiter_user_id": w["rec_id"], "kpi_key": "outreach", "target": 5}]}

PATH_VALUES = {"activity_kind": "contract", "po_period": "daily"}
_DOC: dict[str, str] = {}  # one stored PDF reused by every world's contract (only its key is per row)


def _soon(days: int = 1) -> str:
    return (now() + timedelta(days=days)).isoformat()


def _upload(_w):
    return {}, {"file": ("signed.pdf", PDF, "application/pdf")}


def _document(_w):
    return {"kind": "company_profile"}, {"file": ("profile.pdf", PDF, "application/pdf")}


def _meeting(_w) -> dict:
    return {"meeting_type": "contract_discussion", "starts_at": _soon(), "mode": "Online"}


def _drive(w) -> dict:
    return {"company_id": w["company"], "college_name": "ABC College", "requirement_ids": [w["requirement"]], "drive_date": w["tomorrow"],
            "job_role": "Graduate Engineer Trainee", "vacancies": 10}  # fmt: skip


def _invoice(w) -> dict:
    return {"requirement_id": w["requirement"], "invoice_number": tag("INV-"), "invoice_date": w["today"], "due_date": w["tomorrow"], "amount": "150000"}


def _vacancy_share(w) -> dict:
    """pob-015 V5: one share per college, requirement, day and channel -- each cell takes its own past day."""
    return {"requirement_id": w["requirement"], "channel": "email", "shared_on": str(now().date() - timedelta(days=1 + int(tag(), 16) % 3000))}


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
    # pob-023 (DEC-SCOPE-408 G6): every library reader adds (a recruiter's shared template is a draft); an approved one is the manager's
    R("post", "/recruiter/templates", lambda w: {"channel": "whatsapp", "kind": "follow_up", "name": tag("R38 T "), "body": "Hi {name}"}, **allow(201, *CREATORS)),
    R("patch", "/recruiter/templates/{activity_template}", {"body": "Hello {name}, {recruiter} here."}, **allow(200, *TEMPLATE_WRITERS)),
    R("get", "/recruiter/templates/{activity_template}/preview", **allow(200, *CREATORS)),
    R("get", "/recruiter/templates/{activity_template}/versions", **allow(200, *CREATORS)),
    # a shared draft / archived template nobody in the world wrote: invisible (404) to a recruiter, the manager's to approve / restore
    R("post", "/recruiter/templates/{activity_draft}/approve", **allow(200, *TEMPLATE_WRITERS), **allow(404, "rec", "rec_out")),
    R("post", "/recruiter/templates/{activity_template}/archive", **allow(200, *TEMPLATE_WRITERS)),
    R("post", "/recruiter/templates/{activity_archived}/restore", **allow(200, *TEMPLATE_WRITERS), **allow(404, "rec", "rec_out")),
    R("post", "/recruiter/messages/copies", lambda w: {"channel": "linkedin", "template_id": w["activity_linkedin"], "contact_id": w["contact"]},
      **allow(201, *EDITORS), **allow(404, *OUT[:2])),
    R("post", "/recruiter/messages", lambda w: {"channel": "whatsapp", "contact_id": w["contact"], "body": "Hi"}, **allow(201, *EDITORS), **allow(404, *OUT)),
    # §2.61 / RM6: render is a template read -- the template readers' role first (the BDMs 403), then the contact's company scope (404)
    R("get", "/recruiter/messages/render?template_id={activity_template}&contact_id={contact}", **allow(200, "rec", "mgr", "super"), **allow(404, "rec_out", "mgr_out")),
    R("get", "/recruiter/companies/{company}/messages", **allow(200, *IN_SCOPE), **allow(404, *OUT)),
    # pob-005 D7 (§2.304): a reply logged on a contact message -- the company's can_edit
    R("post", "/recruiter/messages/{activity_message}/reply", {}, **allow(200, *EDITORS), **allow(404, *OUT)),
    # pob-007 A1/A3: LinkedIn logging and a message outcome -- the company's can_edit, like a send and a reply
    R("post", "/recruiter/messages/linkedin", lambda w: {"contact_id": w["contact"], "action": "connection_request"}, **allow(201, *EDITORS), **allow(404, *OUT)),
    R("post", "/recruiter/messages/{activity_message}/outcome", {"outcome": "Asked for a call"}, **allow(200, *EDITORS), **allow(404, *OUT)),
    # pob-008 (§2.314): the cadence library -- read by the recruiter-CRM roles, written by the Team Lead and super_admin; a run starts and
    # stops on a contact message with the company's can_edit
    R("get", "/recruiter/cadences", **allow(200, *LISTERS)),
    R("post", "/recruiter/cadences", lambda w: {"name": tag("R38 Cad "), "steps": [{"day": 0, "channel": "email"}, {"day": 3, "channel": "call"}]},
      **allow(201, *TEMPLATE_WRITERS)),
    R("patch", "/recruiter/cadences/{activity_cadence}", lambda w: {"description": tag("R38 ")}, **allow(200, *TEMPLATE_WRITERS)),
    R("post", "/recruiter/messages/{activity_message}/cadence", lambda w: {"cadence_id": w["activity_cadence"]}, **allow(201, *EDITORS), **allow(404, *OUT)),
    R("post", "/recruiter/messages/{activity_run_message}/cadence/stop", **allow(200, *EDITORS), **allow(404, *OUT)),
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
    # pob-003 company documents (§2.299): read in the company scope, upload by `can_edit`
    R("get", "/recruiter/companies/{company}/documents", **allow(200, *IN_SCOPE), **allow(404, *OUT)),
    R("post", "/recruiter/companies/{company}/documents", form=_document, **allow(201, *EDITORS), **allow(404, *OUT)),
    R("get", "/recruiter/companies/documents/{activity_document}/download", **allow(200, *IN_SCOPE), **allow(404, *OUT)),
    # rec-031 revenue (§2.102): the role first (bdm 403), then the requirement's scope (404); the fee override is the manager's (RV10) --
    # `rec` reaches it in scope and gets 403, `rec_out` is out of scope first (404, as an unknown id)
    R("get", "/recruiter/companies/{company}/revenue", **allow(200, *REVENUE), **allow(404, *REVENUE_OUT)),
    R("get", "/recruiter/requirements/{requirement}/revenue", **allow(200, *REVENUE), **allow(404, *REVENUE_OUT)),
    R("put", "/recruiter/requirements/{requirement}/fee", {"fee_basis": "fixed", "fee_value": "60000"}, **allow(200, "mgr", "super"), **allow(404, *REVENUE_OUT)),
    R("get", "/recruiter/invoices", **allow(200, *REVENUE, *REVENUE_OUT)),
    R("post", "/recruiter/invoices", _invoice, **allow(201, *REVENUE), **allow(404, *REVENUE_OUT)),
    R("post", "/recruiter/invoices/{activity_invoice}/cancel", {"reason": "Raised in error"}, **allow(200, *REVENUE), **allow(404, *REVENUE_OUT)),
    R("post", "/recruiter/invoices/{activity_invoice}/payments", lambda w: {"received_on": w["today"], "amount": "1000"}, **allow(201, *REVENUE), **allow(404, *REVENUE_OUT)),
    # pob-012 vendor commercials (§2.324): the `commercials.vendor` grant first (bdm 403), then the vendor's company scope (404)
    R("get", "/recruiter/companies/{activity_vendor}/vendor-bills", **allow(200, *VENDOR_COMM), **allow(404, *VENDOR_COMM_OUT)),
    R("post", "/recruiter/companies/{activity_vendor}/vendor-bills", lambda w: {"kind": "payable", "bill_number": tag("VB-"), "bill_date": w["today"], "due_date": w["today"],
      "amount": "5000"}, **allow(201, *VENDOR_COMM), **allow(404, *VENDOR_COMM_OUT)),  # fmt: skip
    R("post", "/recruiter/vendor-bills/{activity_vendor_bill}/cancel", {"reason": "Raised in error"}, **allow(200, *VENDOR_COMM), **allow(404, *VENDOR_COMM_OUT)),
    R("post", "/recruiter/vendor-bills/{activity_vendor_bill}/payments", lambda w: {"paid_on": w["today"], "amount": "1000"}, **allow(201, *VENDOR_COMM), **allow(404, *VENDOR_COMM_OUT)),
    R("get", "/recruiter/vendors/performance", **allow(200, *VENDOR_COMM, *VENDOR_COMM_OUT)),
    R("get", "/recruiter/vendors/{activity_vendor}/performance", **allow(200, *VENDOR_COMM), **allow(404, *VENDOR_COMM_OUT)),
    # rec-032 dashboard (§2.106), narrowed to `rec`: another recruiter naming them 403; a manager's non-report 404
    R("get", "/recruiter/dashboard?recruiter={rec_id}", **allow(200, "rec", "mgr", "super"), rec_out=403, mgr_out=404),
    # rec-033 performance (§2.108, PF1) and its CSV, rec-034 per recruiter (§2.109, own row only; it_admin 403), rec-035 management (§2.110)
    R("get", "/recruiter/performance?recruiter={rec_id}", **allow(200, "mgr", "super", "it_admin"), mgr_out=404),
    R("get", "/recruiter/performance.csv", **allow(200, *METRICS)),
    R("get", "/recruiter/performance.xlsx", **allow(200, *METRICS)),  # nehn-004
    R("get", "/recruiter/performance/by-recruiter?recruiter={rec_id}", **allow(200, "rec", "mgr", "super"), rec_out=403, mgr_out=404),
    R("get", "/recruiter/management", **allow(200, *METRICS)),
    # pob-029 (§2.328, R1): the Team Lead and super_admin; out of scope reads as zero, never 403
    *(R("get", f"/recruiter/reports/placement-outcomes{ext}", **allow(200, "mgr", "mgr_out", "super")) for ext in ("", ".csv", ".xlsx")),
    # hrc-033 (§2.308): `reports.recruitment` opens them; a filter or figure outside the caller's scope reads as zero, never 403
    R("get", "/recruiter/recruitment-dashboards/{board}", **allow(200, "rec", "rec_out", "mgr", "mgr_out", "super", "it_admin", "hr_mgr", "officer")),
    R("get", "/recruiter/recruitment-dashboards/{board}.csv", **allow(200, "rec", "rec_out", "mgr", "mgr_out", "super", "it_admin", "hr_mgr", "officer")),
    R("get", "/recruiter/recruitment-dashboards/{board}.xlsx", **allow(200, "rec", "rec_out", "mgr", "mgr_out", "super", "it_admin", "hr_mgr", "officer")),
    R("get", "/recruiter/recruitment-dashboards/{board}/drill/{figure}", **allow(200, "rec", "rec_out", "mgr", "mgr_out", "super", "it_admin", "hr_mgr", "officer")),
    # pob-013 college placement profiles (§2.303, P3/P4): every recruiter and manager reads every college, the BDMs of the college module
    # read by bdm-002 scope; the placement team, super_admin and the assigned BDM write -- both managers and another BDM 403 after scope
    R("get", "/recruiter/colleges", **allow(200, *COLLEGE_READERS)),
    R("get", "/recruiter/colleges/{college}", **allow(200, *COLLEGE_READERS)),
    R("put", "/recruiter/colleges/{college}/profile", lambda w: {"drive_process": f"Test then HR {tag()}"}, **allow(200, *COLLEGE_WRITERS)),
    R("post", "/recruiter/colleges/{college}/courses", lambda w: {"course": f"B.Tech {tag()}"}, **allow(201, *COLLEGE_WRITERS)),
    R("delete", "/recruiter/colleges/{college}/courses/{college_course}", **allow(200, *COLLEGE_WRITERS)),
    R("post", "/recruiter/colleges/{college}/batches", {"pass_out_year": 2027}, **allow(201, *COLLEGE_WRITERS)),
    R("delete", "/recruiter/colleges/{college}/batches/{college_batch}", **allow(200, *COLLEGE_WRITERS)),
    R("post", "/recruiter/colleges/{college}/calendar", lambda w: {"title": "PPT", "kind": "pre_placement_talk", "starts_on": w["tomorrow"]}, **allow(201, *COLLEGE_WRITERS)),
    R("delete", "/recruiter/colleges/{college}/calendar/{college_event}", **allow(200, *COLLEGE_WRITERS)),
    R("post", "/recruiter/colleges/{college}/interactions", lambda w: {"channel": "meeting", "occurred_at": now().isoformat(), "summary": "Met the TPO"}, **allow(201, *COLLEGE_WRITERS)),
    R("patch", "/recruiter/colleges/{college}/contacts/{college_contact}", lambda w: {"office_details": f"Block {tag()}"}, **allow(200, *COLLEGE_WRITERS)),
    # pob-014 institution student pool (§2.316, S3/S4/S10): every college reader opens the pool (it lists only what they may see); only a
    # placement manager or super_admin writes a data permission -- the placement team and the college's BDM 403 after scope
    R("get", "/recruiter/colleges/{college}/student-pool", **allow(200, *COLLEGE_READERS)),
    R("post", "/recruiter/colleges/{college}/data-permissions", lambda w: {"agreement_reference": f"MoU {tag()}", "purposes": ["placement"], "valid_from": w["tomorrow"],
                                                                         "expires_on": w["tomorrow"], "user_ids": [w["rec_id"]]}, **allow(201, *PERMISSION_WRITERS)),  # fmt: skip
    R("patch", "/recruiter/colleges/{college}/data-permissions/{college_permission}", {"notes": "Renewed"}, **allow(200, *PERMISSION_WRITERS)),
    R("post", "/recruiter/colleges/{college}/data-permissions/{college_permission}/revoke", {}, **allow(200, *PERMISSION_WRITERS)),
    # pob-015 vacancy sharing and the campus calendar (§2.317, V2/V12): every college reader reads; the college's writers share a requirement
    # of their own scope (rec_out: not theirs, 404) and record the answer; both managers and another BDM 403 after scope
    R("get", "/recruiter/colleges/{college}/vacancies", **allow(200, *COLLEGE_READERS)),
    R("get", "/recruiter/colleges/{college}/vacancy-options", **allow(200, *COLLEGE_WRITERS)),
    R("post", "/recruiter/colleges/{college}/vacancy-shares", _vacancy_share, **allow(201, "rec", "super", "bdm"), rec_out=404),
    R("patch", "/recruiter/colleges/{college}/vacancy-shares/{college_share}", {"response": "interested"}, **allow(200, *COLLEGE_WRITERS)),
    R("get", "/recruiter/campus-calendar", **allow(200, *COLLEGE_READERS)),
    R("get", "/recruiter/campus-calendar.ics", **allow(200, *COLLEGE_READERS)),
    R("get", "/recruiter/campus-summary", **allow(200, *COLLEGE_READERS)),
    # pob-009 (§2.315, T1): targets, territory, target companies, the daily plan and activity reports -- a PO's own; the Team Lead's direct reports
    R("get", "/recruiter/targets", **allow(200, *POS)),
    R("get", "/recruiter/manager/targets", **allow(200, "mgr", "mgr_out", "super")),
    R("get", "/recruiter/manager/targets/{rec_id}", **allow(200, *TEAM_LEADS), mgr_out=404),
    R("put", "/recruiter/manager/targets", _po_targets, **allow(200, *TEAM_LEADS), mgr_out=404),
    R("put", "/recruiter/manager/team/{rec_id}/territory", {"territory": "North"}, **allow(200, *TEAM_LEADS), mgr_out=404),
    R("post", "/recruiter/manager/target-companies", lambda w: {"recruiter_user_id": w["rec_id"], "month": w["po_month"], "company_ids": [w["company"]]},
      **allow(201, *TEAM_LEADS), mgr_out=404),
    R("delete", "/recruiter/manager/target-companies/{po_target_company}", **allow(204, *TEAM_LEADS), mgr_out=404),
    R("get", "/recruiter/daily-plan", **allow(200, *POS)),
    R("post", "/recruiter/daily-plan/items", lambda w: {"follow_up_id": w["activity_fu"]}, rec=201, rec_out=404),
    R("patch", "/recruiter/daily-plan/items/{po_plan_item}", {"done": True}, rec=200, rec_out=404),
    R("delete", "/recruiter/daily-plan/items/{po_plan_item}", rec=204, rec_out=404),
    R("get", "/recruiter/activity-reports/{po_period}/{po_today}", **allow(200, *POS)),
    R("post", "/recruiter/activity-reports/{po_period}/{po_today}/submit", {}, **allow(201, *POS)),
    R("get", "/recruiter/activity-contacts?period=daily&start={po_today}&recruiter_id={rec_id}", **allow(200, "rec", *TEAM_LEADS), rec_out=403, mgr_out=404),
    R("get", "/recruiter/manager/activity-reports?period=daily&start={po_today}", **allow(200, "mgr", "mgr_out", "super")),
    R("get", "/recruiter/manager/activity-reports/{rec_id}/{po_period}/{po_today}", **allow(200, *TEAM_LEADS), mgr_out=404),
]


async def _college(db, bdm) -> dict:
    """pob-013: a college organization of `bdm` (the college module) with a TPO contact, a course without batches, a batch and an event."""
    name, city = f"R38 College {tag()}", "Pune"
    keys = orgs.org_keys(name, city)
    org = await add(db, BdmOrganization(code=await orgs.next_code(db), org_type="college", bdm_type="college", name=name, name_key=keys[0], city=city,
                                        city_key=keys[1], assigned_bdm_user_id=bdm.id, created_by_user_id=bdm.id))  # fmt: skip
    contact = await add(db, BdmOrganizationContact(organization_id=org.id, name="Ms Iyer", role="placement_officer", is_primary=True))
    course = await add(db, BdmOrgCourse(organization_id=org.id, course="MBA", course_key=f"|mba{tag()}"))
    batch = await add(db, BdmOrgPlacementBatch(organization_id=org.id, pass_out_year=2027, created_by_user_id=bdm.id))
    event = await add(db, BdmOrgPlacementEvent(organization_id=org.id, title="Drive", kind="campus_drive", starts_on=now().date(), created_by_user_id=bdm.id))
    permission = await add(db, InstitutionDataPermission(organization_id=org.id, agreement_reference="MoU R38", purposes=["placement"], valid_from=now().date(),
                                                         expires_on=now().date() + timedelta(days=90), created_by_user_id=bdm.id))  # fmt: skip
    return {"college": str(org.id), "college_contact": str(contact.id), "college_course": str(course.id), "college_batch": str(batch.id),
            "college_event": str(event.id), "college_permission": str(permission.id)}  # fmt: skip


async def build(client, db, w) -> None:
    """A follow-up, a call (rec's, today), a template, a started meeting and a drive on `company`; a second company of rec's (same BDM) with a
    draft contract carrying a contract document; an unpaid invoice on `requirement`."""
    users, company_id, contact_id, job_id = w["users"], UUID(w["company"]), UUID(w["contact"]), UUID(w["requirement"])
    rec = users["rec"]
    fu = await add(db, RecruiterFollowUp(company_id=company_id, due_at=now() + timedelta(days=1), reason="offer_status", created_by_user_id=rec.id))
    call = await add(db, RecruiterCall(company_id=company_id, contact_id=contact_id, caller_user_id=rec.id, occurred_at=now(), direction="outgoing",
                                       outcome="connected"))  # fmt: skip
    message = await add(db, RecruiterMessage(company_id=company_id, contact_id=contact_id, sender_user_id=rec.id, channel="whatsapp", body="Hi", sent_at=now()))
    template = await add(db, RecruiterMessageTemplate(channel="whatsapp", kind="follow_up", name=tag("R38 T "), body="Hi {name}, {recruiter} here.", active=True))
    # pob-023: a shared draft, an archived template and an approved LinkedIn one
    draft = await add(db, RecruiterMessageTemplate(channel="whatsapp", kind="follow_up", category="whatsapp", name=tag("R38 D "), body="Hi", status="draft"))
    archived = await add(db, RecruiterMessageTemplate(channel="whatsapp", kind="follow_up", category="whatsapp", name=tag("R38 A "), body="Hi", status="archived"))
    linkedin = await add(db, RecruiterMessageTemplate(channel="linkedin", kind=None, category="linkedin", name=tag("R38 L "), body="Hi {name}"))
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
    document = await add(db, CompanyDocument(company_id=company_id, kind="company_profile", name="profile.pdf", content_type="application/pdf",
                                             size_bytes=len(PDF), storage_key=_DOC["key"], uploaded_by_user_id=rec.id))  # fmt: skip
    invoice = await add(db, RecruiterInvoice(job_id=job_id, invoice_number=tag("INV-"), invoice_date=now().date() - timedelta(days=1),
                                             due_date=now().date() + timedelta(days=30), amount=Decimal("150000.00"), created_by_user_id=rec.id))  # fmt: skip
    vendor = await add(db, Company(name=f"R38 Vendor {tag()}", partner_type="vendor", vendor_status="active", assigned_recruiter_user_id=rec.id,
                                   assigned_bdm_user_id=users["bdm"].id, created_by_user_id=rec.id))  # fmt: skip  # pob-012
    vendor_bill = await add(db, VendorBill(company_id=vendor.id, kind="payable", bill_number=tag("VB-"), bill_date=now().date() - timedelta(days=1),
                                           due_date=now().date() + timedelta(days=30), amount=Decimal("50000.00"), created_by_user_id=rec.id))  # fmt: skip
    w.update({"activity_vendor": str(vendor.id), "activity_vendor_bill": str(vendor_bill.id)})
    college = await _college(db, users["bdm"])
    share = await add(db, InstitutionVacancyShare(organization_id=UUID(college["college"]), job_id=job_id, shared_on=now().date(), channel="visit",
                                                  shared_by_user_id=rec.id))  # fmt: skip  # pob-015
    college["college_share"] = str(share.id)
    po_today = today_ist(now())  # pob-009: a target company and a plan item of rec's for today (IST)
    target = await add(db, RecruiterTargetCompany(recruiter_user_id=rec.id, company_id=company_id, month=po_today.replace(day=1), added_by_user_id=users["mgr"].id))
    plan_item = await add(db, RecruiterPlanItem(recruiter_user_id=rec.id, plan_date=po_today, company_id=company_id))
    # pob-008: a cadence, and a second contact whose message runs it (the first contact's message stays free to start one)
    steps = [{"day": 0, "channel": "email", "template_id": None}, {"day": 3, "channel": "call", "template_id": None}]
    cadence = await add(db, RecruiterCadence(name=tag("R38 Cadence "), steps=steps))
    other = await add(db, CompanyContact(company_id=company_id, name="R38 Second"))
    run_message = await add(db, RecruiterMessage(company_id=company_id, contact_id=other.id, sender_user_id=rec.id, channel="whatsapp", body="Hi", sent_at=now()))
    await add(db, RecruiterContactCadence(cadence_id=cadence.id, contact_id=other.id, company_id=company_id, message_id=run_message.id, name=cadence.name,
                                          steps=steps, started_at=now(), started_by_user_id=rec.id, next_step_at=now() + timedelta(days=3)))  # fmt: skip
    w.update({"activity_cadence": str(cadence.id), "activity_run_message": str(run_message.id)})
    await db.commit()
    w.update({
        **college,
        "activity_fu": str(fu.id), "activity_call": str(call.id), "activity_template": str(template.id), "activity_draft": str(draft.id), "activity_archived": str(archived.id), "activity_linkedin": str(linkedin.id), "activity_meeting": str(meeting.id),
        "activity_drive": str(drive.id), "activity_contract_company": str(second.id), "activity_contract": str(contract.id), "activity_invoice": str(invoice.id),
        "activity_document": str(document.id), "activity_message": str(message.id),
        "po_today": po_today.isoformat(), "po_month": po_today.strftime("%Y-%m"), "po_target_company": str(target.id), "po_plan_item": str(plan_item.id),
    })  # fmt: skip
