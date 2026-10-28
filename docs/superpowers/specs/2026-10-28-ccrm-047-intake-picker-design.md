# ccrm-047 — Intake Month+Year picker (design)

Source: `docs/delivery/COUNSELOR_CRM_BACKLOG_2.md` § ccrm-047 (Q8, A4, L5). No hard dependency. No migration.

## Intent
Intake is free text today ("Fall 2027", "September next year"), so reports and filters by intake (ccrm-052/053) get
inconsistent values. Every place a person *enters* an intake for a lead, a student profile or a new application gets one shared
picker (month Jan–Dec + year) that writes `"Sep 2027"` into the existing columns.

## Decisions (builder's calls — `NEEDS_CONFIRMATION` where noted)
- I1 Format: `^(Jan|Feb|…|Dec) \d{4}$` (`models.COURSE_MONTHS`). Picker years: current year … current + 3; a saved year outside
  that range is still offered so it displays. Past month of the current year allowed (backlog default).
- I2 "New values only": the backend validates an intake only when it differs from what is stored, so a legacy free-text value
  displays as-is and survives unrelated edits (AC6). Malformed new value → 422 with `loc` = the field.
- I3 Lead create (`TelecallerLeadCreate`, telecaller/manager and counselor walk-in routes): optional `intake`; format-validated in
  the schema; allowed only when the product's group is `overseas` (else 422 — the qualification form shows intake for the
  overseas group only). When given, a `lead_qualifications` row is created with it in the same transaction.
- I4 Lead qualification `PUT`: intake checked only when changed (service, I2).
- I5 Student profile `PUT` (student's own and staff routes): `preferred_intake` checked only when changed (`student_profiles.save`).
  `write()` stays unvalidated so ccrm-008 conversion copies a legacy lead intake unchanged.
- I6 Application create (`OverseasApplicationCreate`): a *sent* intake must match the format. Omitted keeps the server default
  "Next intake" (API backward compatibility). Application `PATCH`, agent applications, the Overseas Admin school-student bridge,
  checklist templates, outcome `new_intake` and CSV import are unchanged (agent / CSV are `NEEDS_CONFIRMATION` in the backlog).
- I7 Frontend: new `components/IntakePicker.tsx` (two labelled selects, "Not recorded" empty option, legacy note
  "Saved as “…” — choose a month and year to replace it."). Used in `NewLeadForm` (overseas-group product only),
  `LeadQualificationForm` (new field kind `intake`), `StudentProfileForm`, `OverseasApplyPanel` (required).
  A half-filled picker is refused client-side ("Choose both the month and the year").

## Non-goals
Changing columns, migrating legacy data, intake on IT leads, agent forms, CSV import, report filters.

## Risks
tel-005/tel-009/ccrm-005/ccrm-007 tests; three existing tests post "Fall 2027" to the student/counselor apply route — they move to
"Sep 2027" because the requirement (AC5) changes that behaviour.

## Acceptance (from backlog)
AC1 telecaller lead with intake "Sep 2027" stored + shown on lead detail; AC2 student sets preferred intake via picker; AC3 counselor
edits student intake; AC4 application intake via picker; AC5 "September next year" (new) → 422; AC6 legacy value displays and an
unrelated profile edit does not fail. Edge: IT lead → intake hidden / refused; conversion copies intake to profile.
