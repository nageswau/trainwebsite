"""rec-038 matrix rows: the profile group -- recruiter roles and reassignment (rec-001, rec-037), the managed lists and campaigns (rec-002),
the Skills Master (rec-006), the company master (rec-003), its contacts (rec-004) and its pipeline (rec-005).

Company rows use the core `company` (rec's, BDM `bdm`) or this group's companies in a known state; `rec_out`, `mgr_out` and `bdm_out` are
out of the company scope, so they read it as missing (404, rec-003 `load_scoped`, RBAC_MATRIX §2.47). In scope with the wrong role is 403
(rec-003 `require`: role first, then state)."""

from app.models import Company, RecCampaign, RecIndustry, RecLeadSource, Skill, SkillAlias, SkillCategory, SkillRelated
from tests.rec038_helpers import R, add, allow, now, tag

PATH_VALUES = {"profile_kind": "industries"}

MANAGERS = ("mgr", "mgr_out", "super")  # rec-001 `require_manager`: the catalogue and Skills Master writers (§2.43, §2.45)
READERS = ("rec", "rec_out", *MANAGERS)  # rec-002 / rec-006 `require_reader`: global lists, no row scope
CREATORS = READERS  # rec-003 `require_creator`: create a company, the BDM picker
SCOPED = ("rec", "rec_out", "mgr", "mgr_out", "super", "bdm", "bdm_out")  # rec-003 `caller_scope`: lists narrowed to the caller's scope
OUT = allow(404, "rec_out", "mgr_out", "bdm_out")  # rec-003 `load_scoped`: out of the company scope reads as missing (§2.47)
READ_ONE = {**allow(200, "rec", "mgr", "super", "bdm"), **OUT}  # in scope: the assigned recruiter, the team's manager, super_admin, the BDM
# rec-003 can_edit / can_archive (and rec-004 contacts, rec-005 move / lost): the assigned recruiter and super_admin; the in-scope manager
# and BDM are 403 (§2.47 "No edit, no archive", R10 read only)
EDIT = allow(403, "mgr", "bdm") | OUT
# rec-003 can_restore / can_reassign, rec-005 reopen: the team's manager and super_admin; the assigned recruiter and the BDM are 403
MANAGE = allow(403, "rec", "bdm") | OUT

