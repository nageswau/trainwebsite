"""nehn-018 (DEC-SCOPE-304) -- which IT student features unlock at which payment state.

The state is derived from the student's own enrolments and IT payments on every call, never stored: a webhook that marks a payment
paid unlocks the very next request (AC2). The policy is `student_access_rules`, also read on every call, so an admin's change applies
at once (AC4). Builder's defaults, NEEDS_CONFIRMATION (OD-06): the state is per student, not per enrolment (the certificate
`pending_fee` basis); an overdue instalment or a refund never re-locks a student who has paid something; overseas students are not gated.
"""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import STUDENT_ACCESS_FEATURES, STUDENT_PAYMENT_STATES, Enrollment, Payment, StudentAccessRule, User

STATES = STUDENT_PAYMENT_STATES
FEATURES = STUDENT_ACCESS_FEATURES
DEFAULT_MIN_STATE = "partially_paid"  # the first payment starts the course
STATE_LABELS = {"registered": "Registered", "enrolled_pending_payment": "Enrolled, payment pending", "partially_paid": "First payment made", "fully_paid": "Fully paid"}
FEATURE_LABELS = {
    "attendance": "Attendance",
    "assignments": "Assignments and projects",
    "assessments": "Examinations",
    "resources": "Course materials",
    "live_classes": "Live classes",
    "questions": "Questions",
    "feedback": "Course feedback",
    "certificates": "Certificates",
}
# A portal section that belongs to a feature; every other student section (course, fees, profile, ...) is never gated.
SECTION_FEATURES = {
    "attendance": "attendance",
    "assignments": "assignments",
    "projects": "assignments",
    "examinations": "assessments",
    "downloads": "resources",
    "questions": "questions",
    "feedback": "feedback",
    "certificates": "certificates",
}
NOT_ENROLLED = ("rejected", "withdrawn", "dropped")  # never seated, or left the course (certificate queue's exclusions)
OWED = ("pending", "overdue")
PAID = ("paid", "succeeded")


async def student_state(db: AsyncSession, student_id) -> str:
    enrolled = await db.scalar(select(Enrollment.id).where(Enrollment.student_id == student_id, Enrollment.status.not_in(NOT_ENROLLED)).limit(1))
    if not enrolled:
        return "registered"
    it_payments = (Payment.user_id == student_id, Payment.division == "it")
    owed = await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(*it_payments, Payment.status.in_(OWED)))
    if not owed or float(owed) <= 0:  # a free course, a student never billed, or a fee discounted to nothing
        return "fully_paid"
    paid = await db.scalar(select(Payment.id).where(*it_payments, Payment.status.in_(PAID)).limit(1))
    return "partially_paid" if paid else "enrolled_pending_payment"


async def policy(db: AsyncSession) -> dict[str, str]:
    stored = dict((await db.execute(select(StudentAccessRule.feature, StudentAccessRule.min_state))).all())
    return {feature: stored.get(feature, DEFAULT_MIN_STATE) for feature in FEATURES}


def _unlocked(state: str, required: str) -> bool:
    return STATES.index(state) >= STATES.index(required)


async def summary(db: AsyncSession, user: User) -> dict:
    """The student's state and every feature's lock, computed once (one state + one policy read)."""
    state, rules = await student_state(db, user.id), await policy(db)
    return {
        "state": state,
        "features": [{"key": f, "label": FEATURE_LABELS[f], "unlocked": _unlocked(state, rules[f]), "required_state": rules[f]} for f in FEATURES],
    }


def locked_features(access: dict) -> set[str]:
    return {f["key"] for f in access["features"] if not f["unlocked"]}


def lock(access: dict, feature: str) -> dict | None:
    """The `locked` block a section carries, or None when the feature is open."""
    entry = next(f for f in access["features"] if f["key"] == feature)
    if entry["unlocked"]:
        return None
    return {"feature": feature, "label": entry["label"], "required_state": entry["required_state"], "current_state": access["state"]}


async def require(db: AsyncSession, user: User, feature: str) -> None:
    """403 `payment_required` for an IT student whose payment state is below the feature's minimum. Every other role passes: call it
    after the route's own role and ownership checks, so a wrong-batch learner keeps the existing 404."""
    if user.role != "it_student":
        return
    locked = lock(await summary(db, user), feature)
    if locked:
        first_step = "Enrol in a course" if locked["current_state"] == "registered" else "Complete your payment"  # nothing to pay before enrolling
        raise HTTPException(403, {"message": f"{first_step} to unlock {locked['label']}.", "code": "payment_required", **locked})
