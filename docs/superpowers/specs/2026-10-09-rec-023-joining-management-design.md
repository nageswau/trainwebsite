# rec-023 — Joining management + placement closure: design

- **Item:** `docs/delivery/RECRUITER_CRM_BACKLOG.md` rec-023 (depends on rec-022, MERGED PR #206).
- **Evidence:** `EVID-018` §17 (lines 704–730): it tracks Expected Joining Date, Actual Joining Date, Joining Location, Reporting Manager, Joining
  Confirmation, Proof/Confirmation and Joining Status. The final statuses are Joined and Did Not Join, because "selection is not the same as placement".
- **Decision:** `DEC-SCOPE-158` (JN1–JN10). These are the recommended answers to Q-22. The owner **confirmed them as built** on 2026-10-09 (EXPLICIT_APPROVAL), after building with the recommended
  answers. Migration `0140_joining_management`, API §12BZ, RBAC §2.84.

## 1. Decisions (JN1–JN10)

| ID | Topic | Decision |
|---|---|---|
| JN1 | Where joining lives | Columns on `job_offers`. There is one offer per application, so there is one joining per offer, and it needs no new table. The existing `job_offers.joining_date` **is** the Expected Joining Date, so it is not duplicated |
| JN2 | When joining starts | When the offer reaches **Accepted**. On the recruiter route, `joining_status` = `pending`. Before Accepted, `joining_status` is NULL and there is no joining panel |
| JN3 | Statuses | `pending` → `joined` \| `did_not_join`. Joined and Did Not Join are final (`409`). Replacement after a later exit is out of scope (Q-22c; the contract field covers it, rec-030) |
| JN4 | Joined needs (AC1, Q-22b) | The actual joining date, **and** proof — a proof file **or** a confirmation name ("Proof/Confirmation", L718). Neither → `422` on `confirmed_by` |
| JN5 | Did Not Join needs (AC2, Q-22a) | A reason, 2–500 characters (`422`). There is also a DB CHECK |
| JN6 | Dates | The actual date is never before the offer date and never in the future (`422`). The expected date is not before the offer date (the existing rec-022 rule). The confirmation date is never in the future |
| JN7 | Side effects of Joined | (1) The application goes Selected → **Joined** through rec-017 `change_status`; `409` if the application is no longer Selected. (2) rec-005 `candidate_joined` on the company (forward only). (3) **Vacancies:** with the job row locked, when the requirement has `vacancies` and the joined count reaches it, the requirement goes to **Closed** (note "All vacancies filled") through rec-007 `change_status`. That fires `requirement_closed` on the company when it was the last live requirement. With no `vacancies`, the recruiter closes the requirement by hand, as today |
| JN8 | Side effect of Did Not Join | The application goes Selected → **Withdrawn** ("Did not join") through rec-017 `follow` (it only moves when allowed) |
| JN9 | Bypass guard | rec-017's `POST /applications/{id}/status` to `joined` is refused (`409`, "Record the joining on the candidate's offer") when the application has an offer. Without an offer, the rec-017 behaviour is unchanged. The legacy `/workflows` offer route keeps AC3 of rec-022: accepted/joined → application Joined, and the joining is marked `joined` (legacy, without an actual date) |
| JN10 | Roles | The writers are rec-017's (`placement_team` within the requirement's scope, and `super_admin`). The manager, BDM and hr_team read within scope (rec-007 `caller_scope`). Out of scope → the same `404`. The student and employer see nothing new |

## 2. Data (migration 0140)

`job_offers` gains these columns, all nullable:
- `joining_status` String(16): CHECK `IN ('pending','joined','did_not_join')`.
- `actual_joining_date` Date.
- `joining_location` String(160).
- `reporting_manager` String(160).
- `joining_confirmed_by` String(160).
- `joining_confirmed_on` Date.
- `not_joined_reason` String(500): CHECK `joining_status IS DISTINCT FROM 'did_not_join' OR not_joined_reason IS NOT NULL`.
- `proof_key` / `proof_content_type` / `proof_name` / `proof_uploaded_at`.

`job_offer_events.event` CHECK gains `joining`, `joined`, `did_not_join` and `proof`. For a replaced proof, the event's `letter_key` column keeps the replaced
object's key; it is never returned.

**Backfill:** accepted offers whose application is Joined → `joined`; other accepted offers → `pending`. Downgrade refuses while any joining data or new event exists.

## 3. API (§12BZ)

- `PUT /recruiter/offers/{id}/joining` sets the joining details, and optionally the status. The body is `joining_status` (`pending`, `joined` or `did_not_join`;
  default: keep the current status), `expected_joining_date`, `actual_joining_date`, `joining_location`, `reporting_manager`, `confirmed_by`, `confirmed_on` and `reason`.
  The fields are replaced as a whole (PUT).
  - `409` when the offer is not Accepted ("Joining is recorded once the offer is Accepted") or the joining is final.
  - `422` on a field.
  - It writes a `joining` event naming the changed fields, then a `joined` / `did_not_join` event (note = the reason).
  - When nothing changed, it writes no event and no audit row.
  - Returns `{offer}`.
- `PUT /recruiter/offers/{id}/joining/proof` uploads the proof: multipart PDF/JPG/PNG through `read_upload`. Keys are `job-joinings/<uuid>`. `409` when the joining is Did Not Join or absent.
- `GET /recruiter/offers/{id}/joining/proof` downloads it for readers within scope. The download is audited, and the file name is `joining-proof-<candidate code>.<ext>`.
- `GET /recruiter/joinings?view=due|joined|did_not_join&limit&offset` lists joinings within the caller's scope, with the three counts.
  - `due` lists pending joinings, expected date ascending with nulls last; each item carries an `overdue` flag (expected date before today, IST).
  - `joined` and `did_not_join` list the most recent first.
- The offer item (`GET …/offer` and every `{offer}` reply) gains `joining`. It is `null` before Accepted; otherwise it holds:
  - the status and its label, the dates, the location, the manager, the confirmation and the reason;
  - `proof {name, content_type, uploaded_at}`, `overdue`, `can_edit` and `can_upload_proof`.

## 4. Web

- **Offer panel (`RecruiterApplicationOffer`):** an Accepted offer shows a **Joining** section with the §17 facts, an "Update joining" form and a proof upload/download.
  - The form has a Status select (Pending, Joined, Did Not Join), the dates, location, manager, confirmation, and a reason that appears only for Did Not Join.
  - The history shows the new events.
- **New page `/recruiter/joinings` ("Joinings"):** it has the Due / Joined / Did not join tabs with counts. Each row shows the candidate, requirement, company,
  expected and actual date, and an Overdue badge, and links to the requirement.
  - The tab and page are kept in the URL.
  - It has loading, error with retry, and empty states.
  - The nav entry appears for the recruiter and the manager.

## 5. Security

- Scope and IDOR checks go through `load_scoped` (404) and `require_writer` (403). Locks are taken in order: application, offer, job, company.
- The proof is PII: it is stored under a server-generated key, its type is judged by content, it is size-capped and its metadata is stripped (`read_upload`).
  The download is audited, the file name is built rather than taken from the upload, and `HEADERS` (nosniff) is set.
- Logs and audit rows carry ids, statuses and field names — never a name, the reason text or a file name.

## 6. Out of scope / follow-ups

- Revenue (rec-031) must count only `joining_status = 'joined'` (AC3). The source field is ready; rec-031 is not built yet.
- Replacement tracking (Q-22c).
- A student or employer view of the joining.
