import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identifiers import uuid_reference
from app.core.rbac import PERMISSIONS
from app.models import (
    AgentCommission,
    AgentStudent,
    Agreement,
    Appointment,
    Assessment,
    AssessmentAttempt,
    Assignment,
    Attendance,
    AttendanceCorrection,
    Batch,
    Certificate,
    Company,
    ConsentRecord,
    CourseFeedback,
    Enquiry,
    Enrollment,
    InboundUniversityEmail,
    Interview,
    Job,
    JobApplication,
    JobOffer,
    LearningResource,
    LiveSession,
    Message,
    OverseasApplication,
    Payment,
    PlacementProfile,
    Program,
    QuestionReply,
    UserRoleAssignment,
    QuestionThread,
    Scholarship,
    ScholarshipApplication,
    School,
    SchoolStaffAssignment,
    SchoolStudent,
    StudentDocument,
    Submission,
    SupportTicket,
    University,
    User,
    VisaCase,
)
from app.services.provisioning import provisioning_statuses, user_ids_with_status

logger = logging.getLogger("app.portal")


async def _safe[T](db: AsyncSession, fn: Callable[[], Awaitable[T]], default: T) -> T:
    """STU-002-AC02: a failed data source for one dashboard widget must not block the
    rest of the dashboard. A raised error inside a plain query poisons the whole
    Postgres transaction (every later query in the same session would then fail too),
    so each risky read runs in its own SAVEPOINT (`db.begin_nested()`) -- a failure
    there rolls back only that savepoint, leaving the outer transaction, and every
    other widget's query, unaffected."""

    try:
        async with db.begin_nested():
            return await fn()
    except Exception:
        logger.exception("dashboard widget query failed")
        return default


# ENH-003 / QA-005: the same wording the Super Admin table and the Manage users panel use for a user's setup state.
_SETUP_LABEL = {"active": "Password set", "pending_setup": "Awaiting setup", "link_expired": "Link expired"}


def _payload(title, subtitle, columns=(), rows=(), metrics=(), actions=(), panels=()):
    # A column tuple may be (key, label) or (key, label, type) -- `type` is an optional,
    # serializable string (e.g. "join") so the frontend `DataTable` can render that one
    # cell specially, per `PENDING_ZOHO_LIVE_CLASSES.md` §6/§1b(a) -- never a function,
    # since this crosses a JSON boundary.
    return {
        "title": title,
        "subtitle": subtitle,
        "metrics": list(metrics),
        "actions": list(actions),
        "columns": [{"key": column[0], "label": column[1], **({"type": column[2]} if len(column) > 2 else {})} for column in columns],
        "rows": list(rows),
        "panels": list(panels),
    }


