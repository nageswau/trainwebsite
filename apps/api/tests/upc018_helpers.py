"""upc-018 fixtures: a fresh university per test (the shared test DB is never truncated) and the funnel's source rows built directly,
each dated into March 2025 (IST) unless a test says otherwise."""

from datetime import UTC, datetime

from app.models import AgentStudentShortlistEntry, ApplicationStatusHistory, OverseasApplication, VisaCase
from tests.agn001_helpers import mk_active_org, uniq
from tests.agn004_helpers import mk_record
from tests.agn011_helpers import mk_deposit
from tests.agn022_helpers import mk_paid_deposit

IN_MARCH = datetime(2025, 3, 15, 6, tzinfo=UTC)
FEB = datetime(2025, 2, 10, 6, tzinfo=UTC)
APRIL = datetime(2025, 4, 10, 6, tzinfo=UTC)
MARCH = {"from": "2025-03-01", "to": "2025-03-31"}


async def agency(db) -> dict:
    return await mk_active_org(db, name=f"Funnel {uniq()}")


async def students(db, org: dict, n: int) -> list:
    return [await mk_record(db, agent=org["master"], full_name=f"Funnel Student {uniq()}") for _ in range(n)]


async def shortlist(db, record, university, when: datetime = IN_MARCH) -> None:
    db.add(AgentStudentShortlistEntry(agent_student_id=record.id, university_id=university.id, course_title="MSc", created_at=when))
    await db.commit()


async def application(db, university, *, org: dict | None = None, record=None, when: datetime = IN_MARCH, status: str = "enquiry", **fields) -> OverseasApplication:
    """An agency row when `record` is given, else a School-or-self row the caller shapes with `fields`."""
    row = OverseasApplication(
        agent_id=org["master"].id if org else None, agent_student_id=record.id if record else None, university_id=university.id,
        status=status, intake="Sep 2025", created_at=when, **fields,
    )  # fmt: skip
    db.add(row)
    await db.commit()
    return row


async def history(db, app, to_status: str, when: datetime = IN_MARCH, from_status: str | None = "enquiry") -> None:
    db.add(ApplicationStatusHistory(application_id=app.id, from_status=from_status, to_status=to_status, created_at=when))
    await db.commit()


async def visa(db, app, decision: str | None = "approved", when: datetime = IN_MARCH) -> None:
    db.add(VisaCase(application_id=app.id, decision=decision, decided_at=when if decision else None))
    await db.commit()


async def paid_deposit(db, app, by, when: datetime = IN_MARCH):
    deposit = await mk_paid_deposit(db, app, by=by, amount="1000.00", status="paid")
    deposit.paid_at = when
    await db.commit()
    return deposit


__all__ = ["APRIL", "FEB", "IN_MARCH", "MARCH", "agency", "application", "history", "mk_deposit", "paid_deposit", "shortlist", "students", "visa"]
