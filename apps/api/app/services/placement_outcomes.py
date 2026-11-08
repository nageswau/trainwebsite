"""pob-029 (DEC-SCOPE-437 R1-R12; design docs/superpowers/specs/2026-11-08-pob-029-placement-outcome-reports-design.md): placement outcome
reports -- the period's placements grouped by company, vendor, role, source, recruiter or PO; the requirement → submission → interview →
offer conversions; offer acceptance, joining rate and time to fill; revenue; replacements, early dropouts and satisfaction.

R3: the cohort is the placements whose offer was accepted (the pob-024 record was created) in the period. The totals, every group row and
the drill-down are computed from the same rows in one statement, so each figure ties out to the placements behind it (AC). R6: the
conversions count the period's own events in the same requirement scope. Readers are the Team Lead (their team + Unassigned, the rec-007
`caller_scope`) and super_admin (R1); the money figures need the rec-031/pob-001 revenue gate (R8). Reads only, except the export's audit."""

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import (
    Candidate,
    Company,
    Interview,
    Job,
    JobApplication,
    JobOffer,
    Placement,
    PlacementSurvey,
    ProfileShare,
    ProfileShareItem,
    RecCandidateSource,
    RecruiterInvoice,
    RecruiterPayment,
    User,
)
from app.services import placements
from app.services import recruiter_requirements as requirements
from app.services.bdm_appointments import IST, today_ist
from app.services.recruiter import MANAGER_ROLE
from app.services.recruiter_revenue import ZERO, money
from app.services.telecaller_performance import date_range

READERS = (MANAGER_ROLE, "super_admin")  # R1: the Team Lead and management
REFUSED = "Placement outcome reports are for Team Leads and administrators"
# R4: the breakdowns; a missing vendor is a direct requirement, a missing person or source is said as such
GROUPS = {
    "company": ("Company", None),
    "vendor": ("Vendor", "Direct"),
    "role": ("Role", None),
    "source": ("Source", "No source"),
    "recruiter": ("Recruiter", "Unassigned"),
    "po": ("Placement officer", "Unassigned"),
}
COUNTS = ("placements", "joined", "pending", "did_not_join", "dropouts", "early_dropouts", "replacements_owed", "replacements_filled")
MONEY = ("fee_generated", "invoiced", "collected", "outstanding")
COLUMNS = [  # the screen's and the export's columns, after the group's own
    ("placements", "Placements"), ("joined", "Joined"), ("pending", "Joining pending"), ("did_not_join", "Did not join"),
    ("joining_rate", "Joining rate %"), ("time_to_fill_days", "Time to fill (days)"), ("dropouts", "Dropouts"),
    ("early_dropouts", "Early dropouts"), ("replacements_owed", "Replacements owed"), ("replacements_filled", "Replacements filled"),
    ("client_rating", "Client rating"), ("candidate_rating", "Candidate rating"),
    ("fee_generated", "Fee generated"), ("invoiced", "Invoiced"), ("collected", "Collected"), ("outstanding", "Outstanding"),
]
DRILL_LIMIT = 100  # R12: the drill-down shows the newest rows; the totals always count all of them
CANCELLED_INTERVIEW = "cancelled"


def _rate(top: int, bottom: int) -> float | None:
    return round(top * 100 / bottom, 1) if bottom else None


def _mean(values: list) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _period(date_from: date | None, date_to: date | None) -> tuple[date, date, datetime, datetime]:
    """R2: rec-033's range rules (the 1st of the month → today by default, never in the future, at most 366 days) over IST days."""
    first, last = date_range(date_from, date_to, today_ist(datetime.now(IST)))
    return first, last, datetime.combine(first, time.min, tzinfo=IST), datetime.combine(last + timedelta(days=1), time.min, tzinfo=IST)


