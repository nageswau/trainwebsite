"""rec-019 (DEC-SCOPE-160, spec §1-§4): profile sharing -- one share of 1-20 pool candidates for one requirement, to its company over Email,
WhatsApp, the employer Portal or Other, and the company's response per candidate.

R8 is enforced here, server-side: the summary a company sees (the email, the WhatsApp text, the portal) is an allowlist that never holds a
phone number, an email address, LinkedIn or a salary (S6). A resume leaves only through a 7-day random token whose SHA-256 alone is stored
(S7), or the employer's own authenticated route; every download is audited. Email and WhatsApp reuse rec-026's `recruiter_messages` row
(the worker, the retries, the daily caps). Functions only; nothing here commits. Logs and audit rows carry ids and the channel -- never a
name, an address or a token."""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from urllib.parse import quote
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    AuditLog,
    Candidate,
    CandidateResume,
    CandidateSkill,
    Company,
    CompanyContact,
    CompanyDocument,
    EmployerProfile,
    InstitutionDataPermission,
    Job,
    JobApplication,
    ProfileShare,
    ProfileShareItem,
    RecruiterMessage,
    Skill,
    User,
)
from app.notifications.phone import wa_number
from app.schemas import RecShareCreate
from app.services import applications, candidate_sourcing, candidates, company_pipeline, contact_status, mailer, recruiter_companies
from app.services import recruiter_contracts as contracts
from app.services import recruiter_messages as messages
from app.services import recruiter_requirements as requirements

logger = logging.getLogger("app.recruiter")

IST = ZoneInfo("Asia/Kolkata")
LINK_TTL = timedelta(days=7)  # S7: the tel-012 C1 period
PUBLIC_RESUME_PATH = "/api/v1/public/shared-resume/"
MESSAGE_CHANNELS = ("email", "whatsapp")
MOVABLE = ("sourced", "screened", "shortlisted")  # S4: moved forward to Profile Shared; later open stages stay where they are
REFUSED = ("rejected", "withdrawn", "joined")
SKILL_LIMIT = 10
CHANNEL_LABELS = {"email": "Email", "whatsapp": "WhatsApp", "portal": "Portal", "other": "Other"}
RESPONSE_LABELS = {"pending": "Pending", "interested": "Interested", "not_interested": "Not interested", "interview_requested": "Interview requested"}
CONTACT_REQUIRED = "Choose the company contact to send the profiles to"
CONTACT_UNUSABLE = "Choose an active contact of this requirement's company"
NO_PORTAL_USERS = "This company has no employer portal account yet. Share by email, WhatsApp or Other"
NOT_IN_POOL = "Choose active candidates from the pool"
NO_PERMISSION = "Record each candidate's permission to be represented (Source and outreach) before sharing"
LINK_GONE = "This link has expired or is no longer available"
ITEM_NOT_FOUND = "Shared profile not found"
# pob-011 (DEC-SCOPE-427 V4-V8): shares to the requirement's vendor
VENDOR_CONTACT_UNUSABLE = "Choose an active contact of this requirement's vendor"
NO_VENDOR = "This requirement did not come through a vendor"
VENDOR_NO_PORTAL = "A vendor has no employer portal. Share by email, WhatsApp or Other"
VENDOR_NOT_ACTIVE = "Profiles can be shared with this vendor only while it is active"
VENDOR_NO_AGREEMENT = "The vendor agreement must be signed or active before sharing profiles with this vendor"
VENDOR_NO_NDA = "Upload the vendor's signed NDA before sharing profiles with it"
CONSENT_MISSING = "Confirm the candidates' consent and say how it was given before sharing their full details with a vendor"
DETAIL_LABELS = {"named": "Named", "anonymised": "Anonymised", "full": "Full details"}


# --- tokens (S7) --------------------------------------------------------------------------------------------------------------------
def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def link(token: str) -> str:
    return f"{settings.frontend_url.rstrip('/')}{PUBLIC_RESUME_PATH}{token}"


# --- the summary (S6) ---------------------------------------------------------------------------------------------------------------
def experience(months: int | None) -> str | None:
    if months is None:
        return None
    years, rest = divmod(months, 12)
    parts = [f"{years} yr{'s' if years != 1 else ''}"] if years else []
    if rest or not years:
        parts.append(f"{rest} mo{'s' if rest != 1 else ''}")
    return " ".join(parts)


