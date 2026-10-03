"""AGN-018 AC04 / G5 -- the SQL offer rule is the twin of `counts_as_offer` (O5): every stage, with and without a recorded offer."""

from datetime import date

import pytest
from sqlalchemy import select

from app.models import OverseasApplication
from app.services.agent_applications import OFFER_COUNTED_STATUSES, OVERSEAS_APPLICATION_STAGES, WITHDRAWN, counts_as_offer
from app.services.agent_dashboard import offer_clause
from tests.agn008_helpers import agency_world, mk_application

STATUSES = [*OVERSEAS_APPLICATION_STAGES, WITHDRAWN, "offer_received", "accepted", "legacy free text"]
RECORDED = {"offer_type": "conditional", "offer_date": date(2026, 9, 1), "offer_conditions": "IELTS 6.5"}


@pytest.mark.asyncio
async def test_sql_offer_clause_matches_counts_as_offer(db_session):
    w = await agency_world(db_session)
    rows = []
    for status in STATUSES:
        for recorded in (False, True):
            fields = RECORDED if recorded else {}
            rows.append(await mk_application(db_session, agent=w["master"], university=w["university"], record=w["record"], status=status, **fields))
    ids = [r.id for r in rows]
    matched = set((await db_session.scalars(select(OverseasApplication.id).where(OverseasApplication.id.in_(ids), offer_clause()))).all())
    assert matched == {r.id for r in rows if counts_as_offer(r)}
    # every offer status without a record, plus every status with one
    assert len(matched) == len(OFFER_COUNTED_STATUSES) + len(STATUSES)
