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
