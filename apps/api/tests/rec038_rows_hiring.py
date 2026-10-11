"""rec-038 matrix rows: the hiring group -- an application's status and history (rec-017), its screening (rec-018), profile sharing with
the employer portal and the public resume link (rec-019), interviews (rec-020) and their feedback (rec-021), offers with the student's own
offers (rec-022) and the joining (rec-023).

Every route here takes rec-007's requirement scope through rec-017's `load_scoped` (RBAC_MATRIX §2.62/§2.74/§2.75/§2.81/§2.84/§2.86/
§2.101): the role check first (any other role 403), then out of scope = 404 for the other team's recruiter and manager and another BDM;
the manager and the assigned BDM read, and a write is theirs to refuse (403) after the scope check. The hiring records live on this
group's own requirement on the world's company (rec's), so no other group's rows see them."""

import secrets
import uuid
from datetime import timedelta

from app.models import CandidateResume, Company, Interview, JobApplication, JobOffer, ProfileShare, ProfileShareItem, RecruiterMessage
from app.services import candidates as candidate_svc
from app.services import offers as offer_svc
from app.services import profile_sharing
from tests.rec038_helpers import PDF, ROLES, R, add, allow, make_candidate, make_job, now, tag

READ = ("rec", "mgr", "super", "bdm")  # rec-007 requirement scope: the recruiter, their manager, super_admin, the assigned BDM (R10)
OUT = ("rec_out", "mgr_out", "bdm_out")  # the same roles outside the record's scope: 404, the same as an unknown id (IDOR)
WRITE = ("rec", "super")  # rec-017 `applications.WRITERS` (rec-007's `can_edit` holders); the manager and the BDM read only (403)
LISTS = (*READ, *OUT)  # a list is filtered by the scope, so an out-of-scope caller gets 200 with none of the world's rows
_FILES: dict[str, str] = {}  # one stored object per kind for the whole run (replacing a letter or proof keeps the old object)


def _file(kind: str, store) -> str:
    if kind not in _FILES:
        _FILES[kind] = store(PDF, "application/pdf")
    return _FILES[kind]


def _at(days: int) -> str:
    return (now() + timedelta(days=days)).replace(second=0, microsecond=0).isoformat()


def _pdf(_w):
    return {}, {"file": ("letter.pdf", PDF, "application/pdf")}


