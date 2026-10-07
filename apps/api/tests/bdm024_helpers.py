"""bdm-024 test world: one manager's team with a BDM of each type, records inside a fixed past IST month (March 2025) and near misses
just outside it or in another team. The test database is shared and never truncated, so every figure is read for this team only."""

import uuid
from datetime import date, datetime

from sqlalchemy import select, update

from app.models import (
    AgentStudent,
    BdmAppointment,
    BdmMou,
    BdmMouEvent,
    BdmOrganization,
    BdmTrip,
    Enquiry,
    Payment,
    SchoolCareerRecord,
    SchoolStudent,
    User,
)
from app.services.agent_network import members_of
from app.services.bdm_appointments import IST
from tests.agn022_helpers import network_world
from tests.bdm001_helpers import make_manager, make_user
from tests.bdm002_helpers import make_bdm
from tests.bdm017_helpers import student_email
from tests.enh016_helpers import make_school
from tests.test_bdm_023_dashboard import org_of

PERIOD = {"from": "2025-03-01", "to": "2025-03-31"}
IN = datetime(2025, 3, 10, 11, 0, tzinfo=IST)
AFTER = datetime(2025, 4, 1, 0, 30, tzinfo=IST)  # 30 minutes after the period's last IST day
BEFORE = datetime(2025, 2, 28, 23, 30, tzinfo=IST)


async def appt(db, bdm_id, org: dict, starts_at: datetime, status: str = "completed") -> BdmAppointment:
    row = BdmAppointment(
        code=f"APT-P{uuid.uuid4().hex[:10]}", bdm_user_id=bdm_id, organization_id=org["id"], contact_name="Dr Rao", starts_at=starts_at,
        appointment_type="college_meeting", status=status, outcome="interested" if status == "completed" else None,
    )
    db.add(row)
    await db.commit()
    return row


async def trip(db, bdm_id, day: date, *, approval: str = "approved", travel_status: str = "planned") -> BdmTrip:
    row = BdmTrip(
        code=f"TRV-P{uuid.uuid4().hex[:10]}", bdm_user_id=bdm_id, travel_date=day, return_date=day, from_place="Hyderabad",
        to_place="Vijayawada", purpose="College visits", mode="train", estimated_cost=1000, approval_status=approval, travel_status=travel_status,
    )
    db.add(row)
    await db.commit()
    return row


async def signed(db, org: dict, actor_id, at: datetime, from_status: str = "proposal_sent") -> None:
    """A status event on the organization's current MoU (one per organization, `uq_bdm_mous_current`)."""
    mou = await db.scalar(select(BdmMou).where(BdmMou.organization_id == org["id"], BdmMou.is_current))
    if mou is None:
        mou = BdmMou(organization_id=org["id"], created_by_user_id=actor_id, status="signed", signed_on=at.date())
        db.add(mou)
        await db.flush()
    db.add(BdmMouEvent(mou_id=mou.id, actor_user_id=actor_id, kind="status", from_status=from_status, to_status="signed", changed=[], created_at=at))
    await db.commit()


async def lead(db, org: dict, bdm_id, created_at: datetime, student: User | None = None, converted_at: datetime | None = None) -> Enquiry:
    row = Enquiry(
        division="it", name="Lead", email=student_email(), subject="Python", message="Lead entered by BDM", source="bdm", status="new",
        crm_sync_status="pending", metadata_json={}, bdm_organization_id=org["id"], bdm_user_id=bdm_id, created_at=created_at,
        converted_user_id=student.id if student else None, converted_at=converted_at if student else None,
        converted_by_user_id=bdm_id if student else None,
    )
    db.add(row)
    await db.commit()
    return row


async def pay(db, student: User, amount: str, created_at: datetime, *, status: str = "paid", currency: str = "INR",
              reference_type: str = "enrollment") -> None:
    db.add(Payment(user_id=student.id, division="it", reference_type=reference_type, amount=amount, currency=currency, status=status,
                   created_at=created_at))
    await db.commit()


async def backdate_org(db, org: dict, at: datetime) -> None:
    await db.execute(update(BdmOrganization).where(BdmOrganization.id == org["id"]).values(created_at=at))
    await db.commit()


async def link(db, org: dict, **ids) -> None:
    await db.execute(update(BdmOrganization).where(BdmOrganization.id == org["id"]).values(**ids))
    await db.commit()


async def school_student(db, school, admin_id, created_at: datetime) -> SchoolStudent:
    row = SchoolStudent(school_id=school.id, student_code=uuid.uuid4().hex[:8].upper(), full_name="Student", created_by_user_id=admin_id,
                        created_at=created_at)
    db.add(row)
    await db.commit()
    return row