async def _it_student(db: AsyncSession, user: User, section: str):
    enrollments = (
        await db.execute(
            select(Enrollment, Batch, Program)
            .join(Batch, Batch.id == Enrollment.batch_id)
            .join(Program, Program.id == Batch.program_id)
            .where(Enrollment.student_id == user.id)
            .order_by(Enrollment.created_at.desc())
        )
    ).all()
    batch_ids = [enrollment.batch_id for enrollment, _, _ in enrollments]
    if section == "dashboard":
        total = await _safe(db, lambda: db.scalar(select(func.count()).select_from(Attendance).where(Attendance.student_id == user.id)), None)
        present = await _safe(
            db, lambda: db.scalar(select(func.count()).select_from(Attendance).where(Attendance.student_id == user.id, Attendance.status.in_(["present", "late", "excused"]))), None
        )
        due = await _safe(db, lambda: db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.user_id == user.id, Payment.status.in_(["pending", "overdue"]))), None)
        applied_jobs = await _safe(db, lambda: db.scalar(select(func.count()).select_from(JobApplication).where(JobApplication.student_id == user.id)), None)
        upcoming_assignments: list[Assignment] = []
        if batch_ids:
            fetched = await _safe(
                db, lambda: db.scalars(select(Assignment).where(Assignment.batch_id.in_(batch_ids), Assignment.published.is_(True)).order_by(Assignment.due_date).limit(5)), None
            )
            upcoming_assignments = list(fetched) if fetched is not None else []
        return _payload(
            "Student Dashboard",
            "Your learning, fees, assessments, and placement journey.",
            (("title", "Upcoming work"), ("due", "Due")),
            ({"title": item.title, "due": item.due_date} for item in upcoming_assignments),
            (
                {"label": "Course progress", "value": f"{enrollments[0][0].progress_percent if enrollments else 0}%"},
                {"label": "Attendance", "value": f"{round(present * 100 / total) if total else 0}%" if total is not None and present is not None else "Unavailable"},
                {"label": "Pending fee", "value": f"INR {float(due):,.0f}" if due is not None else "Unavailable"},
                {"label": "Applied jobs", "value": applied_jobs if applied_jobs is not None else "Unavailable"},
                {"label": "Enrollments", "value": len(enrollments)},
            ),
            ({"label": "View assignments", "href": "/it/student/assignments"}, {"label": "Open course", "href": "/it/student/course"}, {"label": "Get support", "href": "/it/student/support"}),
        )
    if section == "profile":
        return _payload(
            "Profile",
            "Keep your contact, education, and career profile current.",
            (("field", "Field"), ("value", "Value")),
            (
                {"field": "Name", "value": user.full_name},
                {"field": "Email", "value": user.email},
                {"field": "Phone", "value": user.phone},
                {"field": "Education", "value": user.profile.get("education")},
                {"field": "Skills", "value": ", ".join(user.profile.get("skills", []))},
            ),
        )
    if section == "course":
        # "Available batches" (STU-001) and "Live classes" (STU-003) used to be dumped
        # here as unclickable text-panel strings -- both now have real interactive
        # components (BatchSlotPicker, LiveClassesPanel) rendered alongside this
        # section instead, each fetching its own clean, structured endpoint. Kept out
        # of this payload so the two representations can't drift apart or duplicate.
        return _payload(
            "Course Enrolled",
            "Your fixed schedule, live classes, provider recordings, and progress.",
            (("enrollment_id", "Enrollment reference"), ("program", "Program"), ("batch", "Batch"), ("schedule", "Schedule"), ("progress", "Progress"), ("status", "Status")),
            (
                {"batch_id": e.batch_id, "enrollment_id": e.enrollment_code, "program": p.title, "batch": b.name, "schedule": b.schedule, "progress": f"{e.progress_percent}%", "status": e.status}
                for e, b, p in enrollments
            ),
        )
    if section == "attendance":
        rows = (
            await db.execute(select(Attendance, Batch).join(Batch, Batch.id == Attendance.batch_id).where(Attendance.student_id == user.id).order_by(Attendance.session_date.desc()).limit(300))
        ).all()
        corrections = (await db.scalars(select(AttendanceCorrection).where(AttendanceCorrection.student_id == user.id).order_by(AttendanceCorrection.created_at.desc()).limit(30))).all()
        # STU-006 (PRD-STU-007): course/module completion % and outstanding blockers
        # (unfinished assignments) belong on this same read-only view, alongside
        # attendance -- not just a session list. STU-006-AC02: a session with no
        # Attendance row is simply absent from `rows` here, never synthesized as
        # "absent" -- there is no scheduled-session calendar independent of marking
        # to diff against, so omission already is the not-yet-recorded state.
        attendance_total = len(rows)
        attendance_present = sum(1 for a, _ in rows if a.status in ("present", "late", "excused"))
        attendance_percent = round(attendance_present * 100 / attendance_total) if attendance_total else None
        progress_percent = enrollments[0][0].progress_percent if enrollments else None
        blockers = []
        if batch_ids:
            assignments = (await db.scalars(select(Assignment).where(Assignment.batch_id.in_(batch_ids), Assignment.published.is_(True)).order_by(Assignment.due_date))).all()
            submitted_ids = set((await db.scalars(select(Submission.assignment_id).where(Submission.student_id == user.id))).all())
            blockers = [a for a in assignments if a.id not in submitted_ids]
        return _payload(
            "Attendance & Progress",
            "Session records, course completion, and outstanding work.",
            (("id", "Record reference"), ("batch", "Batch"), ("date", "Date"), ("status", "Status"), ("notes", "Notes")),
            ({"id": a.id, "batch": b.name, "date": a.session_date, "status": a.status, "notes": a.notes} for a, b in rows),
            (
                {"label": "Attendance", "value": f"{attendance_percent}%" if attendance_percent is not None else "No sessions recorded yet"},
                {"label": "Course progress", "value": f"{progress_percent}%" if progress_percent is not None else "Not enrolled"},
                {"label": "Outstanding blockers", "value": len(blockers)},
            ),
            panels=(
                {"title": "Correction requests", "items": [f"Request {c.id}: {c.requested_status} - {c.status}" for c in corrections]},
                {"title": "Outstanding blockers", "items": [f"{a.title} (due {a.due_date}) - not submitted" for a in blockers] or ["No outstanding blockers"]},
            ),
        )
    if section in {"assignments", "projects"}:
        assignment_type = "project" if section == "projects" else "assignment"
        work = (
            (
                await db.scalars(
                    select(Assignment).where(Assignment.batch_id.in_(batch_ids), Assignment.assignment_type == assignment_type, Assignment.published.is_(True)).order_by(Assignment.due_date)
                )
            ).all()
            if batch_ids
            else []
        )
        submissions = (await db.scalars(select(Submission).where(Submission.student_id == user.id))).all()
        by_assignment = {item.assignment_id: item for item in submissions}
        return _payload(
            section.title(),
            "Submit trainer-created work and review scores and feedback.",
            (("id", "reference"), ("title", "Title"), ("due", "Due"), ("submission", "Submission"), ("score", "Score"), ("feedback", "Feedback")),
            (
                {
                    "id": a.id,
                    "title": a.title,
                    "due": a.due_date,
                    # STU-004-AC02: a late submission is flagged here, never silently
                    # shown identically to an on-time one.
                    "submission": (
                        f"{by_assignment[a.id].status} (late)" if a.id in by_assignment and by_assignment[a.id].is_late else by_assignment[a.id].status if a.id in by_assignment else "not submitted"
                    ),
                    "score": f"{by_assignment[a.id].score}/{a.max_score}" if a.id in by_assignment and by_assignment[a.id].score is not None else None,
                    "feedback": by_assignment[a.id].feedback if a.id in by_assignment else None,
                }
                for a in work
            ),
        )
    if section == "examinations":
        # TRN-006-AC02: a Draft assessment must never be visible to Students -- this is
        # the only Student-facing assessment read, and it previously had no status filter
        # at all. Every other status (scheduled/open/closed/published) stays visible;
        # only "draft" is excluded.
        assessments = (
            (await db.scalars(select(Assessment).where(Assessment.batch_id.in_(batch_ids), Assessment.status != "draft").order_by(Assessment.scheduled_at))).all() if batch_ids else []
        )
        attempts = (await db.scalars(select(AssessmentAttempt).where(AssessmentAttempt.student_id == user.id).order_by(AssessmentAttempt.attempt_no.desc()))).all()
        latest = {}
        [latest.setdefault(a.assessment_id, a) for a in attempts]
        return _payload(
            "Examinations",
            "Timed trainer-authored assessments and published results.",
            (("id", "Assessment reference"), ("title", "Assessment"), ("scheduled", "Scheduled"), ("duration", "Minutes"), ("status", "Status"), ("result", "Result")),
            (
                {
                    "id": a.id,
                    "title": a.title,
                    "scheduled": a.scheduled_at,
                    "duration": a.duration_minutes,
                    "status": a.status,
                    "result": f"{float(latest[a.id].percentage):.1f}% ({latest[a.id].grade})" if a.id in latest and latest[a.id].percentage is not None else "not attempted",
                }
                for a in assessments
            ),
        )
    if section == "certificates":
        rows = (
            await db.execute(select(Certificate, Program).join(Program, Program.id == Certificate.program_id).where(Certificate.student_id == user.id).order_by(Certificate.issued_on.desc()))
        ).all()
        # STU-007: "file" used to surface the raw stored `file_url` here -- through the
        # generic table, which only ever renders plain text (never a link), that was an
        # inert string, not a working download. The real "Download" action now lives in
        # `CertificateDownloadPanel`, which exchanges `id` for a signed, short-lived URL
        # (`GET /workflows/it/certificates/{id}/download`) rather than exposing a
        # permanently-public object link here.
        return _payload(
            "Certificates",
            "Issued completion certificates with verification codes.",
            (("number", "Certificate"), ("program", "Program"), ("issued", "Issued"), ("status", "Status"), ("verification", "Verification")),
            ({"id": c.id, "number": c.certificate_no, "program": p.title, "issued": c.issued_on, "status": c.status, "verification": c.verification_code} for c, p in rows),
        )
    if section == "feedback":
        # STU-008-AC03: only a batch the student actually holds an Enrollment for is
        # offered here at all -- there is no free-text batch reference to submit against.
        given = set((await db.scalars(select(CourseFeedback.batch_id).where(CourseFeedback.student_id == user.id))).all())
        return _payload(
            "Course Feedback",
            "Share feedback on your enrolled course and trainer.",
            (("program", "Program"), ("batch", "Batch"), ("status", "Feedback status")),
            ({"batch_id": e.batch_id, "program": p.title, "batch": b.name, "status": "Submitted" if e.batch_id in given else "Not yet submitted"} for e, b, p in enrollments),
        )
    if section == "questions":
        threads = (await db.scalars(select(QuestionThread).where(QuestionThread.student_id == user.id).order_by(QuestionThread.created_at.desc()))).all()
        reply_counts = dict((await db.execute(select(QuestionReply.thread_id, func.count()).where(QuestionReply.thread_id.in_([t.id for t in threads])).group_by(QuestionReply.thread_id))).all()) if threads else {}
        batches_by_id = {b.id: b.name for _, b, _ in enrollments}
        return _payload(
            "My Questions",
            "Questions raised against your enrolled batch and trainer replies.",
            (("id", "Question reference"), ("batch", "Batch"), ("subject", "Subject"), ("status", "Status")),
            ({"id": t.id, "batch": batches_by_id.get(t.batch_id, "-"), "subject": t.subject, "status": f"{reply_counts.get(t.id, 0)} repl{'y' if reply_counts.get(t.id, 0) == 1 else 'ies'}" if reply_counts.get(t.id) else "Awaiting reply"} for t in threads),
        )
    if section == "fees":
        rows = (await db.scalars(select(Payment).where(Payment.user_id == user.id, Payment.division == "it").order_by(Payment.created_at.desc()))).all()
        return _payload(
            "Fee Status",
            "Installments, due dates, and provider status.",
            (("id", "Payment reference"), ("type", "Type"), ("amount", "Amount"), ("provider", "Provider"), ("due", "Due"), ("status", "Status")),
            ({"id": p.id, "type": p.reference_type, "amount": f"{p.currency} {float(p.amount):,.2f}", "provider": p.provider, "due": p.due_date, "status": p.status} for p in rows),
        )
    if section == "interview-schedule":
        rows = (
            await db.execute(
                select(Interview, Job, Company)
                .join(JobApplication, JobApplication.id == Interview.application_id)
                .join(Job, Job.id == JobApplication.job_id)
                .join(Company, Company.id == Job.company_id)
                .where(JobApplication.student_id == user.id)
                .order_by(Interview.scheduled_at)
            )
        ).all()
        return _payload(
            "Interview Schedule",
            "Mock and employer interview appointments.",
            (("role", "Role"), ("company", "Company"), ("scheduled", "Scheduled"), ("mode", "Mode"), ("link", "Meeting"), ("result", "Result")),
            ({"role": j.title, "company": c.name, "scheduled": i.scheduled_at, "mode": i.mode, "link": i.meeting_url, "result": i.result} for i, j, c in rows),
        )
    if section == "placement-status":
        profile = await db.scalar(select(PlacementProfile).where(PlacementProfile.student_id == user.id))
        offers = (
            await db.execute(
                select(JobOffer, Job, Company)
                .join(JobApplication, JobApplication.id == JobOffer.application_id)
                .join(Job, Job.id == JobApplication.job_id)
                .join(Company, Company.id == Job.company_id)
                .where(JobApplication.student_id == user.id)
            )
        ).all()
        rows = (
            ()
            if not profile
            else (
                {"stage": "Readiness", "status": profile.readiness_status},
                {"stage": "Resume", "status": profile.resume_status},
                {"stage": "Mock interview", "status": profile.mock_interview_status},
                {"stage": "Aptitude", "status": profile.aptitude_status},
                {"stage": "Available", "status": profile.available},
            )
        )
        return _payload(
            "Placement Status",
            "Preparation stages, offers, and joining progress.",
            (("stage", "Stage"), ("status", "Status")),
            rows,
            panels=({"title": "Offers", "items": [f"{c.name} - {j.title}: {o.status}" for o, j, c in offers]},),
        )
    if section == "job-applications":
        rows = (
            await db.execute(
                select(JobApplication, Job, Company)
                .join(Job, Job.id == JobApplication.job_id)
                .join(Company, Company.id == Job.company_id)
                .where(JobApplication.student_id == user.id)
                .order_by(JobApplication.created_at.desc())
            )
        ).all()
        open_jobs = (await db.execute(select(Job, Company).join(Company, Company.id == Job.company_id).where(Job.status == "open").order_by(Job.created_at.desc()).limit(100))).all()
        return _payload(
            "Job Applications",
            "Applications, interviews, offers, and joining status.",
            (("role", "Role"), ("company", "Company"), ("location", "Location"), ("status", "Status")),
            ({"role": j.title, "company": c.name, "location": j.location, "status": a.status} for a, j, c in rows),
            panels=({"title": "Open jobs", "items": [f"Job reference {j.id}: {c.name} / {j.title} / {j.location}" for j, c in open_jobs]},),
        )
    if section == "downloads":
        resources = (await db.scalars(select(LearningResource).where(LearningResource.batch_id.in_(batch_ids)).order_by(LearningResource.created_at.desc()))).all() if batch_ids else []
        return _payload(
            "Downloads",
            "Approved course materials and resources.",
            (("title", "Resource"), ("type", "Type"), ("url", "Download")),
            ({"title": r.title, "type": r.resource_type, "url": r.url} for r in resources),
        )
    if section == "support":
        rows = (await db.scalars(select(SupportTicket).where(SupportTicket.user_id == user.id).order_by(SupportTicket.created_at.desc()))).all()
        return _payload(
            "Support Tickets",
            "Learning, finance, and technical support requests.",
            (("id", "Ticket"), ("subject", "Subject"), ("priority", "Priority"), ("status", "Status")),
            ({"id": t.id, "subject": t.subject, "priority": t.priority, "status": t.status} for t in rows),
        )


