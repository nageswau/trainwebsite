import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.database import SessionLocal, engine
from app.core.security import hash_password
from app.models import *

PASSWORD = "Demo@123"
USERS = [
    ("superadmin@edusphere.local", "Global Super Admin", "super_admin", "global"),
    ("itadmin@edusphere.local", "IT Division Administrator", "it_admin", "it"),
    ("student.it@edusphere.local", "Arjun Rao", "it_student", "it"),
    ("trainer@edusphere.local", "Meera Iyer", "trainer", "it"),
    ("placement@edusphere.local", "Kiran Placement", "placement_team", "it"),
    ("hr@edusphere.local", "Priya HR", "hr_team", "it"),
    ("overseasadmin@edusphere.local", "Overseas Administrator", "overseas_admin", "overseas"),
    ("student.overseas@edusphere.local", "Ananya Sharma", "overseas_student", "overseas"),
    ("counselor@edusphere.local", "Ritika Counselor", "counselor", "overseas"),
    ("university.rep@edusphere.local", "Daniel University Rep", "university_rep", "overseas"),
    ("agent@edusphere.local", "Global Admissions Agent", "agent", "overseas"),
]
UNIVERSITIES = [
    ("united-kingdom", "university-of-manchester", "University of Manchester", "Manchester"),
    ("united-kingdom", "university-of-birmingham", "University of Birmingham", "Birmingham"),
    ("germany", "technical-university-of-munich", "Technical University of Munich", "Munich"),
    ("germany", "rwth-aachen", "RWTH Aachen University", "Aachen"),
    ("canada", "university-of-waterloo", "University of Waterloo", "Waterloo"),
    ("canada", "university-of-alberta", "University of Alberta", "Edmonton"),
    ("australia", "monash-university", "Monash University", "Melbourne"),
    ("usa", "arizona-state-university", "Arizona State University", "Tempe"),
    ("ireland", "university-college-dublin", "University College Dublin", "Dublin"),
    ("netherlands", "tu-delft", "Delft University of Technology", "Delft"),
]


async def user(db, email, name, role, division):
    x = await db.scalar(select(User).where(User.email == email))
    if not x:
        x = User(email=email, password_hash=hash_password(PASSWORD), full_name=name, role=role, division=division, profile={"demo": True})
        db.add(x)
        await db.flush()
    return x


