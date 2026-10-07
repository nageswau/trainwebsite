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

    asyncio.run(_run())


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
def send_bdm_reminders_task():
    """bdm-012 (DEC-SCOPE-098 R2): every 5 minutes via beat. Idempotent per reminder (notifications.dedupe_key), so a rerun or an
    overlapping run creates nothing new."""
    from app.services.bdm_reminders import run_bdm_reminders

    return _run_with_fresh_pool(run_bdm_reminders)


celery.conf.beat_schedule = {
    "enh014-sweep-stale-deliveries": {"task": "app.worker.sweep_stale_deliveries_task", "schedule": 300.0},
    "agn017-daily-reminders": {"task": "app.worker.send_daily_reminders_task", "schedule": crontab(hour=2, minute=30)},  # UTC = 08:00 IST
    "bdm012-reminders": {"task": "app.worker.send_bdm_reminders_task", "schedule": 300.0},
}
