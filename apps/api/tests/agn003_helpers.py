"""AGN-003 test helpers: an agency student with an application and one document (the agent review and §6 matrix tests)."""

import uuid

from app.models import AgentStudent, Country, OverseasApplication, StudentDocument, University
from tests.agn001_helpers import mk_user

DOC_VERIFY = "/api/v1/workflows/overseas/documents/{}/verify"


async def mk_university(db) -> University:
    country = Country(
        slug=f"agn003-country-{uuid.uuid4().hex[:8]}", name="Testland", overview="", tuition="", living_expenses="",
        visa_process=[], work_opportunities="", post_study_work="", pr_opportunities="", faq=[],
    )
    db.add(country)
    await db.flush()
    university = University(
        country_id=country.id, slug=f"agn003-university-{uuid.uuid4().hex[:8]}", name="AGN003 University", city="Testville",
        overview="", eligibility="", requirements=[], deadlines=[], scholarships=[],
    )
    db.add(university)
    await db.commit()
    return university


async def agency_document(db, ctx: dict, *, attached: bool = True, status: str = "pending", counselor=None, assigned_to=None) -> dict:
    """A student linked to the agency's Master, an application referred by that Master, and one document on it (or, with
    attached=False, a document on the student only). `assigned_to` (an AgentOrgMember) assigns the student to a staff member --
    staff only reach their assigned students (AGN-004 DEC-SCOPE-042 G4, adopted by AGN-003 on merging `main`)."""
    student = await mk_user(db, role="overseas_student", full_name="Agency Student")
    db.add(AgentStudent(agent_id=ctx["master"].id, student_id=student.id, status="active", assigned_member_id=assigned_to.id if assigned_to else None))
    university = await mk_university(db)
    application = OverseasApplication(
        student_id=student.id, university_id=university.id, agent_id=ctx["master"].id, counselor_id=counselor.id if counselor else None,
        intake="Fall 2027", status="enquiry",
    )
    db.add(application)
    await db.flush()
    document = StudentDocument(
        student_id=student.id, application_id=application.id if attached else None, document_type="Passport",
        file_url="uploads/agn003-passport.pdf", verification_status=status,
    )
    db.add(document)
    await db.commit()
    return {"student": student, "university": university, "application": application, "document": document}