async def perf_world(client, db) -> dict:
    """Leaves the client signed out. Expected figures for PERIOD are in EXPECTED."""
    manager = await make_manager(db, name=f"Perf Manager {uuid.uuid4().hex[:4]}")
    c1 = await make_bdm(db, manager, "college")
    s1 = await make_bdm(db, manager, "school")
    a1 = await make_bdm(db, manager, "agent")
    a2 = await make_bdm(db, manager, "agent", active=False)  # deactivated: records count, P-01 does not
    org_c = await org_of(client, c1, org_type="college")
    org_c2 = await org_of(client, c1, org_type="college")  # nothing in the period: not listed in the BDM's organizations
    org_s = await org_of(client, s1, org_type="school")
    org_a = await org_of(client, a1, org_type="agent")

    # College: meetings 1, trips 1, new organizations 1, MoUs 1, leads 2, students 1, revenue 1250.50
    await appt(db, c1.id, org_c, IN)
    await appt(db, c1.id, org_c, AFTER)
    await appt(db, c1.id, org_c, IN, status="scheduled")
    the_trip = await trip(db, c1.id, date(2025, 3, 5))
    await trip(db, c1.id, date(2025, 3, 6), travel_status="cancelled")
    await trip(db, c1.id, date(2025, 3, 7), approval="rejected")
    await trip(db, c1.id, date(2025, 4, 1))
    await backdate_org(db, org_c, IN)
    await signed(db, org_c, c1.id, IN)
    await signed(db, org_c, c1.id, IN, from_status="signed")  # kept signed: not a transition
    await signed(db, org_c, c1.id, AFTER)
    st1, st2 = await make_user(db, "it_student", "it"), await make_user(db, "it_student", "it")
    await lead(db, org_c, c1.id, IN, st1, IN)
    await lead(db, org_c, c1.id, IN, st2, AFTER)  # a lead of the period, a student of the next one
    await lead(db, org_c, c1.id, BEFORE)
    await pay(db, st1, "1000.00", IN)
    await pay(db, st2, "250.50", IN, status="succeeded")
    await pay(db, st1, "500.00", IN, status="pending")
    await pay(db, st1, "300.00", IN, reference_type="agent_deposit")
    await pay(db, st1, "100.00", IN, currency="USD")
    await pay(db, st1, "700.00", AFTER)

    # School: students 2 in the linked School
    ctx = await make_school(db)
    await db.commit()
    school = ctx["school"]
    await link(db, org_s, school_id=school.id)
    admin = ctx["school_coordinator"].id
    sa = await school_student(db, school, admin, IN)
    await school_student(db, school, admin, IN)
    await school_student(db, school, admin, AFTER)

    # Agent: students 4 (the agency's active students, all moved into the period); the inactive BDM's meeting counts
    n = await network_world(db)
    await link(db, org_a, agent_org_id=n["org"].id)
    await db.execute(update(AgentStudent).where(AgentStudent.agent_id.in_(members_of(n["org"].id))).values(created_at=IN))
    await db.commit()
    await appt(db, a2.id, org_a, IN)

    # Another team: never in this manager's figures
    m2 = await make_manager(db)
    x = await make_bdm(db, m2, "college")
    org_x = await org_of(client, x, org_type="college")
    await appt(db, x.id, org_x, IN)
    await lead(db, org_x, x.id, IN)
    return {"manager": manager, "c1": c1, "s1": s1, "a1": a1, "a2": a2, "x": x, "org_c": org_c, "org_c2": org_c2, "org_s": org_s,
            "org_a": org_a, "org_x": org_x, "trip": the_trip, "st1": st1, "st2": st2, "school": school, "school_ctx": ctx,
            "school_student": sa, "n": n}


async def career_done(db, student: SchoolStudent) -> None:
    counselor = await make_user(db, "career_counselor", "overseas")
    db.add(SchoolCareerRecord(school_student_id=student.id, career_counselor_user_id=counselor.id, record_type="guidance_session", notes="x",
                              status="completed"))
    await db.commit()


# P-01...P-08 x (agent, school, college) for PERIOD
EXPECTED = {
    "P-01": [1, 1, 1],
    "P-02": [1, 0, 1],
    "P-03": [0, 0, 1],
    "P-04": [0, 0, 1],
    "P-05": [0, 0, 1],
    "P-06": [0, 0, 2],
    "P-07": [4, 2, 1],
    "P-08": [None, None, "1250.50"],
}
