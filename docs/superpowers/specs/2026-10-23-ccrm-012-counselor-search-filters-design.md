# ccrm-012 — Counselor quick search and list filters (design)

Source: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` §ccrm-012 (spec §12, UNVERIFIED source). Dependencies ccrm-011 (PR #301) and ccrm-014
(PR #303) are merged. Owner instruction for this session: proceed on recommended answers; QS1-QS8 below are **UNVERIFIED** calls.

## Intent

An overseas counselor finds a lead, student or application in one place, and narrows the Students / Applications / Leads lists, without
ever seeing a record outside their own caseload (backlog acceptance: searching another counselor's student's phone returns nothing).

## Decisions (UNVERIFIED, recommended defaults)

- **QS1 Who:** the overseas counselor only (`role=counselor`, `division=overseas`); anyone else 403. nehn-041 (admin unified search) may
  reuse the service later; not built here.
- **QS2 Scope:** leads = `lead_handover.counselor_scope` (owner + division); students = `counselor_students.visible_student_ids`
  (own applications' students + csc-001 linked students); applications = `counselor_id == me`, `with_owner` (agency students without a
  login appear through their applications; School-bridged rows stay out, as on every shared list).
- **QS3 Matching:** `q` stripped, 3-100 characters (422 otherwise). Case-insensitive literal substring (`ILIKE … ESCAPE`) of name, email
  and the code (lead `LD-`, student code, application `APP-`). When `q` is phone-shaped (only digits, spaces, `+ - ( ) .`, at least 3
  digits) its digits also match a digits-only substring of the phone (`Enquiry.phone_normalized`, `regexp_replace(User.phone, '\D', '')`).
- **QS4 Result shape:** `{q, leads, students, applications}`; each group `{items (≤10), more: bool}`; items carry an `href` to the
  page that already exists (lead detail, student notes page, applications list filtered by nothing — the app code is shown).
- **QS5 Rate limit:** 30 searches per rolling minute per counselor, counted from `AuditLog` rows `counselor.search` (the lookups
  `purpose=link` precedent); 429 + `Retry-After`. The audit row stores no search text (PII), only result counts.
- **QS6 Students/Applications filters** (extend `services/application_filters.py`): `country` (university's country id), `university`,
  `intake` (exact), `stage` (7 stages + `withdrawn`), `sub_status` (ccrm-014 catalogue; must fit the stage when both sent), `from` / `to`
  (application created date, inclusive; `from <= to`). Same rules as AGN-023: SQL-side before the 500-row cap, a bad / repeated value is
  422 never ignored. Options are built from the caller's own applications (counselor) or all (admin), so no out-of-scope university or
  country is named. Available to the overseas counselor and Overseas Admin (shared bar), still only on students/applications.
- **QS7 Leads filters:** `GET /counselor/leads` gains `stage` (lead stage key), `priority` (hot/warm/cold), `from` / `to` (lead created
  date). Bad value 422. The leads panel keeps them in the URL.
- **QS8 Placement / perf:** the search box is a panel on the counselor dashboard. No migration: every query is scope-first (bounded by
  the counselor's ids); enquiries already carry `ix_enquiries_phone_normalized` and `ix_enquiries_email_lower`. Trigram indexes are not
  added (no pg_trgm in the project; the scoped sets are small).

## Non-goals

Admin unified search (nehn-041); full-text resume search; saving filters; exports (ccrm-035); dashboard redesign (ccrm-032).

## Regression risks

AGN-023 filter contract and tests; `management_metrics` builds `ApplicationFilters(agency, counselor)` positionally (new fields default
None); `CounselorLeadsPanel` paging; the IT counselor's leads (filters work there too — same route — but search is overseas only).
