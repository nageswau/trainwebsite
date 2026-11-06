"""itc-002 (DEC-SCOPE-336): typed notifications that link to a record.

`EVENTS` is the catalogue: each dotted event type names the record it is about and carries FIXED, preview-safe text. `notify` takes
no free text, so an amount, score, note or HR comment can never reach an in-app preview, an email subject or a WhatsApp/SMS line
(source §7, last line); the recipient opens EduSphere for the detail. The catalogue rows other than `it.fee.payment_received` are
`NEEDS_CONFIRMATION` against the source's §7 table: the item that first emits each one (itc-009/016/023/025/026/027) confirms it.
"""

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification, NotificationDelivery, NotificationPreference, User
from app.notifications.dispatch import NOTIFIED_KEY, add_pending, allowed_channels

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    entity_type: str
    title: str
    body: str


EVENTS: dict[str, Event] = {
    "it.lead.assigned": Event("lead", "New lead assigned", "A lead was handed over to you. Open EduSphere to view it."),
    "it.followup.overdue": Event("lead_follow_up", "Follow-up overdue", "A follow-up is past its due time. Open EduSphere to act on it."),
    "it.fee.payment_received": Event("payment", "Payment received", "Your payment was received. Open EduSphere to view your receipt."),
    "it.fee.payment_due": Event("payment", "Fee payment due", "A fee payment is due. Open EduSphere for the details."),
    # itc-016 (DEC-SCOPE-358 F4): the student's overdue reminder and the linked IT counselor's copy -- never an amount or a date
    "it.fee.payment_overdue": Event("payment", "Fee payment overdue", "A fee payment is past its due date. Open EduSphere for the details."),
    "it.fee.student_overdue": Event("payment", "Student's fee payment overdue", "A fee payment of your student is past its due date. Open EduSphere for the details."),
    "it.batch.changed": Event("batch", "Course or batch updated", "Your course, batch or timetable was updated. Open EduSphere to see what changed."),
    # itc-025 (DEC-SCOPE-348): the linked IT counselor's copy of a batch change of one or more of their students
    "it.batch.student_changed": Event("batch", "Student's batch updated", "The course, batch or timetable of your student was updated. Open EduSphere to see what changed."),
    # itc-023 (DEC-SCOPE-352 R6): staff (trainer, counselor) get `at_risk`; the student a separate supportive, generic `check_in`; a
    # clearing is `back_on_track` for all three. No figure or reason is ever in the text.
    "it.training.at_risk": Event("enrollment", "Student at risk", "A student's attendance or progress needs attention. Open EduSphere for the details."),
    "it.training.check_in": Event("enrollment", "Let's get you back on track", "Your trainer and counselor are here to help with your course. Open EduSphere to see your attendance and progress."),
    "it.training.back_on_track": Event("enrollment", "Back on track", "Attendance and progress are back on track. Open EduSphere for the details."),
    "it.resume.uploaded": Event("resume", "Resume uploaded", "A resume was uploaded. Open EduSphere to review it."),
    "it.placement.updated": Event("student", "Placement status updated", "Your placement status was updated. Open EduSphere to see it."),
    # itc-028 (DEC-SCOPE-351 N8): a staff note was shared with the student -- never the note's text
    "it.student.update_shared": Event("student_note", "New update for you", "An update was shared with you. Open EduSphere to read it."),
    # itc-027 (DEC-SCOPE-354 H8): `it.resume.uploaded` (above) goes to the HR owner and the counselor, `it.placement.updated` to the
    # student on a stage move; the counselor's copy of that move and the HR owner's (re)assignment are these two. Never a stage or note.
    "it.hr_review.updated": Event("hr_review_task", "HR review updated", "HR updated the resume review of your student. Open EduSphere to see it."),
    "it.hr_review.assigned": Event("hr_review_task", "Resume review assigned", "A resume review was assigned to you. Open EduSphere to start it."),
    # hrc-012 (DEC-SCOPE-382 O10): a new primary recruiter, placement officer or collaborator -- never the candidate's name
    "it.candidate.assigned": Event("candidate", "Candidate assigned to you", "A candidate was assigned to you. Open EduSphere to view them."),
    # hrc-024 (DEC-SCOPE-393 R9): no routing rule found a recruiter for a new website candidate -- never the candidate's name
    "it.candidate.unassigned": Event("candidate", "Candidate needs a recruiter", "A new candidate has no recruiter yet. Open EduSphere to assign one."),
    # hrc-016 (DEC-SCOPE-387 T7): a candidate task's new assignee -- never the candidate's name or the task's text
    "it.candidate.task_assigned": Event("candidate_task", "Candidate task assigned to you", "A candidate task was assigned to you. Open EduSphere to see your tasks."),
    # hrc-009 (DEC-SCOPE-390 R6): a vacancy's owners, when its eligibility changed under open applications -- only the count, never a name
    "it.requirement.review_needed": Event("job", "Applications need review", "Applications to review: {count}. A vacancy's eligibility criteria changed. Open EduSphere to confirm or move them."),
    # hrc-032 (DEC-SCOPE-412): the §13 triggers that had no notice, and the candidate's stage and result, whose text used to name the outcome
    "it.application.new": Event("job_application", "New application", "A candidate applied to a vacancy you own. Open EduSphere to review it."),
    "it.application.updated": Event("job_application", "Job application updated", "Your application was updated. Open EduSphere to see where it stands."),
    "it.requirement.changed": Event("job", "Vacancy updated", "A vacancy you own was updated. Open EduSphere to see what changed."),
    "it.requirement.assigned": Event("job", "Vacancy assigned to you", "A vacancy was assigned to you. Open EduSphere to view it."),
    "it.requirement.approval_needed": Event("job", "Vacancy needs approval", "A vacancy is waiting for your approval. Open EduSphere to review it."),
    "it.interview.feedback_overdue": Event("interview", "Interview feedback overdue", "Feedback for an interview is overdue. Open EduSphere to add it."),
    "it.interview.result_published": Event("interview_result", "Interview result", "An interview result was published for you. Open EduSphere to read it."),
    "it.job.new_match": Event("job", "New job for your profile", "A new job fits your profile. Open EduSphere to see it. A match does not guarantee selection."),
}
COUNT = "{count}"

