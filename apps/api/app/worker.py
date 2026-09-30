import asyncio
from uuid import UUID

from celery import Celery

from app.core.config import settings

celery = Celery("edusphere", broker=settings.redis_url, backend=settings.redis_url)
celery.conf.update(task_serializer="json", result_serializer="json", accept_content=["json"], timezone="UTC")


@celery.task
def heartbeat_task():
    return {"status": "ok"}


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
            status = await sync_crm_enquiry(
                {
                    "id": str(enquiry.id),
                    "division": enquiry.division,
                    "name": enquiry.name,
                    "email": enquiry.email,
                    "phone": enquiry.phone,
                    "subject": enquiry.subject,
                    "message": enquiry.message,
                    "source": enquiry.source,
                }
            )
            enquiry.crm_sync_status = status
            await db.commit()
            if status == "failed":
                # Raise only after persisting the attempt's outcome, so `crm_sync_status`
                # always reflects the most recent try even mid-retry -- never silently
                # stuck on a stale "pending" while retries are in flight.
                raise RuntimeError("CRM webhook delivery failed")

    asyncio.run(_run())


@celery.task
def deliver_notification_task(delivery_id: str):
    """ENH-014 (spec §6.5): send one queued NotificationDelivery. Retries are re-enqueued by `deliver` itself with the D11
    countdowns (not Celery autoretry), so attempts are counted on the row. Each run is a fresh event loop, so the pool is
    disposed at the end of each run: connections are closed on the loop that opened them."""

    async def _run():
        from app.core.database import engine
        from app.notifications.delivery import deliver

        try:
            return await deliver(UUID(delivery_id))
        finally:
            await engine.dispose()

    return asyncio.run(_run())


@celery.task
def sweep_stale_deliveries_task():
    """ENH-014 (spec §6.5): every 5 minutes via beat. Same per-run pool disposal as `deliver_notification_task`."""

    async def _run():
        from app.core.database import engine
        from app.notifications.delivery import sweep_stale_deliveries

        try:
            return await sweep_stale_deliveries()
        finally:
            await engine.dispose()

    return asyncio.run(_run())


celery.conf.beat_schedule = {"enh014-sweep-stale-deliveries": {"task": "app.worker.sweep_stale_deliveries_task", "schedule": 300.0}}
