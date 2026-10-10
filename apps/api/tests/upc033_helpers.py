"""upc-033 test builders: one fixture "world" for the partnership permission matrix and the commission sweep (spec
docs/superpowers/specs/2026-10-10-upc-033-permission-matrix-design.md, PX2/PX5/PX6). Users are inserted directly and signed in with the token
`/auth/login` issues (no bcrypt round); universities, courses, agreements, terms and documents go through their real routes, so each is valid.
Every value is unique per call: the test database is shared and never truncated."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import update

from app.models import (
    BdmProfile,
    OverseasApplication,
    PartnershipEvent,
    PartnershipMessageTemplate,
    PartnershipProfile,
    PartnershipTask,
    University,
    UniversityCommissionReceipt,
    UniversityContact,
    UniversityImportBatch,
    UniversityMeeting,
    UniversityVisit,
    User,
)
from tests.tel026_helpers import headers
from tests.upc003_helpers import catalogue_country, payload
from tests.upc019_helpers import agreement

__all__ = ["COMMISSION_ROLES", "OTHER_ROLES", "ROLES", "SENTINELS", "headers", "today", "world"]

API = "/api/v1"
# Who calls (PX2). `pm_out` / `head_out` are the same role as `pm` / `head` on another partnership team.
COMMISSION_ROLES = ("pm", "pm_out", "head", "head_out", "super")  # partnership_access.COMMISSION_ROLES
OTHER_ROLES = ("anon", "ovs_admin", "it_admin", "bdm", "cns", "rep", "agent", "student")  # the sweep's non-commission callers (PX6)
ROLES = (*COMMISSION_ROLES, *OTHER_ROLES)

MARK = "Zq033secret"  # in every planted commission text
# PX6: one distinctive value per commission column. None of them may reach a non-commission role, in any response. The integer parts are
# over 59, so no timestamp's "ss.ffffff" can contain one.
SENTINELS = {"course_percent": "73.19", "course_amount": "24681.35", "term_percent": "61.83", "receipt_amount": "8642.97", "text": MARK}
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _u(label: str = "") -> str:
    return f"{label}{uuid.uuid4().hex[:8]}"


def today() -> date:
    return datetime.now(UTC).date()


async def _add(db, row):
    db.add(row)
    await db.flush()
    return row


async def _user(db, role: str, division: str, **over) -> User:
    return await _add(db, User(email=f"{_u('u33-')}@example.local", password_hash="!", full_name=f"{role} {_u()}", role=role, division=division,
                               active=True, email_verified=True, phone="+91 98765 43210", **over))  # fmt: skip


async def _pm(db, head: User) -> User:
    user = await _user(db, "partnership_manager", "overseas")
    await _add(db, PartnershipProfile(user_id=user.id, employee_id=_u("E33-"), reporting_head_user_id=head.id))
    return user


async def _ok(response, status: int = 201) -> dict:
    assert response.status_code == status, f"world setup: {response.request.method} {response.request.url} {response.status_code} {response.text[:300]}"
    return response.json()


async def _university(client, db, actor: User, country_id, pm: User, **values) -> University:
    made = await _ok(await client.post(f"{API}/partnership/universities", headers=headers(actor),
                                       json=payload(country_id, name=f"U33 University {_u()}", overview="A partner university.")))  # fmt: skip
    uid = uuid.UUID(made["university"]["id"])
    await db.execute(update(University).where(University.id == uid).values(primary_manager_user_id=pm.id, **values))
    await db.commit()
    return await db.get(University, uid)


async def _document(client, uid, pm: User, kind: str, title: str, shareable: bool) -> str:
    url = f"{API}/partnership/universities/{uid}/documents"
    data = {"kind": kind, "title": title, "shareable": "true" if shareable else "false"}
    made = await _ok(await client.post(url, headers=headers(pm), data=data, files={"file": ("doc.pdf", PDF, "application/pdf")}))
    return made["document"]["id"]


async def world(client, db) -> dict:
    """Users by matrix role (plus `pm2`, a second report of `head`, for assign / reassign targets) and the ids every row refers to."""
    head, head_out = await _user(db, "partnership_head", "global"), await _user(db, "partnership_head", "global")
    pm, pm2, pm_out = await _pm(db, head), await _pm(db, head), await _pm(db, head_out)
    bdm_mgr = await _user(db, "bdm_manager", "global")
    bdm = await _user(db, "bdm", "it")
    await _add(db, BdmProfile(user_id=bdm.id, bdm_type="college", employee_id=_u("B33-"), reporting_manager_user_id=bdm_mgr.id))
    users = {
        "pm": pm, "pm_out": pm_out, "head": head, "head_out": head_out, "super": await _user(db, "super_admin", "global"),
        "ovs_admin": await _user(db, "overseas_admin", "overseas"), "it_admin": await _user(db, "it_admin", "it"), "bdm": bdm,
        "cns": await _user(db, "counselor", "overseas"), "agent": await _user(db, "agent", "overseas"),
        "student": await _user(db, "overseas_student", "overseas"), "pm2": pm2,
    }  # fmt: skip
    await db.commit()
    super_ = users["super"]
    country = await catalogue_country(db)
    uni = await _university(client, db, super_, country.id, pm, catalogue_visible=True)  # published: the public catalogue and counselor slice
    internal = await _university(client, db, super_, country.id, pm)  # unpublished, for publish
    lost = await _university(client, db, super_, country.id, pm, lost_at=datetime.now(UTC), lost_reason="No reply")
    inactive = await _university(client, db, super_, country.id, pm, active=False)
    users["rep"] = await _user(db, "university_rep", "overseas", profile={"university_id": str(uni.id)})

    # Commission data (PX6 sentinels): two courses, a draft agreement with a term, a signed (active) one, a receipt, a commission document.
    base = f"{API}/partnership/universities/{uni.id}"
    category = _u("U33 cat ")
    course = (await _ok(await client.post(f"{base}/courses", headers=headers(pm), json={
        "title": _u("MSc U33 "), "level": "PG", "category": category, "duration": "1 year", "intakes": ["Sep"],
        "tuition_amount": "18000", "tuition_currency": "GBP", "commission": {"percent": SENTINELS["course_percent"]}})))["course"]  # fmt: skip
    await _ok(await client.post(f"{base}/courses", headers=headers(pm), json={
        "title": _u("BSc U33 "), "level": "UG", "category": category, "duration": "3 years", "intakes": ["Sep"],
        "commission": {"amount": SENTINELS["course_amount"], "currency": "GBP"}}))  # fmt: skip
    draft = (await _ok(await client.post(f"{base}/agreements", headers=headers(pm), json={
        "agreement_type": "mou", "start_date": (today() - timedelta(days=10)).isoformat(),
        "expiry_date": (today() + timedelta(days=1000)).isoformat(), "exclusivity": "exclusive"})))["agreement"]  # fmt: skip
    term = (await _ok(await client.post(f"{API}/partnership/agreements/{draft['id']}/commission-terms", headers=headers(pm), json={
        "commission_percent": SENTINELS["term_percent"], "currency": "GBP", "trigger": "enrolment", "conditions": f"{MARK} term"})))["term"]  # fmt: skip
    signed = await agreement(db, uni, head, status="active", start=today() - timedelta(days=30), expiry=today() + timedelta(days=700))
    doc = await _document(client, uni.id, pm, "fee_structure", _u("Fees U33 "), True)
    secret_doc = await _document(client, uni.id, pm, "commission_agreement", f"{MARK} commission {_u()}", False)
    receipt = await _add(db, UniversityCommissionReceipt(university_id=uni.id, amount=Decimal(SENTINELS["receipt_amount"]), currency="GBP",
                                                         received_on=today(), reference=f"{MARK}-{_u()}", note=f"{MARK} note",
                                                         created_by_user_id=head.id))  # fmt: skip
    application = await _add(db, OverseasApplication(student_id=users["student"].id, university_id=uni.id, course_id=uuid.UUID(course["id"]),
                                                     counselor_id=users["cns"].id, status="enrolled", intake="Sep 2027"))  # fmt: skip

    # Partnership work on `uni`, owned by `pm` (each route's own actor rule).
    now = datetime.now(UTC)
    contact = await _add(db, UniversityContact(university_id=uni.id, name="Priya Raman", email=f"{_u('c33-')}@example.local", phone="+44 20 0000 0001",
                                               whatsapp="+44 7700 900001", is_primary=True, shareable=True))  # fmt: skip
    spare_contact = await _add(db, UniversityContact(university_id=uni.id, name="Arun Spare", email=f"{_u('s33-')}@example.local"))
    meeting = await _add(db, UniversityMeeting(code=_u("UM33-"), university_id=uni.id, meeting_type="introduction", starts_at=now - timedelta(hours=2),
                                               mode="online", responsible_user_id=pm.id, created_by_user_id=pm.id))  # fmt: skip

    async def visit(**over) -> UniversityVisit:
        return await _add(db, UniversityVisit(code=_u("VS33-"), university_id=uni.id, city="London", purpose="Partnership review", lead_user_id=pm.id,
                                              created_by_user_id=pm.id, proposed_date=today() + timedelta(days=10), **over))  # fmt: skip

    draft_visit = await visit()
    waiting_visit = await visit(submitted_at=now)
    approved_visit = await visit(status="approved", submitted_at=now, confirmed_date=today())
    booked_visit = await visit(status="travel_booked", submitted_at=now, confirmed_date=today())
    done_visit = await visit(status="visit_completed", submitted_at=now, confirmed_date=today())
    event = await _add(db, PartnershipEvent(code=_u("PE33-"), kind="education_fair", title="U33 fair", starts_on=today() + timedelta(days=5),
                                            ends_on=today() + timedelta(days=6), owner_user_id=pm.id, created_by_user_id=pm.id))  # fmt: skip
    task = await _add(db, PartnershipTask(university_id=uni.id, kind="follow_up", title="Follow up on proposal", assignee_user_id=pm.id,
                                          created_by_user_id=pm.id, due_on=today() + timedelta(days=2), source="manual"))  # fmt: skip
    template = await _add(db, PartnershipMessageTemplate(channel="whatsapp", name=_u("U33 tpl "), body="Hi {name}"))
    batch = await _add(db, UniversityImportBatch(uploaded_by_user_id=head.id, idempotency_key=_u(), file_sha256=uuid.uuid4().hex * 2))
    await db.commit()

    ids = {
        "uni": uni.id, "internal": internal.id, "lost": lost.id, "inactive": inactive.id, "course": course["id"], "agreement": draft["id"],
        "signed": signed.id, "term": term["id"], "doc": doc, "secret_doc": secret_doc, "receipt": receipt.id, "application": application.id,
        "contact": contact.id, "spare_contact": spare_contact.id, "meeting": meeting.id, "draft_visit": draft_visit.id, "waiting_visit": waiting_visit.id,
        "approved_visit": approved_visit.id, "booked_visit": booked_visit.id, "done_visit": done_visit.id, "event": event.id, "task": task.id,
        "template": template.id, "batch": batch.id, "country": country.id,
    }  # fmt: skip
    return {"users": users, "slug": uni.slug, "uni_name": uni.name, "country_slug": country.slug, "category": category, "today": today().isoformat(),
            "month": today().strftime("%Y-%m"), **{k: str(v) for k, v in ids.items()}, **{f"{k}_id": str(u.id) for k, u in users.items()}}  # fmt: skip
