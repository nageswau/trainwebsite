"""pob-026 (DEC-SCOPE-435 S1-S10; design docs/superpowers/specs/2026-11-08-pob-026-satisfaction-survey-design.md): the client and candidate
satisfaction surveys of a placement -- the daily sweep that sends each side one survey (or records why it could not) and resends it once
(S1-S7), the signed no-login link (S6), the one response (S8), the refused-lookup throttle (S9) and the block on the placement (S10).

The link carries only the survey id. The email is a rec-026 `recruiter_messages` row, so it shows on the company / candidate timeline and the
worker retries it. Audit and logs carry ids and the rating, never a name, an address or the comment."""

import logging
import math
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from fastapi import HTTPException
from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import ALGORITHM
from app.models import AuditLog, Candidate, Company, CompanyContact, JobOffer, Placement, PlacementSurvey, ProfileShare, ProfileShareItem, User
from app.models import RecruiterMessage as RM
from app.notifications.dispatch import enqueue_recruiter_email
from app.services import recruiter_requirements as requirements

logger = logging.getLogger("app.recruiter")

SURVEY_AFTER_DAYS = 30  # S1: due this many days after the actual joining date ...
SURVEY_LOOKBACK_DAYS = 120  # ... and never for a joining older than this (no flood of old placements)
SURVEY_RESEND_DAYS = 7  # S7: one reminder when still unanswered this long after the first send
SURVEY_LINK_DAYS = 30  # S6: each link is valid this long from its send
SWEEP_LIMIT = 200
LINK_TYPE = "placement_survey"
PUBLIC_PATH = "/feedback/"
RESPONDED_ACTION, REFUSED_ACTION = "placement_survey.responded", "placement_survey.refused"
REFUSED_MAX_PER_IP = 20  # S9: refused lookups per IP per rolling hour
REFUSED_WINDOW = timedelta(hours=1)
NOT_FOUND = "This feedback link is not valid"
GONE = "This feedback link has already been used or has expired"
THROTTLED = "Too many attempts. Try again later"
SKIP_LABELS = {
    "no_contact": "No active client contact with an email address",
    "no_email": "The candidate has no email address",
    "no_sender": "No active owner to send it from",
}
STATUS_LABELS = {"sent": "Sent", "responded": "Responded", "skipped": "Not sent"}


# --- recipients (S3/S4) --------------------------------------------------------------------------------------------------------------
def _reachable(contact: CompanyContact | None, company_id: UUID) -> bool:
    return bool(contact and contact.company_id == company_id and contact.active and contact.merged_into_id is None and contact.email
                and contact.status != "do_not_contact")  # fmt: skip


async def client_contact(db: AsyncSession, placement: Placement) -> CompanyContact | None:
    """The contact the candidate was last submitted to for this requirement; else (they have left) the company's primary contact."""
    submitted = await db.scalar(
        select(CompanyContact)
        .join(ProfileShare, ProfileShare.contact_id == CompanyContact.id)
        .join(ProfileShareItem, ProfileShareItem.share_id == ProfileShare.id)
        .where(ProfileShare.job_id == placement.job_id, ProfileShare.company_id == placement.company_id, ProfileShareItem.candidate_id == placement.candidate_id)
        .order_by(ProfileShare.created_at.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    if _reachable(submitted, placement.company_id):
        return submitted
    primaries = await db.scalars(
        select(CompanyContact)
        .where(CompanyContact.company_id == placement.company_id, CompanyContact.is_primary)
        .order_by(CompanyContact.created_at.desc())
        .execution_options(populate_existing=True)
    )
    return next((c for c in primaries if _reachable(c, placement.company_id)), None)


async def _sender(db: AsyncSession, placement: Placement) -> User | None:
    for user_id in (placement.po_owner_user_id, placement.recruiter_user_id, placement.created_by_user_id):
        user = await db.get(User, user_id) if user_id else None
        if user and user.active:
            return user
    return None


# --- the link (S6) -----------------------------------------------------------------------------------------------------------------------
def link(survey_id: UUID, now: datetime) -> str:
    token = jwt.encode({"sub": str(survey_id), "type": LINK_TYPE, "exp": now + timedelta(days=SURVEY_LINK_DAYS)}, settings.secret_key, algorithm=ALGORITHM)
    return f"{settings.frontend_url.rstrip('/')}{PUBLIC_PATH}{token}"


async def from_token(db: AsyncSession, token: str, *, lock: bool = False) -> PlacementSurvey:
    """404 for a bad signature, another token type or an unknown survey; 410 once answered or expired."""
    try:
        claims = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM], options={"verify_exp": False})
        survey_id = UUID(str(claims.get("sub"))) if claims.get("type") == LINK_TYPE else None
        expires_at = datetime.fromtimestamp(float(claims["exp"]), UTC)
    except (jwt.PyJWTError, ValueError, KeyError, TypeError):
        survey_id = None
    stmt = select(PlacementSurvey).where(PlacementSurvey.id == survey_id).execution_options(populate_existing=True)
    survey = await db.scalar(stmt.with_for_update() if lock else stmt) if survey_id else None
    if survey is None or survey.sent_at is None:
        raise HTTPException(404, NOT_FOUND)
    if survey.responded_at is not None or expires_at <= datetime.now(UTC):
        raise HTTPException(410, GONE)
    return survey


