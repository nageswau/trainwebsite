"""AGN-014 test helpers: a commission on its own application, university and country, with an explicit created_at."""

import uuid
from datetime import datetime

from app.models import AgentCommission, Country, OverseasApplication, University
from tests.agn001_helpers import mk_user

REPORT = "/api/v1/workflows/overseas/agent/commissions/report"
CSV = REPORT + ".csv"


async def mk_commission(
    db, ctx: dict, *, status: str = "paid", amount: float = 1000, currency: str = "INR", created_at: datetime | None = None,
    student_name: str = "Report Student", university_name: str = "Report University", country_name: str = "Reportland",
    intake: str = "Sep 2027", agent=None, student: bool = True, claim_reference: str | None = None,
) -> AgentCommission:
    """`ctx["master"]` owns the commission unless `agent` (e.g. a staff user) is given; `student=False` leaves the application
    without a login (`student_id` NULL), as a bridged school-student application has. Claimed-or-later statuses get a unique
    claim reference unless one is given."""
    suffix = uuid.uuid4().hex[:8]
    country = Country(
        slug=f"agn014-country-{suffix}", name=country_name, overview="", tuition="", living_expenses="", visa_process=[],
        work_opportunities="", post_study_work="", pr_opportunities="", faq=[],
    )
    db.add(country)
    await db.flush()
    university = University(
        country_id=country.id, slug=f"agn014-university-{suffix}", name=university_name, city="Testville", overview="",
        eligibility="", requirements=[], deadlines=[], scholarships=[],
    )
    db.add(university)
    await db.flush()
    owner = agent or ctx["master"]
    student_user = await mk_user(db, role="overseas_student", full_name=student_name) if student else None
    application = OverseasApplication(
        student_id=student_user.id if student_user else None, university_id=university.id, agent_id=owner.id, intake=intake, status="enrolled",
    )
    db.add(application)
    await db.flush()
    commission = AgentCommission(
        agent_id=owner.id, application_id=application.id, amount=amount, currency=currency, status=status, created_by="system_trigger",
        claim_reference=claim_reference or (None if status in {"estimated", "eligible"} else f"CLM-{suffix}"),
    )
    if created_at is not None:
        commission.created_at = created_at
    db.add(commission)
    await db.commit()
    return commission
