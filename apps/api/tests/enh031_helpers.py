"""ENH-031 -- fixtures for the lookup tests."""

from app.models import Country, OverseasApplication, OverseasCourse, University
from tests.agn001_helpers import uniq


async def mk_university(db, name: str | None = None) -> University:
    country = Country(slug=uniq("e31-c"), name="Testland", overview="", tuition="", living_expenses="", visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[])
    db.add(country)
    await db.flush()
    university = University(country_id=country.id, slug=uniq("e31-u"), name=name or uniq("E31 Uni"), city="", overview="", eligibility="", requirements=[], deadlines=[], scholarships=[])
    db.add(university)
    await db.commit()
    return university


async def mk_course(db, university: University, title: str) -> OverseasCourse:
    course = OverseasCourse(university_id=university.id, title=title, level="Masters", category="Engineering", duration="1 year", tuition_fee="", intake="Sep")
    db.add(course)
    await db.commit()
    return course


async def mk_application(db, *, student=None, university, counselor=None, agent=None, status="enquiry", course=None, reference=None, school_student=None) -> OverseasApplication:
    application = OverseasApplication(
        student_id=student.id if student else None, school_student_id=school_student.id if school_student else None,
        university_id=university.id, course_id=course.id if course else None, counselor_id=counselor.id if counselor else None,
        agent_id=agent.id if agent else None, intake="Sep 2027", status=status, application_reference=reference,
    )
    db.add(application)
    await db.commit()
    return application
