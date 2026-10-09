# rec-022 — Offer management (design)

**Status: MERGED** as PR #206 @ `27c41baa` (2026-10-09). Built on `feature/rec-022` from `main` @ `365fdd97`.

- **Feature:** `rec-022` (`docs/delivery/RECRUITER_CRM_BACKLOG.md` §rec-022). **Dependencies:** rec-020 (PR #193) and rec-017 (PR #178), both
  merged.
- **Evidence:** `EVID-018` §16 (lines 676–702). It lists 9 offer fields (Candidate, Company, Job, Offer Date, Position, Salary, Joining
  Date, Offer Letter, Offer Status) and 4 statuses, "Offer Pending → Offer Received → Accepted → Declined". The section opens with "Once
  selected". §5's pipeline stage "Selected" (rec-005, event `candidate_selected`, reserved for rec-022) is reached by an offer.
- **Module scope:** `DEC-SCOPE-116`. R8: candidate phone and email are never shared. R10: recruiters do every write.
- **Decision:** `DEC-SCOPE-155`. OF1–OF10 are **recommended defaults**, taken on the owner's standing instruction for build sessions
  ("proceed with the recommended answers; ask only if required"). They stay `UNVERIFIED` until the owner confirms them. OF2, OF6 and OF7
  answer the backlog's Q-21.
- **Numbering (FINAL):** migration `0138_offer_management` on `0137_resume_search`, API §12BW and RBAC §2.81. Drafted as `0136` /
  DEC-SCOPE-152 / §12BT / §2.78; upc-011 (`0136`, 152), upc-018 (153) and rec-014 (`0137`, 154) merged first.

## 1. Decisions (UNVERIFIED defaults)

| # | Point | Answer |
|---|---|---|
| OF1 | Statuses | The 4 §16 values in source order: `offer_pending` (Offer Pending), `offer_received` (Offer Received), `accepted`, `declined`. A CHECK holds them. **Final** = accepted, declined |
| OF2 | Meaning (Q-21a) | Offer Pending: the company has said yes, but the offer has not reached the candidate. Offer Received: the offer (normally the letter) is with the candidate. The letter is **not** required for Offer Received: legacy rows have none, and the letter is a separate upload |
| OF3 | Moves (`POST …/status`) | offer_pending → offer_received, accepted, declined. offer_received → accepted, declined. Accepted and declined are final (rec-023 owns Joined / Did Not Join). Anything else → `409`. An optional note ≤ 500 goes on the history row |
| OF4 | Record (`POST /recruiter/applications/{id}/offer`) | **Only for a Selected application** (AC1, `409`). A second offer on an application → `409` (the existing unique index decides a race). Body: `status` (offer_pending \| offer_received, default offer_pending), `position` (required, 2–160, the UI pre-fills the requirement title), `compensation` (salary, optional, > 0 and < 10^12), `currency` (3 capital letters, default INR), `offered_on` (default today, never in the future, `422`), `joining_date` (optional, not before `offered_on`, `422`). Side effects: rec-005 `candidate_selected` on the company (forward only). The application is already Selected and stays so |
| OF5 | Revise (`PATCH /recruiter/offers/{id}`) | The backlog edge case "a revised offer (re-issue = update with history)": position, salary, currency, offer date and joining date on a non-final offer (`409` on accepted/declined). Only changed values count; a change writes a `revised` history row naming the fields (never the values: the salary is PII) |
| OF6 | Side effects of a move (Q-21b) | **Declined** → the application goes to **Withdrawn** (the candidate's choice; Rejected is the company's) via rec-017 `follow`. **Accepted** keeps the application at Selected on the recruiter routes: "selection is not the same as placement", and rec-023's joining moves it to Joined. Reaching Offer Received (on record or move) notifies a student candidate in-app (the existing "Job offer received" notice). External candidates get nothing new |
| OF7 | Letter (Q-21c) | `PUT /recruiter/offers/{id}/letter` (multipart): the recruiter uploads it. The bytes decide the type (PDF or image), the size cap applies and image metadata is stripped (`agent_documents.read_upload`, the bdm-005 MoU pattern). The key is server-made under `job-offers/`. Replacing keeps the old object (its key is on the history row, never returned). Allowed on any offer except a declined one. `GET /recruiter/offers/{id}/letter` streams it in the read scope; the audit row is committed before any byte leaves; the file name is `offer-<candidate code>.<ext>`. The legacy typed `letter_url` is kept, shown as "Letter link" when it is `http(s)` |
| OF8 | Who | Writes: rec-017's writers (`placement_team` in the requirement's scope, `super_admin`). `placement_manager` and the assigned BDM read (`403` on writes). Reads use rec-007's requirement scope; out of scope = `404`. **`it_student`** reads their own offers (`GET /workflows/it/student/offers`) and downloads their own letter. **Employers:** nothing new; EMP-006 stays NOT_STARTED and rec-022 does not supersede it (Q-21d) |
| OF9 | Legacy routes | `POST /workflows/it/offers` and `PATCH /workflows/it/offers/{id}` (placement_team, hr_team, it_admin) delegate to `services/offers`. A legacy status word is mapped: offered → offer_received, pending → offer_pending, accepted and joined → accepted, declined and rejected → declined. Any other word → `422` (it used to be stored free; the CHECK now refuses it). They keep their permissive moves (any of the 4), but every change writes a history row (AC2). **AC3:** a legacy accepted/joined still moves the application to Joined via `follow`, as before. Legacy create still follows the application to Selected and notifies the student. `letter_url` stays writable there. Responses only gain fields |
| OF10 | Data mapping | Existing rows: offered → offer_received; accepted, joined → accepted; declined, rejected, withdrawn → declined; pending → offer_pending; any other value → offer_received (it was recorded as an offer). No history is backfilled |