async def skill_names(db: AsyncSession, candidate_ids: list[UUID]) -> dict[UUID, list[str]]:
    """Up to SKILL_LIMIT active skill names per candidate, verified first -- one query."""
    rows = await db.execute(
        select(CandidateSkill.candidate_id, Skill.name)
        .join(Skill, Skill.id == CandidateSkill.skill_id)
        .where(CandidateSkill.candidate_id.in_(candidate_ids), Skill.active.is_(True))
        .order_by(CandidateSkill.candidate_id, (CandidateSkill.status == "verified").desc(), func.lower(Skill.name))
    )
    names: dict[UUID, list[str]] = {cid: [] for cid in candidate_ids}
    for candidate_id, name in rows.all():
        if len(names[candidate_id]) < SKILL_LIMIT:
            names[candidate_id].append(name)
    return names


def summary(candidate: Candidate, skills: list[str]) -> dict:
    """The allowlist a company may see. Adding a field here is a decision (R8), never a convenience."""
    return {
        "code": candidate.candidate_code,
        "name": candidate.name,
        "qualification": candidate.qualification,
        "college": candidate.college,
        "passing_year": candidate.passing_year,
        "experience_months": candidate.experience_months,
        "current_company": candidate.current_company,
        "location": candidate.location,
        "preferred_locations": list(candidate.preferred_locations or []),
        "preferred_role": candidate.preferred_role,
        "notice_days": candidate.notice_days,
        "skills": skills,
    }


def vendor_summary(candidate: Candidate, skills: list[str], detail: str) -> dict:
    """pob-011 V6: what a vendor sees. Anonymised drops the name and current company (and the share gets no resume link); full adds the
    contact details, which only a share with the consent stub, an NDA and a current agreement reaches."""
    base = summary(candidate, skills)
    if detail == "anonymised":
        return base | {"name": None, "current_company": None}
    return base | {"email": candidate.email, "mobile": candidate.mobile}


def _who(s: dict) -> str:
    return f"{s['name']} ({s['code']})" if s["name"] else f"Candidate {s['code']}"


def _lines(s: dict) -> list[str]:
    fields = (
        ("Email", s.get("email")),
        ("Mobile", s.get("mobile")),
        ("Qualification", " · ".join(str(v) for v in (s["qualification"], s["college"], s["passing_year"]) if v)),
        ("Experience", experience(s["experience_months"])),
        ("Current company", s["current_company"]),
        ("Location", s["location"]),
        ("Preferred locations", ", ".join(s["preferred_locations"])),
        ("Preferred role", s["preferred_role"]),
        ("Notice period", f"{s['notice_days']} days" if s["notice_days"] is not None else None),
        ("Skills", ", ".join(s["skills"])),
    )
    return [f"   {label}: {value}" for label, value in fields if value]


def _resume_line(token: str | None, expires_at: datetime) -> str:
    return f"Resume: {link(token)} (link valid until {expires_at.astimezone(IST):%d %b %Y})" if token else "Resume on request"


def email_text(job: Job, company: Company, contact: CompanyContact, sender: User, entries: list[tuple[dict, str | None]], expires_at: datetime) -> tuple[str, str]:
    lines = [f"Dear {contact.name},", "", f"Please find {len(entries)} candidate profile{'s' if len(entries) != 1 else ''} for {job.title} ({job.requirement_code}) at {company.name}.", ""]
    for number, (s, token) in enumerate(entries, 1):
        lines += [f"{number}. {_who(s)}", *_lines(s), f"   {_resume_line(token, expires_at)}", ""]
    lines += ["Please reply with your feedback on each profile.", "", "Regards,", sender.full_name]
    return f"Candidate profiles: {job.title}"[:200], "\n".join(lines)


