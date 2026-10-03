"""AGN-018 fixture: one agency (Master + three staff) and a noise agency, with every case the KPI definitions distinguish
(spec §4, §8 AC01). The expected numbers are hand counts, worked out next to the rows that produce them."""

import uuid
from datetime import date

from app.models import AgentCommission, AgentStudent, Country, University
from tests.agn001_helpers import mk_active_org, mk_user, uniq
from tests.agn004_helpers import mk_record, mk_staff
from tests.agn008_helpers import mk_application, mk_school_student
from tests.agn009_helpers import mk_doc
from tests.agn012_helpers import mk_case
from tests.agn016_helpers import mk_task

DASHBOARD_API = "/api/v1/workflows/overseas/agent/crm/dashboard"
PORTAL_DASHBOARD = "/api/v1/portal/overseas/agent/dashboard"
OFFERED = {"offer_type": "unconditional", "offer_date": date(2026, 9, 1)}


async def mk_place(db, *, university: str, country: str) -> University:
    """A university in its own country, both named (mk_university names every one alike)."""
    suffix = uuid.uuid4().hex[:8]
    c = Country(slug=f"agn018-c-{suffix}", name=country, overview="", tuition="", living_expenses="", visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[])
    db.add(c)
    await db.flush()
    u = University(country_id=c.id, slug=f"agn018-u-{suffix}", name=university, city="Testville", overview="", eligibility="", requirements=[], deadlines=[], scholarships=[])
    db.add(u)
    await db.commit()
    return u


async def mk_commission(db, *, agent, application, status: str, amount: float, currency: str = "INR") -> AgentCommission:
    """A commission on an existing application (agn014's builder makes its own application, which would change the counts)."""
    row = AgentCommission(
        agent_id=agent.id, application_id=application.id, amount=amount, currency=currency, status=status, created_by="system_trigger",
        claim_reference=None if status in {"estimated", "eligible"} else f"CLM-{uniq()}",
    )
    db.add(row)
    await db.commit()
    return row


async def dashboard_world(db) -> dict:
    ctx = await mk_active_org(db, name=f"Dash {uniq()}")
    other = await mk_active_org(db, name=f"Noise {uniq()}")
    master = ctx["master"]
    s1 = await mk_staff(db, ctx["org"], full_name="Staff One")
    s2 = await mk_staff(db, ctx["org"], full_name="Staff Two")
    s3 = await mk_staff(db, ctx["org"], full_name="Staff Three")
    u1 = await mk_place(db, university="Alpha University", country="Aland")
    u2 = await mk_place(db, university="Beta University", country="Betaland")

    r1 = await mk_record(db, agent=master, full_name=f"R1 {uniq()}", assigned_member=s1["member"])  # s1, no login
    login = await mk_user(db, role="overseas_student", full_name=f"R2 {uniq()}")
    r2 = AgentStudent(agent_id=master.id, student_id=login.id, status="active", assigned_member_id=s1["member"].id)  # s1, with a login
    db.add(r2)
    await db.commit()
    r3 = await mk_record(db, agent=master, full_name=f"R3 {uniq()}", assigned_member=s2["member"])  # s2
    r4 = await mk_record(db, agent=master, full_name=f"R4 {uniq()}", assigned_member=s1["member"], status="archived")  # s1, archived
    r5 = await mk_record(db, agent=master, full_name=f"R5 {uniq()}")  # unassigned

    async def app(record, university, status, **fields):
        return await mk_application(db, agent=master, university=university, record=record, status=status, **fields)

    a1 = await app(r1, u1, "enquiry")
    a2 = await app(r1, u1, "offer")
    a3 = await app(r2, u2, "visa_documentation")
    a4 = await app(r2, u2, "enrolled")
    a5 = await app(r3, u1, "withdrawn", **OFFERED)  # withdrawn after its offer: an offer, not an open application
    await app(r3, u1, "university_selection", **OFFERED)  # a6: offer recorded before the stage moved
    await app(r4, u1, "enquiry")  # a7: an archived student's application stays
    a8 = await app(r5, u2, "offer_received")  # legacy offer value, unassigned student
    await app(r1, u1, "withdrawn")  # a10: withdrawn, no offer -- counted nowhere
    await mk_application(db, agent=master, university=u1, school_student=await mk_school_student(db), status="offer")  # bridged: nowhere

    await mk_case(db, a3, status="decision", decision="approved")
    await mk_case(db, a3, status="checklist")  # a second case on a3: still one visa application
    await mk_case(db, a5, status="decision", decision="refused")

    await mk_doc(db, record=r1)  # pending, unattached (s1)
    await mk_doc(db, record=r1, status="verified")
    await mk_doc(db, record=r2, application=a3)  # pending, attached (s1)
    await mk_doc(db, record=r3)  # pending (s2)
    await mk_doc(db, record=r5)  # pending (unassigned)

    await mk_task(db, record=r1, author=master)  # open (s1)
    await mk_task(db, record=r1, author=master, status="done")
    await mk_task(db, record=r3, author=master)  # open (s2)
    await mk_task(db, record=r4, author=master)  # open, but the student is archived: not pending
    await mk_task(db, record=r5, author=master, status="cancelled")

    await mk_commission(db, agent=master, application=a1, status="estimated", amount=200, currency="USD")
    await mk_commission(db, agent=master, application=a2, status="eligible", amount=1000)
    await mk_commission(db, agent=master, application=a3, status="claimed", amount=500)
    await mk_commission(db, agent=master, application=a4, status="paid", amount=12000)
    await mk_commission(db, agent=master, application=a8, status="paid", amount=500, currency="USD")

    # Noise agency: never counted anywhere above.
    nr = await mk_record(db, agent=other["master"], full_name=f"Noise {uniq()}")
    na = await mk_application(db, agent=other["master"], university=u1, record=nr, status="enrolled")
    await mk_case(db, na, status="decision", decision="approved")
    await mk_doc(db, record=nr)
    await mk_task(db, record=nr, author=other["master"])
    await mk_commission(db, agent=other["master"], application=na, status="paid", amount=999)

    return ctx | {"other": other, "s1": s1, "s2": s2, "s3": s3, "u1": u1, "u2": u2, "apps": {"a1": a1, "a3": a3, "a4": a4}}


# Hand counts. Master: students r1 r2 r3 r5; applications a1 a2 a3 a4 a6 a7 a8; offers a2 a3 a4 a5 a6 a8; visa a3 a5 (approved a3);
# enrolled a4; pending documents r1 r2(a3) r3 r5; pending tasks r1 r3. s1 (r1 r2 r4): a1 a2 a3 a4 a7. s2 (r3): a6, offers a5 a6.
MASTER = {"students": 4, "applications": 7, "offers": 6, "visa_applications": 2, "visa_approvals": 1, "enrollments": 1, "pending_documents": 4, "pending_actions": 2}
S1 = {"students": 2, "applications": 5, "offers": 3, "visa_applications": 1, "visa_approvals": 1, "enrollments": 1, "pending_documents": 2, "pending_actions": 1}
S2 = {"students": 1, "applications": 1, "offers": 2, "visa_applications": 1, "visa_approvals": 0, "enrollments": 0, "pending_documents": 1, "pending_actions": 1}
S3 = dict.fromkeys(MASTER, 0)
