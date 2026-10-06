"""tel-003 -- the Lead ID and the new columns' defaults on the shared database (spec §3; AC1, L1, L3)."""

import asyncio
import re
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models import Enquiry

CODE = re.compile(r"^LD-\d{6,}$")


def enquiry(**overrides) -> Enquiry:
    values = {"division": "it", "name": "Lead", "email": f"lead-{uuid.uuid4().hex[:8]}@example.local", "subject": "Python",
              "message": "Hello there", "source": "website"} | overrides
    return Enquiry(**values)


@pytest.mark.asyncio
async def test_a_direct_insert_gets_a_lead_code_and_the_defaults(db_session):
    lead = enquiry()
    db_session.add(lead)
    await db_session.commit()
    assert CODE.match(lead.lead_code)  # returned by the INSERT itself (eager_defaults): no lazy load on an async session
    assert (lead.priority, lead.phone_normalized) == ("warm", None)
    assert lead.stage_changed_at is not None


@pytest.mark.asyncio
async def test_twenty_concurrent_creates_get_twenty_distinct_codes():
    async def create() -> str:
        async with SessionLocal() as session:
            lead = enquiry()
            session.add(lead)
            await session.commit()
            return lead.lead_code

    codes = await asyncio.gather(*(create() for _ in range(20)))
    assert len(set(codes)) == 20 and all(CODE.match(c) for c in codes)


@pytest.mark.asyncio
async def test_the_code_expression_never_truncates_past_six_digits(db_session):
    """Review focus 1: lpad would cut LD-1234567 to LD-123456; format('%6s') only pads."""
    expression = "'LD-' || translate(format('%6s', CAST(:n AS bigint)), ' ', '0')"
    assert await db_session.scalar(sa.text(f"SELECT {expression}"), {"n": 7}) == "LD-000007"
    assert await db_session.scalar(sa.text(f"SELECT {expression}"), {"n": 1234567}) == "LD-1234567"


@pytest.mark.asyncio
async def test_a_source_outside_the_list_is_refused_by_the_database(db_session):
    db_session.add(enquiry(source="tiktok"))
    with pytest.raises(IntegrityError, match="ck_enquiries_source"):
        await db_session.commit()


@pytest.mark.asyncio
async def test_the_phone_is_normalised_on_insert_and_on_edit(db_session):
    """L3 + review focus 4: the validator re-derives phone_normalized whenever phone changes."""
    lead = enquiry(phone="098765 43210")
    assert lead.phone_normalized == "+919876543210"
    db_session.add(lead)
    await db_session.commit()
    lead.phone = "+44 20 7946 0958"
    await db_session.commit()
    stored = await db_session.scalar(sa.select(Enquiry.phone_normalized).where(Enquiry.id == lead.id))
    assert stored == "+442079460958"
    lead.phone = "12"
    assert lead.phone_normalized is None
