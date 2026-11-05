"""hrc-021 (DEC-SCOPE-397): a candidate's engagement status, derived from what already happened -- never stored, so it cannot drift (E1).

`expression()` is one SQL CASE over correlated sub-queries on indexed columns: selected as a column it labels a page of rows, compared in a
WHERE it filters the pool, both in the query that already runs (no extra query). First match wins (E2): the two manual flags from the
stored `status` (E3), placed, active, inactive, then the ladder shortlisted > screened > contacted > uncontacted > new."""

from collections.abc import Iterable
from datetime import timedelta
from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import CANDIDATE_ENGAGEMENTS, ApplicationScreening, Candidate, CareerApplication, JobApplication, JobApplicationStatusHistory, RecruiterCall, RecruiterMessage
from app.services.candidate_privacy import CLOSED_APPLICATIONS

LABELS = ("New", "Uncontacted", "Contacted", "Screened", "Shortlisted", "Active", "Inactive", "Placed", "Not interested", "Do not contact")
ENGAGEMENTS = dict(zip(CANDIDATE_ENGAGEMENTS, LABELS, strict=True))
SHORTLISTED_ON = ("shortlisted", "profile_shared", "interview", "selected", "joined")
ACTIVE_DAYS, INACTIVE_DAYS = 30, 90  # E4 / Appendix B, measured from the database clock (E8)


def expression():
    A, H = aliased(JobApplication), aliased(JobApplicationStatusHistory)
    C, M, W, S = RecruiterCall, RecruiterMessage, CareerApplication, ApplicationScreening

    def application(*where):
        return select(A.id).where(A.candidate_id == Candidate.id, *where).exists()

    def reached(statuses: tuple[str, ...]):  # now, or at any point in its history
        ever = select(H.id).join(A, A.id == H.application_id).where(A.candidate_id == Candidate.id, H.to_status.in_(statuses)).exists()
        return or_(application(A.status.in_(statuses)), ever)

    def since(days: int):
        return func.now() - timedelta(days=days)

    def called(after=None):  # a logged call or message (rec-025 / rec-026), optionally only since `after`
        call, message = select(C.id).where(C.candidate_id == Candidate.id), select(M.id).where(M.candidate_id == Candidate.id)
        if after is not None:
            call, message = call.where(C.occurred_at >= after), message.where(M.sent_at >= after)
        return or_(call.exists(), message.exists())

    def pipeline(after):  # E4: an application change or a website application
        return or_(application(A.updated_at >= after), select(W.id).where(W.candidate_id == Candidate.id, W.created_at >= after).exists())

    open_application = application(A.status.notin_(CLOSED_APPLICATIONS))
    quiet = since(INACTIVE_DAYS)
    return case(
        (Candidate.status == "do_not_contact", "do_not_contact"),
        (Candidate.status == "not_looking", "not_interested"),
        (or_(application(A.status == "joined"), Candidate.status == "placed") & ~open_application, "placed"),  # E5
        (or_(open_application, pipeline(since(ACTIVE_DAYS))), "active"),
        (~or_(Candidate.created_at >= quiet, called(quiet), pipeline(quiet)), "inactive"),  # E6
        (reached(SHORTLISTED_ON), "shortlisted"),
        (or_(select(S.application_id).join(A, A.id == S.application_id).where(A.candidate_id == Candidate.id).exists(), reached(("screened",))), "screened"),
        (called(), "contacted"),
        (Candidate.owner_user_id.is_not(None), "uncontacted"),
        else_="new",
    )


def out(key: str | None) -> dict | None:
    return {"key": key, "label": ENGAGEMENTS[key]} if key else None


async def of(db: AsyncSession, candidate_ids: Iterable[UUID]) -> dict[UUID, str]:
    ids = list(candidate_ids)
    if not ids:
        return {}
    return dict((await db.execute(select(Candidate.id, expression()).where(Candidate.id.in_(ids)))).all())