def whatsapp_text(job: Job, contact: CompanyContact, sender: User, entries: list[tuple[dict, str | None]], expires_at: datetime) -> str:
    lines = [f"Hi {contact.name}, candidate profiles for {job.title} ({job.requirement_code}):", ""]
    for number, (s, token) in enumerate(entries, 1):
        facts = ", ".join(v for v in (s.get("email"), s.get("mobile"), experience(s["experience_months"]), s["location"], ", ".join(s["skills"][:5])) if v)
        lines += [f"{number}. {_who(s)}{f' – {facts}' if facts else ''}", f"   {_resume_line(token, expires_at)}"]
    lines += ["", f"– {sender.full_name}"]
    return "\n".join(lines)


def wa_url(mobile: str | None, text: str) -> str:
    return f"https://wa.me/{wa_number(mobile)}?text={quote(text, safe='')}"


# --- create (S1-S5, S11) ------------------------------------------------------------------------------------------------------------
async def _contact(db: AsyncSession, company_id: UUID, payload: RecShareCreate) -> CompanyContact | None:
    """A contact of the recipient company: the requirement's own (the end client) or, on a vendor share, the vendor's (pob-011 V4)."""
    if payload.contact_id is None:
        if payload.channel in MESSAGE_CHANNELS:
            raise HTTPException(422, CONTACT_REQUIRED)
        return None
    contact = await db.get(CompanyContact, payload.contact_id)
    if contact is None or contact.company_id != company_id:
        raise HTTPException(422, VENDOR_CONTACT_UNUSABLE if payload.recipient == "vendor" else CONTACT_UNUSABLE)
    if not contact.active:
        raise HTTPException(409, messages.CONTACT_INACTIVE)
    contact_status.refuse_do_not_contact(contact)  # pob-005 D6
    return contact


async def _check_channel(db: AsyncSession, job: Job, channel: str, contact: CompanyContact | None) -> None:
    if channel == "email":
        if not mailer.smtp_configured():
            raise HTTPException(503, messages.EMAIL_NOT_CONFIGURED)
        if not contact.email:
            raise HTTPException(409, messages.NO_EMAIL["contact"])
    elif channel == "whatsapp" and wa_number(contact.mobile) is None:
        raise HTTPException(409, messages.NO_NUMBER["contact"])
    elif channel == "portal" and not await db.scalar(select(EmployerProfile.id).where(EmployerProfile.company_id == job.company_id).limit(1)):
        raise HTTPException(409, NO_PORTAL_USERS)


def _names(people) -> str:
    return ", ".join(f"{c.name} ({c.candidate_code})" for c in people)


async def _candidates(db: AsyncSession, ids: list[UUID], user: User) -> list[Candidate]:
    """Pool members only (a student who has not opted in is not one, S4), read-locked, in the order chosen. pob-014 (DEC-SCOPE-425 S9):
    an institution's student only while the sharer is on its active permission, and only when that permission allows placement."""
    rows = (await db.scalars(select(Candidate).where(Candidate.id.in_(ids), *candidates.pool_filter(user.id)).with_for_update(read=True))).all()
    found = {c.id: c for c in rows}
    archived = [c for c in rows if c.archived_at is not None]
    if len(found) != len(ids) or archived:
        raise HTTPException(422, f"{NOT_IN_POOL}{f': {_names(archived)} is archived' if archived else ''}")
    permission_ids = {c.institution_permission_id for c in rows} - {None}
    if permission_ids:
        # FOR SHARE: a concurrent revoke or purpose change waits for this share's commit
        permissions = (await db.scalars(select(InstitutionDataPermission).where(InstitutionDataPermission.id.in_(permission_ids)).with_for_update(read=True))).all()
        allowed = {p.id for p in permissions if "placement" in p.purposes}
        barred = [c for c in rows if c.institution_permission_id is not None and c.institution_permission_id not in allowed]
        if barred:
            raise HTTPException(422, f"Their institution's permission does not cover the placement purpose: {_names(barred)}")
    # pob-018 (DEC-SCOPE-428 A7, AC3): under the same FOR SHARE lock, so a concurrent withdrawal waits for this share's commit
    unpermitted = [found[i] for i in ids if not candidate_sourcing.permitted(found[i])]
    if unpermitted:
        raise HTTPException(422, f"{NO_PERMISSION}: {_names(unpermitted)}")
    return [found[i] for i in ids]


