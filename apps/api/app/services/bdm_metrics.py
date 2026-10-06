"""bdm-021 (DEC-SCOPE-086, spec §2-§4): a College organization's student funnel and revenue, computed live from attributed records (D5b).

Read-only; nothing here writes. `S` is the set of students linked to the organization's leads (bdm-017's explicit conversion link;
L9 makes it one lead per student, so a student counts for one organization only). Each stage counts distinct students by its own
definition (B6). Only aggregates leave this module (AC3).
"""

from decimal import Decimal

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.payments import PAID_STATUSES
from app.models import BdmOrganization, Certificate, Enquiry, Enrollment, JobApplication, JobOffer, Payment, User
from app.services.agent_deposits import REFERENCE_TYPE as AGENT_DEPOSIT

CURRENCY = "INR"
ACCEPTED_OFFER = ("accepted", "joined")  # workflows.update_job_offer marks the application hired on these

# (key, label, definition) -- the written definitions of spec §3, sent with every response so the panel shows the same words.
STAGES = (
    ("contacted", "Contacted", "Leads entered by BDMs for this organization (students contacted = leads entered)."),
    ("leads", "Leads", "Student enquiries attributed to this organization."),
    ("registrations", "Registrations", "Students whose account is linked to one of these leads."),
    ("training", "Training", "Registered students with at least one enrollment that is not withdrawn."),
    ("certification", "Certification", "Registered students with at least one issued certificate."),
    ("internship", "Internship", "Internships are not recorded in EduSphere."),
    ("placement", "Placement", "Registered students with an accepted or joined job offer."),
)
REVENUE_LINES = (
    ("training", "Training fees", "Paid INR payments of the registered students; pending, failed and refunded payments are excluded."),
    ("internship", "Internship", "No internship revenue is recorded in EduSphere."),
    ("placement", "Placement", "No placement revenue is recorded in EduSphere."),
    ("other", "Other", "No other revenue is recorded in EduSphere."),
)


def show_revenue(user: User, org: BdmOrganization) -> bool:
    """B3: the assigned BDM, a manager (load_scoped already limited them to their team) and super_admin."""
    return user.role in ("bdm_manager", "super_admin") or org.assigned_bdm_user_id == user.id


async def college_business(db: AsyncSession, org: BdmOrganization, with_revenue: bool) -> dict:
    """One SELECT of scalar subqueries over `S` -- a constant query count whatever the organization's size."""
    students = select(Enquiry.converted_user_id).where(Enquiry.bdm_organization_id == org.id, Enquiry.converted_user_id.is_not(None))

    def distinct_students(column, *where):
        return select(func.count(distinct(column))).where(column.in_(students), *where).scalar_subquery()

    query = select(
        select(func.count()).select_from(Enquiry).where(Enquiry.bdm_organization_id == org.id).scalar_subquery(),
        distinct_students(Enquiry.converted_user_id, Enquiry.bdm_organization_id == org.id),
        distinct_students(Enrollment.student_id, Enrollment.status != "withdrawn"),
        distinct_students(Certificate.student_id, Certificate.status == "issued"),
        select(func.count(distinct(JobApplication.student_id)))
        .join(JobOffer, JobOffer.application_id == JobApplication.id)
        .where(JobApplication.student_id.in_(students), JobOffer.status.in_(ACCEPTED_OFFER))
        .scalar_subquery(),
        select(func.coalesce(func.sum(Payment.amount), 0))
        .where(
            Payment.user_id.in_(students),
            Payment.status.in_(PAID_STATUSES),
            Payment.currency == CURRENCY,
            Payment.reference_type != AGENT_DEPOSIT,
        )
        .scalar_subquery(),
    )
    leads, registrations, training, certification, placement, fees = (await db.execute(query)).one()
    counts = {"contacted": leads, "leads": leads, "registrations": registrations, "training": training, "certification": certification, "placement": placement}
    funnel = [{"key": k, "label": label, "definition": d, "tracked": k in counts, "count": counts.get(k)} for k, label, d in STAGES]
    revenue = None
    if with_revenue:
        amounts = {"training": Decimal(str(fees)).quantize(Decimal("0.01"))}
        revenue = {"lines": [{"key": k, "label": label, "definition": d, "tracked": k in amounts, "amount": amounts.get(k)} for k, label, d in REVENUE_LINES]}
    return {"organization_id": org.id, "currency": CURRENCY, "funnel": funnel, "revenue": revenue}
