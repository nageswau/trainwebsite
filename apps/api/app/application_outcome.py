"""ccrm-015 (DEC-SCOPE-244): an overseas application's exception outcome, independent of its stage. One definition; the web mirrors it in
apps/web/lib/applicationOutcome.ts and migration 0170 repeats the values in its CHECK. No model imports."""

OUTCOMES = ("rejected", "withdrawn", "deferred", "on_hold", "offer_declined", "visa_refused")
TERMINAL = frozenset({"rejected", "withdrawn", "offer_declined", "visa_refused"})  # O2: only the Overseas Admin reopens these
SETTABLE = ("rejected", "withdrawn", "deferred", "on_hold", "offer_declined")  # O4: visa_refused is ccrm-026's to write
CLEARED = "cleared"  # an event row: the outcome was resumed or reopened
REQUESTERS = ("student", "counselor", "agent", "university")


def label(outcome: str | None) -> str | None:
    return outcome.replace("_", " ").capitalize() if outcome else None
