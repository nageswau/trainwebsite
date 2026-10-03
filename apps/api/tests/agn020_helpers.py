"""AGN-020 fixture: one agency (Master + three staff) and a noise agency, with every case the report definitions distinguish
(spec §4, §8 AC1). The expected numbers are hand counts, worked out next to the rows that produce them."""

from datetime import UTC, date, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.models import AgentOrgMember, AgentStudent, OverseasApplication, User
from tests.agn001_helpers import mk_active_org, mk_user, uniq
from tests.agn004_helpers import mk_record, mk_staff
from tests.agn008_helpers import mk_application, mk_school_student
from tests.agn012_helpers import mk_case
from tests.agn018_helpers import OFFERED, mk_place

REPORTS = "/api/v1/workflows/overseas/agent/crm/reports"
EARLY = datetime(2026, 1, 31, 23, 30, tzinfo=UTC)  # a1's created time: the last half hour of 31 January (UTC)


async def load_user(db, user_id) -> User:
    """The user as `get_current_user` loads it (membership + organisation eager), for service-level tests."""
    return await db.scalar(
        select(User).where(User.id == user_id).options(selectinload(User.role_assignments), selectinload(User.agent_membership).selectinload(AgentOrgMember.org)).execution_options(populate_existing=True)
    )


async def reports_world(db) -> dict:
    ctx = await mk_active_org(db, name=f"Rep {uniq()}")
    other = await mk_active_org(db, name=f"Noise {uniq()}")
    master = ctx["master"]
    s1 = await mk_staff(db, ctx["org"], full_name="Staff One", can_view_reports=True)
    s2 = await mk_staff(db, ctx["org"], full_name="Staff Two", can_view_reports=True)
    s3 = await mk_staff(db, ctx["org"], full_name="Staff Three")  # Reports off
    noise_staff = await mk_staff(db, other["org"], full_name="Noise Staff")
    u1 = await mk_place(db, university="Alpha University", country="Aland")
    u2 = await mk_place(db, university="Beta University", country="Betaland")

    r1 = await mk_record(db, agent=master, full_name=f"Zoë {uniq()}", assigned_member=s1["member"])  # s1, no login
    r1.preferred_country, r1.preferred_intake = "Aland", "Sep 2027"
    login = await mk_user(db, role="overseas_student", full_name=f"R2 {uniq()}")
    r2 = AgentStudent(agent_id=master.id, student_id=login.id, status="active", assigned_member_id=s1["member"].id)  # s1, login
    db.add(r2)
    await db.commit()
    r3 = await mk_record(db, agent=master, full_name=f"=cmd {uniq()}", assigned_member=s2["member"])  # s2, a formula-looking name
    r4 = await mk_record(db, agent=master, full_name=f"R4 {uniq()}", assigned_member=s1["member"], status="archived")  # s1, archived
    r5 = await mk_record(db, agent=master, full_name=f"R5 {uniq()}")  # unassigned

    async def app(record, university, status, intake, **fields):
        return await mk_application(db, agent=master, university=university, record=record, status=status, intake=intake, **fields)

    a1 = await app(r1, u1, "enquiry", "Sep 2027")
    a2 = await app(r1, u1, "offer", "September 2027", submitted_on=date(2026, 8, 1))
    a3 = await app(r2, u2, "visa_documentation", "09/2027", submitted_on=date(2026, 7, 1))
    a4 = await app(r2, u2, "enrolled", "2027-09", submitted_on=date(2026, 6, 1), enrollment_date=date(2027, 9, 15), university_student_id="UNI-4")
    a5 = await app(r3, u1, "withdrawn", "Next intake", **OFFERED)  # withdrawn after its offer
    a6 = await app(r3, u1, "university_selection", "Jan 2028", **OFFERED)
    a7 = await app(r4, u1, "enquiry", "Next intake")  # archived student's application stays
    a8 = await app(r5, u2, "offer_received", "Jan 2028")  # legacy offer value, unassigned
    a9 = await app(r5, u2, "enrolled", "Fall 2027")  # enrolled with no enrollment date (legacy)
    a10 = await app(r1, u1, "withdrawn", "Sep 2027")  # withdrawn, no offer
    await mk_application(db, agent=master, university=u1, school_student=await mk_school_student(db), status="offer", intake="Sep 2027")  # bridged: nowhere
    await db.execute(update(OverseasApplication).where(OverseasApplication.id == a1.id).values(created_at=EARLY))
    await db.commit()

    await mk_case(db, a3, status="decision", decision="approved")
    await mk_case(db, a3, status="checklist")  # a second case on a3: still one visa application
    await mk_case(db, a5, status="decision", decision="refused")

    nr = await mk_record(db, agent=other["master"], full_name=f"Noise {uniq()}", assigned_member=noise_staff["member"])
    noise_place = await mk_place(db, university="Gamma University", country="Gammaland")
    na = await mk_application(db, agent=other["master"], university=noise_place, record=nr, status="enrolled", intake="Sep 2027")
    await mk_case(db, na, status="decision", decision="approved")

    return ctx | {
        "other": other, "s1": s1, "s2": s2, "s3": s3, "noise_staff": noise_staff, "u1": u1, "u2": u2, "noise_place": noise_place,
        "records": {"r1": r1, "r2": r2, "r3": r3, "r4": r4, "r5": r5}, "login": login,
        "apps": {"a1": a1, "a2": a2, "a3": a3, "a4": a4, "a5": a5, "a6": a6, "a7": a7, "a8": a8, "a9": a9, "a10": a10},
    }


