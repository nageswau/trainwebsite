# ccrm-005 — Lead data fields: contact preference, study, academic, English, consent, referral

Design, 2026-10-25. Backlog item `ccrm-005` (`docs/delivery/COUNSELOR_CRM_BACKLOG.md`), spec §3 "Lead creation fields" (UNVERIFIED
source, owner request; see the backlog's evidence note). Dependency `ccrm-003` (counselor write scope) is merged (PR #305).
Numbers: migration `0182_lead_data_fields`, `DEC-SCOPE-260`, API §12FM, RBAC §2.174 (re-chained at merge: ccrm-017 took 258 / 12FK, ccrm-004 took 259 / 0181 / 12FL / 2.173).

## 1. What the spec asks for, against what exists

| Spec §3 group | Field | Today | ccrm-005 |
| --- | --- | --- | --- |
| Identity and contact | preferred contact method | — | `enquiries.contact_preference` (call / WhatsApp / email / SMS) |
| | date of enquiry | `created_at` only | `enquiries.enquiry_date` (defaults to the created date in IST, editable) |
| Study preferences | preferred country | free product ("Destination") | `lead_qualifications.preferred_country_id` (FK `countries`) |
| | study mode | `preferred_mode` online/offline (IT batches) | `lead_qualifications.study_mode` (full-time / part-time / online, the ccrm-007 list) |
| | preferred campus if known | — | `lead_qualifications.preferred_campus` (text) |
| | course, level, intake, budget | exist (tel-009) | unchanged |
| Academic profile | percentage / CGPA | percentage only | `lead_qualifications.academic_cgpa` (0–10) beside the percentage |
| | backlogs | — | `lead_qualifications.backlogs` (0–99) |
| English proficiency | test, score, date, validity, status | one free-text `english_test_status` | child table `lead_english_tests` (≤ 5 rows, the ccrm-007 shape) |
| Consent and source notes | marketing preferences | — | `enquiries.marketing_opt_in` (yes / no / not asked) + `marketing_consent_at` |
| | referral details | — | `enquiries.referral_name`, `enquiries.referral_contact` |

## 2. Decisions (builder's recommended defaults; the owner pre-authorised "proceed with recommended answers" — NEEDS_CONFIRMATION)

- **LF1 — two homes.** Contact preference, enquiry date, marketing consent and referral apply to every lead (IT too), so they are
  `enquiries` columns and are edited with the lead's details. Study, academic and English fields are overseas questions, so they join
  tel-009's **overseas** qualification group (`lead_qualifications` + `lead_english_tests`) and follow its QD2 rule (applicable fields
  replaced, the other group's values kept, a field that does not apply → 422).
- **LF2 — nothing is mandatory** at create or at any stage (the backlog's open question). The existing required fields are unchanged.
- **LF3 — English tests** reuse ccrm-007's row rules exactly (`StudentEnglishTestIn`: test type list, per-test score range, a taken test
  not dated in the future, valid-until not before the test date), at most 5. The read adds `expired` (valid-until before today, IST).
  The free-text `english_test_status` stays (old data; a summary line).
- **LF4 — enquiry date** is between 2000-01-01 and today (IST, one day of slack as `_not_future`). Default is the created date; set on
  create, CSV import and the details edit. Existing leads are back-filled from `created_at` (IST date).
- **LF5 — consent change is audited** with its own row `lead.consent_change` `{from, to}` (booleans/null only) and stamps
  `marketing_consent_at`; clearing back to "not asked" clears the stamp. Create records the stamp when a value is given (the
  `lead.create` row already exists).
- **LF6 — CSV import** gains the five `enquiries` columns (`contact_preference`, `enquiry_date` as YYYY-MM-DD, `marketing_opt_in`
  yes/no, `referral_name`, `referral_contact`). Study and English fields stay in the qualification form (one campaign's product decides
  the group; a CSV of English test rows is out of scope).
- **LF7 — counselor writes** on a lead handed to them (owner + division, ccrm-003's scope): `PATCH /counselor/leads/{id}` with the five
  `enquiries` fields only (contact details, product and priority stay the telecaller's), and `GET/PUT /counselor/leads/{id}/qualification`
  (the tel-009 service; a closed lead may still be corrected). The telecaller on a handed-over lead stays read-only (D1).
- **LF8 — conversion carries the new data** (ccrm-008 K3, "do not re-enter"): study mode, preferred country, CGPA (when there is no
  percentage), backlogs and the English tests are copied into the student profile; a value the profile refuses stays on the lead.
- **LF9 — logs and audit rows** name fields only, never values (referral names and contacts are personal data).

## 3. API (§12FM)

- `POST /telecaller/leads`, `POST /counselor/walk-in-leads` (same schema), `PATCH /telecaller/leads/{id}`: optional
  `contact_preference`, `enquiry_date`, `marketing_opt_in`, `referral_name`, `referral_contact`.
- Every lead read (`bdm_leads.admin_out`: admin, telecaller, counselor) adds those five plus `marketing_consent_at`. Additive.
- `GET/PUT /telecaller/leads/{id}/qualification` and the new counselor pair: overseas group adds `preferred_country_id`,
  `study_mode`, `preferred_campus`, `academic_cgpa`, `backlogs`, `english_tests[]`; the read adds `preferred_country {id, name}` and
  `english_tests[].expired`. An unknown country → 422.
- `PATCH /counselor/leads/{id}` → the counselor lead detail. Another counselor's lead → 404; a non-counselor → 404 (the scope is empty).
- `GET /telecaller/imports/template` gains the five columns.

## 4. Data (migration 0182)

Additive. `enquiries`: 5 nullable columns + `enquiry_date` (added nullable, back-filled, then NOT NULL with an IST server default);
CHECKs for the contact preference list, the referral lengths and `(marketing_opt_in IS NULL) = (marketing_consent_at IS NULL)`.
`lead_qualifications`: 5 nullable columns + CHECKs (study mode list, CGPA 0–10, backlogs 0–99), FK to `countries` ON DELETE SET NULL.
New `lead_english_tests` (FK `enquiries` ON DELETE CASCADE, unique (lead, position), type/status CHECKs). Downgrade drops them.

## 5. UI

- `NewLeadForm` (telecaller, manager, counselor walk-in) and the telecaller `Lead details` edit: a "Contact and consent" group —
  preferred contact method, enquiry date, marketing consent (Not asked / Yes / No), referral name, referral contact. One shared
  `LeadContactFields` component; the details view lists them.
- `LeadQualificationForm`: the overseas section adds country (the public study-destination list), study mode, preferred campus,
  CGPA, backlogs, and an English tests list using ccrm-007's `EnglishTestRow` (expired badge). It takes the API URL, so the counselor
  lead detail reuses it.
- `CounselorLeadDetail`: "Edit details" for the five fields, and the qualification section.

## 6. Tests

Backend: migration round trip; create/edit/import round trip of the five fields; consent audit; enquiry-date range; qualification
new fields + English tests round trip, expired flag, unknown country 422, IT lead 422 for overseas fields; counselor PATCH /
qualification scope (own 200, other counselor 404, telecaller 403 on handed-over); conversion copies the new data.
Frontend: vitest for the shared fields component, the qualification form's new fields, the counselor detail edit. Playwright e2e:
create a lead with the fields, edit, qualification with an expired IELTS, counselor edit.

## 7. Regression risks

Import template columns (tel-006 tests assert the header), the qualification form and its tests, `admin_out` consumers (additive keys),
the duplicate panel (unchanged), ccrm-008 conversion (new copied values), tel-024/mgmt reports (no change).