# --- the sweep (S1-S5, S7) -------------------------------------------------------------------------------------------------------------
def _email(survey: PlacementSurvey, placement: Placement, company: Company, greeting: str, sender: User, now: datetime, reminder: bool) -> RM:
    about = f"the {placement.role} role at {company.name}"
    if survey.respondent == "client":
        ask = f"How satisfied are you with the candidate we placed in {about}?"
    else:
        ask = f"How satisfied are you with your placement in {about}?"
    body = (f"Hello {greeting},\n\n{'A reminder: ' if reminder else ''}{ask} Rate it from 1 to 5 and add a comment if you like -- it takes "
            f"a minute and needs no login:\n\n{link(survey.id, now)}\n\nThe link works for {SURVEY_LINK_DAYS} days.\n\nThank you")  # fmt: skip
    return RM(
        company_id=company.id if survey.contact_id else None,
        contact_id=survey.contact_id,
        candidate_id=None if survey.contact_id else placement.candidate_id,
        sender_user_id=sender.id,
        channel="email",
        subject=f"{'Reminder: ' if reminder else ''}How did your placement go?",
        body=body,
        delivery_status="queued",
        sent_at=now,
    )


async def _candidate_name(db: AsyncSession, placement: Placement) -> str | None:
    """S4: the candidate's name when they can be emailed (an address, not archived)."""
    candidate = await db.get(Candidate, placement.candidate_id)
    return candidate.name if candidate and candidate.email and candidate.archived_at is None else None


async def _queue(db: AsyncSession, survey: PlacementSurvey, placement: Placement, greeting: str, sender: User, now: datetime, reminder: bool) -> RM:
    message = _email(survey, placement, await db.get(Company, placement.company_id), greeting, sender, now, reminder)
    db.add(message)
    await db.flush()
    return message


async def _send_new(db: AsyncSession, placement: Placement, respondent: str, now: datetime) -> RM | None:
    survey = PlacementSurvey(id=uuid4(), placement_id=placement.id, respondent=respondent)  # the id signs the link before the insert
    if respondent == "client":
        contact = await client_contact(db, placement)
        survey.contact_id, greeting = (contact.id, contact.name) if contact else (None, None)
        survey.skip_reason = None if contact else "no_contact"
    else:
        greeting = await _candidate_name(db, placement)
        survey.skip_reason = None if greeting else "no_email"
    sender = await _sender(db, placement) if not survey.skip_reason else None
    if not survey.skip_reason and sender is None:
        survey.contact_id, survey.skip_reason = None, "no_sender"
    message = None
    if not survey.skip_reason:
        message = await _queue(db, survey, placement, greeting, sender, now, reminder=False)
        survey.message_id, survey.sent_at = message.id, now
    db.add(survey)
    await db.flush()
    return message


async def _resend(db: AsyncSession, survey: PlacementSurvey, now: datetime) -> RM | None:
    placement = await db.get(Placement, survey.placement_id)
    sender = await _sender(db, placement)
    if survey.contact_id:
        contact = await db.get(CompanyContact, survey.contact_id)
        greeting = contact.name if _reachable(contact, placement.company_id) else None
    else:
        greeting = await _candidate_name(db, placement)
    if greeting is None or sender is None:  # the recipient has since left or opted out: no reminder (checked again tomorrow)
        return None
    message = await _queue(db, survey, placement, greeting, sender, now, reminder=True)
    survey.resend_message_id, survey.resent_at = message.id, now
    return message


def _missing(respondent: str):
    return ~exists().where(PlacementSurvey.placement_id == Placement.id, PlacementSurvey.respondent == respondent)