async def _vendor(db: AsyncSession, job: Job, payload: RecShareCreate) -> Company | None:
    """pob-011 V4-V7: the vendor a vendor share goes to, after its gate (read-locked so a concurrent suspension waits); None for a client
    share. Every refusal happens before anything is written."""
    if payload.recipient == "client":
        return None
    if job.via_vendor_id is None:
        raise HTTPException(422, NO_VENDOR)
    if payload.channel == "portal":
        raise HTTPException(422, VENDOR_NO_PORTAL)
    vendor = await db.scalar(select(Company).where(Company.id == job.via_vendor_id).with_for_update(read=True))
    if vendor.vendor_status != "active":
        raise HTTPException(409, VENDOR_NOT_ACTIVE)
    agreement = await contracts.company_contract_ref(db, vendor, "vendor")
    if agreement is None or agreement["status"] not in ("signed", "active"):
        raise HTTPException(409, VENDOR_NO_AGREEMENT)
    if await db.scalar(select(CompanyDocument.id).where(CompanyDocument.company_id == vendor.id, CompanyDocument.kind == "nda").limit(1)) is None:
        raise HTTPException(409, VENDOR_NO_NDA)
    if payload.detail == "full" and not (payload.consent_confirmed and payload.consent_reference):
        raise HTTPException(409, CONSENT_MISSING)
    return vendor


async def _repeats(db: AsyncSession, job: Job, people: list[Candidate], to_vendor: bool) -> tuple[list[Candidate], bool]:
    """The candidates already shared for this requirement or (pob-011 V8) for another requirement of the same end client when this share
    or the earlier one went through a vendor. The flag says whether any repeat is only of the second kind (the wording names the route)."""
    other_route = and_(Job.company_id == job.company_id, true() if to_vendor else ProfileShare.recipient == "vendor")
    rows = (
        await db.execute(
            select(ProfileShareItem.candidate_id, ProfileShare.job_id)
            .join(ProfileShare, ProfileShare.id == ProfileShareItem.share_id)
            .join(Job, Job.id == ProfileShare.job_id)
            .where(or_(ProfileShare.job_id == job.id, other_route), ProfileShareItem.candidate_id.in_([c.id for c in people]))
        )
    ).all()
    same_job = {cid for cid, job_id in rows if job_id == job.id}
    shared = {cid for cid, _ in rows}
    return [c for c in people if c.id in shared], bool(shared - same_job)


