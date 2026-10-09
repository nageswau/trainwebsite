"""upc-011 (DEC-SCOPE-152, spec CL1/CL6): partnership event values -- the six §9 calendar kinds that are neither university meetings
(upc-009) nor university visits (upc-010), in source order (EVID-020 L358-L363), and the statuses.

Constants only, with no app imports, so the model CHECKs, the migration's parity test, the service and the schemas share one list. Labels
live in the web client (`lib/partnershipCalendar.ts`)."""

KINDS = ("conference", "education_fair", "partner_meeting", "mou_signing", "webinar", "university_presentation")
STATUSES = ("scheduled", "cancelled")
MAX_EMPLOYEES = 10  # CL5 (upc-009 MG7)
MAX_SPAN_DAYS = 31  # CL2: an event spans at most one calendar window
