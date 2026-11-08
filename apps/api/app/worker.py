import asyncio
from uuid import UUID

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging

from app.core.config import settings
from app.core.logging import configure_logging

celery = Celery("edusphere", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(task_serializer="json", result_serializer="json", accept_content=["json"], timezone="UTC")


@setup_logging.connect
def configure_worker_logging(**_kwargs) -> None:
    """O-1 (spec §6.5): with a receiver connected, Celery skips its own logging setup, so worker and beat log through the
    API's JsonFormatter: `extra_fields` (delivery id, channel, status, attempt) are rendered and secret keys redacted.
    The level comes from settings.log_level (LOG_LEVEL); Celery's `--loglevel` flag no longer applies."""
    configure_logging(settings.log_level)


@celery.task
def heartbeat_task():
    return {"status": "ok"}


def crm_payload(enquiry) -> dict:
    """The CRM webhook body (INTEGRATION_CONTRACTS.md §1); tel-003 adds `lead_code` (additive)."""
    return {
        "id": str(enquiry.id),
        "lead_code": enquiry.lead_code,
        "division": enquiry.division,
        "name": enquiry.name,
        "email": enquiry.email,
        "phone": enquiry.phone,
        "subject": enquiry.subject,
        "message": enquiry.message,
        "source": enquiry.source,
    }


@celery.task(bind=True, autoretry_for=(RuntimeError,), retry_backoff=True, retry_backoff_max=600, retry_jitter=True, max_retries=5)
def sync_enquiry_to_crm_task(self, enquiry_id: str):
    """PUB-002 / INTEGRATION_CONTRACTS.md §1 outbox pattern.

    The Enquiry row is already committed by the caller before this task is ever queued
    (app.api.public.create_enquiry) -- this task only handles the webhook side, off the
    request/response path, with exponential-backoff retry up to 5 attempts. A webhook
    failure never risks the already-captured enquiry data; it only delays how quickly
    `crm_sync_status` reflects a successful sync.
    """

    async def _run() -> None:
        from sqlalchemy import select

        from app.core.database import SessionLocal
        from app.models import Enquiry
        from app.services.integrations import sync_crm_enquiry

        async with SessionLocal() as db:
            enquiry = await db.scalar(select(Enquiry).where(Enquiry.id == UUID(enquiry_id)))
            if enquiry is None:
                return
            status = await sync_crm_enquiry(crm_payload(enquiry))
            enquiry.crm_sync_status = status
            await db.commit()
            if status == "failed":
                # Raise only after persisting the attempt's outcome, so `crm_sync_status`
                # always reflects the most recent try even mid-retry -- never silently
                # stuck on a stale "pending" while retries are in flight.
                raise RuntimeError("CRM webhook delivery failed")

    # tel-014 QA-01: a bare asyncio.run left pooled connections on this run's closed loop, crashing the next task on the process
    _run_with_fresh_pool(_run)


def _run_with_fresh_pool(make_coro):
    """Each task run is a fresh event loop, so the engine pool is disposed at the end of each run: connections are
    closed on the loop that opened them."""

    async def _run():
        from app.core.database import engine

        try:
            return await make_coro()
        finally:
            await engine.dispose()

    return asyncio.run(_run())


@celery.task
def deliver_notification_task(delivery_id: str):
    """ENH-014 (spec §6.5): send one queued NotificationDelivery. Retries are re-enqueued by `deliver` itself with the D11
    countdowns (not Celery autoretry), so attempts are counted on the row."""
    from app.notifications.delivery import deliver

    return _run_with_fresh_pool(lambda: deliver(UUID(delivery_id)))


@celery.task
def sweep_stale_deliveries_task():
    """ENH-014 (spec §6.5): every 5 minutes via beat."""
    from app.notifications.delivery import sweep_stale_deliveries

    return _run_with_fresh_pool(sweep_stale_deliveries)


@celery.task
def send_daily_reminders_task():
    """AGN-017 (DEC-SCOPE-059 N4): daily via beat. Idempotent per India day (notifications.dedupe_key), so a rerun or a second beat
    process creates nothing new."""
    from app.services.agent_notifications import run_daily_reminders

    return _run_with_fresh_pool(run_daily_reminders)


@celery.task
def expire_documents_task():
    """ccrm-021 (DEC-SCOPE-251 S4): daily at 00:05 IST via beat. Idempotent (an expired document is not picked again)."""
    from app.services.document_expiry import run_document_expiry

    return _run_with_fresh_pool(run_document_expiry)


@celery.task
def expire_offers_task():
    """ccrm-025 (DEC-SCOPE-255 D3): daily at 00:10 IST via beat. Idempotent (an expired offer is no longer active)."""
    from app.services.application_offers import run_offer_expiry

    return _run_with_fresh_pool(run_offer_expiry)


@celery.task
def send_counselor_reminders_task():
    """ccrm-030 (DEC-SCOPE-270 RM8): daily at 08:15 IST via beat. Idempotent per firing (counselor_reminder_log.dedupe_key), so a rerun, a
    second beat process or the admin's "Run now" creates nothing new."""
    from app.services.counselor_reminders import run_counselor_reminders

    return _run_with_fresh_pool(run_counselor_reminders)


@celery.task
def send_bdm_reminders_task():
    """bdm-012 (DEC-SCOPE-102 R2): every 5 minutes via beat. Idempotent per reminder (notifications.dedupe_key), so a rerun or an
    overlapping run creates nothing new."""
    from app.services.bdm_reminders import run_bdm_reminders

    return _run_with_fresh_pool(run_bdm_reminders)


@celery.task
def sweep_lead_conversions_task():
    """tel-018 (DEC-SCOPE-101, T5): every 15 minutes via beat -- linked leads whose student has since enrolled become Converted."""
    from app.core.database import SessionLocal
    from app.services.lead_handover import sweep_conversions

    async def run():
        async with SessionLocal() as db:
            return await sweep_conversions(db)

    return _run_with_fresh_pool(run)


@celery.task
def send_telecaller_alerts_task():
    """tel-020 (DEC-SCOPE-111): every 15 minutes via beat. Idempotent per alert (notifications.dedupe_key), so a rerun or an overlapping
    run creates nothing new and a late run catches up (AC2)."""
    from app.services.telecaller_alerts import run_telecaller_alerts

    return _run_with_fresh_pool(run_telecaller_alerts)


@celery.task
def escalate_overdue_follow_ups_task():
    """itc-009 (DEC-SCOPE-342): every 15 minutes via beat. Once per follow-up (lead_follow_ups.escalated_at), so a rerun or an overlapping
    run escalates nothing twice."""
    from app.services.follow_up_escalations import run_follow_up_escalations

    return _run_with_fresh_pool(run_follow_up_escalations)


@celery.task
def flag_at_risk_students_task():
    """itc-023 (DEC-SCOPE-352 R7): daily at 07:00 IST via beat. Once per transition (the open-flag unique index and conditional UPDATE),
    so a rerun or an overlapping run alerts nobody twice."""
    from app.services.it_at_risk import run_at_risk_sweep

    return _run_with_fresh_pool(run_at_risk_sweep)


@celery.task
def send_fee_reminders_task():
    """itc-016 (DEC-SCOPE-358 F6): daily at 08:30 IST via beat. Once per (installment, rule, IST day) (fee_reminder_log's unique key), so a
    rerun or an overlapping run reminds nobody twice."""
    from app.services.fee_reminders import run_fee_reminders

    return _run_with_fresh_pool(run_fee_reminders)


@celery.task
def candidate_retention_task():
    """hrc-035 (DEC-SCOPE-396 K8): daily at 02:00 IST via beat. Does nothing until super_admin sets a retention period; an anonymised
    candidate no longer matches, so a rerun or an overlapping run anonymises nobody twice."""
    import app.main  # noqa: F401 -- mgmt-032: load the app's services first (circular imports under the worker)
    from app.services.candidate_privacy import run_retention

    return _run_with_fresh_pool(run_retention)


@celery.task
def send_partnership_alerts_task():
    """upc-015 (DEC-SCOPE-164 AL3): every IST hour via beat, acting from 09:00 IST. Idempotent per alert (notifications.dedupe_key), so the
    later runs of the day create nothing new and a worker restart during the day still sends that day's alerts."""
    from app.services.partnership_alerts import run_partnership_alerts

    return _run_with_fresh_pool(run_partnership_alerts)


@celery.task
def deliver_lead_email_task(message_id: str):
    """tel-014 (DEC-SCOPE-106 E4/E5): send one queued lead email; retries are re-enqueued by `deliver_lead_email` itself."""
    from app.notifications.lead_email import deliver_lead_email

    return _run_with_fresh_pool(lambda: deliver_lead_email(UUID(message_id)))


@celery.task
def sweep_stale_lead_emails_task():
    """tel-014 (E5): every 5 minutes via beat."""
    from app.notifications.lead_email import sweep_stale_lead_emails

    return _run_with_fresh_pool(sweep_stale_lead_emails)


@celery.task
def deliver_recruiter_email_task(message_id: str):
    """rec-026 (DEC-SCOPE-135 MS7): send one queued recruiter email; retries are re-enqueued by `deliver_recruiter_email` itself."""
    from app.notifications.recruiter_email import deliver_recruiter_email

    return _run_with_fresh_pool(lambda: deliver_recruiter_email(UUID(message_id)))


@celery.task
def sweep_stale_recruiter_emails_task():
    """rec-026 (MS7): every 5 minutes via beat."""
    from app.notifications.recruiter_email import sweep_stale_recruiter_emails

    return _run_with_fresh_pool(sweep_stale_recruiter_emails)


@celery.task
def deliver_university_email_task(message_id: str):
    """upc-012 (DEC-SCOPE-140 UC7): send one queued university email; retries are re-enqueued by `deliver_university_email` itself."""
    from app.notifications.university_email import deliver_university_email

    return _run_with_fresh_pool(lambda: deliver_university_email(UUID(message_id)))


@celery.task
def sweep_stale_university_emails_task():
    """upc-012 (UC7): every 5 minutes via beat."""
    from app.notifications.university_email import sweep_stale_university_emails

    return _run_with_fresh_pool(sweep_stale_university_emails)


@celery.task
def deliver_student_email_task(message_id: str):
    """ccrm-037 (DEC-SCOPE-273 MT6): send one queued counselor email to a student; retries are re-enqueued by `deliver_student_email`."""
    from app.notifications.student_email import deliver_student_email

    return _run_with_fresh_pool(lambda: deliver_student_email(UUID(message_id)))


@celery.task
def sweep_stale_student_emails_task():
    """ccrm-037 (MT6): every 5 minutes via beat."""
    from app.notifications.student_email import sweep_stale_student_emails

    return _run_with_fresh_pool(sweep_stale_student_emails)


@celery.task
def draft_monthly_review_task():
    """mgmt-032 (DEC-SCOPE-220 MR3): on the 1st at 06:00 IST via beat -- drafts the previous month's review. Idempotent per month (the
    unique month; an existing review is never overwritten), so a rerun or a second beat process creates nothing new."""
    import app.main  # noqa: F401 -- QA32-01: the services the review reads (ledger -> telecaller_*) only import in the API's order
    from app.services.monthly_review import run_monthly_reviews

    return _run_with_fresh_pool(run_monthly_reviews)


@celery.task
def convert_candidate_preview_task(kind: str, row_id: str):
    """hrc-015 (DEC-SCOPE-379 D1): a DOC/DOCX resume or candidate document's PDF preview. Idempotent (only a pending row converts)."""
    import app.main  # noqa: F401 -- the models' import order, as the monthly review task does
    from app.services.candidate_previews import convert

    return _run_with_fresh_pool(lambda: convert(kind, row_id))


@celery.task
def feedback_overdue_task():
    """hrc-032 (DEC-SCOPE-413 N6): hourly via beat. Idempotent (`interviews.overdue_notified_at`)."""
    from app.services.recruitment_notices import run_feedback_overdue

    return _run_with_fresh_pool(run_feedback_overdue)


@celery.task
def interview_reminders_task():
    """pob-022 (DEC-SCOPE-421 A3): every 15 minutes via beat. Idempotent (`interviews.first_reminder_at` / `second_reminder_at`)."""
    from app.services.interview_automation import run_reminders

    return _run_with_fresh_pool(run_reminders)


@celery.task
def escalations_task():
    """pob-027 (DEC-SCOPE-434 I8): every 15 minutes via beat. Idempotent (`escalation_events` unique per rule and item)."""
    from app.services.escalations import run_escalations

    return _run_with_fresh_pool(run_escalations)


@celery.task
def interview_feedback_chase_task():
    """pob-022 (A5/A6): hourly via beat. Idempotent (`interviews.chase_follow_up_id` / `chase_escalated_at`)."""
    from app.services.interview_automation import run_feedback_chase

    return _run_with_fresh_pool(run_feedback_chase)


@celery.task
def placement_invoice_notices_task():
    """pob-024 (DEC-SCOPE-432 P12): daily via beat. Once per due date (`placements.due_notified_at` / `overdue_notified_at`)."""
    import app.services.telecaller_alerts  # noqa: F401 -- enters main's telecaller import cycle at the end that resolves (pob-008)
    from app.services.placements import run_invoice_notices

    return _run_with_fresh_pool(run_invoice_notices)


@celery.task
def placement_surveys_task():
    """pob-026 (DEC-SCOPE-435 S1/S7): daily via beat. Once per placement and respondent (a unique row); one reminder (`resent_at`)."""
    import app.services.telecaller_alerts  # noqa: F401 -- enters main's telecaller import cycle at the end that resolves (pob-008)
    from app.services.placement_surveys import run_surveys

    return _run_with_fresh_pool(run_surveys)


@celery.task
def recruiter_follow_up_reminders_task():
    """pob-008 (DEC-SCOPE-423 B1): every 5 minutes via beat. Once per follow-up (`recruiter_follow_ups.reminded_at`)."""
    import app.services.telecaller_alerts  # noqa: F401 -- enters main's telecaller import cycle at the end that resolves (test_pob_008)
    from app.services.recruiter_cadences import run_follow_up_reminders

    return _run_with_fresh_pool(run_follow_up_reminders)


@celery.task
def recruiter_cadences_task():
    """pob-008 (B8): every 15 minutes via beat. Once per step (`recruiter_contact_cadences.step` / `next_step_at`)."""
    import app.services.telecaller_alerts  # noqa: F401 -- as above
    from app.services.recruiter_cadences import run_cadences

    return _run_with_fresh_pool(run_cadences)


@celery.task
def new_matches_task():
    """hrc-032 (DEC-SCOPE-413 N7): hourly via beat. Idempotent (`jobs.match_notified_at`)."""
    from app.services.recruitment_notices import run_new_matches

    return _run_with_fresh_pool(run_new_matches)


@celery.task
def company_inactive_sweep_task():
    """pob-004 (DEC-SCOPE-417 D8): daily via beat. Idempotent."""
    import app.main  # noqa: F401 -- mgmt-032: load the app's services first (circular imports under the worker)
    from app.services.company_pipeline import run_inactive_sweep

    return _run_with_fresh_pool(run_inactive_sweep)


@celery.task
def portal_events_retention_task():
    """hrc-034 (DEC-SCOPE-416 I4): daily via beat. Idempotent."""
    from app.services.portal_events import run_retention

    return _run_with_fresh_pool(run_retention)


celery.conf.beat_schedule = {
    "enh014-sweep-stale-deliveries": {"task": "app.worker.sweep_stale_deliveries_task", "schedule": 300.0},
    "hrc032-feedback-overdue": {"task": "app.worker.feedback_overdue_task", "schedule": crontab(minute=10)},
    "hrc032-new-matches": {"task": "app.worker.new_matches_task", "schedule": crontab(minute=40)},
    "pob004-company-inactive-sweep": {"task": "app.worker.company_inactive_sweep_task", "schedule": crontab(hour=19, minute=30)},  # UTC = 01:00 IST
    "pob022-interview-reminders": {"task": "app.worker.interview_reminders_task", "schedule": crontab(minute="*/15")},
    "pob008-follow-up-reminders": {"task": "app.worker.recruiter_follow_up_reminders_task", "schedule": 300.0},
    "pob024-invoice-notices": {"task": "app.worker.placement_invoice_notices_task", "schedule": crontab(hour=3, minute=15)},  # UTC 03:15 = 08:45 IST
    "pob026-placement-surveys": {"task": "app.worker.placement_surveys_task", "schedule": crontab(hour=3, minute=30)},  # UTC 03:30 = 09:00 IST
    "pob008-cadences": {"task": "app.worker.recruiter_cadences_task", "schedule": crontab(minute="*/15")},
    "pob027-escalations": {"task": "app.worker.escalations_task", "schedule": crontab(minute="5-59/15")},
    "pob022-feedback-chase":{"task": "app.worker.interview_feedback_chase_task", "schedule": crontab(minute=20)},
    "hrc034-portal-events-retention": {"task": "app.worker.portal_events_retention_task", "schedule": crontab(hour=19, minute=15)},  # UTC = 00:45 IST
    "agn017-daily-reminders": {"task": "app.worker.send_daily_reminders_task", "schedule": crontab(hour=2, minute=30)},  # UTC = 08:00 IST
    "ccrm030-counselor-reminders": {"task": "app.worker.send_counselor_reminders_task", "schedule": crontab(hour=2, minute=45)},  # UTC = 08:15 IST
    "ccrm021-document-expiry": {"task": "app.worker.expire_documents_task", "schedule": crontab(hour=18, minute=35)},  # UTC = 00:05 IST
    "ccrm025-offer-expiry": {"task": "app.worker.expire_offers_task", "schedule": crontab(hour=18, minute=40)},  # UTC = 00:10 IST
    "bdm012-reminders":{"task": "app.worker.send_bdm_reminders_task", "schedule": 300.0},
    "tel018-conversion-sweep": {"task": "app.worker.sweep_lead_conversions_task", "schedule": 900.0},
    "tel014-sweep-stale-lead-emails": {"task": "app.worker.sweep_stale_lead_emails_task", "schedule": 300.0},
    "tel020-alerts": {"task": "app.worker.send_telecaller_alerts_task", "schedule": 900.0},
    "itc009-escalations": {"task": "app.worker.escalate_overdue_follow_ups_task", "schedule": 900.0},
    "itc023-at-risk": {"task": "app.worker.flag_at_risk_students_task", "schedule": crontab(hour=1, minute=30)},  # UTC 01:30 = 07:00 IST
    "itc016-fee-reminders": {"task": "app.worker.send_fee_reminders_task", "schedule": crontab(hour=3, minute=0)},  # UTC 03:00 = 08:30 IST
    "hrc035-candidate-retention": {"task": "app.worker.candidate_retention_task", "schedule": crontab(hour=20, minute=30)},  # UTC 20:30 = 02:00 IST
    "rec026-sweep-stale-recruiter-emails": {"task": "app.worker.sweep_stale_recruiter_emails_task", "schedule": 300.0},
    "upc012-sweep-stale-university-emails": {"task": "app.worker.sweep_stale_university_emails_task", "schedule": 300.0},
    "ccrm037-sweep-stale-student-emails": {"task": "app.worker.sweep_stale_student_emails_task", "schedule": 300.0},
    "upc015-alerts": {"task": "app.worker.send_partnership_alerts_task", "schedule": crontab(minute=30)},  # UTC :30 = every IST hour
    "mgmt032-monthly-review": {"task": "app.worker.draft_monthly_review_task", "schedule": crontab(day_of_month=1, hour=0, minute=30)},  # UTC 00:30 = 06:00 IST
}
