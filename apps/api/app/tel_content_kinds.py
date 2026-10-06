"""tel-012 (DEC-SCOPE-078): the fixed message-template kinds of EVID-019 §11 (WhatsApp) and §12 (email), and the asset kinds. The
model CHECKs and the API types read them from here; migration 0079 keeps its own frozen copy."""

WHATSAPP_KINDS = (
    "welcome",
    "course_details",
    "brochure",
    "fee_details",
    "counselling_appointment",
    "reminder",
    "follow_up",
    "overseas_destination",
    "document_request",
)
EMAIL_KINDS = (
    "course_brochure",
    "fee_proposal",
    "counselling_confirmation",
    "overseas_information",
    "university_information",
    "follow_up",
    "appointment_confirmation",
)
KINDS_BY_CHANNEL = {"whatsapp": WHATSAPP_KINDS, "email": EMAIL_KINDS}
ASSET_KINDS = ("brochure", "fee")