## 2. Data (`0138`)

- **`job_offers`** gains `position` (String 160, nullable: legacy rows), `letter_key` (String 255), `letter_content_type` (String 80),
  `letter_name` (String 255, display only), `letter_uploaded_at`, `created_by_user_id` (FK users, RESTRICT, nullable: legacy). Its
  `status` gets the OF10 mapping, the server default `offer_received` and the CHECK `ck_job_offers_status`.
- **`job_offer_events`**: append-only history (the backlog's `offer_status_history`; it also holds revisions and letters, so it is named as
  rec-020's `interview_events`). `id`, `offer_id` (FK RESTRICT), `event` (CHECK created / status / revised / letter), `from_status`,
  `to_status`, `fields` (JSON array of field names, nullable), `note` (≤ 500), `letter_key` (the replaced key, never returned),
  `actor_user_id` (FK, nullable), `position` (identity), `created_at`. Index `(offer_id, position)`.
- `downgrade()` refuses while any event exists. The steps are guarded (0001 builds a fresh database from the current models).

## 3. API (§12BW)

| Method/Path | Notes |
|---|---|
| `GET /recruiter/applications/{id}/offer` | `{offer: item \| null, can_create}` (`can_create` = a writer, the application Selected, no offer) |
| `POST /recruiter/applications/{id}/offer` | OF4. `201`, `{offer}` |
| `PATCH /recruiter/offers/{id}` | OF5. `{offer}` |
| `POST /recruiter/offers/{id}/status` | OF3 / OF6. Body `{status, note?}`. `{offer}` |
| `PUT /recruiter/offers/{id}/letter` | OF7. multipart `file`. `{offer}` |
| `GET /recruiter/offers/{id}/letter` | OF7. The file; `404` when none |
| `GET /workflows/it/student/offers` | OF8. The caller's offers, newest first |
| `GET /workflows/it/student/offers/{id}/letter` | OF8. Only the caller's own (`404` otherwise) |

Each write: resolve the offer's application through the requirement scope (`404`), lock the application, check the writer (`403`), lock
the offer and check its state (`409`), validate, change, history row, side effects, audit `recruiter_offer.{create,update,status,letter,
letter_downloaded}` (ids, keys, field names; never the salary or a note), one commit, then the log line.

**Item:** `id`, `status`, `status_label`, `position`, `compensation`, `currency`, `offered_on`, `joining_date`, `letter {name,
content_type, uploaded_at} | null`, `letter_url` (http(s) only, else null), `application {id, status, status_label}`, `candidate {id,
code, name}`, `requirement {id, code, title}`, `company {id, name}`, `history [{event, from_status, to_status, fields, note, actor,
created_at}]`, `allowed_statuses [{key, label}]` (writers only), `can_edit`, `can_upload`.

The student item has the company, requirement title, position, status label, salary, currency, dates and `has_letter` / `letter_url`; no
history and no actor names.

## 4. Web

- **Requirement page, candidate row:** an **Offer** toggle next to Interviews. It shows the offer (status, position, salary, dates,
  letter download or link, history) with Change status, Edit and Upload letter when the API allows them, or "No offer yet." with
  "+ Record offer" when `can_create`. Any change re-reads the candidates list, so the application's status follows (Declined → Withdrawn).
- **Student placement-status page:** a "My offers" card (company, position, status, salary, dates, Download letter). It replaces the
  portal's text-only "Offers" panel there (QA-04: the same offers were listed twice).
- **ADM-007 offers screen** (`/it/placement/offers`): the status column shows the label. The legacy "Create offer" form stays.
- Loading, empty, error and retry states; 422s placed on their fields; an in-flight guard on every submit (rec-020 QA-01).

## 5. Tests

- **Backend:** `test_rec_022_offers.py` — record only for Selected (AC1), the duplicate `409`, fields and their `422`s, moves and the
  final `409`, history for create / status / revise / letter (AC2), Declined → Withdrawn, Accepted keeps Selected, the company stage,
  the student notice, the letter upload (type, size, replace keeps history) and download (scope, audit), roles and scope, the student
  reads, the legacy routes' mapping and AC3. `test_rec_022_migration.py` — the CHECKs equal the model, the mapping, head, downgrade
  refusal. `test_rec_017_legacy`, `test_bdm_021_business` and `test_rpt_001_reporting` keep passing (their direct inserts use the new
  status keys).
- **vitest:** the lib helpers, the offer panel and the student card.
- **e2e:** `rec-022-offers.spec.ts` — a Selected candidate → record an offer → upload a letter → Offer Received → Accepted; history shows
  each step.

## 6. Plan (TDD, in order)

1. Model + migration: `OFFER_STATUSES`, `OFFER_CHECKS`, `JobOffer` columns, `JobOfferEvent`; `0138` with the mapping. Test first:
   `test_rec_022_migration.py`.
2. `services/offers.py`: catalogue, `from_legacy`, moves, `create`, `revise`, `change_status`, the letter, reads. Test first:
   `test_rec_022_offers.py` per behaviour.
3. `api/recruiter_offers.py` (recruiter + student routers), schemas, `main.py`. Then the legacy `workflows.py` routes delegate; the
   portal offers / placement-status sections use the labels; the two fixtures move to the new keys.
4. Web: `lib/recruiterOffers.ts`, `RecruiterApplicationOffer.tsx`, the Offer toggle, `StudentOffersCard.tsx` on placement-status;
   vitest first.
5. e2e spec, browser QA on an isolated stack (`-p rec022`, web 3122, api 8122), docs (DEC-SCOPE-155, API §12BW, RBAC §2.81, DATA_MODEL,
   backlog status).

## 7. Security review (Phase 3)

- Scope: every recruiter read and write resolves through rec-017 `load_scoped` (out of scope = `404`); writers only (`403`). Students
  read only rows where `job_applications.student_id` is theirs (`404` otherwise: no IDOR).
- The letter: the type by content, the size cap, image metadata stripped, server-made keys, `nosniff` and an attachment disposition with a
  built name. The audit row is committed before bytes leave.
- PII: the salary, notes and file names never reach logs or audit metadata. Writes are POST/PATCH/PUT only (SameSite=Lax cookies).
