"""ccrm-013 (DEC-SCOPE-256): an application's university-side fields and the counselor-editable dates. One definition; the web mirrors the
lists in apps/web/lib/applicationDetails.ts and migration 0179 repeats them in its CHECKs. No model imports."""

from decimal import Decimal

CURRENCIES = ("INR", "GBP", "USD", "EUR", "CAD", "AUD", "NZD", "SGD", "AED")  # F1
SCHOLARSHIP_STATUSES = ("none", "applied", "awarded", "declined")  # F3
SCHOLARSHIP_LABELS = {"none": "None", "applied": "Applied", "awarded": "Awarded", "declined": "Declined"}

# Everything the details route reads and writes, in the form's order. The three dates existed before (AGN-008); the rest are 0179's.
DETAIL_FIELDS = (
    "faculty", "campus", "course_start_date", "university_portal_url", "university_contact_name", "university_contact_email",
    "tuition_fee", "currency", "scholarship_status", "scholarship_amount", "submitted_on", "application_deadline", "offer_deadline",
    "documents_completed_on", "decision_due_on",
)  # fmt: skip
NEW_FIELDS = tuple(name for name in DETAIL_FIELDS if name not in {"submitted_on", "application_deadline", "offer_deadline"})

CURRENCY_REQUIRED = "Currency is required with a tuition fee or a scholarship amount"
AMOUNT_NEEDS_AWARD = "A scholarship amount is recorded only when the scholarship is awarded"


def scholarship_label(status: str | None) -> str | None:
    return SCHOLARSHIP_LABELS.get(status) if status else None


def problem(values: dict) -> str | None:
    """F3/F4 on the row as it will be saved (not just the payload): a fee or amount needs a currency; an amount needs `awarded`."""
    if values.get("scholarship_amount") is not None and values.get("scholarship_status") != "awarded":
        return AMOUNT_NEEDS_AWARD
    if (values.get("tuition_fee") is not None or values.get("scholarship_amount") is not None) and not values.get("currency"):
        return CURRENCY_REQUIRED
    return None


def scholarship_text(status: str | None, amount: Decimal | None, currency: str | None) -> str | None:
    """The student's view (F9): "Awarded — GBP 1,500.00", or the label alone."""
    label = scholarship_label(status)
    if label and amount is not None and currency:
        return f"{label} — {currency} {amount:,.2f}"
    return label