# fmt: off
ROWS = [
    # rec-017 -- an application's status and history (§2.62)
    R("get", "/recruiter/applications/{application}/history", **allow(200, *READ), **allow(404, *OUT)),
    R("post", "/recruiter/applications/{application}/status", {"status": "screened"}, **allow(200, *WRITE), **allow(404, *OUT)),
    # rec-018 -- screening (§2.75): the readers read, the writers save (the manager and BDM 403 after the scope check)
    R("get", "/recruiter/applications/{application}/screening", **allow(200, *READ), **allow(404, *OUT)),
    R("put", "/recruiter/applications/{application}/screening", {"result": "hold"}, **allow(200, *WRITE), **allow(404, *OUT)),
    # rec-019 -- profile sharing (§2.86): share / respond are the writers'; the employer reads its company's Portal shares; the public
    # resume link needs no session (the token is the credential, S7), so every caller -- anonymous too -- gets the file
    R("post", "/recruiter/shares", lambda w: {"requirement_id": w["requirement"], "candidate_ids": [w["candidate"]], "channel": "other", "note": tag("R38 ")},
      **allow(201, *WRITE), **allow(404, *OUT)),
    R("patch", "/recruiter/shares/{hiring_share}/items/{hiring_share_item}", lambda w: {"feedback": tag("Strong fit ")}, **allow(200, *WRITE), **allow(404, *OUT)),
    R("get", "/recruiter/companies/{company}/shares", **allow(200, *READ), **allow(404, *OUT)),  # rec-003 company scope (out of scope 404)
    R("get", "/recruiter/requirements/{requirement}/shares", **allow(200, *READ), **allow(404, *OUT)),
    R("get", "/employer/shared-profiles", employer=200),  # S8: `employer_company` -- every other role 403 ("Employer role required")
    R("patch", "/employer/shared-profiles/{hiring_share_item}", {"response": "interested"}, employer=200),
    R("get", "/employer/shared-profiles/{hiring_share_item}/resume", employer=200),
    R("get", "/public/shared-resume/{hiring_token}", **allow(200, *ROLES)),
    # rec-020 -- interviews (§2.74): the lists are scope-filtered (200 for every recruiter-side role); one interview is scoped (404)
    R("get", "/recruiter/applications/{hiring_app}/interviews", **allow(200, *READ), **allow(404, *OUT)),
    R("get", "/recruiter/interviews", **allow(200, *LISTS)),
    R("post", "/recruiter/interviews", lambda w: {"application_id": w["hiring_app"], "round": "technical_round", "scheduled_at": _at(4), "mode": "Online", "notify": False},
      **allow(201, *WRITE), **allow(404, *OUT)),
    R("get", "/recruiter/interviews/{hiring_interview}", **allow(200, *READ), **allow(404, *OUT)),
    R("patch", "/recruiter/interviews/{hiring_interview}", lambda w: {"interviewer": tag("Meera ")}, **allow(200, *WRITE), **allow(404, *OUT)),
    R("post", "/recruiter/interviews/{hiring_interview}/reschedule", lambda w: {"scheduled_at": _at(3), "notify": False}, **allow(200, *WRITE), **allow(404, *OUT)),
    R("post", "/recruiter/interviews/{hiring_interview}/status", {"status": "confirmed"}, **allow(200, *WRITE), **allow(404, *OUT)),
    # rec-021 -- feedback (§2.101) on the Completed interview
    R("put", "/recruiter/interviews/{hiring_done}/feedback", {"overall_rating": 4, "strengths": "Clear Java answers"}, **allow(200, *WRITE), **allow(404, *OUT)),
    # rec-022 -- offers (§2.81): the manager reads and downloads the letter; the student reads only their own offers (anyone else 403)
    R("get", "/recruiter/applications/{application}/offer", **allow(200, *READ), **allow(404, *OUT)),
    R("post", "/recruiter/applications/{hiring_selected}/offer", {"position": "Java Developer"}, **allow(201, *WRITE), **allow(404, *OUT)),
    R("patch", "/recruiter/offers/{hiring_offer}", lambda w: {"position": tag("Lead ")}, **allow(200, *WRITE), **allow(404, *OUT)),
    R("post", "/recruiter/offers/{hiring_offer}/status", {"status": "accepted"}, **allow(200, *WRITE), **allow(404, *OUT)),
    R("get", "/recruiter/offers/{hiring_offer}/letter", **allow(200, *READ), **allow(404, *OUT)),
    R("put", "/recruiter/offers/{hiring_offer}/letter", form=_pdf, **allow(200, *WRITE), **allow(404, *OUT)),
    R("get", "/workflows/it/student/offers", student=200),
    R("get", "/workflows/it/student/offers/{hiring_student_offer}/letter", student=200),
    # rec-023 -- the joining (§2.84) on the Accepted offer: read / proof download for the readers, update / proof upload for the writers
    R("put", "/recruiter/offers/{hiring_accepted}/joining", lambda w: {"joining_location": tag("Pune ")}, **allow(200, *WRITE), **allow(404, *OUT)),
    R("get", "/recruiter/offers/{hiring_accepted}/joining/proof", **allow(200, *READ), **allow(404, *OUT)),
    R("put", "/recruiter/offers/{hiring_accepted}/joining/proof", form=_pdf, **allow(200, *WRITE), **allow(404, *OUT)),
    R("get", "/recruiter/joinings", **allow(200, *LISTS)),
]
# fmt: on
PATH_VALUES = {}


