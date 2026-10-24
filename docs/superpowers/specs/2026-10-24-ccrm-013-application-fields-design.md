# ccrm-013 — Application fields and counselor-editable dates (design)

Backlog: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` `ccrm-013` (absorbs `nehn-037` part 3, scholarship). Owner answers CC4/CC5 apply.
Dependencies: none. The owner asked to proceed with recommended answers; every F-call below is a recommended default,
`NEEDS_CONFIRMATION`, recorded as `DEC-SCOPE-256`.

## Intent

The counselor runs every application (CC4) but cannot record the university-side facts of one (faculty, campus, start date, fees,
scholarship…) nor correct its three dates. The student must see a scholarship update on their own page (nehn-037 AC2).

## What is built

- **Columns** on `overseas_applications` (migration `0179_application_fields`, all nullable, additive): `faculty` (140),
  `campus` (140), `course_start_date` (date), `university_portal_url` (500), `university_contact_name` (140),
  `university_contact_email` (254), `tuition_fee` (Numeric 12,2), `currency` (3), `scholarship_status` (20),
  `scholarship_amount` (Numeric 12,2), `documents_completed_on` (date), `decision_due_on` (date). CHECKs: currency in the list,
  scholarship status in the list, fee/amount ≥ 0, amount only when `awarded`.
- **Route** `GET` + `PATCH /workflows/overseas/applications/{id}/details` — counselor (own applications, direct **and agency**, CC4),
  Overseas Admin; scoped and row-locked through the ccrm-015 entry (`_outcome_entry`: scope, recheck, archived agency record → 409).
  The generic `PATCH /overseas/applications/{id}` is unchanged (it still refuses a counselor on an agency application, AGN-023 H4).
- **FE** counselor "Evaluate Applications" card: an "Application details" toggle opening `ApplicationDetailsForm` (view + edit).
  Student `/overseas/student/applications`: "Course start" and "Scholarship" columns. Agency application detail: the new fields
  read-only.

## Calls (F1–F9, recommended defaults)

- **F1 Currency list:** INR, GBP, USD, EUR, CAD, AUD, NZD, SGD, AED. One currency per application, used by fee and scholarship amount.
- **F2 Route:** a dedicated details route (like ccrm-014/015/023) instead of loosening the generic PATCH, so the counselor can edit agency
  applications without opening the stage/commission path the generic PATCH guards.
- **F3 Scholarship:** status none/applied/awarded/declined. Amount accepted only with `awarded` ("officially confirmed"); moving away from
  awarded clears the amount. An amount needs a currency.
- **F4 Currency required** whenever a fee or a scholarship amount is set (422).
- **F5 Dates:** all pass the 2000–2100 range check; `submitted_on` and `documents_completed_on` cannot be in the future (1-day IST slack,
  existing `_not_future`). `documents_completed_on` is editable now; ccrm-019 will also set it automatically.
- **F6 Portal URL:** http(s) only, no `user:password@` part (stored only, never credentials). Contact email validated.
- **F7 Closed applications:** details stay editable (withdrawn/terminal), as the generic PATCH leaves non-status fields editable; an
  archived agency record answers 409 (existing ccrm-015 entry rule).
- **F8 History/notify (CC5):** every save writes an audit row with the changed fields' before/after (author = actor). On an agency
  application the AGN-017 recipients get "Application details updated" (no values in the body). The student (with a login) is notified
  only when the scholarship status changes.
- **F9 Visibility:** student sees course start date and scholarship (status + amount); portal URL, contact, fee, faculty/campus and internal
  dates stay staff/agency-side. The agency sees all fields read-only; the agent's own edit form is unchanged.

## Non-goals

No new roles; no change to the agent PATCH, the stage machine, AGN-017 reminder logic (it reads the same deadline columns, so a counselor
edit simply moves the reminder date) or ccrm-019's automation.

## Tests

API: role/scope (other counselor 403, agent 403, admin ok, agency app ok for counselor), validation (currency with fee, amount only when
awarded, future submitted_on, portal URL credentials/scheme, unknown currency), round-trip of every field, null clears, audit diff, agency
notice, student notice on scholarship change only, student portal columns, agency detail fields. Migration test (upgrade/downgrade).
Web: component test for the form (view, edit, validation message, save). Playwright: counselor edits details, student sees scholarship.
