"""ccrm-017 (DEC-SCOPE-258, J1-J4): a direct overseas student's journey stage -- one value derived on every read from the student's
applications (stage + ccrm-015 outcome) and whether a counselor is engaged; never stored on an application. No model imports, so
ccrm-032 and nehn-033 can reuse it. Spec: docs/superpowers/specs/2026-10-25-ccrm-017-student-journey-stage-design.md."""

from app.application_outcome import TERMINAL

STAGES = (("lead", "Lead"), ("counselling", "Counselling"), ("applying", "Applying"), ("offer", "Offer"), ("visa", "Visa"), ("enrolled", "Enrolled"))
LABELS = dict(STAGES)
ORDER = tuple(LABELS)
# J2: DEC-WF-001 application stage -> journey stage; any other (legacy) value reads Counselling
APPLICATION_STAGE = {
    "enquiry": "counselling",
    "eligibility_evaluation": "counselling",
    "university_selection": "applying",
    "offer": "offer",
    "visa_documentation": "visa",
    "status_tracking": "visa",
    "enrolled": "enrolled",
    "university_review": "applying",  # browser QA-01: the seed's pre-DEC-WF-001 "with the university" status
}
NOTES = {"on_hold": "On hold", "deferred": "Deferred"}
ALL_CLOSED = "All applications closed"


def _rank(app) -> int:
    return ORDER.index(APPLICATION_STAGE.get(app.status, "counselling"))


def derive(apps: list, *, engaged: bool) -> tuple[str, object | None, str | None]:
    """(stage, best application or None, note). J3: the furthest live application, a tie to the most recently updated; J4: with none
    live, Counselling once a counselor is engaged or an application ever existed, else Lead."""
    live = [a for a in apps if a.status != "withdrawn" and a.outcome not in TERMINAL]  # withdrawn status = AGN-008's terminal stage
    if not live:
        return ("counselling", None, ALL_CLOSED) if apps else ("counselling" if engaged else "lead", None, None)
    best = max(live, key=lambda a: (_rank(a), a.updated_at))
    return ORDER[_rank(best)], best, NOTES.get(best.outcome)


def steps(stage: str) -> list[dict]:
    at = ORDER.index(stage)
    return [{"key": key, "label": label, "state": "done" if i < at else "current" if i == at else "upcoming"} for i, (key, label) in enumerate(STAGES)]