async def create(db: AsyncSession, user: User, payload: RecShareCreate, now: datetime) -> tuple[ProfileShare, str | None]:
    """The error order of spec §3. Returns the share and, for WhatsApp, the wa.me URL. An email is stored `queued`; the route publishes
    it after the commit (rec-026 MS7)."""
    job = await requirements.load_scoped(db, user, payload.requirement_id, lock=True)  # serialises shares of one requirement (S5)
    applications.require_writer(user, job.id, "create_profile_share")
    if job.status in requirements.ENDED:
        raise HTTPException(409, "Profiles cannot be shared for a closed or cancelled requirement")
    vendor = await _vendor(db, job, payload)
    detail = (payload.detail or "anonymised") if vendor else "named"
    contact = await _contact(db, vendor.id if vendor else job.company_id, payload)
    await _check_channel(db, job, payload.channel, contact)
    people = await _candidates(db, payload.candidate_ids, user)
    existing = {
        a.candidate_id: a for a in (await db.scalars(select(JobApplication).where(JobApplication.job_id == job.id, JobApplication.candidate_id.in_(payload.candidate_ids)).with_for_update())).all()
    }
    closed = [c for c in people if c.id in existing and existing[c.id].status in REFUSED]
    if closed:
        raise HTTPException(422, f"Rejected, withdrawn or joined candidates cannot be shared for this requirement: {_names(closed)}")
    repeats, across = await _repeats(db, job, people, vendor is not None)
    if repeats and not payload.repeat:
        where = "for this requirement or with its end client through another route" if across else "for this requirement"  # pob-011 V8
        raise HTTPException(
            409,
            {
                "message": f"{len(repeats)} of these candidates {'was' if len(repeats) == 1 else 'were'} already shared {where}. Share again?",  # QA-02
                "duplicates": [{"id": str(c.id), "name": c.name, "code": c.candidate_code} for c in repeats],
            },
        )
    if payload.channel in MESSAGE_CHANNELS:
        await messages.check_cap(db, user, payload.channel, now)

    company = await db.get(Company, job.company_id)
    latest = (
        select(CandidateResume.candidate_id, func.max(CandidateResume.version).label("version"))
        .where(CandidateResume.candidate_id.in_(payload.candidate_ids))
        .group_by(CandidateResume.candidate_id)
        .subquery()
    )
    resumes = dict(
        (
            await db.execute(
                select(CandidateResume.candidate_id, CandidateResume.id).join(latest, (latest.c.candidate_id == CandidateResume.candidate_id) & (latest.c.version == CandidateResume.version))
            )
        ).all()
    )
    skills = await skill_names(db, payload.candidate_ids)
    expires_at = now + LINK_TTL
    linked = payload.channel in MESSAGE_CHANNELS and detail != "anonymised"  # pob-011 V6: an anonymised share never carries a resume link
    tokens = {c.id: secrets.token_urlsafe(32) if linked and c.id in resumes else None for c in people}
    entries = [(vendor_summary(c, skills[c.id], detail) if vendor else summary(c, skills[c.id]), tokens[c.id]) for c in people]
    recipient_id = vendor.id if vendor else company.id

    message, url = None, None
    if payload.channel in MESSAGE_CHANNELS:
        if payload.channel == "email":
            subject, body = email_text(job, company, contact, user, entries, expires_at)
        else:
            subject, body = None, whatsapp_text(job, contact, user, entries, expires_at)
            url = wa_url(contact.mobile, body)
        message = RecruiterMessage(
            company_id=recipient_id,
            contact_id=contact.id,
            sender_user_id=user.id,
            channel=payload.channel,
            subject=subject,
            body=body,
            delivery_status="queued" if payload.channel == "email" else None,
            sent_at=now,
        )
        db.add(message)
        await db.flush()
        await recruiter_companies.refresh_last_contact(db, recipient_id)  # pob-003 D4

    share = ProfileShare(
        job_id=job.id,
        company_id=recipient_id,
        recipient=payload.recipient,
        detail=detail,
        consent_reference=payload.consent_reference if detail == "full" else None,  # pob-011 V7: confirmed by the sharer
        contact_id=contact.id if contact else None,
        channel=payload.channel,
        note=payload.note,
        message_id=message.id if message else None,
        shared_by_user_id=user.id,
    )
    db.add(share)
    await db.flush()
    await contact_status.advance(db, user, [share.contact_id], "contacted", "share")  # pob-005 D4
    note = f"Profile shared ({CHANNEL_LABELS[payload.channel]})"
    for candidate in people:
        application = existing.get(candidate.id)
        if application is None:
            application = await applications.create(db, user, job, candidate, "profile_shared", note)
        elif application.status in MOVABLE:
            await applications.change_status(db, user, application, "profile_shared", note)
        token = tokens[candidate.id]
        db.add(
            ProfileShareItem(
                share_id=share.id,
                candidate_id=candidate.id,
                application_id=application.id,
                resume_id=resumes.get(candidate.id),
                token_hash=digest(token) if token else None,
                token_expires_at=expires_at if token else None,
            )
        )
    await db.flush()
    if vendor is None:  # pob-011 V9: the end client did not receive a vendor share from us, so its BD pipeline stays
        await company_pipeline.apply_event(db, await db.scalar(select(Company).where(Company.id == company.id).with_for_update().execution_options(populate_existing=True)), "profiles_shared", user)
    db.add(
        AuditLog(
            user_id=user.id,
            action="profile_share.create",
            entity_type="profile_share",
            entity_id=str(share.id),
            metadata_json={"job_id": str(job.id), "channel": share.channel, "candidate_ids": [str(c.id) for c in people], "repeat": bool(repeats),
                          "recipient": share.recipient, "detail": share.detail},  # fmt: skip  # pob-011: never the consent text
        )
    )
    return share, url