async def _trainer(db: AsyncSession, user: User, section: str):
    batches = (await db.scalars(select(Batch).where(Batch.trainer_id == user.id).order_by(Batch.start_date.desc()))).all()
    batch_ids = [b.id for b in batches]
    if section == "dashboard":
        assignments = await db.scalar(select(func.count()).select_from(Assignment).where(Assignment.batch_id.in_(batch_ids))) if batch_ids else 0
        pending = (
            await db.scalar(select(func.count()).select_from(Submission).join(Assignment).where(Assignment.batch_id.in_(batch_ids), Submission.status.in_(["submitted", "resubmitted"])))
            if batch_ids
            else 0
        )
        sessions = await db.scalar(select(func.count()).select_from(LiveSession).where(LiveSession.batch_id.in_(batch_ids), LiveSession.status == "scheduled")) if batch_ids else 0
        return _payload(
            "Trainer Dashboard",
            "Assigned batches, learning work, live classes, and reviews.",
            (("batch", "Batch"), ("schedule", "Schedule"), ("capacity", "Capacity"), ("status", "Status")),
            ({"batch": b.name, "schedule": b.schedule, "capacity": b.capacity, "status": b.status} for b in batches),
            (
                {"label": "Assigned batches", "value": len(batches)},
                {"label": "Assignments", "value": assignments or 0},
                {"label": "Upcoming sessions", "value": sessions or 0},
                {"label": "Pending reviews", "value": pending or 0},
            ),
        )
    if section == "attendance":
        rows = (
            await db.execute(
                select(Attendance, User, Batch)
                .join(User, User.id == Attendance.student_id)
                .join(Batch, Batch.id == Attendance.batch_id)
                .where(Batch.trainer_id == user.id)
                .order_by(Attendance.session_date.desc())
                .limit(300)
            )
        ).all()
        corrections = (
            await db.execute(
                select(AttendanceCorrection, Attendance, User, Batch)
                .join(Attendance, Attendance.id == AttendanceCorrection.attendance_id)
                .join(User, User.id == AttendanceCorrection.student_id)
                .join(Batch, Batch.id == Attendance.batch_id)
                .where(Batch.trainer_id == user.id, AttendanceCorrection.status == "pending")
                .order_by(AttendanceCorrection.created_at.desc())
            )
        ).all()
        return _payload(
            "Student Attendance",
            "Mark attendance and review corrections.",
            (("student", "Student"), ("batch", "Batch"), ("date", "Date"), ("status", "Status")),
            ({"student": s.full_name, "batch": b.name, "date": a.session_date, "status": a.status} for a, s, b in rows),
            panels=({"title": "Pending corrections", "items": [f"{s.full_name} / {b.name} / {a.session_date} / {a.status} → {c.requested_status} / {c.reason}" for c, a, s, b in corrections]},),
        )
    if section == "assignments":
        rows = (await db.execute(select(Assignment, Batch).join(Batch, Batch.id == Assignment.batch_id).where(Batch.trainer_id == user.id).order_by(Assignment.due_date.desc()))).all()
        submissions = (
            (
                await db.execute(
                    select(Submission, Assignment, User)
                    .join(Assignment, Assignment.id == Submission.assignment_id)
                    .join(User, User.id == Submission.student_id)
                    .where(Assignment.batch_id.in_(batch_ids), Submission.status.in_(["submitted", "resubmitted", "revision_required"]))
                    .order_by(Submission.created_at.desc())
                )
            ).all()
            if batch_ids
            else []
        )
        return _payload(
            "Assignments",
            "Create assignments/projects, review submissions, and publish feedback.",
            (("title", "Title"), ("batch", "Batch"), ("type", "Type"), ("due", "Due")),
            ({"title": a.title, "batch": b.name, "type": a.assignment_type, "due": a.due_date} for a, b in rows),
            panels=({"title": "Submissions to review", "items": [f"{student.full_name} / {a.title} / {s.status}" for s, a, student in submissions]},),
        )
    if section == "assessments":
        rows = (await db.execute(select(Assessment, Batch).join(Batch, Batch.id == Assessment.batch_id).where(Batch.trainer_id == user.id).order_by(Assessment.scheduled_at.desc()))).all()
        return _payload(
            "Assessments",
            "Trainer-authored questions, attempts, and grading.",
            (("title", "Assessment"), ("batch", "Batch"), ("scheduled", "Scheduled"), ("status", "Status")),
            ({"title": a.title, "batch": b.name, "scheduled": a.scheduled_at, "status": a.status} for a, b in rows),
        )
    if section == "materials":
        rows = (
            await db.execute(select(LearningResource, Batch).join(Batch, Batch.id == LearningResource.batch_id).where(Batch.trainer_id == user.id).order_by(LearningResource.created_at.desc()))
        ).all()
        return _payload(
            "Course Materials",
            "Notes, links, and approved provider recordings.",
            (("resource", "Resource"), ("batch", "Batch"), ("type", "Type"), ("url", "URL")),
            ({"resource": r.title, "batch": b.name, "type": r.resource_type, "url": r.url} for r, b in rows),
        )
    if section == "live-sessions":
        rows = (await db.execute(select(LiveSession, Batch).join(Batch, Batch.id == LiveSession.batch_id).where(Batch.trainer_id == user.id).order_by(LiveSession.starts_at.desc()))).all()
        return _payload(
            "Live Sessions",
            "Schedule Google Meet, Zoho Meeting, or manual-provider sessions.",
            (("title", "Session"), ("batch", "Batch"), ("provider", "Provider"), ("starts", "Starts"), ("meeting", "Join", "join"), ("recording", "Recording")),
            # `ends_at`/`host_url` aren't shown as their own columns -- they back the
            # "join" cell's own time-window gating and host detection (`JoinSessionButton`).
            # The "meeting" cell itself now prefers `host_url` when present, matching
            # `LiveClassesPanel`'s own already-established "host gets the host link"
            # precedent -- previously this table showed the plain participant link even
            # to the trainer who owns the session.
            ({"title": s.title, "batch": b.name, "provider": s.provider, "starts": s.starts_at, "ends_at": s.ends_at, "meeting": s.host_url or s.meeting_url, "host_url": s.host_url, "recording": s.recording_url or s.recording_status} for s, b in rows),
        )
    if section == "student-progress":
        rows = (
            await db.execute(
                select(Enrollment, User, Batch)
                .join(User, User.id == Enrollment.student_id)
                .join(Batch, Batch.id == Enrollment.batch_id)
                .where(Batch.trainer_id == user.id, Enrollment.status == "active")
                .order_by(User.full_name)
            )
        ).all()
        return _payload(
            "Student Progress",
            "Progress and attendance risk across assigned batches.",
            (("student", "Student"), ("batch", "Batch"), ("enrollment", "Enrollment number"), ("progress", "Progress")),
            ({"student": s.full_name, "batch": b.name, "enrollment": e.enrollment_code, "progress": f"{e.progress_percent}%"} for e, s, b in rows),
        )
    if section == "support":
        # STU-005: division-scoped, not just batch-scoped -- any trainer in the division
        # can pick up a ticket, unassigned or not (STU-005-AC02: never hidden).
        rows = (await db.scalars(select(SupportTicket).where(SupportTicket.division == user.division).order_by(SupportTicket.created_at.desc()))).all()
        return _payload(
            "Support Tickets",
            "Student support requests for your division.",
            (("id", "Ticket"), ("subject", "Subject"), ("priority", "Priority"), ("status", "Status"), ("assigned", "Assigned")),
            ({"id": t.id, "subject": t.subject, "priority": t.priority, "status": t.status, "assigned": "Yes" if t.assigned_to_user_id else "Unassigned"} for t in rows),
        )
    if section == "questions":
        rows = (
            await db.execute(
                select(QuestionThread, User, Batch)
                .join(User, User.id == QuestionThread.student_id)
                .join(Batch, Batch.id == QuestionThread.batch_id)
                .where(Batch.trainer_id == user.id)
                .order_by(QuestionThread.created_at.desc())
            )
        ).all()
        thread_ids = [t.id for t, _, _ in rows]
        reply_counts = dict((await db.execute(select(QuestionReply.thread_id, func.count()).where(QuestionReply.thread_id.in_(thread_ids)).group_by(QuestionReply.thread_id))).all()) if thread_ids else {}
        return _payload(
            "Student Questions",
            "Questions raised by students in your batches -- reply below.",
            (("id", "Question reference"), ("student", "Student"), ("batch", "Batch"), ("subject", "Subject"), ("status", "Status")),
            ({"id": t.id, "student": s.full_name, "batch": b.name, "subject": t.subject, "status": "Answered" if reply_counts.get(t.id) else "Awaiting reply"} for t, s, b in rows),
        )


