"""tel-026 test builders: one fixture "world" for the §22 permission matrix. Rows are inserted directly and sessions are minted with the token
`/auth/login` issues, so a world costs no bcrypt round. Every value is unique per call: the test database is shared and never truncated."""

import uuid
from datetime import UTC, date, datetime, timedelta

from app.core.security import create_token
from app.models import (
    Appointment,
    BdmMeetingRequest,
    Enquiry,
    LeadCall,
    LeadFollowUp,
    LeadImportBatch,
    LeadMessage,
    LeadQualification,
    TelAsset,
    TelCampaign,
    TelDistributionRule,
    TelecallerProfile,
    TelMessageTemplate,
    TelProduct,
    TelScript,
    TelTarget,
    User,
)

# Who calls. `tel_out` / `mgr_out` / `cns_out` are the same role as `tel` / `mgr` / `cns` but outside the world's leads.
ROLES = ("anon", "tel", "tel_out", "mgr", "mgr_out", "cns", "cns_out", "it_admin", "ovs_admin", "super", "student")


def _u(label: str = "") -> str:
    return f"{label}{uuid.uuid4().hex[:8]}"


async def _add(db, row):
    db.add(row)
    await db.flush()
    return row


async def _user(db, role: str, division: str) -> User:
    return await _add(db, User(email=f"{_u('t26-')}@example.local", password_hash="!", full_name=f"{role} {_u()}", role=role,
                               division=division, active=True, email_verified=True, phone="+91 98765 43210"))


async def _telecaller(db, manager: User, team: str = "it") -> User:
    user = await _user(db, "telecaller", team)
    await _add(db, TelecallerProfile(user_id=user.id, team=team, employee_id=_u("E26-"), reporting_manager_user_id=manager.id))
    return user


def _lead(tel: User | None, **over) -> Enquiry:
    return Enquiry(**({"division": "it", "name": f"Lead {_u()}", "email": f"{_u()}@example.local", "phone": "9876543210", "subject": "Course",
                       "message": "", "source": "website", "status": "follow_up", "telecaller_user_id": tel.id if tel else None} | over))


def headers(user: User | None) -> dict:
    if user is None:
        return {}
    return {"Cookie": f"edusphere_access={create_token(str(user.id), user.role, user.division, 'access', user.session_version)}"}


def at(*, days: int = 1, hours: int = 0) -> str:
    return (datetime.now(UTC).replace(second=0, microsecond=0) + timedelta(days=days, hours=hours)).isoformat()


async def world(db) -> dict:
    """Users by matrix role (plus `spare`, a telecaller with no work, `gone`, a deactivated one, and `spare_mgr`, a manager with no
    reports) and the ids every row's path or body refers to."""
    mgr = await _user(db, "telecaller_manager", "global")
    mgr_out = await _user(db, "telecaller_manager", "global")
    spare_mgr = await _user(db, "telecaller_manager", "global")
    tel, tel_out, spare, gone = (await _telecaller(db, mgr), await _telecaller(db, mgr_out), await _telecaller(db, mgr),
                                 await _telecaller(db, mgr))
    gone.active = False
    users = {
        "tel": tel, "tel_out": tel_out, "mgr": mgr, "mgr_out": mgr_out, "cns": await _user(db, "counselor", "it"),
        "cns_out": await _user(db, "counselor", "it"), "it_admin": await _user(db, "it_admin", "it"),
        "ovs_admin": await _user(db, "overseas_admin", "overseas"), "super": await _user(db, "super_admin", "global"),
        "student": await _user(db, "it_student", "it"), "spare": spare, "spare_mgr": spare_mgr, "gone": gone,
    }
    cns = users["cns"]
    product = await _add(db, TelProduct(product_group="it", name=_u("T26 product "), team="it", active=True, sort_order=1000))
    campaign = await _add(db, TelCampaign(name=_u("T26 campaign "), source="instagram", product_id=product.id, start_date=date(2026, 9, 1)))
    lead = await _add(db, _lead(tel, product_id=product.id))
    fresh = await _add(db, _lead(tel, product_id=product.id))  # no appointment yet
    await _add(db, _lead(gone))  # the deactivated telecaller's open lead, for the tel-025 handover
    bare = await _add(db, TelProduct(product_group="it", name=_u("T26 bare "), team="it", active=True, sort_order=1000))  # no script yet
    handed = await _add(db, _lead(tel, owner_id=cns.id, status="counselling_scheduled"))
    linked_student = await _user(db, "it_student", "it")
    linked = await _add(db, _lead(tel, owner_id=cns.id, status="application_enrollment", converted_user_id=linked_student.id,
                                  converted_at=datetime.now(UTC), converted_by_user_id=cns.id))
    now = datetime.now(UTC)
    call = await _add(db, LeadCall(lead_id=lead.id, caller_user_id=tel.id, call_type="outgoing", outcome="interested", duration_seconds=60,
                                   occurred_at=now))
    follow_up = await _add(db, LeadFollowUp(lead_id=lead.id, due_at=now + timedelta(days=1), reason="course_details", status="open",
                                            created_by_user_id=tel.id))
    message = await _add(db, LeadMessage(lead_id=lead.id, sender_user_id=tel.id, channel="whatsapp", body="Hello", sent_at=now))
    appointment = await _add(db, Appointment(division="it", staff_id=cns.id, scheduled_at=now - timedelta(hours=1),
                                             appointment_type="it_course_counselling", status="scheduled", lead_id=lead.id,
                                             appointment_code=_u("CAP-T26"), booked_by_user_id=tel.id, mode="Online"))
    await _add(db, LeadQualification(lead_id=lead.id, updated_by_user_id=tel.id))
    request = await _add(db, BdmMeetingRequest(code=_u("MR26-"), requester_user_id=tel.id, request_type="college", bdm_type="college",
                                               organization_name="Govt College", person_name="Dr Rao", contact_phone="+91 98765 43210",
                                               proposed_at=now + timedelta(days=2), mode="In person", purpose="Partnership"))
    script = await _add(db, TelScript(product_id=product.id, name=_u("T26 script "), steps=[{"title": "Open", "notes": None}]))
    template = await _add(db, TelMessageTemplate(channel="whatsapp", kind="welcome", name=_u("T26 tpl "), body="Hi {name}"))
    asset = await _add(db, TelAsset(name=_u("T26 brochure "), kind="brochure", storage_key=f"tel-assets/{_u()}.pdf", file_name="b.pdf",
                                    size_bytes=10, uploaded_by_user_id=mgr.id))
    rule = await _add(db, TelDistributionRule(team="it", kind="city", city=_u("City "), telecaller_user_id=tel.id))
    target = await _add(db, TelTarget(scope="user", user_id=tel.id, period="daily", kpi="calls", value=50, effective_from=date.today(),
                                      set_by_user_id=mgr.id))
    batch = await _add(db, LeadImportBatch(campaign_id=campaign.id, division="it", uploaded_by_user_id=mgr.id, idempotency_key=_u(),
                                           file_sha256=uuid.uuid4().hex * 2))
    await db.commit()
    ids = {"lead": lead.id, "fresh": fresh.id, "handed": handed.id, "linked": linked.id, "call": call.id, "follow_up": follow_up.id, "message": message.id, "appointment": appointment.id,
           "request": request.id, "script": script.id, "template": template.id, "asset": asset.id, "rule": rule.id, "target": target.id,
           "batch": batch.id, "product": product.id, "bare_product": bare.id, "campaign": campaign.id}
    return {"users": users, "student_email": users["student"].email, **{k: str(v) for k, v in ids.items()}, **{f"{k}_id": str(u.id) for k, u in users.items()}}