# --- responses (S9) ------------------------------------------------------------------------------------------------------------------
def respond(item: ProfileShareItem, user: User, response: str | None, now: datetime) -> list[str]:
    """Records who answered and when, only when the response changes. Returns the changed field names."""
    changed = []
    if response is not None and response != item.response:
        item.response, item.responded_by_user_id, item.responded_at = response, user.id, now
        changed.append("response")
    return changed


async def load_item(db: AsyncSession, share_id: UUID, item_id: UUID) -> tuple[ProfileShare, ProfileShareItem]:
    row = (
        await db.execute(select(ProfileShare, ProfileShareItem).join(ProfileShareItem, ProfileShareItem.share_id == ProfileShare.id).where(ProfileShare.id == share_id, ProfileShareItem.id == item_id))
    ).first()
    if row is None:
        raise HTTPException(404, ITEM_NOT_FOUND)
    return row[0], row[1]


# --- the employer portal (S8) --------------------------------------------------------------------------------------------------------
async def employer_company(db: AsyncSession, user: User) -> UUID:
    if user.role != "employer":
        raise HTTPException(403, "Employer role required")
    company_id = await db.scalar(select(EmployerProfile.company_id).where(EmployerProfile.user_id == user.id))
    if company_id is None:
        raise HTTPException(404, "Employer profile not found")
    return company_id


def _portal(company_id: UUID):
    return (
        select(ProfileShareItem, ProfileShare, Candidate, Job)
        .join(ProfileShare, ProfileShare.id == ProfileShareItem.share_id)
        .join(Candidate, Candidate.id == ProfileShareItem.candidate_id)
        .join(Job, Job.id == ProfileShare.job_id)
        .where(ProfileShare.company_id == company_id, ProfileShare.channel == "portal")
    )


async def portal_item(db: AsyncSession, company_id: UUID, item_id: UUID, *, lock: bool = False):
    """Another company's item, or one not shared to the portal, is the same 404 as a missing one."""
    stmt = _portal(company_id).where(ProfileShareItem.id == item_id)
    row = (await db.execute(stmt.with_for_update(of=ProfileShareItem) if lock else stmt)).first()
    if row is None:
        raise HTTPException(404, ITEM_NOT_FOUND)
    return row


async def portal_page(db: AsyncSession, company_id: UUID, limit: int, offset: int) -> dict:
    total = await db.scalar(select(func.count()).select_from(_portal(company_id).subquery()))
    rows = (await db.execute(_portal(company_id).order_by(ProfileShare.created_at.desc(), ProfileShareItem.id).limit(limit).offset(offset))).all()
    skills = await skill_names(db, [candidate.id for _, _, candidate, _ in rows]) if rows else {}
    return {"items": [portal_out(item, share, candidate, job, skills[candidate.id]) for item, share, candidate, job in rows], "total": total or 0, "limit": limit, "offset": offset}


def portal_out(item: ProfileShareItem, share: ProfileShare, candidate: Candidate, job: Job, skills: list[str]) -> dict:
    return {
        "id": item.id,
        "shared_at": share.created_at,
        "requirement": {"code": job.requirement_code, "title": job.title},
        "candidate": summary(candidate, skills),
        "has_resume": item.resume_id is not None,
        "response": item.response,
        "response_label": RESPONSE_LABELS[item.response],
    }


# --- resume downloads (S7, S8) --------------------------------------------------------------------------------------------------------
async def item_by_token(db: AsyncSession, token: str, now: datetime) -> tuple[ProfileShareItem, Candidate, CandidateResume] | None:
    """None for an unknown or expired token, an archived candidate or no resume -- the route answers one 404 for all of them."""
    row = (
        await db.execute(
            select(ProfileShareItem, Candidate, CandidateResume)
            .join(Candidate, Candidate.id == ProfileShareItem.candidate_id)
            .join(CandidateResume, CandidateResume.id == ProfileShareItem.resume_id)
            .where(ProfileShareItem.token_hash == digest(token), ProfileShareItem.token_expires_at > now, Candidate.archived_at.is_(None))
        )
    ).first()
    return tuple(row) if row else None


def download_audit(db: AsyncSession, user: User | None, item: ProfileShareItem, via: str) -> None:
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action="profile_share.resume_download",
            entity_type="profile_share_item",
            entity_id=str(item.id),
            metadata_json={"via": via, "candidate_id": str(item.candidate_id)},
        )
    )