async def _overseas_student(db: AsyncSession, user: User, section: str):
    applications = (
        await db.execute(
            select(OverseasApplication, University)
            .join(University, University.id == OverseasApplication.university_id)
            .where(OverseasApplication.student_id == user.id)
            .order_by(OverseasApplication.updated_at.desc())
        )
    ).all()
    app_ids = [a.id for a, _ in applications]
    if section == "dashboard":
        documents = (await db.scalars(select(StudentDocument).where(StudentDocument.student_id == user.id))).all()
        visas = (await db.scalars(select(VisaCase).where(VisaCase.application_id.in_(app_ids)))).all() if app_ids else []
        return _payload(
            "Overseas Student Dashboard",
            "Current application status and next required action.",
            (("university", "University"), ("intake", "Intake"), ("status", "Status"), ("next_action", "Next action")),
            ({"university": u.name, "intake": a.intake, "status": a.status, "next_action": a.next_action} for a, u in applications),
            (
                {"label": "Applications", "value": len(applications)},
                {"label": "Verified documents", "value": sum(1 for d in documents if d.verification_status == "verified")},
                {"label": "Offers", "value": sum(1 for a, _ in applications if a.status in {"offer_received", "accepted"})},
                {"label": "Visa cases", "value": len(visas)},
            ),
        )
    if section == "profile":
        return _payload(
            "Profile",
            "Academic profile and study preferences.",
            (("field", "Field"), ("value", "Value")),
            (
                {"field": "Name", "value": user.full_name},
                {"field": "Education", "value": user.profile.get("education")},
                {"field": "Preferred countries", "value": ", ".join(user.profile.get("preferred_countries", []))},
                {"field": "Preferred intake", "value": user.profile.get("preferred_intake")},
                {"field": "English test", "value": user.profile.get("english_test")},
            ),
        )
    if section == "applications":
        universities = (await db.scalars(select(University).order_by(University.name).limit(200))).all()
        return _payload(
            "Applications",
            "Application stages and required next actions.",
            (("id", "reference"), ("university", "University"), ("reference", "Reference"), ("intake", "Intake"), ("status", "Status"), ("next_action", "Next action")),
            ({"id": a.id, "university": u.name, "reference": a.application_reference, "intake": a.intake, "status": a.status, "next_action": a.next_action} for a, u in applications),
            panels=({"title": "University catalogue IDs", "items": [f"University reference {u.id}: {u.name}, {u.city}" for u in universities]},),
        )
    if section == "documents":
        rows = (await db.scalars(select(StudentDocument).where(StudentDocument.student_id == user.id).order_by(StudentDocument.updated_at.desc()))).all()
        # OVS-005: "file" used to surface the raw stored `file_url` here -- through the
        # generic table, which only ever renders plain text (never a link), that was a
        # permanently-public object path, not the least-privilege access this feature's
        # own security note requires. The real "Download" action now lives in
        # `DocumentDownloadPanel`, which exchanges `id` for a real download URL (`GET
        # /workflows/overseas/documents/{id}/download`) rather than exposing the stored
        # value here.
        return _payload(
            "Documents",
            "Admission and visa documents and verification results.",
            (("id", "reference"), ("type", "Document"), ("status", "Verification"), ("notes", "Notes")),
            ({"id": d.id, "type": d.document_type, "status": d.verification_status, "notes": d.reviewer_notes} for d in rows),
        )
    if section == "offer-letters":
        return _payload(
            "Offer Letters",
            "Conditional and unconditional offers.",
            (("university", "University"), ("status", "Status"), ("offer", "Offer letter"), ("next_action", "Next action")),
            (
                {"university": u.name, "status": a.status, "offer": a.offer_letter_url, "next_action": a.next_action}
                for a, u in applications
                if a.offer_letter_url or a.status in {"offer_received", "accepted"}
            ),
        )
    if section == "visa-status":
        rows = (
            await db.execute(
                select(VisaCase, OverseasApplication, University)
                .join(OverseasApplication, OverseasApplication.id == VisaCase.application_id)
                .join(University, University.id == OverseasApplication.university_id)
                .where(OverseasApplication.student_id == user.id)
            )
        ).all()
        return _payload(
            "Visa Status",
            "Visa checklist, appointment, and decision tracking.",
            (("university", "University"), ("status", "Status"), ("appointment", "Appointment"), ("reference", "Reference")),
            ({"university": u.name, "status": v.status, "appointment": v.appointment_date, "reference": v.tracking_reference} for v, _, u in rows),
        )
    if section == "scholarships":
        # OVS-006: the public scholarship list already exists (`/public/scholarships`);
        # this is the self-scoped "your applications" half so the student-facing panel
        # can show which ones they've already applied to, not just an apply form.
        rows = (
            await db.execute(
                select(ScholarshipApplication, Scholarship)
                .join(Scholarship, Scholarship.id == ScholarshipApplication.scholarship_id)
                .where(ScholarshipApplication.student_id == user.id)
                .order_by(ScholarshipApplication.created_at.desc())
            )
        ).all()
        return _payload(
            "Scholarships",
            "Scholarship applications and their current status.",
            (("scholarship_id", "reference"), ("title", "Scholarship"), ("amount", "Amount"), ("status", "Status")),
            ({"scholarship_id": sa.scholarship_id, "title": s.title, "amount": s.amount, "status": sa.status} for sa, s in rows),
        )
    if section == "university-communication":
        rows = (await db.scalars(select(InboundUniversityEmail).where(InboundUniversityEmail.student_id == user.id).order_by(InboundUniversityEmail.received_at.desc()))).all()
        return _payload(
            "University Communication",
            "Automatically routed university correspondence.",
            (("sender", "From"), ("subject", "Subject"), ("received", "Received"), ("match", "Routing")),
            ({"sender": m.sender, "subject": m.subject, "received": m.received_at, "match": m.match_status} for m in rows),
        )
    if section == "payments":
        rows = (await db.scalars(select(Payment).where(Payment.user_id == user.id, Payment.division == "overseas").order_by(Payment.created_at.desc()))).all()
        return _payload(
            "Payments",
            "Service and application payment records.",
            (("id", "Payment reference"), ("type", "Type"), ("amount", "Amount"), ("provider", "Provider"), ("status", "Status")),
            ({"id": p.id, "type": p.reference_type, "amount": f"{p.currency} {float(p.amount):,.2f}", "provider": p.provider, "status": p.status} for p in rows),
        )
    if section == "appointments":
        rows = (await db.scalars(select(Appointment).where(Appointment.student_id == user.id, Appointment.division == "overseas").order_by(Appointment.scheduled_at.desc()))).all()
        return _payload(
            "Appointments",
            "Counseling, visa, and pre-departure appointments.",
            (("id", "reference"), ("type", "Appointment"), ("scheduled", "Scheduled"), ("mode", "Mode"), ("status", "Status")),
            ({"id": a.id, "type": a.appointment_type, "scheduled": a.scheduled_at, "mode": a.mode, "status": a.status} for a in rows),
        )
    if section == "counselor-chat":
        rows = (await db.scalars(select(Message).where(or_(Message.sender_id == user.id, Message.recipient_id == user.id)).order_by(Message.created_at.desc()).limit(200))).all()
        return _payload(
            "Counselor Chat",
            "Secure conversation history.",
            (("from", "Sender reference"), ("message", "Message"), ("sent", "Sent")),
            ({"from": m.sender_id, "message": m.body, "sent": m.created_at} for m in rows),
        )
    if section == "downloads":
        documents = (await db.scalars(select(StudentDocument).where(StudentDocument.student_id == user.id, StudentDocument.verification_status == "verified"))).all()
        rows = [{"name": d.document_type, "url": d.file_url} for d in documents] + [{"name": f"Offer letter - {u.name}", "url": a.offer_letter_url} for a, u in applications if a.offer_letter_url]
        return _payload("Downloads", "Verified documents and offer letters.", (("name", "Document"), ("url", "Download")), rows)


async def _agent(db: AsyncSession, user: User, section: str):
    students = (await db.execute(select(AgentStudent, User).join(User, User.id == AgentStudent.student_id).where(AgentStudent.agent_id == user.id))).all()
    applications = (
        await db.execute(
            select(OverseasApplication, University, User)
            .join(University, University.id == OverseasApplication.university_id)
            .join(User, User.id == OverseasApplication.student_id)
            .where(OverseasApplication.agent_id == user.id)
            .order_by(OverseasApplication.updated_at.desc())
        )
    ).all()
    # AGT-002: the roster below needs each referred student's application status
    # alongside the referral link itself -- `applications` is already scoped to this
    # agent, so pick each student's most recent application (already ordered above)
    # rather than issuing a second query.
    latest_application_by_student = {}
    for a, u, s in applications:
        latest_application_by_student.setdefault(s.id, (a, u))
    commissions = (await db.scalars(select(AgentCommission).where(AgentCommission.agent_id == user.id))).all()
    if section == "dashboard":
        return _payload(
            "Agent Dashboard",
            "Your students, applications, next actions, and commissions.",
            (("student", "Student"), ("university", "University"), ("status", "Status"), ("next_action", "Next action")),
            ({"student": s.full_name, "university": u.name, "status": a.status, "next_action": a.next_action} for a, u, s in applications),
            (
                {"label": "Students", "value": len(students)},
                {"label": "Applications", "value": len(applications)},
                {"label": "Claimable commission", "value": f"INR {sum(float(c.amount) for c in commissions if c.status in {'eligible', 'estimated'}):,.0f}"},
                {"label": "Claims", "value": sum(1 for c in commissions if c.status == "claimed")},
            ),
        )
    if section == "students":
        return _payload(
            "Students",
            "Students linked to your agency account, with each one's current application status (AGT-002).",
            (("id", "Student reference"), ("student", "Student"), ("email", "Email"), ("phone", "Phone"), ("status", "Referral status"), ("application_status", "Application status"), ("university", "University")),
            (
                {
                    "id": s.id,
                    "student": s.full_name,
                    "email": s.email,
                    "phone": s.phone,
                    "status": link.status,
                    "application_status": latest_application_by_student[s.id][0].status if s.id in latest_application_by_student else "No application yet",
                    "university": latest_application_by_student[s.id][1].name if s.id in latest_application_by_student else "-",
                }
                for link, s in students
            ),
        )
    if section == "applications":
        return _payload(
            "Applications",
            "Applications belonging to your linked students.",
            (("id", "reference"), ("student", "Student"), ("university", "University"), ("status", "Status"), ("next_action", "Next action")),
            ({"id": a.id, "student": s.full_name, "university": u.name, "status": a.status, "next_action": a.next_action} for a, u, s in applications),
        )
    if section == "documents":
        app_ids = [a.id for a, _, _ in applications]
        docs = (
            (
                await db.execute(
                    select(StudentDocument, User).join(User, User.id == StudentDocument.student_id).where(StudentDocument.application_id.in_(app_ids)).order_by(StudentDocument.updated_at.desc())
                )
            ).all()
            if app_ids
            else []
        )
        return _payload(
            "Documents",
            "Documents uploaded for your linked student applications.",
            (("id", "reference"), ("student", "Student"), ("document", "Document"), ("status", "Status"), ("file", "File")),
            ({"id": d.id, "student": s.full_name, "document": d.document_type, "status": d.verification_status, "file": d.file_url} for d, s in docs),
        )
    if section == "commissions":
        return _payload(
            "Commissions",
            "Eligibility, claims, and payment status.",
            (("id", "reference"), ("application", "Application"), ("amount", "Amount"), ("status", "Status"), ("claim", "Claim reference")),
            ({"id": c.id, "application": c.application_id, "amount": f"{c.currency} {float(c.amount):,.2f}", "status": c.status, "claim": c.claim_reference} for c in commissions),
        )
    if section == "reports":
        return _payload(
            "Agent Reports",
            "Application and commission summary.",
            (("metric", "Metric"), ("value", "Value")),
            (
                {"metric": "Students", "value": len(students)},
                {"metric": "Applications", "value": len(applications)},
                {"metric": "Offers", "value": sum(1 for a, _, _ in applications if a.status in {"offer_received", "accepted"})},
                {"metric": "Paid commission", "value": sum(float(c.amount) for c in commissions if c.status == "paid")},
            ),
        )