ROWS = [
    # rec-001 recruiter roles (§2.42): own profile; the manager's team; the admin Recruiter Staff list and manager picker (super / it_admin)
    R("get", "/recruiter/me", **allow(200, "rec", "rec_out")),
    R("patch", "/recruiter/profile", {"phone": "+91 90000 00038"}, **allow(200, "rec", "rec_out")),
    R("get", "/recruiter/manager/team", **allow(200, *MANAGERS)),
    # rec-037 reassignment (§2.103): rec reports to mgr; mgr_out's direct-report check is a 403 (RC9, logged), not a 404
    R("post", "/recruiter/manager/reassign", lambda w: {"from_user_id": w["rec_id"], "to_user_id": w["rec2_id"]}, **allow(200, "mgr", "super"), mgr_out=403),
    R("get", "/admin/recruiters", **allow(200, "super", "it_admin")),
    R("get", "/admin/placement-managers", **allow(200, "super", "it_admin")),
    # rec-002 catalogues and campaigns (§2.43): recruiters read (active only), managers and super_admin write
    R("get", "/recruiter/catalogue/campaigns", **allow(200, *READERS)),
    R("post", "/recruiter/catalogue/campaigns", lambda w: {"name": tag("R38 Camp "), "lead_source_id": w["pf_lead_source"], "start_date": w["today"]}, **allow(201, *MANAGERS)),
    R("patch", "/recruiter/catalogue/campaigns/{pf_campaign}", lambda w: {"name": tag("R38 Camp ")}, **allow(200, *MANAGERS)),
    R("get", "/recruiter/catalogue/{profile_kind}", **allow(200, *READERS)),
    R("post", "/recruiter/catalogue/{profile_kind}", lambda w: {"name": tag("R38 Ind ")}, **allow(201, *MANAGERS)),
    R("patch", "/recruiter/catalogue/{profile_kind}/{pf_industry}", lambda w: {"name": tag("R38 Ind ")}, **allow(200, *MANAGERS)),
    # rec-006 Skills Master (§2.45): recruiters read active rows (no profile needed), managers and super_admin write
    R("get", "/recruiter/skill-categories", **allow(200, *READERS)),
    R("post", "/recruiter/skill-categories", lambda w: {"name": tag("R38 Cat ")}, **allow(201, *MANAGERS)),
    R("patch", "/recruiter/skill-categories/{pf_category}", lambda w: {"name": tag("R38 Cat ")}, **allow(200, *MANAGERS)),
    R("get", "/recruiter/skills", **allow(200, *READERS)),
    R("post", "/recruiter/skills", lambda w: {"name": tag("R38 Sk "), "category_id": w["pf_category"]}, **allow(201, *MANAGERS)),
    R("get", "/recruiter/skills/{pf_skill}", **allow(200, *READERS)),
    R("patch", "/recruiter/skills/{pf_skill}", lambda w: {"name": tag("R38 Sk ")}, **allow(200, *MANAGERS)),
    R("post", "/recruiter/skills/{pf_skill}/aliases", lambda w: {"alias": tag("R38 Al ")}, **allow(201, *MANAGERS)),
    R("delete", "/recruiter/skills/{pf_skill}/aliases/{pf_alias}", **allow(204, *MANAGERS)),
    R("post", "/recruiter/skills/{pf_merge_source}/merge", lambda w: {"into_skill_id": w["pf_skill"]}, **allow(200, *MANAGERS)),
    R("post", "/recruiter/skills/{pf_skill}/related", lambda w: {"skill_id": w["pf_unrelated"]}, **allow(201, *MANAGERS)),
    R("delete", "/recruiter/skills/{pf_skill}/related/{pf_related}", **allow(204, *MANAGERS)),
    # rec-003 company master (§2.47): scope first (404), then the action's role (403)
    R("get", "/recruiter/companies", **allow(200, *SCOPED)),
    R("post", "/recruiter/companies", lambda w: {"name": tag("R38 New Co ")}, **allow(201, *CREATORS)),
    R("get", "/recruiter/companies/bdm-options", **allow(200, *CREATORS)),
    R("get", "/recruiter/companies/{company}", **READ_ONE),
    R("patch", "/recruiter/companies/{company}", lambda w: {"city": tag("Pune ")}, **allow(200, "rec", "super"), **EDIT),
    R("post", "/recruiter/companies/{company}/archive", **allow(200, "rec", "super"), **EDIT),
    R("post", "/recruiter/companies/{pf_archived}/restore", **allow(200, "mgr", "super"), **MANAGE),
    R("post", "/recruiter/companies/{company}/assign", lambda w: {"recruiter_user_id": w["rec2_id"]}, **allow(200, "mgr", "super"), **MANAGE),
    # rec-005 company pipeline (§2.53): rec-003's can_edit moves and marks lost; the manager reopens; the board is the caller's scope
    R("post", "/recruiter/companies/{pf_company}/stage", {"from_stage": "new_lead", "to_stage": "contacted"}, **allow(200, "rec", "super"), **EDIT),
    R("post", "/recruiter/companies/{pf_company}/lost", {"reason": "Hiring freeze this year"}, **allow(200, "rec", "super"), **EDIT),
    R("post", "/recruiter/companies/{pf_lost}/reopen", {"reason": "Hiring again"}, **allow(200, "mgr", "super"), **MANAGE),
    R("get", "/recruiter/companies/{company}/stage-history", **READ_ONE),
    # rec-004 company contacts (§2.51): the company's scope and can_edit
    R("get", "/recruiter/companies/{company}/contacts", **READ_ONE),
    R("post", "/recruiter/companies/{company}/contacts", lambda w: {"name": tag("R38 Contact ")}, **allow(201, "rec", "super"), **EDIT),
    R("patch", "/recruiter/contacts/{contact}", lambda w: {"designation": tag("HR ")}, **allow(200, "rec", "super"), **EDIT),
    R("get", "/recruiter/pipeline", **allow(200, *SCOPED)),
]


async def build(client, db, w) -> None:
    """A lead source + campaign and an industry (rec-002); a category, skills, an alias and a related pair (rec-006); rec's companies in a
    known state -- active at New Lead, archived, Lost -- all with `bdm` as the BDM (rec-003 / rec-005)."""
    rec, bdm = w["users"]["rec"], w["users"]["bdm"]
    source = await add(db, RecLeadSource(name=tag("R38 Src "), active=True))
    campaign = await add(db, RecCampaign(name=tag("R38 Camp "), lead_source_id=source.id, start_date=now().date(), active=True))
    industry = await add(db, RecIndustry(name=tag("R38 Ind "), active=True))
    category = await add(db, SkillCategory(name=tag("R38 Cat "), active=True))
    skill, related, unrelated, merge_source = [await add(db, Skill(name=tag("R38 Sk "), category_id=category.id, active=True)) for _ in range(4)]
    alias = await add(db, SkillAlias(skill_id=skill.id, alias=tag("R38 Al ")))
    a, b = sorted((skill.id, related.id))
    await add(db, SkillRelated(skill_a_id=a, skill_b_id=b))

    def company(**fields) -> Company:
        return Company(name=tag("R38 Co "), assigned_recruiter_user_id=rec.id, assigned_bdm_user_id=bdm.id, created_by_user_id=rec.id, **fields)

    active, archived = await add(db, company()), await add(db, company(archived_at=now()))
    lost = await add(db, company(lost_at=now(), lost_reason="Budget cut"))
    await db.commit()
    w.update({
        "pf_lead_source": str(source.id), "pf_campaign": str(campaign.id), "pf_industry": str(industry.id), "pf_category": str(category.id),
        "pf_skill": str(skill.id), "pf_related": str(related.id), "pf_unrelated": str(unrelated.id), "pf_merge_source": str(merge_source.id),
        "pf_alias": str(alias.id), "pf_company": str(active.id), "pf_archived": str(archived.id), "pf_lost": str(lost.id),
    })  # fmt: skip