async def _cohort(db: AsyncSession, scope: list, start: datetime, end: datetime, filters: dict) -> list:
    vendor, recruiter, po = aliased(Company), aliased(User), aliased(User)
    source_id = func.coalesce(JobApplication.submitted_source_id, Candidate.source_id)

    def rating(respondent: str):
        return select(PlacementSurvey.rating).where(PlacementSurvey.placement_id == Placement.id, PlacementSurvey.respondent == respondent).scalar_subquery()

    paid = select(func.sum(RecruiterPayment.amount)).where(RecruiterPayment.invoice_id == RecruiterInvoice.id).scalar_subquery()
    where = [Placement.job_id.in_(select(Job.id).where(*scope)), Placement.created_at >= start, Placement.created_at < end]
    for key, column in (("company", Placement.company_id), ("vendor", Placement.vendor_company_id), ("recruiter", Placement.recruiter_user_id),
                        ("po", Placement.po_owner_user_id), ("source", source_id)):  # fmt: skip
        if filters.get(key):
            where.append(column == filters[key])
    stmt = (
        select(
            Placement, JobOffer.joining_status, JobOffer.actual_joining_date, Job.created_at.label("opened_at"), Job.requirement_code, Job.title,
            Company.name.label("company_name"), vendor.name.label("vendor_name"), recruiter.full_name.label("recruiter_name"),
            po.full_name.label("po_name"), source_id.label("source_id"), RecCandidateSource.name.label("source_name"),
            Candidate.candidate_code, Candidate.name.label("candidate_name"), RecruiterInvoice.amount.label("invoiced"), paid.label("collected"),
            rating("client").label("client_rating"), rating("candidate").label("candidate_rating"),
        )  # fmt: skip
        .join(JobOffer, JobOffer.id == Placement.offer_id)
        .join(Job, Job.id == Placement.job_id)
        .join(Company, Company.id == Placement.company_id)
        .join(JobApplication, JobApplication.id == Placement.application_id)
        .join(Candidate, Candidate.id == Placement.candidate_id)
        .outerjoin(vendor, vendor.id == Placement.vendor_company_id)
        .outerjoin(recruiter, recruiter.id == Placement.recruiter_user_id)
        .outerjoin(po, po.id == Placement.po_owner_user_id)
        .outerjoin(RecCandidateSource, RecCandidateSource.id == source_id)
        .outerjoin(RecruiterInvoice, and_(RecruiterInvoice.id == Placement.invoice_id, RecruiterInvoice.cancelled_at.is_(None)))
        .where(*where)
        .order_by(Placement.created_at.desc(), Placement.id)
    )
    return (await db.execute(stmt)).all()


def _status(row) -> str:
    return row.joining_status or "pending"


def _figures(rows: list, revenue: bool) -> dict:
    """R5/R7-R10 for any set of cohort rows -- so the Total is the sum of the group rows and of the drill-down."""
    counts = dict.fromkeys(COUNTS, 0)
    fill_days, client, candidate = [], [], []
    sums = dict.fromkeys(MONEY, ZERO)
    for row in rows:
        p, status = row.Placement, _status(row)
        counts["placements"] += 1
        counts[status] += 1
        if status == "joined" and row.actual_joining_date:
            # R7: requirement opened → joined; a legacy joining dated before the requirement was recorded counts as 0 (QA-03)
            fill_days.append(max(0, (row.actual_joining_date - row.opened_at.astimezone(IST).date()).days))
            sums["fee_generated"] += money(p.expected_fee)
        if p.dropout_on is not None:
            counts["dropouts"] += 1
            if placements.owes_replacement(p):  # R9: inside the guarantee (pob-025 G5)
                counts["early_dropouts"] += 1
                counts["replacements_filled" if p.replaced_by_placement_id else "replacements_owed"] += 1
        if row.client_rating is not None:
            client.append(row.client_rating)
        if row.candidate_rating is not None:
            candidate.append(row.candidate_rating)
        sums["invoiced"] += money(row.invoiced)
        sums["collected"] += money(row.collected)
    sums["outstanding"] = sums["invoiced"] - sums["collected"]
    return {
        **counts,
        "joining_rate": _rate(counts["joined"], counts["joined"] + counts["did_not_join"]),  # R7: of the decided joinings
        "time_to_fill_days": _mean(fill_days),
        "client_rating": _mean(client), "client_responses": len(client),
        "candidate_rating": _mean(candidate), "candidate_responses": len(candidate),
        **{key: str(value) if revenue else None for key, value in sums.items()},
    }  # fmt: skip


def _group_key(row, group: str) -> tuple:
    p = row.Placement
    return {
        "company": (p.company_id, row.company_name),
        "vendor": (p.vendor_company_id, row.vendor_name),
        "role": (p.role.casefold(), p.role),
        "source": (row.source_id, row.source_name),
        "recruiter": (p.recruiter_user_id, row.recruiter_name),
        "po": (p.po_owner_user_id, row.po_name),
    }[group]