async def run_surveys(now: datetime | None = None) -> dict[str, int]:
    """Daily (beat). A due placement gets its missing rows; an unanswered survey sent SURVEY_RESEND_DAYS ago gets its one reminder. Bounded
    batches with `FOR UPDATE SKIP LOCKED`; the unique (placement, respondent) is the backstop. The emails publish after the commit."""
    now = now or datetime.now(UTC)
    today = now.astimezone(requirements.IST).date()
    counts = {"sent": 0, "skipped": 0, "resent": 0}
    queued: list[UUID] = []
    async with SessionLocal() as db:
        due = await db.scalars(
            select(Placement)
            .join(JobOffer, JobOffer.id == Placement.offer_id)
            .where(
                JobOffer.joining_status == "joined",
                JobOffer.actual_joining_date <= today - timedelta(days=SURVEY_AFTER_DAYS),
                JobOffer.actual_joining_date >= today - timedelta(days=SURVEY_LOOKBACK_DAYS),
                or_(_missing("client"), _missing("candidate")),
            )
            .order_by(JobOffer.actual_joining_date, Placement.id)
            .limit(SWEEP_LIMIT)
            .with_for_update(of=Placement, skip_locked=True)
        )
        for placement in list(due):
            have = set(await db.scalars(select(PlacementSurvey.respondent).where(PlacementSurvey.placement_id == placement.id)))
            for respondent in ("client", "candidate"):
                if respondent in have:
                    continue
                message = await _send_new(db, placement, respondent, now)
                counts["sent" if message else "skipped"] += 1
                queued += [message.id] if message else []
        reminders = await db.scalars(
            select(PlacementSurvey)
            .where(
                PlacementSurvey.sent_at <= now - timedelta(days=SURVEY_RESEND_DAYS),
                PlacementSurvey.sent_at > now - timedelta(days=SURVEY_LINK_DAYS),  # an unsendable reminder stops being retried
                PlacementSurvey.resent_at.is_(None),
                PlacementSurvey.responded_at.is_(None),
            )
            .order_by(PlacementSurvey.sent_at, PlacementSurvey.id)
            .limit(SWEEP_LIMIT)
            .with_for_update(skip_locked=True)
        )
        for survey in list(reminders):
            message = await _resend(db, survey, now)
            if message:
                counts["resent"] += 1
                queued.append(message.id)
        await db.commit()
    for message_id in queued:
        enqueue_recruiter_email(message_id)
    logger.info("placement_surveys_sweep", extra={"extra_fields": counts})
    return counts


# --- the public link (S8/S9) ------------------------------------------------------------------------------------------------------------
async def wait_seconds(db: AsyncSession, ip: str) -> int:
    since = datetime.now(UTC) - REFUSED_WINDOW
    newest = (
        await db.scalars(
            select(AuditLog.created_at)
            .where(AuditLog.action == REFUSED_ACTION, AuditLog.created_at > since, AuditLog.metadata_json["ip"].as_string() == ip)
            .order_by(AuditLog.created_at.desc())
            .limit(REFUSED_MAX_PER_IP)
        )
    ).all()
    if len(newest) < REFUSED_MAX_PER_IP:
        return 0
    return min(int(REFUSED_WINDOW.total_seconds()), max(1, math.ceil((newest[-1] + REFUSED_WINDOW - datetime.now(UTC)).total_seconds())))


def refused(db: AsyncSession, ip: str, status: int) -> None:
    db.add(AuditLog(user_id=None, action=REFUSED_ACTION, entity_type="placement_survey", entity_id=None, metadata_json={"ip": ip, "status": status}))


async def public_out(db: AsyncSession, survey: PlacementSurvey) -> dict:
    placement = await db.get(Placement, survey.placement_id)
    company = await db.get(Company, placement.company_id)
    return {"respondent": survey.respondent, "role": placement.role, "company": company.name}


def respond(db: AsyncSession, survey: PlacementSurvey, rating: int, comment: str | None, now: datetime) -> None:
    survey.rating, survey.comment, survey.responded_at = rating, comment or None, now
    db.add(AuditLog(user_id=None, action=RESPONDED_ACTION, entity_type="placement_survey", entity_id=str(survey.id),
                    metadata_json={"placement_id": str(survey.placement_id), "respondent": survey.respondent, "rating": rating}))  # fmt: skip


# --- on the placement (S10) ----------------------------------------------------------------------------------------------------------
def _row_out(survey: PlacementSurvey | None) -> dict | None:
    if survey is None:
        return None
    status = "skipped" if survey.skip_reason else "responded" if survey.responded_at else "sent"
    return {
        "status": status,
        "status_label": STATUS_LABELS[status],
        "sent_at": survey.sent_at,
        "resent_at": survey.resent_at,
        "responded_at": survey.responded_at,
        "rating": survey.rating,
        "comment": survey.comment,
        "skip_reason": survey.skip_reason,
        "skip_reason_label": SKIP_LABELS.get(survey.skip_reason) if survey.skip_reason else None,
    }


async def satisfaction(db: AsyncSession, placement_id: UUID) -> dict:
    rows = {s.respondent: s for s in await db.scalars(select(PlacementSurvey).where(PlacementSurvey.placement_id == placement_id).execution_options(populate_existing=True))}
    return {respondent: _row_out(rows.get(respondent)) for respondent in ("client", "candidate")}