def resume_name(candidate: Candidate, resume: CandidateResume) -> str:
    return f"resume-{candidate.candidate_code}.{candidates.EXTENSION.get(resume.content_type, 'bin')}"


# --- lists and output -------------------------------------------------------------------------------------------------------------
def can_respond(user: User, job: Job) -> bool:
    return applications.can_write(user) and job.status not in requirements.ENDED


async def page(db: AsyncSession, user: User, where, limit: int, offset: int) -> dict:
    """Newest first; four queries whatever the page size (count, shares, items, people)."""
    total = await db.scalar(select(func.count()).select_from(ProfileShare).where(where))
    rows = (
        await db.execute(
            select(ProfileShare, Job, User, CompanyContact, RecruiterMessage)
            .join(Job, Job.id == ProfileShare.job_id)
            .join(User, User.id == ProfileShare.shared_by_user_id)
            .outerjoin(CompanyContact, CompanyContact.id == ProfileShare.contact_id)
            .outerjoin(RecruiterMessage, RecruiterMessage.id == ProfileShare.message_id)
            .where(where)
            .order_by(ProfileShare.created_at.desc(), ProfileShare.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    items = await _items(db, [share.id for share, *_ in rows])
    return {
        "items": [share_out(share, job, sender, contact, message, items.get(share.id, []), can_respond(user, job)) for share, job, sender, contact, message in rows],
        "total": total or 0,
        "limit": limit,
        "offset": offset,
    }


async def one(db: AsyncSession, user: User, share_id: UUID) -> dict:
    return (await page(db, user, ProfileShare.id == share_id, 1, 0))["items"][0]


async def _items(db: AsyncSession, share_ids: list[UUID]) -> dict[UUID, list[dict]]:
    if not share_ids:
        return {}
    responder = select(User.id, User.full_name).subquery()
    rows = (
        await db.execute(
            select(ProfileShareItem, Candidate, responder.c.full_name)
            .join(Candidate, Candidate.id == ProfileShareItem.candidate_id)
            .outerjoin(responder, responder.c.id == ProfileShareItem.responded_by_user_id)
            .where(ProfileShareItem.share_id.in_(share_ids))
            .order_by(func.lower(Candidate.name), ProfileShareItem.id)
        )
    ).all()
    out: dict[UUID, list[dict]] = {}
    for item, candidate, responder_name in rows:
        out.setdefault(item.share_id, []).append(item_out(item, candidate, responder_name))
    return out


def item_out(item: ProfileShareItem, candidate: Candidate, responder_name: str | None) -> dict:
    return {
        "id": item.id,
        "candidate": {"id": candidate.id, "code": candidate.candidate_code, "name": candidate.name},
        "application_id": item.application_id,
        "has_resume": item.resume_id is not None,
        "link_expires_at": item.token_expires_at,
        "response": item.response,
        "response_label": RESPONSE_LABELS[item.response],
        "feedback": item.feedback,
        "responded_by": {"id": item.responded_by_user_id, "full_name": responder_name} if item.responded_by_user_id else None,
        "responded_at": item.responded_at,
    }


def share_out(share: ProfileShare, job: Job, sender: User, contact: CompanyContact | None, message: RecruiterMessage | None, items: list[dict], respond_ok: bool) -> dict:
    return {
        "id": share.id,
        "channel": share.channel,
        "channel_label": CHANNEL_LABELS[share.channel],
        "requirement": {"id": job.id, "code": job.requirement_code, "title": job.title},
        "company_id": share.company_id,
        "recipient": share.recipient,  # pob-011 V10
        "detail": share.detail,
        "detail_label": DETAIL_LABELS[share.detail],
        "consent_reference": share.consent_reference,
        "contact": {"id": contact.id, "name": contact.name} if contact else None,
        "note": share.note,
        "message": {"id": message.id, "delivery_status": message.delivery_status} if message else None,
        "shared_by": {"id": sender.id, "full_name": sender.full_name},
        "created_at": share.created_at,
        "items": items,
        "can_respond": respond_ok,
    }


def log(event: str, user: User | None, entity_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id) if user else None, "entity_id": str(entity_id), **extra}})