async def _operations(db: AsyncSession, user: User, section: str):
    if user.role in {"placement_team", "hr_team"}:
        if section == "dashboard":
            jobs = (await db.execute(select(Job, Company).join(Company, Company.id == Job.company_id).where(Job.status == "open"))).all()
            interviews = await db.scalar(select(func.count()).select_from(Interview)) or 0
            offers = await db.scalar(select(func.count()).select_from(JobOffer)) or 0
            return _payload(
                "Placement Dashboard" if user.role == "placement_team" else "HR Dashboard",
                "Candidate, requirement, interview, and offer operations.",
                (("role", "Role"), ("company", "Company"), ("location", "Location")),
                ({"role": j.title, "company": c.name, "location": j.location} for j, c in jobs),
                ({"label": "Open requirements", "value": len(jobs)}, {"label": "Interviews", "value": interviews}, {"label": "Offers", "value": offers}),
            )
        if section == "candidates":
            # ADM-007-AC02: a withdrawn candidate no longer appears in this active
            # matching pool -- their JobApplication/Interview/JobOffer history is
            # untouched (none of it references PlacementProfile) and stays visible via
            # the "interviews"/"offers" sections regardless.
            rows = (
                await db.execute(
                    select(User, PlacementProfile)
                    .outerjoin(PlacementProfile, PlacementProfile.student_id == User.id)
                    .where(User.role == "it_student", User.division == "it", or_(PlacementProfile.id.is_(None), PlacementProfile.withdrawn.is_(False)))
                )
            ).all()
            return _payload(
                "Candidate Database",
                "Placement readiness and availability.",
                (("id", "Student reference"), ("student", "Student"), ("skills", "Skills"), ("readiness", "Readiness"), ("available", "Available")),
                (
                    {
                        "id": s.id,
                        "student": s.full_name,
                        "skills": ", ".join(s.profile.get("skills", [])),
                        "readiness": p.readiness_status if p else "preparation",
                        "available": p.available if p else False,
                    }
                    for s, p in rows
                ),
            )
        if section in {"company-requirements", "job-requirements"}:
            # ADM-008, tester feedback 2026-09-04 (RAID.md I-13): `Job.closes_on` was
            # already collected by the "Create job requirement" form and already
            # enforced server-side (EMP-002-AC02 -- a job past its close date is hidden
            # from students even if never explicitly closed), but never shown back on
            # this table -- confirmed directly against the running app: HR could type a
            # close date and never see it again anywhere. Added the column here; no
            # write path change needed, `update_job` (workflows.py) already accepts
            # `closes_on` for this role.
            rows = (await db.execute(select(Job, Company).join(Company, Company.id == Job.company_id).order_by(Job.created_at.desc()))).all()
            return _payload(
                "Job Requirements",
                "Employer requirements and publication status.",
                (("id", "reference"), ("role", "Role"), ("company", "Company"), ("location", "Location"), ("status", "Status"), ("closes_on", "Closes on")),
                ({"id": j.id, "role": j.title, "company": c.name, "location": j.location, "status": j.status, "closes_on": j.closes_on} for j, c in rows),
            )
        if section == "shortlists":
            # ADM-008: "HR Team manages hiring requirements and shortlists." The real
            # interactive picker (select a requirement, view its shortlist) lives in
            # `HrShortlistPanel.tsx` below this generic payload -- kept out of this table
            # so the two representations can't drift, same pattern as STU-001/STU-003's
            # "course" section.
            return _payload("Requirement Shortlists", "Select a hiring requirement below to review its shortlisted candidates.", (), ())
        if section == "interviews":
            rows = (
                await db.execute(
                    select(Interview, JobApplication, Job, User)
                    .join(JobApplication, JobApplication.id == Interview.application_id)
                    .join(Job, Job.id == JobApplication.job_id)
                    .join(User, User.id == JobApplication.student_id)
                    .order_by(Interview.scheduled_at.desc())
                )
            ).all()
            return _payload(
                "Interviews",
                "Interview scheduling and outcomes.",
                (
                    ("id", "Interview reference"),
                    ("application_id", "Application reference"),
                    ("student", "Student"),
                    ("role", "Role"),
                    ("scheduled", "Scheduled"),
                    ("mode", "Mode"),
                    ("result", "Result"),
                ),
                ({"id": i.id, "application_id": a.id, "student": s.full_name, "role": j.title, "scheduled": i.scheduled_at, "mode": i.mode, "result": i.result} for i, a, j, s in rows),
            )
        if section == "offers":
            rows = (
                await db.execute(
                    select(JobOffer, JobApplication, Job, User)
                    .join(JobApplication, JobApplication.id == JobOffer.application_id)
                    .join(Job, Job.id == JobApplication.job_id)
                    .join(User, User.id == JobApplication.student_id)
                )
            ).all()
            return _payload(
                "Offer Management",
                "Offers, acceptance, and joining status.",
                (
                    ("id", "Offer reference"),
                    ("application_id", "Application reference"),
                    ("student", "Student"),
                    ("role", "Role"),
                    ("amount", "Compensation"),
                    ("status", "Status"),
                    ("joining", "Joining"),
                ),
                (
                    {
                        "id": o.id,
                        "application_id": a.id,
                        "student": s.full_name,
                        "role": j.title,
                        "amount": f"{o.currency} {float(o.compensation):,.2f}" if o.compensation is not None else None,
                        "status": o.status,
                        "joining": o.joining_date,
                    }
                    for o, a, j, s in rows
                ),
            )
        if section == "reports" and user.role == "placement_team":
            # RPT-001: same gap as IT Admin's own "reports" fix above -- `PORTAL_NAV
            # ["it/placement"]` lists "Reports" but no handler existed. Named scope:
            # "employer job activity, placement outcomes" -- derived from real Job/
            # JobApplication/JobOffer rows, never fabricated. Excludes `hr_team`, which
            # shares this outer role block for every other section -- not named in
            # `RPT-001-AC03`'s RBAC scope, so deliberately not extended to it here.
            job_rows = (await db.execute(select(Job, Company).join(Company, Company.id == Job.company_id).order_by(Company.name))).all()
            offers = (await db.scalars(select(JobOffer))).all()
            applications_count = await db.scalar(select(func.count()).select_from(JobApplication)) or 0
            company_names = sorted({c.name for _, c in job_rows})
            company_rows = [
                {
                    "company": name,
                    "open_requirements": sum(1 for j, c in job_rows if c.name == name and j.status == "open"),
                    "total_requirements": sum(1 for j, c in job_rows if c.name == name),
                }
                for name in company_names
            ]
            return _payload(
                "Placement Reports",
                "Employer job activity and placement outcomes.",
                (("company", "Company"), ("open_requirements", "Open requirements"), ("total_requirements", "Total requirements")),
                company_rows,
                (
                    {"label": "Job requirements", "value": len(job_rows)},
                    {"label": "Applications received", "value": applications_count},
                    {"label": "Offers made", "value": len(offers)},
                    {"label": "Offers accepted/joined", "value": sum(1 for o in offers if o.status in {"accepted", "joined"})},
                ),
            )
    if user.role in {"counselor", "university_rep", "overseas_admin"}:
        stmt = select(OverseasApplication, University, User).join(University, University.id == OverseasApplication.university_id).join(User, User.id == OverseasApplication.student_id)
        if user.role == "counselor":
            stmt = stmt.where(OverseasApplication.counselor_id == user.id)
        elif user.role == "university_rep":
            stmt = stmt.where(OverseasApplication.university_id == uuid_reference(user.profile.get("university_id"), "university reference", required=False))
        applications = (await db.execute(stmt.order_by(OverseasApplication.updated_at.desc()).limit(500))).all()
        app_ids = [a.id for a, _, _ in applications]
        if section == "dashboard":
            return _payload(
                "Counselor Dashboard" if user.role == "counselor" else "University Partner Dashboard" if user.role == "university_rep" else "Overseas Administration Dashboard",
                "Application pipeline and next actions.",
                (("student", "Student"), ("university", "University"), ("status", "Status"), ("next_action", "Next action")),
                ({"student": s.full_name, "university": u.name, "status": a.status, "next_action": a.next_action} for a, u, s in applications),
                (
                    {"label": "Applications", "value": len(applications)},
                    {"label": "Awaiting documents", "value": sum(1 for a, _, _ in applications if a.status in {"profile_evaluation", "documents_pending"})},
                    {"label": "Offers", "value": sum(1 for a, _, _ in applications if a.status in {"offer_received", "accepted"})},
                    # ENH-003 / QA-006: an admin's time-sensitive to-do belongs in the first viewport, not only in the panel below.
                    *(({"label": "Expired welcome links", "value": len(await user_ids_with_status(db, user, "link_expired"))},) if user.role == "overseas_admin" else ()),
                ),
            )
        if section == "offer-letters" and user.role == "university_rep":
            # UNI-001, tester feedback 2026-09-04: this nav item fell through to the
            # generic "Application Tracking" branch below -- byte-identical heading and
            # unfiltered rows to "Applications", indistinguishable from it. The Student
            # role's own "offer-letters" section (this file, ~line 576) already has a
            # dedicated, filtered view for the same underlying concept ("offer_letter_url
            # set, or status has reached offer/accepted") -- never extended to this role.
            # Mirrors that existing precedent rather than inventing a new one.
            return _payload(
                "Offer Letters",
                "Conditional and unconditional offers for applications sent to your institution.",
                (("student", "Student"), ("status", "Status"), ("offer", "Offer letter"), ("next_action", "Next action")),
                (
                    {"student": s.full_name, "status": a.status, "offer": a.offer_letter_url, "next_action": a.next_action}
                    for a, u, s in applications
                    if a.offer_letter_url or a.status in {"offer_received", "accepted"}
                ),
            )
        if section in {"students", "applications", "admission-updates", "offer-letters"}:
            return _payload(
                "Application Tracking",
                "Assigned applications and next actions.",
                (("id", "reference"), ("student", "Student"), ("university", "University"), ("reference", "Reference"), ("status", "Status"), ("next_action", "Next action")),
                ({"id": a.id, "student_id": s.id, "student": s.full_name, "university": u.name, "reference": a.application_reference, "status": a.status, "next_action": a.next_action} for a, u, s in applications),
            )
        if section == "documents":
            docs = (
                (
                    await db.execute(
                        select(StudentDocument, User).join(User, User.id == StudentDocument.student_id).where(StudentDocument.application_id.in_(app_ids)).order_by(StudentDocument.updated_at.desc())
                    )
                ).all()
                if app_ids
                else []
            )
            return _payload(
                "Document Verification",
                "Admission and visa document review queue.",
                (("id", "reference"), ("student", "Student"), ("document", "Document"), ("status", "Status"), ("notes", "Notes")),
                ({"id": d.id, "student": s.full_name, "document": d.document_type, "status": d.verification_status, "notes": d.reviewer_notes} for d, s in docs),
            )
        if section == "visa":
            visas = (
                (
                    await db.execute(
                        select(VisaCase, OverseasApplication, User)
                        .join(OverseasApplication, OverseasApplication.id == VisaCase.application_id)
                        .join(User, User.id == OverseasApplication.student_id)
                        .where(VisaCase.application_id.in_(app_ids))
                    )
                ).all()
                if app_ids
                else []
            )
            return _payload(
                "Visa Tracking",
                "Visa checklists, appointments, and outcomes.",
                (("id", "reference"), ("student", "Student"), ("status", "Status"), ("appointment", "Appointment"), ("reference", "Reference")),
                ({"id": v.id, "student": s.full_name, "status": v.status, "appointment": v.appointment_date, "reference": v.tracking_reference} for v, _, s in visas),
            )
        if section == "appointments":
            student_ids = [a.student_id for a, _, _ in applications]
            rows = (await db.scalars(select(Appointment).where(Appointment.student_id.in_(student_ids)).order_by(Appointment.scheduled_at.desc()))).all() if student_ids else []
            return _payload(
                "Appointments",
                "Counseling and visa appointment operations.",
                (("id", "reference"), ("student_id", "Student reference"), ("type", "Type"), ("scheduled", "Scheduled"), ("status", "Status")),
                ({"id": a.id, "student_id": a.student_id, "type": a.appointment_type, "scheduled": a.scheduled_at, "status": a.status} for a in rows),
            )
        if section in {"university-communication", "student-communication"}:
            rows = (
                (await db.scalars(select(InboundUniversityEmail).where(InboundUniversityEmail.application_id.in_(app_ids)).order_by(InboundUniversityEmail.received_at.desc()))).all()
                if app_ids
                else []
            )
            return _payload(
                "University Communication",
                "Routed university emails and matching status.",
                (("sender", "From"), ("subject", "Subject"), ("received", "Received"), ("match", "Routing")),
                ({"sender": m.sender, "subject": m.subject, "received": m.received_at, "match": m.match_status} for m in rows),
            )
        if section == "leads" and user.role == "counselor":
            # CNS-001: PORTAL_NAV lists "Leads" for the Counselor workspace, but no
            # section handler existed for it at all -- the link 404'd ("Workspace not
            # found") before this. `Enquiry.owner_id` (DATA_MODEL.md #2.3) is the real,
            # already-existing routing mechanism (ADM-002 already lets Admin set it) --
            # scoped here to leads actually routed to this Counselor, never the full
            # division-wide queue that only Admin sees.
            rows = (await db.scalars(select(Enquiry).where(Enquiry.division == "overseas", Enquiry.owner_id == user.id).order_by(Enquiry.created_at.desc()))).all()
            return _payload(
                "My Leads",
                "Enquiries routed to you.",
                (("id", "reference"), ("name", "Name"), ("subject", "Interest"), ("status", "Status")),
                ({"id": e.id, "name": e.name, "subject": e.subject, "status": e.status} for e in rows),
            )
        if section == "reports" and user.role == "counselor":
            # CNS-001: same gap as "leads" -- PORTAL_NAV lists "Reports" but no handler
            # existed. A real aggregate of this Counselor's own already-scoped caseload,
            # not a fabricated metric.
            docs = (
                (await db.scalars(select(StudentDocument).where(StudentDocument.application_id.in_(app_ids)))).all()
                if app_ids
                else []
            )
            visas = (
                (await db.scalars(select(VisaCase).where(VisaCase.application_id.in_(app_ids)))).all()
                if app_ids
                else []
            )
            return _payload(
                "My Caseload Report",
                "Aggregate status across your assigned applications.",
                (("status", "Application status"), ("count", "Count")),
                ({"status": status, "count": sum(1 for a, _, _ in applications if a.status == status)} for status in sorted({a.status for a, _, _ in applications})),
                (
                    {"label": "Assigned applications", "value": len(applications)},
                    {"label": "Documents pending verification", "value": sum(1 for d in docs if d.verification_status == "pending")},
                    {"label": "Active visa cases", "value": len(visas)},
                ),
            )
        if section == "reports" and user.role == "university_rep":
            # UNI-001: same gap class as CNS-001's own "leads"/"reports" fix above --
            # PORTAL_NAV lists "Reports" for the university rep workspace too, but this
            # handler was counselor-only, so the Rep's own link 404'd ("Workspace not
            # found"), confirmed directly. A real aggregate of this Rep's own
            # already-scoped (university_id) applications -- offer stage onward per the
            # confirmed `OVERSEAS_APPLICATION_STAGES` sequence, not an invented status.
            offer_onward = {"offer", "visa_documentation", "status_tracking", "enrolled"}
            return _payload(
                "University Partner Report",
                "Aggregate status across applications sent to your institution.",
                (("status", "Application status"), ("count", "Count")),
                ({"status": status, "count": sum(1 for a, _, _ in applications if a.status == status)} for status in sorted({a.status for a, _, _ in applications})),
                (
                    {"label": "Applications", "value": len(applications)},
                    {"label": "Offers extended", "value": sum(1 for a, _, _ in applications if a.status in offer_onward)},
                ),
            )
        if section == "counselor-chat" and user.role == "counselor":
            # RAID.md I-19: `PORTAL_NAV` never listed this section for the Counselor role
            # at all -- the Student side's own `counselor-chat` (`ROLE_ACTION_MATRIX.md`'s
            # confirmed "direct messaging with their assigned counselor") had a read-only
            # history view and, until this same fix, no way to send. A one-sided send with
            # no page for the counselor to ever see or reply isn't real messaging -- same
            # generic query as the Student side's own section (`_overseas_student`,
            # sender or recipient = the current user), reused here rather than duplicated
            # differently.
            rows = (await db.scalars(select(Message).where(or_(Message.sender_id == user.id, Message.recipient_id == user.id)).order_by(Message.created_at.desc()).limit(200))).all()
            return _payload(
                "Counselor Chat",
                "Secure conversation history with your assigned students.",
                (("from", "Sender reference"), ("message", "Message"), ("sent", "Sent")),
                ({"from": m.sender_id, "message": m.body, "sent": m.created_at} for m in rows),
            )
        if section == "reports" and user.role == "overseas_admin":
            # RPT-002, tester feedback 2026-09-04 (RAID.md I-14): "reports not working"
            # traced (by direct reproduction against the running app, not guessed from
            # the report alone) to Overseas Admin's own "Reports" link, which showed
            # "Access unavailable -- Workspace not found" -- `PORTAL_NAV["overseas/
            # admin"]` lists "Reports" but no handler ever existed for this role
            # (`RPT-002` was `NOT_STARTED`, not a regression). Named scope
            # (`RPT-002-AC01`): "application funnel by stage, agent commission report,
            # visa-status aging". Dependencies confirmed sufficient: `AGT-003` (commission
            # accrual) is complete; `OVS-004` is complete for the read side this report
            # needs. `applications`/`app_ids` above are already unscoped for this role (no
            # `.where()` added in the shared query above), matching the confirmed
            # "Overseas Admin" RBAC scope -- division-wide, not narrowed to Counselor's or
            # University Rep's own precedent in this same block.
            stages = ["enquiry", "eligibility_evaluation", "university_selection", "offer", "visa_documentation", "status_tracking", "enrolled"]
            funnel = {stage: 0 for stage in stages}
            for a, _, _ in applications:
                if a.status in funnel:
                    funnel[a.status] += 1
            visa_rows = (
                (
                    await db.execute(
                        select(VisaCase, OverseasApplication, User)
                        .join(OverseasApplication, OverseasApplication.id == VisaCase.application_id)
                        .join(User, User.id == OverseasApplication.student_id)
                        .where(VisaCase.application_id.in_(app_ids))
                        .order_by(VisaCase.updated_at.asc())
                    )
                ).all()
                if app_ids
                else []
            )
            now = datetime.now(UTC)
            commissions = (await db.execute(select(AgentCommission, User).join(User, User.id == AgentCommission.agent_id))).all()
            commission_summary: dict[str, dict] = {}
            for commission, agent in commissions:
                bucket = commission_summary.setdefault(agent.full_name, {})
                key = commission.currency
                entry = bucket.setdefault(key, {"count": 0, "total": 0.0, "pending": 0})
                entry["count"] += 1
                entry["total"] += float(commission.amount)
                if commission.status in {"estimated", "eligible", "claimed", "payout_pending"}:
                    entry["pending"] += 1
            return _payload(
                "Overseas Partner Reports",
                "Application funnel by stage, agent commission report, and visa-status aging.",
                (("student", "Student"), ("status", "Visa status"), ("appointment", "Appointment"), ("days_since_update", "Days in current status")),
                (
                    {
                        "student": s.full_name,
                        "status": v.status,
                        "appointment": v.appointment_date,
                        "days_since_update": (now - v.updated_at).days,
                    }
                    for v, _, s in visa_rows
                ),
                tuple({"label": stage.replace("_", " ").title(), "value": count} for stage, count in funnel.items()),
                panels=(
                    {
                        "title": "Agent commission report",
                        "items": [
                            f"{agent}: {currency} {data['total']:,.2f} across {data['count']} commission(s), {data['pending']} pending payout"
                            for agent, buckets in sorted(commission_summary.items())
                            for currency, data in sorted(buckets.items())
                        ] or ["No agent commissions recorded yet."],
                    },
                ),
            )
        if section == "school-applications" and user.role in {"counselor", "overseas_admin"}:
            # SCH-010 (DEC-SCOPE-018): read-only summary of bridged School->Overseas
            # applications -- creation itself is handled by AdminSchoolApplicationsPanel.tsx
            # (POST /overseas-admin/school-students/{id}/applications), same "read via the
            # generic portal section, write via a dedicated panel" split as `schools` above.
            # Joined against SchoolStudent, never User, since a bridged row has no User.
            stmt = (
                select(OverseasApplication, SchoolStudent, University)
                .join(SchoolStudent, SchoolStudent.id == OverseasApplication.school_student_id)
                .join(University, University.id == OverseasApplication.university_id)
                .where(OverseasApplication.school_student_id.is_not(None))
                .order_by(OverseasApplication.created_at.desc())
            )
            if user.role == "counselor":
                stmt = stmt.where(OverseasApplication.counselor_id == user.id)
            rows = (await db.execute(stmt)).all()
            return _payload(
                "School-Linked Overseas Applications",
                "Overseas applications started for School-affiliated students. Start a new one below by Student ID.",
                (("id", "reference"), ("student", "Student"), ("student_code", "Student ID"), ("university", "University"), ("status", "Status")),
                ({"id": a.id, "student": s.full_name, "student_code": s.student_code, "university": u.name, "status": a.status} for a, s, u in rows),
            )
    if user.role in {"it_admin", "overseas_admin", "super_admin"}:
        division = user.division if user.role != "super_admin" else None
        if section == "dashboard":
            users_q = select(func.count()).select_from(User)
            leads_q = select(func.count()).select_from(Enquiry)
            payments_q = select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "paid")
            if division:
                users_q = users_q.where(User.division == division)
                leads_q = leads_q.where(Enquiry.division == division)
                payments_q = payments_q.where(Payment.division == division)
            return _payload(
                "Administration Dashboard",
                "Live operational overview for your division.",
                (("area", "Area"), ("status", "Status")),
                (
                    {"area": "Authentication and RBAC", "status": "Active"},
                    {"area": "Provider integrations", "status": "Configuration dependent"},
                    {"area": "Background notifications", "status": "Active"},
                ),
                (
                    {"label": "Users", "value": await db.scalar(users_q) or 0},
                    {"label": "Enquiries", "value": await db.scalar(leads_q) or 0},
                    {"label": "Collected payments", "value": f"INR {float(await db.scalar(payments_q) or 0):,.0f}"},
                    # ENH-003 / QA-006: same scoped count the Super Admin dashboard already leads with.
                    {"label": "Expired welcome links", "value": len(await user_ids_with_status(db, user, "link_expired"))},
                ),
            )
        if section == "reports" and user.role in {"it_admin", "super_admin"}:
            # RPT-001: `PORTAL_NAV["it/admin"]` lists "Reports" but no handler existed at
            # all -- confirmed directly, same 404 bug class `CNS-001`/`UNI-001` found for
            # their own roles. Named scope: "enrolment funnel, course performance, student
            # progress" -- each derived from real, already-existing data (Enquiry ->
            # Enrollment -> Certificate is the actual funnel; per-course figures come from
            # real `Enrollment.progress_percent` averages), never a fabricated/zero-filled
            # placeholder (`RPT-001-AC02`) -- an honest computed 0 from a genuinely empty
            # dataset is not a fabrication. Excludes `overseas_admin` -- out of this
            # feature's confirmed RBAC scope (`RPT-001-AC03`), left for `RPT-002`.
            leads_count = await db.scalar(select(func.count()).select_from(Enquiry).where(Enquiry.division == "it")) or 0
            enrollments = (await db.scalars(select(Enrollment))).all()
            certificates_count = await db.scalar(select(func.count()).select_from(Certificate)) or 0
            programs = (await db.scalars(select(Program).order_by(Program.title))).all()
            batch_program = dict((await db.execute(select(Batch.id, Batch.program_id))).all())
            course_rows = []
            for p in programs:
                batch_ids = {b_id for b_id, prog_id in batch_program.items() if prog_id == p.id}
                p_enrollments = [e for e in enrollments if e.batch_id in batch_ids]
                avg_progress = round(sum(e.progress_percent for e in p_enrollments) / len(p_enrollments), 1) if p_enrollments else 0
                course_rows.append({"course": p.title, "enrollments": len(p_enrollments), "avg_progress": avg_progress})
            return _payload(
                "IT Reports",
                "Enrolment funnel, course performance, and student progress.",
                (("course", "Course"), ("enrollments", "Enrollments"), ("avg_progress", "Avg. progress %")),
                course_rows,
                (
                    {"label": "Leads", "value": leads_count},
                    {"label": "Enrolments", "value": len(enrollments)},
                    {"label": "Certificates issued", "value": certificates_count},
                    {"label": "Active enrolments", "value": sum(1 for e in enrollments if e.status == "active")},
                ),
            )
        if section == "resources" and user.role in {"it_admin", "super_admin"}:
            # ADM-009: mirrors the Trainer's own "materials" section (services/portal.py
            # `_trainer`, same LearningResource+Batch join) but unscoped across every
            # batch/trainer, not just the caller's own -- that cross-trainer oversight is
            # the entire point of this feature. Batches/Programs have no `division` field
            # (Overseas has no batches at all), so no division filter applies here.
            rows = (
                await db.execute(
                    select(LearningResource, Batch, User)
                    .join(Batch, Batch.id == LearningResource.batch_id)
                    .outerjoin(User, User.id == Batch.trainer_id)
                    .order_by(LearningResource.created_at.desc())
                    .limit(500)
                )
            ).all()
            return _payload(
                "Resources & Recordings",
                "Trainer-uploaded course resources and recordings across every batch.",
                (("resource", "Resource"), ("batch", "Batch"), ("trainer", "Trainer"), ("type", "Type"), ("url", "URL")),
                ({"resource": r.title, "batch": b.name, "trainer": t.full_name if t else "Unassigned", "type": r.resource_type, "url": r.url} for r, b, t in rows),
            )
        if section == "consent" and user.role in {"it_admin", "super_admin"}:
            # ADM-010: mirrors ADM-009's shape -- STU-009's self-scoped agreement/consent
            # flow (GET/POST /workflows/it/student/agreements...) already existed and
            # worked; no cross-student Admin oversight existed anywhere. Agreements are
            # division="it" only (no Overseas equivalent named anywhere), matching this
            # feature's own IT-Admin-only RBAC. Every it_student is listed even if they
            # have never consented at all -- an honest "not yet" row, never omitted.
            agreement = await db.scalar(select(Agreement).where(Agreement.division == "it", Agreement.active.is_(True)).order_by(Agreement.created_at.desc()))
            # Ordered by most-recently-created, not name -- matches the `role_map`
            # section's own convention below, and (RAID.md I-06) the shared dev DB has
            # accumulated thousands of synthetic `it_student` rows over the session, so
            # an alphabetical cap would near-never surface a freshly created student.
            students = (await db.scalars(select(User).where(User.role == "it_student", User.division == "it").order_by(User.created_at.desc()).limit(500))).all()
            consents = {}
            if agreement:
                rows = (await db.scalars(select(ConsentRecord).where(ConsentRecord.agreement_id == agreement.id, ConsentRecord.user_id.in_([s.id for s in students])))).all()
                consents = {c.user_id: c for c in rows}
            pending_counts = dict(
                (await db.execute(
                    select(Enrollment.student_id, func.count())
                    .where(Enrollment.status == "pending_consent", Enrollment.student_id.in_([s.id for s in students]))
                    .group_by(Enrollment.student_id)
                )).all()
            ) if students else {}
            return _payload(
                "Agreement & Consent Oversight",
                f"Consent status for {agreement.title} ({agreement.version})." if agreement else "No active enrolment agreement is configured.",
                (("student", "Student"), ("email", "Email"), ("consented", "Consented"), ("accepted_at", "Accepted"), ("pending", "Pending enrolments")),
                (
                    {
                        "student": s.full_name,
                        "email": s.email,
                        "consented": "Yes" if s.id in consents else "Not yet",
                        "accepted_at": consents[s.id].created_at if s.id in consents else None,
                        "pending": pending_counts.get(s.id, 0),
                    }
                    for s in students
                ),
            )
        if section == "roles" and user.role in {"it_admin", "super_admin"}:
            # ADM-012 -- PARTIAL scope, deliberately: the confirmed requirement
            # (`PRD-ADM-013`) is "Admin can view role/permission assignments"; whether
            # permissions should be admin-configurable at runtime "was never asked"
            # (PRD.md's own status for this requirement) and `core/rbac.py`'s `PERMISSIONS`
            # is a static code table with no DB-backed concept to edit -- building live
            # permission editing here would mean inventing a security-critical runtime
            # engine on an explicitly unconfirmed requirement, not extending a confirmed
            # one. This lists the real, currently-enforced bundle per role (straight from
            # `core/rbac.py`, never a hand-copied duplicate that could drift from what's
            # actually enforced) plus how many active users hold each role. No write
            # endpoint exists -- flagged in `PRD_OPEN_ITEMS.md`, not silently omitted.
            user_counts = dict((await db.execute(select(User.role, func.count()).group_by(User.role))).all())
            return _payload(
                "Roles & Permissions",
                "Read-only: the permission bundle actually enforced per role. Runtime editing is an open item (PRD-ADM-013), not built here.",
                (("role", "Role"), ("permissions", "Permissions"), ("users", "Active users")),
                (
                    {"role": role, "permissions": ", ".join(sorted(perms)), "users": user_counts.get(role, 0)}
                    for role, perms in sorted(PERMISSIONS.items())
                ),
            )
        role_map = {"users": None, "students": "it_student" if division == "it" else "overseas_student", "trainers": "trainer", "counselors": "counselor"}
        if section in role_map:
            stmt = select(User)
            stmt = stmt.where(User.division == division) if division else stmt
            if role_map[section]:
                stmt = stmt.where(User.role == role_map[section])
            rows = (await db.scalars(stmt.order_by(User.created_at.desc()).limit(500))).all()
            setup = await provisioning_statuses(db, [u.id for u in rows])  # absent = has set a password
            return _payload(
                section.title(),
                "Role-scoped user administration.",
                (("id", "reference"), ("name", "Name"), ("email", "Email"), ("role", "Role"), ("active", "Active"), ("setup", "Setup")),
                ({"id": u.id, "name": u.full_name, "email": u.email, "role": u.role, "active": u.active, "setup": _SETUP_LABEL[setup.get(u.id, "active")]} for u in rows),
            )
        if section == "agents" and division == "overseas":
            # AGT-001: Overseas Admin's own approve/reject queue -- the generic
            # role_map listing below has no `approval_status` column to show at all.
            rows = (
                await db.execute(
                    select(User, UserRoleAssignment).join(UserRoleAssignment, UserRoleAssignment.user_id == User.id).where(User.role == "agent", UserRoleAssignment.role == "agent").order_by(User.created_at.desc())
                )
            ).all()
            return _payload(
                "Agent Registrations",
                "Approve or reject Agent self-registrations.",
                (("id", "reference"), ("name", "Name"), ("email", "Email"), ("status", "Approval status")),
                ({"id": agent.id, "name": agent.full_name, "email": agent.email, "status": assignment.approval_status} for agent, assignment in rows),
            )
        if section == "schools" and division == "overseas":
            # SCH-003 / ENH-009 (DEC-SCOPE-025): Overseas Admin's own partner-school list --
            # creation/edit handled by AdminSchoolCreatePanel.tsx/AdminSchoolEditPanel.tsx, same
            # "read via the generic portal section, write via a dedicated panel" split already
            # established for `universities` (RAID.md I-32).
            rows = (await db.scalars(select(School).order_by(School.created_at.desc()))).all()
            return _payload(
                "Partner Schools",
                "Every School partner record. Create a new one to seed its Coordinator account.",
                (("id", "reference"), ("school_code", "School ID"), ("name", "Name"), ("branch", "Branch"), ("city", "City"), ("state", "State"), ("board", "Board"), ("tier", "Tier"), ("created_at", "Created")),
                ({"id": s.id, "school_code": s.school_code or "-", "name": s.name, "branch": s.branch or "-", "city": s.city or "-", "state": s.state or "-", "board": s.board or "-", "tier": s.tier or "-", "created_at": s.created_at} for s in rows),
            )
        if section == "school-staff" and division == "overseas":
            # SCH-004/005/006 (DEC-SCOPE-014): Academic Team/Career Counselor/Psychometric
            # Team accounts -- creation and portfolio management handled by
            # AdminSchoolStaffPanel.tsx, same split as `schools` above.
            service_roles = ("academic_team", "career_counselor", "psychometric_team")
            rows = (await db.scalars(select(User).where(User.role.in_(service_roles)).order_by(User.created_at.desc()))).all()
            assignments = (await db.scalars(select(SchoolStaffAssignment))).all()
            portfolio_counts: dict = {}
            for a in assignments:
                portfolio_counts[a.user_id] = portfolio_counts.get(a.user_id, 0) + 1
            return _payload(
                "Academic Team / Career Counselor / Psychometric Team",
                "Every specialized School service-delivery staff account and how many schools are in their portfolio.",
                (("id", "reference"), ("name", "Name"), ("email", "Email"), ("role", "Role"), ("portfolio_size", "Schools in portfolio")),
                ({"id": u.id, "name": u.full_name, "email": u.email, "role": u.role, "portfolio_size": portfolio_counts.get(u.id, 0)} for u in rows),
            )
        if section == "commissions" and division == "overseas":
            # AGT-003-AC02: Overseas Admin needs to see every commission in the division
            # (including system-triggered "estimated" rows with no amount yet) to set/
            # adjust the amount -- no such view existed anywhere before this feature.
            rows = (
                await db.execute(
                    select(AgentCommission, University, User)
                    .join(OverseasApplication, OverseasApplication.id == AgentCommission.application_id)
                    .join(University, University.id == OverseasApplication.university_id)
                    .join(User, User.id == OverseasApplication.student_id)
                    .order_by(AgentCommission.created_at.desc())
                )
            ).all()
            agent_ids = {c.agent_id for c, _, _ in rows}
            agents = {a.id: a.full_name for a in (await db.scalars(select(User).where(User.id.in_(agent_ids))))} if agent_ids else {}
            return _payload(
                "Agent Commissions",
                "Every commission in the division -- set/adjust the amount on system-estimated rows.",
                (("id", "reference"), ("agent", "Agent"), ("student", "Student"), ("university", "University"), ("amount", "Amount"), ("status", "Status"), ("created_by", "Origin")),
                ({"id": c.id, "agent": agents.get(c.agent_id, "-"), "student": student.full_name, "university": university.name, "amount": f"{c.currency} {float(c.amount):,.2f}", "status": c.status, "created_by": c.created_by} for c, university, student in rows),
            )
        if section == "employers":
            # ADM-004: no `employer` role exists anywhere in this codebase yet -- employer
            # self-registration (EMP-001) hasn't been built, so there are no employer
            # accounts to list. An honest empty directory, not a 404 or fabricated data.
            return _payload(
                "Employers",
                "Employer directory -- available once employer accounts can be created (EMP-001).",
                (("id", "reference"), ("name", "Name"), ("email", "Email"), ("role", "Role"), ("active", "Active")),
                (),
            )
        if section == "programs":
            rows = (await db.scalars(select(Program).order_by(Program.title))).all()
            return _payload(
                "Programs",
                "IT curriculum, fees, and publication status.",
                (("id", "reference"), ("title", "Program"), ("duration", "Duration"), ("fees", "Fees"), ("active", "Active")),
                ({"id": p.id, "title": p.title, "duration": p.duration, "fees": float(p.fees), "active": p.active} for p in rows),
            )
        if section == "batches":
            rows = (await db.execute(select(Batch, Program).join(Program, Program.id == Batch.program_id).order_by(Batch.start_date.desc()))).all()
            counts = dict((await db.execute(select(Enrollment.batch_id, func.count()).group_by(Enrollment.batch_id))).all())
            return _payload(
                "Batches",
                "Capacity-safe schedules and trainer assignment.",
                (("id", "reference"), ("batch", "Batch"), ("program", "Program"), ("schedule", "Schedule"), ("capacity", "Capacity"), ("enrolled", "Enrolled"), ("status", "Status")),
                ({"id": b.id, "batch": b.name, "program": p.title, "schedule": b.schedule, "capacity": b.capacity, "enrolled": counts.get(b.id, 0), "status": b.status} for b, p in rows),
            )
        if section == "certificates":
            rows = (
                await db.execute(select(Certificate, User, Program).join(User, User.id == Certificate.student_id).join(Program, Program.id == Certificate.program_id).order_by(Certificate.issued_on.desc()))
            ).all()
            return _payload(
                "Certificates",
                "Issued completion certificates across the division (ADM-006).",
                (("number", "Certificate"), ("student", "Student"), ("program", "Program"), ("issued", "Issued"), ("status", "Status"), ("override", "Issued via override")),
                ({"number": c.certificate_no, "student": s.full_name, "program": p.title, "issued": c.issued_on, "status": c.status, "override": "Yes" if not c.criteria_snapshot.get("eligible", True) else "No"} for c, s, p in rows),
            )
        if section == "enrollments":
            stmt = select(Enrollment, User, Batch).join(User, User.id == Enrollment.student_id).join(Batch, Batch.id == Enrollment.batch_id)
            rows = (await db.execute(stmt.order_by(Enrollment.created_at.desc()).limit(500))).all()
            return _payload(
                "Enrolments",
                "Review and approve or reject student enrolments (ADM-005).",
                (("id", "reference"), ("student", "Student"), ("batch", "Batch"), ("enrollment_code", "Enrolment code"), ("status", "Status")),
                ({"id": e.id, "student": s.full_name, "batch": b.name, "enrollment_code": e.enrollment_code, "status": e.status} for e, s, b in rows),
            )
        if section == "universities":
            rows = (await db.scalars(select(University).order_by(University.name))).all()
            return _payload(
                "Universities",
                "Verified university catalogue and representative ownership.",
                (("id", "reference"), ("name", "University"), ("city", "City"), ("slug", "Slug")),
                ({"id": u.id, "name": u.name, "city": u.city, "slug": u.slug} for u in rows),
            )
        if section == "leads":
            stmt = select(Enquiry)
            stmt = stmt.where(Enquiry.division == division) if division else stmt
            rows = (await db.scalars(stmt.order_by(Enquiry.created_at.desc()))).all()
            return _payload(
                "Leads",
                "Website and CRM enquiry pipeline.",
                (("id", "reference"), ("name", "Name"), ("subject", "Interest"), ("status", "Status"), ("crm", "CRM sync")),
                ({"id": e.id, "name": e.name, "subject": e.subject, "status": e.status, "crm": e.crm_sync_status} for e in rows),
            )
        if section == "payments":
            stmt = select(Payment, User).join(User, User.id == Payment.user_id)
            stmt = stmt.where(Payment.division == division) if division else stmt
            rows = (await db.execute(stmt.order_by(Payment.created_at.desc()))).all()
            return _payload(
                "Payments",
                "Payment plans, reconciliation, and provider status.",
                (("id", "reference"), ("student", "User"), ("amount", "Amount"), ("provider", "Provider"), ("status", "Status")),
                ({"id": p.id, "student": u.full_name, "amount": f"{p.currency} {float(p.amount):,.2f}", "provider": p.provider, "status": p.status} for p, u in rows),
            )
        if section == "support":
            stmt = select(SupportTicket)
            stmt = stmt.where(SupportTicket.division == division) if division else stmt
            rows = (await db.scalars(stmt.order_by(SupportTicket.created_at.desc()))).all()
            return _payload(
                "Support Tickets",
                "Student support requests (STU-005) -- unassigned tickets stay visible here, never hidden.",
                (("id", "reference"), ("subject", "Subject"), ("priority", "Priority"), ("status", "Status"), ("assigned", "Assigned")),
                ({"id": t.id, "subject": t.subject, "priority": t.priority, "status": t.status, "assigned": "Yes" if t.assigned_to_user_id else "Unassigned"} for t in rows),
            )


async def section_payload(db: AsyncSession, user: User, section: str) -> dict | None:
    if user.role == "it_student":
        result = await _it_student(db, user, section)
    elif user.role == "trainer":
        result = await _trainer(db, user, section)
    elif user.role == "overseas_student":
        result = await _overseas_student(db, user, section)
    elif user.role == "agent":
        result = await _agent(db, user, section)
    else:
        result = await _operations(db, user, section)
    return result
