"""AGN-019 fixture: AGN-018's dashboard world plus the funnel's awkward cases (spec §4, §7 AC1). Hand counts sit next to the rows.

dashboard_world (see agn018_helpers): s1 holds r1 (a1 enquiry, a2 offer, a10 withdrawn without offer), r2 (login; a3
visa_documentation with an approved and a second case, a4 enrolled) and r4 (archived; a7 enquiry); s2 holds r3 (a5 withdrawn after
its offer, refused visa; a6 offer recorded at university_selection); r5 is unassigned (a8 legacy offer_received); s3 holds nothing.
Added here: r6 (s2) submitted but not offered, r7 (s2) enrolled with no visa case, r8 (s3) with no application."""

from datetime import date

from tests.agn001_helpers import uniq
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import mk_application
from tests.agn018_helpers import dashboard_world

PERFORMANCE_API = "/api/v1/workflows/overseas/agent/crm/performance"
STAGES = ("students", "applications", "submitted", "offers", "visa", "enrolled")
TABLE = ("students", "applications", "offers", "visa_applications", "visa_approvals", "enrollments")


async def performance_world(db) -> dict:
    w = await dashboard_world(db)
    master, s2, s3, u1 = w["master"], w["s2"], w["s3"], w["u1"]
    r6 = await mk_record(db, agent=master, full_name=f"R6 {uniq()}", assigned_member=s2["member"])
    await mk_application(db, agent=master, university=u1, record=r6, status="eligibility_evaluation", submitted_on=date(2026, 8, 1))
    r7 = await mk_record(db, agent=master, full_name=f"R7 {uniq()}", assigned_member=s2["member"])
    await mk_application(db, agent=master, university=u1, record=r7, status="enrolled")
    r8 = await mk_record(db, agent=master, full_name=f"R8 {uniq()}", assigned_member=s3["member"])
    return w | {"r6": r6, "r7": r7, "r8": r8}


def table(*values) -> dict:
    return dict(zip(TABLE, values, strict=True))


def funnel(*values) -> dict:
    return dict(zip(STAGES, values, strict=True))


# Table (AGN-018 G3 columns): students = active records; applications = not withdrawn; offers = O5; visa = distinct applications with
# a case / an approved case; enrollments = stage enrolled.
TABLE_S1 = table(2, 5, 3, 1, 1, 1)  # r1 r2 (r4 archived); a1 a2 a3 a4 a7; offers a2 a3 a4; visa a3 (approved)
TABLE_S2 = table(3, 3, 3, 1, 0, 1)  # r3 r6 r7; a6 a11 a12; offers a5 a6 a12; visa a5 (refused); enrolled a12
TABLE_S3 = table(1, 0, 0, 0, 0, 0)  # r8
TABLE_UNASSIGNED = table(1, 1, 1, 0, 0, 0)  # r5; a8
TABLE_TOTAL = table(7, 9, 7, 2, 1, 2)

# Funnel ("reached at least"): levels r1 3, r2 5, r3 4, r4 1, r5 3, r6 2, r7 5, r8 0.
FUNNEL_S1 = funnel(3, 3, 2, 2, 1, 1)
FUNNEL_S2 = funnel(3, 3, 3, 2, 2, 1)
FUNNEL_S3 = funnel(1, 0, 0, 0, 0, 0)
FUNNEL_UNASSIGNED = funnel(1, 1, 1, 1, 0, 0)
FUNNEL_TOTAL = funnel(8, 7, 6, 5, 3, 2)