# hrc-032 (N1, N8): what the Delivery exceptions page covers, with each type's label. The first group is catalogued above; the second writes its
# own text (an interview's date, an Application ID: never a result) and only tags its notice with the type.
RECRUITMENT_EVENTS: dict[str, str] = {
    **{key: EVENTS[key].title for key in (
        "it.candidate.assigned", "it.candidate.unassigned", "it.candidate.task_assigned", "it.requirement.review_needed", "it.application.new", "it.application.updated",
        "it.requirement.changed", "it.requirement.assigned", "it.requirement.approval_needed", "it.interview.feedback_overdue", "it.interview.result_published", "it.job.new_match",
    )},
    "it.application.received": "Application received",
    "it.interview.scheduled": "Interview scheduled",
    "it.interview.updated": "Interview updated",
    "it.interview.rescheduled": "Interview rescheduled",
    "it.interview.cancelled": "Interview cancelled",
    "it.interview.assigned": "Interview assigned",
    "it.offer.received": "Job offer received",
}

# itc-025 (DEC-SCOPE-348): "a summary of what changed" from a FIXED vocabulary of field names -- never the values (dates, trainer names,
# reasons), so the preview-safe rule above still holds.
CHANGE_LABELS: dict[str, str] = {
    "name": "batch name",
    "start_date": "start date",
    "end_date": "end date",
    "trainer": "trainer",
    "timetable": "timetable",
    "timezone": "time zone",
    "mode": "mode",
    "cancelled_class": "cancelled class",
    "batch": "batch",
}


async def notify(db: AsyncSession, recipients: Iterable[User | None], event_type: str, entity_id: UUID | str, *, action_url: str | None = None, changes: Sequence[str] = (), count: int | None = None) -> list[Notification]:
    """One in-app notice per recipient plus queued email and opted-in WhatsApp/SMS, published only when the caller's transaction
    commits (a rollback sends nothing). Missing and deactivated recipients are skipped, and a (recipient, event, record) already
    notified in this transaction is not notified again. Bulk: one insert per table and one preference query for the whole batch.
    `changes` (itc-025) appends "Changed: <labels>." from `CHANGE_LABELS`; an unknown key is refused like an unknown event.
    `count` (hrc-009) fills the `{count}` of an event that has one, and is required there and refused elsewhere: a whole number is the
    only variable text a notice can carry."""
    event = EVENTS.get(event_type)
    if event is None:
        raise ValueError(f"Unknown notification event: {event_type}")
    if unknown := [key for key in changes if key not in CHANGE_LABELS]:
        raise ValueError(f"Unknown change label: {unknown}")
    if (COUNT in event.body) != isinstance(count, int):
        raise ValueError(f"{event_type} takes a count" if COUNT in event.body else f"{event_type} takes no count")
    body = event.body.replace(COUNT, str(count)) if count is not None else event.body
    body = f"{body} Changed: {', '.join(CHANGE_LABELS[key] for key in changes)}." if changes else body
    entity = str(entity_id)
    seen: set = db.sync_session.info.setdefault(NOTIFIED_KEY, set())
    targets: list[User] = []
    for user in recipients:
        if user is None or not user.active or (key := (user.id, event_type, entity)) in seen:
            continue
        seen.add(key)
        targets.append(user)
    if not targets:
        return []
    notes = [Notification(user_id=u.id, title=event.title, body=body, read=False, action_url=action_url, event_type=event_type, entity_type=event.entity_type, entity_id=entity) for u in targets]
    db.add_all(notes)
    await db.flush()
    prefs = {p.user_id: p for p in await db.scalars(select(NotificationPreference).where(NotificationPreference.user_id.in_([u.id for u in targets])))}
    await add_pending(db, [NotificationDelivery(notification_id=n.id, channel=c, status="queued", attempt_count=0) for n in notes for c in allowed_channels(prefs.get(n.user_id))])
    logger.info("notification_event_queued", extra={"extra_fields": {"event_type": event_type, "entity_type": event.entity_type, "recipients": len(notes)}})
    return notes
