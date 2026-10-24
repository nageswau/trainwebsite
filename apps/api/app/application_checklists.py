"""ccrm-019 (DEC-SCOPE-257): an application checklist item's status and the readiness summary. Pure rules; the web mirrors the labels
in lib/applicationChecklist.ts. AC1: an item is its counselor mark when set, else the best status among its current linked documents,
else `pending` (missing)."""

# What a counselor may mark an item (migration 0180 repeats it).
MARKS = ("requested", "not_required")
COMPLETE = frozenset({"verified", "approved", "not_required"})
# Best first: a document further down the list never hides a better one linked to the same item.
RANK = ("verified", "approved", "not_required", "under_review", "review", "uploaded", "pending", "draft", "requested", "incomplete", "reupload_required", "expired")
NO_TEMPLATE_GATE_MODE = "warn"  # AC5
READY_FOR_SUBMISSION = "ready_for_submission"

GATE_BLOCKED = "Ready for Submission needs every required checklist document complete"
GATE_NEEDS_REASON = "Some required checklist documents are not complete -- give an override reason to continue"


def item_status(mark: str | None, document_statuses: list[str]) -> str:
    if mark:
        return mark
    known = [s for s in document_statuses if s in RANK]
    return min(known, key=RANK.index) if known else "pending"


def summary(items: list[dict]) -> dict:
    """`items`: dicts with id, label, required, status."""
    required = [i for i in items if i["required"]]
    optional = [i for i in items if not i["required"]]
    missing = [{"id": i["id"], "label": i["label"], "status": i["status"]} for i in required if i["status"] not in COMPLETE]
    return {
        "required_total": len(required),
        "required_complete": len(required) - len(missing),
        "optional_total": len(optional),
        "optional_complete": sum(i["status"] in COMPLETE for i in optional),
        "ready": not missing,
        "missing": missing,
    }
