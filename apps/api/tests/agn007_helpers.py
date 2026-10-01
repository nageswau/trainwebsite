"""AGN-007 test helpers: a catalogue university with two courses, a second catalogue university with one, and URL builders."""

import uuid

from app.models import Country, OverseasCourse, University

UNIVERSITIES = "/api/v1/workflows/overseas/agent/crm/universities"


def shortlist(student_id) -> str:
    return f"/api/v1/workflows/overseas/agent/crm/students/{student_id}/shortlist"


async def mk_catalogue(db) -> dict:
    tag = uuid.uuid4().hex[:8]
    country = Country(slug=f"agn007-country-{tag}", name=f"Catalogland {tag}", overview="", tuition="", living_expenses="", visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[])
    db.add(country)
    await db.flush()
    unis = []
    for label in ("a", "b"):
        u = University(country_id=country.id, slug=f"agn007-{label}-{tag}", name=f"AGN007 Uni {label.upper()} {tag}", city="Catalog City", overview="", eligibility="", requirements=["IELTS 6.5", "Transcript"], deadlines=[], scholarships=[])
        db.add(u)
        unis.append(u)
    await db.flush()
    course = OverseasCourse(university_id=unis[0].id, title=f"MSc Data {tag}", level="PG", category="Tech", duration="1 year", tuition_fee="EUR 20,000", intake="Sep 2027")
    other_course = OverseasCourse(university_id=unis[1].id, title=f"MBA {tag}", level="PG", category="Business", duration="1 year", tuition_fee="EUR 30,000", intake="Jan 2028")
    db.add_all([course, other_course])
    await db.commit()
    return {"country": country, "university": unis[0], "course": course, "other_university": unis[1], "other_course": other_course}
