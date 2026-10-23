"""ccrm-012 test world: two overseas counselors, each with direct applications in two countries and their own leads; one more student is
only linked (csc-001) to counselor A."""

import uuid
from datetime import UTC, datetime

from app.models import Country, Enquiry, OverseasStudentCounselor, University
from tests.agn001_helpers import mk_user, uniq
from tests.agn008_helpers import mk_application

PORTAL = "/api/v1/portal/overseas/{}/{}"
LEADS = "/api/v1/counselor/leads"
SEARCH = "/api/v1/counselor/search"


async def mk_university(db, country_name: str) -> University:
    tag = uuid.uuid4().hex[:8]
    country = Country(slug=f"ccrm012-{tag}", name=f"{country_name} {tag}", overview="", tuition="", living_expenses="", visa_process=[], work_opportunities="",
                      post_study_work="", pr_opportunities="", faq=[])
    db.add(country)
    await db.flush()
    university = University(country_id=country.id, slug=f"ccrm012-u-{tag}", name=f"CCRM012 Uni {country_name} {tag}", city="Testville", overview="",
                            eligibility="", requirements=[], deadlines=[], scholarships=[])
    db.add(university)
    await db.commit()
    return university


async def mk_lead(db, owner, **fields) -> Enquiry:
    lead = Enquiry(division=owner.division, name=fields.pop("name", f"Lead {uniq()}"), subject="Study abroad", message="Interested", owner_id=owner.id, **fields)
    db.add(lead)
    await db.commit()
    return lead


async def search_world(db) -> dict:
    w: dict = {}
    w["a"] = await mk_user(db, role="counselor", full_name=f"Counsellor A {uniq()}")
    w["b"] = await mk_user(db, role="counselor", full_name=f"Counsellor B {uniq()}")
    w["admin"] = await mk_user(db, role="overseas_admin", full_name=f"Admin {uniq()}")
    w["uk"] = await mk_university(db, "Britannia")
    w["ca"] = await mk_university(db, "Mapleland")
    tag = uuid.uuid4().hex[:6]
    w["s1"] = await mk_user(db, role="overseas_student", full_name=f"Zara Quill {tag}")
    w["s1"].phone, w["s1"].student_code = "+91 98765 43210", f"Z{tag[:5].upper()}"
    w["s2"] = await mk_user(db, role="overseas_student", full_name=f"Omar Vance {tag}")
    w["s2"].phone = "+44 7700 900123"
    w["linked"] = await mk_user(db, role="overseas_student", full_name=f"Linked Lia {tag}")
    w["other"] = await mk_user(db, role="overseas_student", full_name=f"Other Ozzy {tag}")
    w["other"].phone = "+91 91234 56789"
    db.add(OverseasStudentCounselor(student_user_id=w["linked"].id, counselor_user_id=w["a"].id, assigned_by_user_id=w["admin"].id))
    await db.commit()
    w["app1"] = await mk_application(db, agent=None, university=w["uk"], student=w["s1"], counselor_id=w["a"].id, status="offer", sub_status="conditional_offer", intake="Sep 2027")
    w["app2"] = await mk_application(db, agent=None, university=w["ca"], student=w["s2"], counselor_id=w["a"].id, status="university_selection", intake="Jan 2028")
    w["app_b"] = await mk_application(db, agent=None, university=w["ca"], student=w["other"], counselor_id=w["b"].id, status="offer", intake="Sep 2027")
    w["app2"].created_at = datetime(2026, 1, 15, tzinfo=UTC)
    w["lead1"] = await mk_lead(db, w["a"], name=f"Hot Harper {tag}", phone="98450 11223", email=f"harper.{tag}@example.local", priority="hot")
    w["lead2"] = await mk_lead(db, w["a"], name=f"Cold Cora {tag}", priority="cold", status="follow_up")
    w["lead_b"] = await mk_lead(db, w["b"], name=f"Bee Lead {tag}", phone="98450 11999")
    w["lead2"].created_at = datetime(2026, 1, 10, tzinfo=UTC)
    await db.commit()
    w["tag"] = tag
    return w
