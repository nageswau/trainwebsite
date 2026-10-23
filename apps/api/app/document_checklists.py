"""ccrm-018 (DEC-SCOPE-248): the document checklist template vocabulary. Migration 0173 repeats KINDS and GATE_MODES
(test_ccrm_018_migration); the web mirrors them in lib/documentChecklists.ts."""

CHECKLIST_KINDS = ("admission", "visa")
CHECKLIST_GATE_MODES = ("block", "warn")  # CC10: block refuses Ready for Submission; warn needs an override reason (ccrm-019)

# ccrm-021's fixed document status list (Appendix A), in display order; an item that names no statuses allows all of these.
STANDARD_STATUSES = ("pending", "requested", "uploaded", "under_review", "verified", "incomplete", "reupload_required", "expired", "not_required")
# The CV/SOP drafting flow (§8), offered per item on top of the standard list.
DRAFTING_STATUSES = ("draft", "review", "approved")
ITEM_STATUSES = STANDARD_STATUSES + DRAFTING_STATUSES

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
