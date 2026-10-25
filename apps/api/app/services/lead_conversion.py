"""ccrm-008 (DEC-SCOPE-252, CC9, K1-K6): the counselor converts a lead handed to them into an overseas student in one step -- the csc-002
account (name, email and phone prefilled from the lead), the tel-018 link (the lead moves to Application/Enrollment) and a copy of the
lead's details into the ccrm-007 profile. Functions only; the route commits through `lead_handover.commit_link` and mails the
set-password link after the commit. Logs and audit rows carry ids only."""

import logging

from fastapi import HTTPException
from pydantic import BaseModel, ValidationError
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import CLOSED
from app.models import Enquiry, LeadQualification, User
from app.schemas import CounselorStudentCreate, StudentProfileSave, StudentQualificationIn
from app.services import bdm_leads, counselor_students, lead_handover, lead_qualification, student_profiles
from app.services.provisioning import IssuedWelcome

logger = logging.getLogger("app.leads")

COUNSELOR_ONLY = "Only an overseas counselor can convert a lead to a student"
CLOSED_LEAD = "This lead is closed; reopen it before converting it"
TOO_EARLY = "Move the lead to Qualified before converting it"
STUDENT_EXISTS = "A student account already has this email or mobile. Link the existing student instead."
LEVELS = {"ug": "UG", "masters": "PG"}  # lead_qualifications.study_level -> the profile's course level


def _accepted(model: type[BaseModel], parts: list[dict]) -> dict:
    """K3: each group of values is kept only if the model accepts it alongside the ones kept so far; a refused value (a passing year past
    the profile's range, a text too long) stays on the lead and never blocks the conversion."""
    kept: dict = {}
    for part in parts:
        if all(value is None for value in part.values()):
            continue
        try:
            model.model_validate(kept | part)
        except ValidationError:
            continue
        kept |= part
    return kept


def profile_from_lead(lead: Enquiry, qual: LeadQualification | None, tests: list[dict] = ()) -> StudentProfileSave | None:
    """What the lead holds that has a structured place in the profile; None when there is nothing to copy. Free text with no such place
    (budget range, English test status, passport status) stays on the linked lead. ccrm-005 LF8: the study mode, preferred country,
    CGPA (when there is no percentage), backlogs and English tests come along too."""
    q = qual or LeadQualification()
    score = ({"score_type": "percentage", "score": q.academic_percentage} if q.academic_percentage is not None
             else {"score_type": "cgpa" if q.academic_cgpa is not None else None, "score": q.academic_cgpa})
    qualification = _accepted(StudentQualificationIn, [
        {"level": "other"}, {"qualification_name": lead.qualification}, {"institution": lead.institution}, {"year_completed": lead.passing_year},
        score, {"backlogs": q.backlogs},
    ])  # fmt: skip
    if len(qualification) == 1:  # the level alone: the lead named no qualification
        qualification = {}
    experience = q.work_experience_years * 12 if q.work_experience_years is not None else None
    fields = _accepted(StudentProfileSave, [
        {"city": lead.city}, {"state": lead.state}, {"preferred_course": q.preferred_course}, {"preferred_intake": q.intake},
        {"preferred_level": LEVELS.get(q.study_level or "")}, {"work_experience_months": experience}, {"work_experience_details": q.current_org},
        {"study_mode": q.study_mode}, {"preferred_country_ids": [q.preferred_country_id] if q.preferred_country_id else None},
        {"english_tests": list(tests) or None},
    ])  # fmt: skip
    if not fields and not qualification:
        return None
    return StudentProfileSave.model_validate(fields | {"qualifications": [qualification] if qualification else []})


async def convert(db: AsyncSession, counselor: User, lead: Enquiry, payload: CounselorStudentCreate) -> tuple[User, IssuedWelcome]:
    """On the locked lead (lock order lead -> counselor -> new student), no commit. Every refusal comes before the account is made, so a
    refused conversion creates nothing (csc-002's audited "Email already exists" commits only its own audit row)."""
    if lead.converted_user_id is not None:
        raise HTTPException(409, bdm_leads.ALREADY_LINKED)
    if lead.status in CLOSED:
        raise HTTPException(409, CLOSED_LEAD)
    if not lead_handover.convertible_stage(lead.status):
        raise HTTPException(422, TOO_EARLY)
    matches = lead_handover.contact_matches(payload.email, payload.phone)
    if matches and await db.scalar(select(exists().where(*lead_handover.student_filters(lead.division), or_(*matches)))):
        raise HTTPException(409, STUDENT_EXISTS)  # K4: the link panel offers that student
    student, issued = await counselor_students.create_student(db, counselor, payload, registration_source="lead_conversion")
    profile = profile_from_lead(lead, await db.get(LeadQualification, lead.id), await lead_qualification.english_tests(db, lead))
    if profile is not None:
        await student_profiles.write(db, counselor, student.id, profile)
    await lead_handover.link_student(db, counselor, lead, User.id == student.id)
    logger.info("lead_converted_to_student", extra={"extra_fields": {"actor_id": str(counselor.id), "lead_id": str(lead.id), "student_id": str(student.id),
                                                                     "profile_copied": profile is not None}})  # fmt: skip
    return student, issued
