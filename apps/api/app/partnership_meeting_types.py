"""upc-009 (DEC-SCOPE-145, spec MG1/MG4/MG9): university meeting values -- the §7 meeting types (EVID-020 L288-L312, source order), the
Online/Offline mode, statuses and history events.

Constants only, with no app imports, so the model CHECKs, the migration's parity test, the service and the schemas share one list. Labels
live in the web client (`lib/meetings.ts`)."""

TYPES = (
    "introduction",
    "partnership_discussion",
    "commercial_discussion",
    "mou_discussion",
    "product_presentation",
    "student_recruitment_discussion",
    "application_process_discussion",
    "marketing_discussion",
    "university_visit",
    "campus_visit",
    "webinar",
    "training_session",
)
MODES = ("online", "offline")
STATUSES = ("scheduled", "completed", "cancelled")
EVENTS = ("scheduled", "edited", "rescheduled", "completed", "cancelled")
MAX_CONTACTS = 20  # MG6
MAX_EMPLOYEES = 10  # MG7 (upc-010 VS11)