async def build(client, db, w) -> None:
    """On the group's own requirement (rec's, on the world's company): an application in Interview with a scheduled and a completed
    interview, a Selected one without an offer, one with an Offer Received offer and its letter, one with an Accepted offer (joining
    pending) and its proof, the student's own Selected application with an offer and its letter, and a candidate with a resume shared
    to the Portal and by WhatsApp (the link's raw token kept in `w`)."""
    rec, student = w["users"]["rec"], w["users"]["student"]
    company = await db.get(Company, uuid.UUID(w["company"]))
    job = await make_job(db, company, rec)

    async def application(status: str, candidate_id=None, student_id=None) -> JobApplication:
        candidate_id = candidate_id or (await make_candidate(db, rec)).id
        return await add(db, JobApplication(job_id=job.id, candidate_id=candidate_id, student_id=student_id, added_by_user_id=rec.id, status=status))

    letter, proof = _file("letter", offer_svc.store), _file("proof", lambda d, t: offer_svc.store(d, t, offer_svc.PROOF_PREFIX))
    letter_fields = {"letter_key": letter, "letter_content_type": "application/pdf", "letter_name": "offer.pdf", "letter_uploaded_at": now()}
    today = now().date()

    interviewing = await application("interview")
    scheduled = await add(db, Interview(application_id=interviewing.id, scheduled_at=(now() + timedelta(days=2)).replace(second=0, microsecond=0),
                                        mode="Online", round="hr_round", status="scheduled", created_by_user_id=rec.id))  # fmt: skip
    done = await add(db, Interview(application_id=interviewing.id, scheduled_at=now() - timedelta(hours=2), mode="Online", round="hr_round",
                                   status="completed", created_by_user_id=rec.id))  # fmt: skip
    selected = await application("selected")
    offered = await application("selected")
    offer = await add(db, JobOffer(application_id=offered.id, status="offer_received", position="Java Developer", offered_on=today, created_by_user_id=rec.id,
                                   **letter_fields))  # fmt: skip
    joining = await application("selected")
    accepted = await add(db, JobOffer(application_id=joining.id, status="accepted", joining_status="pending", position="Java Developer", offered_on=today,
                                      joining_date=today + timedelta(days=14), created_by_user_id=rec.id, proof_key=proof, proof_content_type="application/pdf",
                                      proof_name="proof.pdf", proof_uploaded_at=now()))  # fmt: skip
    mine = await application("selected", candidate_id=uuid.UUID(w["student_candidate"]), student_id=student.id)
    student_offer = await add(db, JobOffer(application_id=mine.id, status="offer_received", position="Java Developer", offered_on=today, created_by_user_id=rec.id,
                                           **letter_fields))  # fmt: skip

    shared = await application("profile_shared")
    resume = await add(db, CandidateResume(candidate_id=shared.candidate_id, version=1, storage_key=_file("resume", candidate_svc.store), content_type="application/pdf",
                                           file_name="resume.pdf", size_bytes=len(PDF), uploaded_by_user_id=rec.id))  # fmt: skip
    portal = await add(db, ProfileShare(job_id=job.id, company_id=company.id, channel="portal", shared_by_user_id=rec.id))
    item = await add(db, ProfileShareItem(share_id=portal.id, candidate_id=shared.candidate_id, application_id=shared.id, resume_id=resume.id))
    message = await add(db, RecruiterMessage(company_id=company.id, contact_id=uuid.UUID(w["contact"]), sender_user_id=rec.id, channel="whatsapp",
                                             body="Profiles for your requirement", sent_at=now()))  # fmt: skip
    whatsapp = await add(db, ProfileShare(job_id=job.id, company_id=company.id, contact_id=message.contact_id, channel="whatsapp", message_id=message.id,
                                          shared_by_user_id=rec.id))  # fmt: skip
    token = secrets.token_urlsafe(32)
    await add(db, ProfileShareItem(share_id=whatsapp.id, candidate_id=shared.candidate_id, application_id=shared.id, resume_id=resume.id,
                                   token_hash=profile_sharing.digest(token), token_expires_at=now() + profile_sharing.LINK_TTL))  # fmt: skip
    await db.commit()
    w |= {
        "hiring_job": str(job.id), "hiring_app": str(interviewing.id), "hiring_interview": str(scheduled.id), "hiring_done": str(done.id),
        "hiring_selected": str(selected.id), "hiring_offer": str(offer.id), "hiring_accepted": str(accepted.id),
        "hiring_student_offer": str(student_offer.id), "hiring_share": str(portal.id), "hiring_share_item": str(item.id), "hiring_token": token,
    }  # fmt: skip