async def main():
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    base = Path(__file__).resolve().parents[1] / "seed"
    programs = json.loads((base / "programs.json").read_text())
    countries = json.loads((base / "countries.json").read_text())
    async with SessionLocal() as db:
        us = {}
        for row in USERS:
            us[row[2]] = await user(db, *row)
        # Enrich demo profiles so dashboard/search screens have realistic role-specific seed data.
        us["it_student"].profile = {
            "demo": True,
            "education": "B.Tech Computer Science",
            "skills": ["Python", "FastAPI", "PostgreSQL", "React"],
            "placement_status": "Available",
            "resume_url": "/demo/arjun-resume.pdf",
        }
        us["trainer"].profile = {"demo": True, "expertise": ["Python", "FastAPI", "Cloud"], "experience_years": 9}
        us["placement_team"].profile = {"demo": True, "team": "Placement Operations"}
        us["hr_team"].profile = {"demo": True, "company": "Demo Hiring Partner", "designation": "Talent Acquisition"}
        us["overseas_student"].profile = {
            "demo": True,
            "education": "B.Tech",
            "preferred_countries": ["United Kingdom", "Germany"],
            "preferred_intake": "September 2027",
            "english_test": "IELTS planned",
        }
        us["counselor"].profile = {"demo": True, "specialisms": ["UK", "Germany", "Ireland"]}
        us["university_rep"].profile = {"demo": True, "university": "University Partner Demo"}
        us["agent"].profile = {"demo": True, "agency_name": "EduSphere Partner Agency", "registration_status": "approved"}
        # AGT-001's approval gate (`core.rbac.agent_is_approved`) checks the
        # `UserRoleAssignment` table, not `User.profile["registration_status"]` above --
        # without an approved row here the demo agent 403s on every agent-scoped route,
        # including its own portal dashboard. `auth._sync_role_assignment` lazily creates
        # a *pending* row for any role="agent" user on their first-ever login and (by
        # design, per its own docstring) never overwrites it afterward -- so a demo
        # environment where someone logs in as the agent before this seed step has run
        # would otherwise be stuck pending forever. Explicitly (re-)approve it here.
        demo_agent_assignment = await db.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == us["agent"].id, UserRoleAssignment.division == "overseas", UserRoleAssignment.role == "agent"))
        if demo_agent_assignment:
            demo_agent_assignment.approval_status = "approved"
        else:
            db.add(UserRoleAssignment(user_id=us["agent"].id, division="overseas", role="agent", approval_status="approved"))
        pmap = {}
        for slug, cat, title, summary, duration, fees, curr in programs:
            p = await db.scalar(select(Program).where(Program.slug == slug))
            if not p:
                p = Program(
                    slug=slug,
                    category=cat,
                    title=title,
                    summary=summary,
                    duration=duration,
                    eligibility="Graduates, final-year students or working professionals. Program-specific prerequisites may apply.",
                    fees=fees,
                    certification=f"EduSphere {title} Completion Certificate",
                    curriculum=curr,
                    placement_assistance="Resume preparation, mock interviews, referrals and placement drives for eligible learners.",
                    trainer_name="EduSphere Industry Trainer",
                )
                db.add(p)
                await db.flush()
            pmap[slug] = p
        b = await db.scalar(select(Batch).where(Batch.name == "PY-FS-AUG-2026"))
        if not b:
            b = Batch(
                program_id=pmap["python-full-stack"].id,
                trainer_id=us["trainer"].id,
                name="PY-FS-AUG-2026",
                start_date=date.today() - timedelta(days=25),
                end_date=date.today() + timedelta(days=85),
                schedule="Mon/Wed/Fri 19:00 IST",
                timezone="Asia/Kolkata",
                capacity=20,
                enrollment_open=True,
                mode="Hybrid",
                status="active",
            )
            db.add(b)
            await db.flush()
            db.add(Enrollment(student_id=us["it_student"].id, batch_id=b.id, enrollment_code="EDU-202608-0001", enrolled_on=date.today() - timedelta(days=25), status="active", progress_percent=42))
            agreement = await db.scalar(select(Agreement).where(Agreement.division == "it", Agreement.version == "v1"))
            if not agreement:
                agreement = Agreement(
                    division="it",
                    version="v1",
                    title="EduSphere IT Programme Enrolment Agreement",
                    body=(
                        "By accepting this agreement you confirm your enrolment details are accurate, "
                        "agree to the programme's attendance and code-of-conduct policies, and consent "
                        "to EduSphere processing your data for enrolment, learning, and placement "
                        "purposes as described in the privacy notice."
                    ),
                    active=True,
                )
                db.add(agreement)
                await db.flush()
            if not await db.scalar(select(ConsentRecord).where(ConsentRecord.user_id == us["it_student"].id, ConsentRecord.agreement_id == agreement.id)):
                db.add(ConsentRecord(user_id=us["it_student"].id, agreement_id=agreement.id, version=agreement.version, ip_address="127.0.0.1"))
            for i in range(12):
                db.add(Attendance(student_id=us["it_student"].id, batch_id=b.id, session_date=date.today() - timedelta(days=2 * i), status="present" if i not in {3, 8} else "absent"))
            for i in range(5):
                db.add(
                    Assignment(
                        batch_id=b.id,
                        title=f"Python Full Stack Assignment {i + 1}",
                        description="Complete the practical task and submit code/repository evidence.",
                        due_date=datetime.now(UTC) + timedelta(days=4 + i * 5),
                        max_score=100,
                    )
                )
            db.add(
                LearningResource(batch_id=b.id, title="FastAPI API Design Notes", resource_type="pdf", url="https://example.com/resources/fastapi-notes.pdf", metadata_json={"module": "Backend APIs"})
            )
        if b and not await db.scalar(select(LiveSession).where(LiveSession.batch_id == b.id)):
            db.add(
                LiveSession(
                    batch_id=b.id,
                    trainer_id=us["trainer"].id,
                    title="FastAPI APIs - Live Session",
                    starts_at=datetime.now(UTC) + timedelta(days=1),
                    provider="google_meet",
                    meeting_url="https://meet.google.com/demo-edusphere",
                    status="scheduled",
                )
            )
        if b and not await db.scalar(select(Assessment).where(Assessment.batch_id == b.id)):
            assessment = Assessment(
                batch_id=b.id,
                title="Backend Module Assessment",
                description="Trainer-authored demo assessment.",
                scheduled_at=datetime.now(UTC) - timedelta(hours=1),
                duration_minutes=45,
                max_score=10,
                pass_percent=50,
                attempts_allowed=2,
                instructions="Answer all questions.",
                status="open",
            )
            db.add(assessment)
            await db.flush()
            db.add_all(
                [
                    AssessmentQuestion(
                        assessment_id=assessment.id,
                        question_type="mcq_single",
                        prompt="Which HTTP method is normally used to create a resource?",
                        options=["GET", "POST", "DELETE", "HEAD"],
                        correct_answers=["POST"],
                        max_score=5,
                        position=1,
                    ),
                    AssessmentQuestion(assessment_id=assessment.id, question_type="text", prompt="Explain API idempotency in your own words.", options=[], correct_answers=[], max_score=5, position=2),
                ]
            )
        companies = []
        for name, site in [
            ("Infosys", "https://infosys.com"),
            ("Accenture", "https://accenture.com"),
            ("TCS", "https://tcs.com"),
            ("Capgemini", "https://capgemini.com"),
            ("Deloitte", "https://deloitte.com"),
        ]:
            x = await db.scalar(select(Company).where(Company.name == name))
            if not x:
                x = Company(name=name, website=site, partner_type="recruiter")
                db.add(x)
                await db.flush()
            companies.append(x)
        if not await db.scalar(select(Job).limit(1)):
            for i, c in enumerate(companies[:4]):
                db.add(
                    Job(
                        company_id=c.id,
                        title=["Python Developer", "Data Analyst", "Cloud Engineer", "DevOps Engineer"][i],
                        location=["Bengaluru", "Hyderabad", "Pune", "Remote/India"][i],
                        description="Hiring opportunity for screened EduSphere candidates.",
                        skills=[["Python", "FastAPI", "SQL"], ["SQL", "Power BI", "Excel"], ["AWS", "Linux", "Networking"], ["Docker", "CI/CD", "Kubernetes"]][i],
                        status="open",
                        closes_on=date.today() + timedelta(days=30 + i * 5),
                    )
                )
        await db.flush()
        job = await db.scalar(select(Job).order_by(Job.id))
        if job and not await db.scalar(select(JobApplication).where(JobApplication.student_id == us["it_student"].id)):
            ja = JobApplication(job_id=job.id, student_id=us["it_student"].id, status="interview_scheduled", resume_url="/demo/arjun-resume.pdf")
            db.add(ja)
            await db.flush()
            db.add(Interview(application_id=ja.id, scheduled_at=datetime.now(UTC) + timedelta(days=3), mode="Online", meeting_url="https://meet.google.com/demo-edusphere"))
        # VISA-002: the actual interview-prep content is a confirmed open item
        # (PRODUCT_DECISION_REGISTER.md DEC-DATA-001/DEC-SCOPE-006) -- illustrative
        # example content for two countries only, deliberately leaving the rest empty so
        # the "explicit fallback, not a 500" path (VISA-002-AC02) is genuinely exercised,
        # not just theoretical.
        interview_prep = {
            "usa": "Typical F-1 visa interview focus areas: your specific study plan and why this program/university, ties to your home country, and how tuition/living costs will be funded. Bring your I-20, SEVIS fee receipt, and financial evidence; answer concisely and consistently with your application.",
            "united-kingdom": "Credibility interviews (where required) focus on your genuine intention to study, your chosen course and institution, and your financial arrangements. Be ready to explain your course choice and post-study plans clearly and consistently with your visa application.",
        }
        cmap = {}
        for slug, name, overview, tuition, living in countries:
            c = await db.scalar(select(Country).where(Country.slug == slug))
            if not c:
                c = Country(
                    slug=slug,
                    name=name,
                    overview=overview,
                    tuition=tuition,
                    living_expenses=living,
                    visa_process=[
                        "Profile and document readiness",
                        "Admission/offer",
                        "Financial documentation",
                        "Visa form and appointment",
                        "Biometrics/interview where applicable",
                        "Decision and travel preparation",
                    ],
                    work_opportunities="Part-time and graduate work depend on current visa rules.",
                    post_study_work="Post-study permission varies by destination and qualification.",
                    pr_opportunities="Permanent residence pathways are country-specific.",
                    faq=[
                        {"q": "When should I apply?", "a": "Start profile evaluation 8–12 months before the intended intake where possible."},
                        {"q": "Do I need an English test?", "a": "Requirements vary by university and course."},
                    ],
                    interview_prep=interview_prep.get(slug),
                )
                db.add(c)
                await db.flush()
            elif c.interview_prep is None and slug in interview_prep:
                # Backfill for a country row that already existed before this field was
                # added -- never overwrites real content, only fills a genuinely empty one.
                c.interview_prep = interview_prep[slug]
            cmap[slug] = c
        umap = {}
        for cslug, slug, name, city in UNIVERSITIES:
            u = await db.scalar(select(University).where(University.slug == slug))
            if not u:
                u = University(
                    country_id=cmap[cslug].id,
                    slug=slug,
                    name=name,
                    city=city,
                    overview=f"Admissions and course profile for {name}.",
                    eligibility="Course-specific academic and English-language requirements apply.",
                    requirements=["Academic transcripts", "Passport", "English-language evidence", "Statement of purpose", "References where required"],
                    deadlines=["Deadlines vary by course and intake"],
                    scholarships=["Merit scholarships may be available"],
                )
                db.add(u)
                await db.flush()
            umap[slug] = u
        us["university_rep"].profile = {"demo": True, "university": "University of Manchester", "university_id": umap["university-of-manchester"].id}
        if not await db.scalar(select(OverseasCourse).limit(1)):
            for slug, title, level, cat, dur, fee, intake in [
                ("university-of-manchester", "MSc Advanced Computer Science", "Masters", "Computer Science", "1 year", "£31,000", "September"),
                ("technical-university-of-munich", "MSc Informatics", "Masters", "Computer Science", "2 years", "See university fee policy", "Winter"),
                ("university-of-waterloo", "Master of Data Science and Artificial Intelligence", "Masters", "Data Science", "16 months", "CAD 42,000", "Fall"),
                ("monash-university", "Master of Artificial Intelligence", "Masters", "Artificial Intelligence", "2 years", "AUD 53,000", "February/July"),
                ("university-college-dublin", "MSc Business Analytics", "Masters", "Business", "1 year", "€24,000", "September"),
            ]:
                db.add(OverseasCourse(university_id=umap[slug].id, title=title, level=level, category=cat, duration=dur, tuition_fee=fee, intake=intake))
        await db.flush()
        course = await db.scalar(select(OverseasCourse).limit(1))
        if course and not await db.scalar(select(OverseasApplication).where(OverseasApplication.student_id == us["overseas_student"].id)):
            app = OverseasApplication(
                student_id=us["overseas_student"].id,
                university_id=course.university_id,
                course_id=course.id,
                counselor_id=us["counselor"].id,
                agent_id=us["agent"].id,
                status="university_review",
                next_action="Await the university admission decision",
                intake="September 2027",
                application_reference="EDU-OVS-2027-0001",
                notes="Demo seeded application",
            )
            db.add(app)
            await db.flush()
            db.add_all(
                [
                    AgentStudent(agent_id=us["agent"].id, student_id=us["overseas_student"].id, status="active"),
                    ApplicationStatusHistory(application_id=app.id, from_status="profile_evaluation", to_status="university_review", next_action=app.next_action, changed_by_id=us["counselor"].id),
                    AgentCommission(agent_id=us["agent"].id, application_id=app.id, amount=15000, currency="INR", status="eligible"),
                    StudentDocument(student_id=us["overseas_student"].id, application_id=app.id, document_type="Passport", file_url="/demo/passport.pdf", verification_status="verified"),
                    StudentDocument(student_id=us["overseas_student"].id, application_id=app.id, document_type="Academic Transcript", file_url="/demo/transcript.pdf", verification_status="verified"),
                    StudentDocument(student_id=us["overseas_student"].id, application_id=app.id, document_type="Statement of Purpose", file_url="/demo/sop.pdf", verification_status="pending"),
                    VisaCase(application_id=app.id, status="not_started", checklist=["Passport", "Offer letter", "Financial evidence", "Visa form"]),
                    Appointment(
                        division="overseas",
                        student_id=us["overseas_student"].id,
                        staff_id=us["counselor"].id,
                        scheduled_at=datetime.now(UTC) + timedelta(days=2),
                        appointment_type="Application Review",
                        mode="Online",
                        status="scheduled",
                    ),
                ]
            )
        if not await db.scalar(select(Scholarship).limit(1)):
            db.add_all(
                [
                    Scholarship(
                        title="Global Merit Scholarship Guidance",
                        country_id=cmap["united-kingdom"].id,
                        eligibility="Strong academic profile and university-specific merit criteria.",
                        amount="Up to £5,000 subject to award",
                        deadline=date.today() + timedelta(days=90),
                    ),
                    Scholarship(
                        title="Germany STEM Opportunity",
                        country_id=cmap["germany"].id,
                        eligibility="STEM applicants meeting scholarship criteria.",
                        amount="Varies",
                        deadline=date.today() + timedelta(days=120),
                    ),
                ]
            )
        if not await db.scalar(select(Payment).where(Payment.user_id == us["it_student"].id)):
            db.add_all(
                [
                    Payment(
                        user_id=us["it_student"].id, division="it", reference_type="enrollment", amount=32500, currency="INR", provider="razorpay", status="paid", provider_reference="DEMO-RZP-1001"
                    ),
                    Payment(
                        user_id=us["it_student"].id,
                        division="it",
                        reference_type="enrollment",
                        amount=32500,
                        currency="INR",
                        provider="razorpay",
                        status="pending",
                        due_date=date.today() + timedelta(days=20),
                    ),
                    Payment(
                        user_id=us["overseas_student"].id,
                        division="overseas",
                        reference_type="service_fee",
                        amount=25000,
                        currency="INR",
                        provider="razorpay",
                        status="paid",
                        provider_reference="DEMO-ST-2001",
                    ),
                ]
            )
        if not await db.scalar(select(Event).limit(1)):
            db.add_all(
                [
                    Event(
                        division="it",
                        title="GenAI Career Webinar",
                        event_type="Webinar",
                        starts_at=datetime.now(UTC) + timedelta(days=6),
                        location="Online",
                        description="Industry panel on GenAI careers.",
                    ),
                    Event(
                        division="overseas",
                        title="UK University Application Workshop",
                        event_type="University Webinar",
                        starts_at=datetime.now(UTC) + timedelta(days=9),
                        location="Online",
                        description="Admissions and scholarship guidance.",
                    ),
                    Event(
                        division="overseas",
                        title="Study Abroad Education Fair",
                        event_type="Education Fair",
                        starts_at=datetime.now(UTC) + timedelta(days=21),
                        location="Hyderabad",
                        description="Meet university representatives and counselors.",
                    ),
                ]
            )
        if not await db.scalar(select(Testimonial).limit(1)):
            db.add_all(
                [
                    Testimonial(
                        division="it", person_name="Rahul K", headline="Placed after Python training", quote="Project-based training and mock interviews helped me move into a backend role.", rating=5
                    ),
                    Testimonial(division="overseas", person_name="Sneha P", headline="Admission and visa support", quote="The counselor kept every document and deadline clear.", rating=5),
                ]
            )
        if not await db.scalar(select(CareerPath).limit(1)):
            db.add_all(
                [
                    CareerPath(
                        division="it",
                        slug="backend-engineer",
                        title="Backend Engineer",
                        summary="Design and build the APIs and data systems that power real applications.",
                        skills=["Python", "FastAPI", "SQL", "REST API design", "Testing"],
                        related_program_slugs=["python-full-stack"],
                        outcomes="Backend Developer, API Engineer, Platform Engineer roles at product and services companies.",
                    ),
                    CareerPath(
                        division="it",
                        slug="data-analyst",
                        title="Data Analyst",
                        summary="Turn raw data into decisions using SQL, Python and visualization tools.",
                        skills=["SQL", "Python", "Data visualization", "Statistics"],
                        related_program_slugs=[],
                        outcomes="Data Analyst, Business Analyst, Reporting Analyst roles.",
                    ),
                ]
            )
        if not await db.scalar(select(RealProject).limit(1)):
            db.add_all(
                [
                    RealProject(
                        division="it",
                        slug="student-placement-tracker",
                        title="Student Placement Tracker",
                        summary="A full-stack app tracking candidate applications through to offer.",
                        description="Learners build a complete application covering authentication, role-based access, a relational data model for candidates/companies/interviews, and a deployed API + frontend -- the same shape of work used in the EduSphere platform itself.",
                        tech_stack=["FastAPI", "PostgreSQL", "Next.js", "Docker"],
                    ),
                    RealProject(
                        division="it",
                        slug="attendance-analytics-dashboard",
                        title="Attendance & Progress Analytics Dashboard",
                        summary="A reporting dashboard aggregating attendance and assignment data per batch.",
                        description="Covers data aggregation queries, chart rendering, and role-scoped views (a Trainer sees only their own batches) -- a realistic slice of the reporting work EduSphere's own Trainer/Admin portals need.",
                        tech_stack=["Python", "SQL", "React"],
                    ),
                ]
            )
        if not await db.scalar(select(ContentPage).where(ContentPage.slug == "business-services").limit(1)):
            db.add(
                ContentPage(
                    division="it",
                    slug="business-services",
                    title="Business Services",
                    body="Corporate training, campus hiring drives, and technology staffing support for partner organisations. Contact our business team to discuss a partnership.",
                    seo={"title": "EduSphere Business Services"},
                )
            )
        if not await db.scalar(select(Enquiry).limit(1)):
            db.add_all(
                [
                    Enquiry(
                        division="it",
                        name="Demo IT Lead",
                        email="itlead@example.com",
                        phone="+919999000001",
                        subject="Python Full Stack",
                        message="Interested in the next evening batch.",
                        source="website",
                        status="new",
                        crm_sync_status="not_configured",
                    ),
                    Enquiry(
                        division="overseas",
                        name="Demo Overseas Lead",
                        email="overseaslead@example.com",
                        phone="+919999000002",
                        subject="Masters in UK",
                        message="Need profile evaluation for September intake.",
                        source="website",
                        status="contacted",
                        crm_sync_status="not_configured",
                    ),
                ]
            )
        if not await db.scalar(select(BlogPost).limit(1)):
            db.add_all(
                [
                    BlogPost(
                        division="it",
                        slug="building-a-python-career-portfolio",
                        title="Building a Python Career Portfolio",
                        summary="How projects, APIs and deployment evidence can strengthen a technology profile.",
                        body="A strong portfolio demonstrates the complete engineering lifecycle: requirements, code quality, testing, APIs, databases, deployment and documentation. EduSphere learners should use approved project work to build evidence of these capabilities.",
                        category="Career",
                        published=True,
                    ),
                    BlogPost(
                        division="overseas",
                        slug="planning-your-study-abroad-timeline",
                        title="Planning Your Study Abroad Timeline",
                        summary="A practical way to organise profile evaluation, applications, funding and visa preparation.",
                        body="Start early enough to compare destinations, confirm official entry requirements, prepare documents and leave room for university and visa processing. Always verify current deadlines and immigration requirements from official sources.",
                        category="Admissions",
                        published=True,
                    ),
                ]
            )
        if not await db.scalar(select(ContentPage).limit(1)):
            db.add_all(
                [
                    ContentPage(
                        division="it", slug="about", title="About EduSphere IT", body="Industry-focused IT training and placement support.", seo={"title": "EduSphere IT Training & Placement"}
                    ),
                    ContentPage(
                        division="overseas",
                        slug="about",
                        title="About EduSphere Overseas",
                        body="Admissions, visa and student guidance for global education.",
                        seo={"title": "EduSphere Overseas Education"},
                    ),
                ]
            )
        if not await db.scalar(select(GalleryItem).limit(1)):
            db.add_all(
                [
                    GalleryItem(division="it", title="Hands-on Training Session", image_url="/gallery/it-training.jpg", alt_text="EduSphere IT training session", category="Training"),
                    GalleryItem(division="it", title="Placement Preparation Workshop", image_url="/gallery/placement-workshop.jpg", alt_text="Placement preparation workshop", category="Placement"),
                    GalleryItem(
                        division="overseas",
                        title="University Information Session",
                        image_url="/gallery/university-session.jpg",
                        alt_text="University information session",
                        category="University Webinar",
                    ),
                    GalleryItem(division="overseas", title="Study Abroad Counseling", image_url="/gallery/counseling.jpg", alt_text="Study abroad counseling session", category="Counseling"),
                ]
            )
        if not await db.scalar(select(Notification).limit(1)):
            db.add_all(
                [
                    Notification(user_id=us["it_student"].id, title="Assignment due soon", body="Python Full Stack Assignment 1 is due this week.", action_url="/it/student/assignments"),
                    Notification(
                        user_id=us["overseas_student"].id,
                        title="Document verification pending",
                        body="Your Statement of Purpose is awaiting counselor review.",
                        action_url="/overseas/student/documents",
                    ),
                ]
            )
        if not await db.scalar(select(SupportTicket).limit(1)):
            db.add(
                SupportTicket(
                    user_id=us["it_student"].id,
                    division="it",
                    subject="Need access to class recording",
                    description="Please confirm recording access for the latest backend session.",
                    priority="normal",
                    status="open",
                )
            )
        if not await db.scalar(select(Message).limit(1)):
            db.add_all(
                [
                    Message(
                        division="overseas",
                        sender_id=us["counselor"].id,
                        recipient_id=us["overseas_student"].id,
                        context_type="counselor_chat",
                        body="I reviewed your academic profile. Please upload the final SOP draft before our next appointment.",
                    ),
                    Message(
                        division="overseas", sender_id=us["overseas_student"].id, recipient_id=us["counselor"].id, context_type="counselor_chat", body="Thank you. I will upload the updated SOP today."
                    ),
                ]
            )
        # School domain (SCH-001-006) -- one fully populated partner school so every School
        # report/dashboard (Admin's Schools/School Staff lists, and all seven School role
        # dashboards) shows real data locally/in dev, not an empty state. Two academic_team
        # members are seeded deliberately -- DEC-ROLE-007's same-actor rule means a result
        # can never be verified/published by the same member who uploaded it, so a single
        # academic_team account could never demonstrate a Published result here.
        school = await db.scalar(select(School).where(School.name == "Sunrise Public School"))
        if not school:
            school = School(name="Sunrise Public School", city="Hyderabad", state="Telangana", created_by_user_id=us["overseas_admin"].id)
            db.add(school)
            await db.flush()

            school_coordinator = await user(db, "school.coordinator@edusphere.local", "Fatima School Coordinator", "school_coordinator", "overseas")
            school_principal = await user(db, "school.principal@edusphere.local", "Rakesh School Principal", "school_principal", "overseas")
            school_teacher = await user(db, "school.teacher@edusphere.local", "Neha School Teacher", "school_teacher", "overseas")
            school_parent = await user(db, "school.parent@edusphere.local", "Vikram School Parent", "school_parent", "overseas")
            academic1 = await user(db, "school.academic1@edusphere.local", "Divya Academic Team", "academic_team", "overseas")
            academic2 = await user(db, "school.academic2@edusphere.local", "Suresh Academic Team", "academic_team", "overseas")
            career_counselor = await user(db, "school.careercounselor@edusphere.local", "Anita Career Counselor", "career_counselor", "overseas")
            psychometric_team = await user(db, "school.psychometric@edusphere.local", "Manoj Psychometric Team", "psychometric_team", "overseas")
            for u in (school_coordinator, school_principal, school_teacher, school_parent):
                u.profile = {"demo": True, "school_id": str(school.id)}
            db.add_all(
                [
                    UserRoleAssignment(user_id=school_coordinator.id, division="overseas", role="school_coordinator", is_active=True, assigned_by_user_id=us["overseas_admin"].id, approval_status="approved"),
                    UserRoleAssignment(user_id=school_principal.id, division="overseas", role="school_principal", is_active=True, assigned_by_user_id=school_coordinator.id, approval_status="approved"),
                    UserRoleAssignment(user_id=school_teacher.id, division="overseas", role="school_teacher", is_active=True, assigned_by_user_id=school_coordinator.id, approval_status="approved"),
                    UserRoleAssignment(user_id=school_parent.id, division="overseas", role="school_parent", is_active=True, assigned_by_user_id=school_coordinator.id, approval_status="approved"),
                    UserRoleAssignment(user_id=academic1.id, division="overseas", role="academic_team", is_active=True, assigned_by_user_id=us["overseas_admin"].id, approval_status="approved"),
                    UserRoleAssignment(user_id=academic2.id, division="overseas", role="academic_team", is_active=True, assigned_by_user_id=us["overseas_admin"].id, approval_status="approved"),
                    UserRoleAssignment(user_id=career_counselor.id, division="overseas", role="career_counselor", is_active=True, assigned_by_user_id=us["overseas_admin"].id, approval_status="approved"),
                    UserRoleAssignment(user_id=psychometric_team.id, division="overseas", role="psychometric_team", is_active=True, assigned_by_user_id=us["overseas_admin"].id, approval_status="approved"),
                    SchoolStaffAssignment(user_id=academic1.id, school_id=school.id, role="academic_team", assigned_by_user_id=us["overseas_admin"].id),
                    SchoolStaffAssignment(user_id=academic2.id, school_id=school.id, role="academic_team", assigned_by_user_id=us["overseas_admin"].id),
                    SchoolStaffAssignment(user_id=career_counselor.id, school_id=school.id, role="career_counselor", assigned_by_user_id=us["overseas_admin"].id),
                    SchoolStaffAssignment(user_id=psychometric_team.id, school_id=school.id, role="psychometric_team", assigned_by_user_id=us["overseas_admin"].id),
                ]
            )

            student_a = SchoolStudent(school_id=school.id, full_name="Aarav Mehta", date_of_birth=date(2015, 4, 12), grade_or_class="Grade 5", created_by_user_id=school_coordinator.id, assigned_teacher_user_id=school_teacher.id)
            student_b = SchoolStudent(school_id=school.id, full_name="Isha Mehta", date_of_birth=date(2017, 9, 3), grade_or_class="Grade 3", created_by_user_id=school_coordinator.id, assigned_teacher_user_id=school_teacher.id)
            student_c = SchoolStudent(school_id=school.id, full_name="Kabir Nair", date_of_birth=date(2016, 1, 20), grade_or_class="Grade 4", created_by_user_id=school_coordinator.id)
            db.add_all([student_a, student_b, student_c])
            await db.flush()
            db.add_all(
                [
                    # One Parent, two linked children -- demonstrates the roster's
                    # multi-child auto-link addendum, not just a single 1:1 link.
                    SchoolParentLink(parent_user_id=school_parent.id, school_student_id=student_a.id, linked_by_user_id=school_coordinator.id),
                    SchoolParentLink(parent_user_id=school_parent.id, school_student_id=student_b.id, linked_by_user_id=school_coordinator.id),
                ]
            )

            activity = SchoolActivity(school_id=school.id, title="Annual Sports Day", scheduled_at=datetime.now(UTC) + timedelta(days=10), created_by_user_id=school_coordinator.id)
            db.add(activity)
            await db.flush()
            db.add_all(
                [
                    SchoolActivityAttendance(activity_id=activity.id, school_student_id=student_a.id, present=True, marked_by_user_id=school_coordinator.id),
                    SchoolActivityAttendance(activity_id=activity.id, school_student_id=student_b.id, present=True, marked_by_user_id=school_coordinator.id),
                    SchoolActivityAttendance(activity_id=activity.id, school_student_id=student_c.id, present=False, marked_by_user_id=school_coordinator.id),
                ]
            )

            # Academic results across all three pipeline stages -- Published (so
            # Coordinator/Principal/Teacher/Parent read-only reports have something to
            # show), Verified (ready to publish), and Draft (never visible outside
            # academic_team, demonstrating the gate itself is real).
            published_result = SchoolAcademicResult(
                school_student_id=student_a.id, academic_year="2026", term="Term 1", subject="Mathematics", max_marks=100, marks_obtained=88, grade="A",
                status="published", uploaded_by_user_id=academic1.id, verified_by_user_id=academic2.id, verified_at=datetime.now(UTC) - timedelta(days=5), published_by_user_id=academic2.id, published_at=datetime.now(UTC) - timedelta(days=3),
            )
            verified_result = SchoolAcademicResult(
                school_student_id=student_b.id, academic_year="2026", term="Term 1", subject="English", max_marks=100, marks_obtained=76, grade="B+",
                status="verified", uploaded_by_user_id=academic1.id, verified_by_user_id=academic2.id, verified_at=datetime.now(UTC) - timedelta(days=1),
            )
            draft_result = SchoolAcademicResult(school_student_id=student_a.id, academic_year="2026", term="Term 1", subject="Science", max_marks=100, marks_obtained=91, status="draft", uploaded_by_user_id=academic1.id)
            db.add_all([published_result, verified_result, draft_result])
            await db.flush()
            db.add_all(
                [
                    SchoolResultStatusHistory(result_id=published_result.id, from_status="draft", to_status="verified", changed_by_user_id=academic2.id),
                    SchoolResultStatusHistory(result_id=published_result.id, from_status="verified", to_status="published", changed_by_user_id=academic2.id),
                    SchoolResultStatusHistory(result_id=verified_result.id, from_status="draft", to_status="verified", changed_by_user_id=academic2.id),
                ]
            )

            db.add_all(
                [
                    SchoolCareerRecord(school_student_id=student_a.id, career_counselor_user_id=career_counselor.id, record_type="guidance_session", notes="Discussed STEM vs. humanities track based on early aptitude signals."),
                    SchoolCareerRecord(school_student_id=student_c.id, career_counselor_user_id=career_counselor.id, record_type="counselling_note", notes="Follow-up planned next term on extracurricular interests."),
                ]
            )
            db.add_all(
                [
                    SchoolPsychometricRecord(school_student_id=student_a.id, psychometric_team_user_id=psychometric_team.id, assessment_type="Aptitude Test", report_url="/demo/aarav-aptitude-report.pdf", status="completed"),
                    SchoolPsychometricRecord(school_student_id=student_c.id, psychometric_team_user_id=psychometric_team.id, assessment_type="Personality Assessment", status="assigned"),
                ]
            )
        await db.commit()
    print("Seed complete; demo password:", PASSWORD)


if __name__ == "__main__":
    asyncio.run(main())
