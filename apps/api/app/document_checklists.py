"""ccrm-018 (DEC-SCOPE-248): the document checklist template vocabulary. Migration 0173 repeats KINDS and GATE_MODES
(test_ccrm_018_migration); the web mirrors them in lib/documentChecklists.ts."""

import re

CHECKLIST_KINDS = ("admission", "visa")
CHECKLIST_GATE_MODES = ("block", "warn")  # CC10: block refuses Ready for Submission; warn needs an override reason (ccrm-019)

# ccrm-021's fixed document status list (Appendix A), in display order; an item that names no statuses allows all of these.
STANDARD_STATUSES = ("pending", "requested", "uploaded", "under_review", "verified", "incomplete", "reupload_required", "expired", "not_required")
# The CV/SOP drafting flow (§8), offered per item on top of the standard list.
DRAFTING_STATUSES = ("draft", "review", "approved")
ITEM_STATUSES = STANDARD_STATUSES + DRAFTING_STATUSES

# ccrm-021 (DEC-SCOPE-251): every stored `student_documents.verification_status` is one of ITEM_STATUSES (migration 0176 repeats it).
# S1: `pending` is a new upload awaiting review; the review routes still accept the pre-0174 outcomes and store their new codes.
LEGACY_STATUSES = {"rejected": "reupload_required", "changes_required": "incomplete"}
# What a counselor / Overseas Admin may set (`expired` only by the daily job; `requested` / `uploaded` belong to ccrm-019/020).
REVIEW_STATUSES = ("under_review", "verified", "incomplete", "reupload_required", "not_required")
# AGN-003 (DEC-SCOPE-044 P5/P6): an agency member decides a pending document; staff may only verify.
AGENT_REVIEW_STATUSES = ("verified", "incomplete", "reupload_required")
# S2: a passport is verified only with a (future) expiry date. S6: the drafting statuses only on CV / SOP types until ccrm-019.
EXPIRY_REQUIRED_TYPES = frozenset({"passport"})
DRAFTING_TYPES = frozenset({"cv", "resume", "sop", "statement of purpose"})


# How the generic portal tables show a status (the web mirrors these in lib/documentChecklists.ts STATUS_LABELS).
STATUS_LABELS = {
    "pending": "Pending review", "requested": "Requested", "uploaded": "Uploaded", "under_review": "Under review", "verified": "Verified",
    "incomplete": "Incomplete", "reupload_required": "Re-upload required", "expired": "Expired", "not_required": "Not required",
    "draft": "Draft", "review": "Review", "approved": "Approved",
}
PASSPORT_EXPIRY_REQUIRED ="Add the passport's expiry date before verifying it"
PASSPORT_EXPIRED = "This passport has expired -- ask the student for a current one"
DRAFTING_ONLY = "Draft, Review and Approved apply to CV and SOP documents only"


def review_status(value: str) -> str:
    """The stored code for a review route's input (a pre-0174 outcome maps to its new code)."""
    return LEGACY_STATUSES.get(value, value)


def _named(document_type: str, names: frozenset[str]) -> bool:
    """Whether a (free-text) document type names one of `names` as whole words: "QA Passport", "SOP draft" (browser QA-01)."""
    words = f" {' '.join(re.findall(r'[a-z]+', document_type.lower()))} "
    return any(f" {name} " in words for name in names)


def review_refusal(document_type: str, status: str, expiry_date, today) -> str | None:
    """Why a counselor / admin may not set `status` on a document of this type (S2, S6), or None."""
    if status in DRAFTING_STATUSES and not _named(document_type, DRAFTING_TYPES):
        return DRAFTING_ONLY
    if status == "verified" and _named(document_type, EXPIRY_REQUIRED_TYPES):
        if expiry_date is None:
            return PASSPORT_EXPIRY_REQUIRED
        if expiry_date < today:
            return PASSPORT_EXPIRED
    return None

MAX_ITEMS = 50

# Courses saved before the course master's level list (upc-017 CO3) carry free-text levels such as the seed's "Masters". Template
# matching reads them through this map (lower-cased); a level outside both the master list and the map matches level-free templates only.
LEGACY_COURSE_LEVELS = {
    "masters": "PG",
    "master's": "PG",
    "master": "PG",
    "postgraduate": "PG",
    "pg": "PG",
    "bachelors": "UG",
    "bachelor's": "UG",
    "bachelor": "UG",
    "undergraduate": "UG",
    "ug": "UG",
    "phd": "PhD",
    "doctorate": "PhD",
    "diploma": "Diploma",
    "foundation": "Foundation",
}


def course_level_key(level: str | None) -> str | None:
    """The course master level an application's course counts as, or None."""
    return LEGACY_COURSE_LEVELS.get(level.strip().lower()) if level else None
