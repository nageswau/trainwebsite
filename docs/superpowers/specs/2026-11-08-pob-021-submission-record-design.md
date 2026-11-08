# pob-021 — Submission record (client or vendor) with skills match, consent and SLA

- **Decision:** `DEC-SCOPE-430` (B1–B14 are the builder's calls, `NEEDS_CONFIRMATION`; the owner asked for recommended answers instead of questions).
- **Source:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` pob-021 (§11.1, §11.2, §9 duplicate flag, §16 two triggers, §17 share gate, §18 AC 9).
- **Dependencies (built):** pob-018 (`DEC-SCOPE-428`), hrc-018 (`DEC-SCOPE-392`), pob-023 (`DEC-SCOPE-408`), pob-011 (`DEC-SCOPE-427`).
- **Migration:** `0311_submissions`. **API:** §12LW. **RBAC:** §2.321.

## Approach

Extend rec-019's `ProfileShareItem` in place. Every shared candidate is one **submission**. There is no new table and no new route family:
the share POST, the item PATCH and the employer portal keep their paths and grow fields. Alternatives were rejected: a separate
`submissions` table would duplicate the share and item rows; a stored `draft` row would need lifecycle cleanup for no AC.

## Calls

| ID | Call |
|---|---|
| B1 | Each item gets `submission_code` `SUB-NNNNNN` from a sequence (server default). Existing items are backfilled in creation order and given the status `submitted`. |
| B2 | `draft` is the wizard's unsaved state and is never stored. A stored submission starts at `submitted`. |
| B3 | **Consent (AC1):** every new submission needs `consent_confirmed` and a `consent_reference` (≤ 300; how and when the candidate agreed), else 409. It is stored per item. This replaces pob-011's stub; a vendor's `full` detail is still recorded on the share. |
| B4 | **Interest/availability:** `interest_confirmed` is required, else 409 (after the consent check). |
| B5 | **Required profile fields:** a current location (an email or mobile is already a database rule), else 422 naming each candidate. |
| B6 | **Eligibility:** the requirement's switched-on hrc-018 hard filters (`matching.hard_filter_gaps`), else 422 naming candidates and filters. |
| B7 | **Duplicates (AC2):** the repeat 409 now covers the same end client across every requirement and route (direct or vendor), not only vendor routes. `repeat: true` resends. |
| B8 | **Summary mode:** a client gets `named` (default) or `anonymised`; a vendor gets `anonymised` (default) or `full` (pob-011). Anonymised drops the name, the current company and the resume (no link, no portal download, `resume_id` NULL). There is no redacted resume rendition until Q-16. |
| B9 | **Compensation:** the salary line ("Expected salary: INR 900000 per year") is sent only when `include_compensation` is ticked; without the `candidates.compensation` grant, ticking it is 403. Recorded as `profile_shares.compensation_included`. |
| B10 | **SLA (AC4):** on submit, one `RecruiterFollowUp` per share (reason `profile_feedback`, the recipient company, the contact, the requirement) is due `now + companies.submission_sla_hours` (1–720; NULL = 48 h; set on the recipient company's edit form). Its id is stored in `profile_shares.follow_up_id`. |
| B11 | **Status (AC5):** `submitted → client_reviewing → shortlisted → interview → rejected / on_hold / selected / withdrawn`. Any open status can move to any other status. `rejected`, `selected` and `withdrawn` are closed (409). `rejected` needs a `rejection_reason` from a 10-entry catalogue (422); leaving `rejected` clears it. Each change is audited as `submission.status` with `{from, to}` and stamps `status_changed_at`. |
| B12 | **Acknowledgement:** `acknowledged: true` stamps `acknowledged_at` once and moves `submitted` to `client_reviewing` (logged). `next_action` (≤ 300) and `next_action_on` sit on the item. |
| B13 | **Client response mapping:** a response from the employer portal or recorded by the recruiter moves an open submission: interested → shortlisted, interview requested → interview, not interested → rejected (`client_not_interested`). A pending response leaves the status as it is. An explicit `status` in the same PATCH wins. |
| B14 | **Match block (AC3):** stored on the item as sent: `{score, required_matched, required_missing, preferred_matched, preferred_missing, explanation[]}`. It comes from hrc-018 `evaluate` with the candidate audience (no salary line) and without the skill gate, so gaps can be shown. The email and WhatsApp text carry "Skills match: X of Y required · gaps: …". The employer portal and the recruiter list show it. |

## Error order (POST /recruiter/shares)

scope 404 → writer 403 → ended 409 → vendor gate (pob-011) → **consent 409 → interest 409 → compensation grant 403** → contact/channel →
pool/permission 422 (pob-018) → **required fields 422 → eligibility 422** → closed applications 422 → duplicate 409 → message cap.

## Security

- Consent text is never written to audit rows or logs; audits carry ids, status and channel only.
- Anonymised mode removes identifiers server-side, including the resume.
- Compensation is gated server-side.
- The item PATCH keeps the requirement's scope (404) and writer (403).
- The employer portal keeps company scoping (another company's item is 404).

## Not built

- The redacted resume rendition (Q-16).
- "Relevant projects" in the match block: there is no candidate projects record (`NEEDS_CONFIRMATION`).
- Email through pob-023 templates: the existing allowlist text is extended instead.
- Client acknowledgement through a public link: the recruiter records it.