# Hand counts (stage columns: applications = non-withdrawn, submitted, offers = O5, visa apps, visa approved, enrolled).
# Master: open a1 a2 a3 a4 a6 a7 a8 a9; submitted a2 a3 a4; offers a2 a3 a4 a5 a6 a8 a9; visa a3 a5 (approved a3); enrolled a4 a9.
STAGES = ("applications", "submitted", "offers", "visa_applications", "visa_approvals", "enrollments")


def counts(*values: int) -> dict:
    return dict(zip(STAGES, values, strict=True))


MASTER_TOTAL = counts(8, 3, 7, 2, 1, 2)
# Aland (u1): a1 a2 a5 a6 a7 a10. Betaland (u2): a3 a4 a8 a9.
MASTER_COUNTRIES = [("Aland", counts(4, 1, 3, 1, 0, 0)), ("Betaland", counts(4, 2, 4, 1, 1, 2))]
# 2027-09: a1 a2 a3 a4 a10. 2028-01: a6 a8. Unstructured ("Next intake" x2, "Fall 2027"): a5 a7 a9.
MASTER_INTAKES = [("Sep 2027", counts(4, 3, 3, 1, 1, 1)), ("Jan 2028", counts(2, 0, 2, 0, 0, 0)), ("Unstructured", counts(2, 0, 2, 1, 0, 1))]
# s1: r1 r2 r4 -> a1 a2 a3 a4 a7 a10 (students: active r1 r2). s2: r3 -> a5 a6. s3: none. Unassigned: r5 -> a8 a9.
MASTER_STAFF = [
    ("Staff One", 2, counts(5, 3, 3, 1, 1, 1)),
    ("Staff Two", 1, counts(1, 0, 2, 1, 0, 0)),
    ("Staff Three", 0, counts(0, 0, 0, 0, 0, 0)),
    ("Unassigned", 1, counts(2, 0, 2, 0, 0, 1)),
]
# s1 own scope: Aland a1 a2 a7 a10; Betaland a3 a4.
S1_COUNTRIES = [("Aland", counts(3, 1, 1, 0, 0, 0)), ("Betaland", counts(2, 2, 2, 1, 1, 1))]
S1_TOTAL = counts(5, 3, 3, 1, 1, 1)
