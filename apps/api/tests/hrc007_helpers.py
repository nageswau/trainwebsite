"""hrc-007 (DEC-SCOPE-380 A4): employer jobs need approval by default. Tests of the employer's self-publish (emp-002, rec-007 J3) run with
that setting off, the behaviour they were written for, and put the seeded value back."""

import pytest_asyncio
from sqlalchemy import update

from app.models import JOB_APPROVAL_DEFAULTS, JobApprovalSetting


@pytest_asyncio.fixture
async def employer_self_publish(db_session):
    await db_session.execute(update(JobApprovalSetting).where(JobApprovalSetting.source == "employer").values(required=False))
    await db_session.commit()
    yield
    await db_session.execute(update(JobApprovalSetting).where(JobApprovalSetting.source == "employer").values(required=JOB_APPROVAL_DEFAULTS["employer"]))
    await db_session.commit()
