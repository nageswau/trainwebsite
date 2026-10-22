"""ccrm-014 (DEC-SCOPE-240, SS1): an overseas application's sub-status, a detail level under its DEC-WF-001 stage. One definition; the
web mirrors it in apps/web/lib/applicationSubStatus.ts. No model imports: `models.OverseasApplication` validates through `fit`."""

SUB_STATUSES: dict[str, tuple[str, ...]] = {
    "university_selection": ("application_created", "documents_pending", "ready_for_submission", "submitted", "under_review"),
    "offer": ("conditional_offer", "unconditional_offer", "offer_accepted"),
    "visa_documentation": ("visa_preparation", "visa_applied"),
    "status_tracking": ("visa_decision_pending", "visa_approved"),
    "enrolled": ("enrolled",),
}
STAGE_OF = {sub: stage for stage, subs in SUB_STATUSES.items() for sub in subs}


def label(sub_status: str | None) -> str | None:
    return sub_status.replace("_", " ").capitalize() if sub_status else None


def fit(stage: str, sub_status: str | None) -> str | None:
    """SS3: the sub-status an application keeps when its stage becomes `stage` -- cleared unless it belongs there; `enrolled` sets it."""
    if stage == "enrolled":
        return "enrolled"
    return sub_status if sub_status in SUB_STATUSES.get(stage, ()) else None
