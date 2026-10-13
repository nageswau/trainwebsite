"""mgmt-025 (EVID-017 §21, spec RC1-RC12): the company-wide Recruitment dashboard -- the eleven Recruiter KPIs and the company pipeline
Lead → Meeting → Requirement → Candidate → Interview → Selection → Joining.

A read-through of the Recruiter CRM's own counts: rec-035's `recruiter_metrics.management` totals as an administrator reads them (AC: the
totals equal rec-035's), rec-033 P4 for the placement rate, rec-034 B4 for new companies and the rec-005 stages for the pipeline. Revenue is
mgmt-008's ledger total and only the finance tier gets it. Reads only; counts and one money total."""

from datetime import date, datetime, time, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Company, Job, User
from app.services import management_metrics, management_recruitment_revenue, recruiter_metrics
from app.services.bdm_appointments import IST
from app.services.management_access import OPERATIONAL_ROLES, can_view_finance

ROLES = tuple(OPERATIONAL_ROLES)  # RC2: rec-033/035 read for the Command Center's operational tier
# RC9: the §21 steps over the rec-005 stages. Requirement Closed is listed apart; Lost is a flag, not a stage.
PIPELINE = (
    ("lead", "Lead", ("new_lead", "contacted", "interested")),
    ("meeting", "Meeting", ("meeting_scheduled", "requirement_discussion")),
    ("requirement", "Requirement", ("requirement_received", "jd_received")),
    ("candidate", "Candidate", ("candidates_sourcing", "profiles_shared")),
    ("interview", "Interview", ("interview",)),
    ("selection", "Selection", ("selected",)),
    ("joining", "Joining", ("joined",)),
)


async def _counts(db: AsyncSession, start: datetime, end: datetime) -> dict:
    """RC4-RC6 and RC9 in one statement: Recruiters, new companies, openings by type, and live companies per stage plus the lost ones."""
    crossed = recruiter_metrics.first_past_interested()
    open_job = Job.status.not_in(recruiter_metrics.PARKED_REQUIREMENTS)
    internship = Job.employment_type == "internship"
    live = [Company.archived_at.is_(None), Company.lost_at.is_(None)]

    def count(*where):
        return select(func.count()).where(*where).scalar_subquery()

    figures = {
        "recruiters": management_metrics.recruiters(),
        "new_companies": select(func.count()).select_from(crossed).where(crossed.c.at >= start, crossed.c.at < end).scalar_subquery(),
        "job_openings": count(open_job, or_(Job.employment_type.is_(None), ~internship)),  # an unset type is a job opening
        "internship_openings": count(open_job, internship),
        "requirement_closed": count(*live, Company.stage == "requirement_closed"),
        "lost": count(Company.archived_at.is_(None), Company.lost_at.is_not(None)),
        **{key: count(*live, Company.stage.in_(stages)) for key, _, stages in PIPELINE},
    }
    row = (await db.execute(select(*(value.label(key) for key, value in figures.items())))).one()
    return row._asdict()


async def dashboard(db: AsyncSession, user: User, date_from: date | None, date_to: date | None, now: datetime) -> dict:
    """RC1-RC12 over the IST days of the period (rec-033's range rules, applied by `recruiter_metrics.management`)."""
    business = await recruiter_metrics.management(db, user, date_from, date_to, now, roles=ROLES)
    first, last, totals = business["date_from"], business["date_to"], business["totals"]
    start, end = datetime.combine(first, time.min, tzinfo=IST), datetime.combine(last + timedelta(days=1), time.min, tzinfo=IST)
    sourced = (await recruiter_metrics.performance(db, user, None, first, last, now, roles=ROLES))["totals"]["candidates_sourced"]
    counts = await _counts(db, start, end)
    revenue = None
    if can_view_finance(user):  # RC8: never queried for the super admin
        revenue = (await management_recruitment_revenue.revenue_by_kind(db, first, last + timedelta(days=1)))["total"]
    joining = totals["joined"]
    return {
        "date_from": first,
        "date_to": last,
        "revenue_visible": revenue is not None,
        "kpis": {
            "recruiters": counts["recruiters"],
            "employer_partners": totals["companies"],
            "new_companies": counts["new_companies"],
            "job_openings": counts["job_openings"],
            "internship_openings": counts["internship_openings"],
            "candidates": totals["candidates_in_pipeline"],
            "interviews": totals["interviews"],
            "selections": totals["selected"],
            "joining": joining,
            "placement_rate": round(joining * 100 / sourced, 1) if sourced else None,  # RC7
            "revenue": revenue,
        },
        "pipeline": [{"key": key, "label": label, "value": counts[key]} for key, label, _ in PIPELINE],
        "requirement_closed": counts["requirement_closed"],
        "lost": counts["lost"],
    }