async def _funnel(db: AsyncSession, scope: list, first: date, last: date, start: datetime, end: datetime, filters: dict) -> dict:
    """R6: the period's requirements opened, candidates first submitted, candidates interviewed, offers made and their decisions -- one
    statement, in the requirement scope narrowed by the company and vendor filters (the other filters belong to a placement)."""
    jobs = select(Job.id).where(*scope)
    if filters.get("company"):
        jobs = jobs.where(Job.company_id == filters["company"])
    if filters.get("vendor"):
        jobs = jobs.where(Job.via_vendor_id == filters["vendor"])
    in_jobs = JobApplication.job_id.in_(jobs)
    first_shared = (
        select(ProfileShareItem.application_id, func.min(ProfileShare.created_at).label("at"))
        .join(ProfileShare, ProfileShare.id == ProfileShareItem.share_id)
        .join(JobApplication, JobApplication.id == ProfileShareItem.application_id)
        .where(in_jobs)
        .group_by(ProfileShareItem.application_id)
        .subquery()
    )
    offered = and_(JobOffer.offered_on >= first, JobOffer.offered_on <= last)
    offers = select(JobOffer.status).join(JobApplication, JobApplication.id == JobOffer.application_id).where(in_jobs, offered).subquery()
    figures = {
        "requirements": select(func.count()).where(Job.id.in_(jobs), Job.created_at >= start, Job.created_at < end),
        "submissions": select(func.count()).select_from(first_shared).where(first_shared.c.at >= start, first_shared.c.at < end),
        "interviews": select(func.count(distinct(Interview.application_id))).join(JobApplication, JobApplication.id == Interview.application_id)
        .where(in_jobs, Interview.scheduled_at >= start, Interview.scheduled_at < end, Interview.status != CANCELLED_INTERVIEW),
        "offers": select(func.count()).select_from(offers),
        "offers_accepted": select(func.count()).select_from(offers).where(offers.c.status == "accepted"),
        "offers_declined": select(func.count()).select_from(offers).where(offers.c.status == "declined"),
    }  # fmt: skip
    row = (await db.execute(select(*(stmt.scalar_subquery().label(key) for key, stmt in figures.items())))).one()
    f = {key: getattr(row, key) or 0 for key in figures}
    return {
        **f,
        "requirement_to_submission": _rate(f["submissions"], f["requirements"]),
        "submission_to_interview": _rate(f["interviews"], f["submissions"]),
        "interview_to_offer": _rate(f["offers"], f["interviews"]),
        "offer_acceptance": _rate(f["offers_accepted"], f["offers_accepted"] + f["offers_declined"]),  # R7: of the decided offers
    }


def _drill(row, revenue: bool) -> dict:
    p, status = row.Placement, _status(row)
    return {
        "id": p.id,
        "status": status,
        "status_label": placements.STATUS_LABELS.get(status, status),
        "candidate": {"id": p.candidate_id, "code": row.candidate_code, "name": row.candidate_name},
        "requirement": {"id": p.job_id, "code": row.requirement_code, "title": row.title},
        "company": {"id": p.company_id, "name": row.company_name},
        "vendor": {"id": p.vendor_company_id, "name": row.vendor_name} if p.vendor_company_id else None,
        "role": p.role,
        "recruiter": row.recruiter_name,
        "po_owner": row.po_name,
        "source": row.source_name,
        "accepted_at": p.created_at,
        "joined_on": row.actual_joining_date if status == "joined" else None,
        "dropout_on": p.dropout_on,
        "early_dropout": placements.owes_replacement(p),
        "client_rating": row.client_rating,
        "candidate_rating": row.candidate_rating,
        "fee": str(money(p.expected_fee)) if revenue and p.expected_fee is not None else None,
    }


async def report(db: AsyncSession, user: User, date_from: date | None, date_to: date | None, group: str, filters: dict) -> dict:
    if user.role not in READERS:
        raise HTTPException(403, REFUSED)
    first, last, start, end = _period(date_from, date_to)
    scope = await requirements.caller_scope(db, user)
    revenue = await placements.commercial(db, user)
    rows = await _cohort(db, scope, start, end, filters)
    groups: dict[tuple, list] = defaultdict(list)
    for row in rows:
        groups[_group_key(row, group)].append(row)
    label, missing = GROUPS[group]
    items = [
        {"key": str(key) if key is not None else None, "label": name or missing or "—", "figures": _figures(members, revenue)}
        for (key, name), members in groups.items()
    ]
    items.sort(key=lambda item: (-item["figures"]["placements"], item["label"].casefold()))
    columns = [{"key": key, "label": text} for key, text in COLUMNS if revenue or key not in MONEY]
    return {
        "date_from": first,
        "date_to": last,
        "group_by": group,
        "group_label": label,
        "filters": {key: value for key, value in filters.items() if value},
        "revenue_visible": revenue,
        "columns": columns,
        "totals": _figures(rows, revenue),
        "items": items,
        "funnel": await _funnel(db, scope, first, last, start, end, filters),
        "placements": [_drill(row, revenue) for row in rows[:DRILL_LIMIT]],
        "placements_total": len(rows),
    }


def export_payload(data: dict) -> dict:
    """R11: the group table as the screen shows it, the Total last (agent_reports.to_csv/to_xlsx guard every text cell)."""
    columns = [{"key": "label", "label": data["group_label"]}, *data["columns"]]

    def flat(label: str, figures: dict) -> dict:
        return {"label": label, **{c["key"]: _cell(figures[c["key"]]) for c in data["columns"]}}

    return {
        "columns": columns,
        "items": [flat(item["label"], item["figures"]) for item in data["items"]],
        "totals": flat("Total", data["totals"]),
    }


def _cell(value) -> str | int | None:
    return value if value is None or isinstance(value, int) else str(value)

