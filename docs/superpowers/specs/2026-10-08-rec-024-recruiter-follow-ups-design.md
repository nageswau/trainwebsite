# rec-024 — Recruiter follow-ups + automatic daily list (design)

- **Feature:** `rec-024` (`docs/delivery/RECRUITER_CRM_BACKLOG.md` §rec-024). **Dependencies:** rec-003 and rec-004, both merged.
- **Evidence:** `EVID-018` §18 (lines 732–756): the 9 reasons and "CRM should automatically generate the daily follow-up list". §2 line 118
  and §4 line 214: "Next Follow-up" on the company and on the contact. Module scope: `DEC-SCOPE-116` (R1, R10, R13).
- **Decision:** `DEC-SCOPE-127`. FU1–FU10 below are **recommended defaults**, taken on the owner's standing instruction for build
  sessions ("proceed with the recommended answers; ask only if blocking"). They stay `UNVERIFIED` until the owner confirms them.
- **Numbering:** migration `0112_recruiter_follow_ups`, API §12AU and RBAC §2.53. Main @ `f5f6822d` ends at `0111_university_pipeline`
  (upc-007), `DEC-SCOPE-126`, §12AT and §2.52. Re-check main at merge, because rec-005 and rec-007 are pending.

## 1. Decisions (UNVERIFIED defaults)

| # | Point | Answer |
|---|---|---|
| FU1 | Q-23 automatic follow-ups | The daily list itself is computed on every read, so no batch job runs. The trigger events (JD pending, profile, interview feedback, offer, joining, contract) belong to records that don't exist yet: rec-008, 019, 021, 022, 023 and 030. Each of those items creates its follow-up through `services.recruiter_follow_ups.create` when it lands. rec-024 fires no automatic follow-up |
| FU2 | The lists (IST) | **Today** = open and due before the end of today in IST, which is due today plus overdue (AC1). **Overdue** = open and due before now. **Upcoming** = open and due from tomorrow in IST onwards. Each list is oldest due first and carries all three counts |
| FU3 | Who writes | The company's `can_edit` holder: the assigned recruiter or `super_admin` (rec-003 D6, rec-004 C1, R10). `placement_manager` and the assigned BDM read only (`403` on writes). An archived company's follow-ups are read-only (`409` "Restore this company first") |
| FU4 | Scope / reassignment | A follow-up belongs to its company and has no assignee column, so a company reassignment moves its follow-ups with it (backlog edge case; rec-037 does bulk moves). Out of scope = `404`, the same as a missing follow-up |
| FU5 | Due time | Date and time with an offset (the web sends IST). It must be in the future and within 366 days; otherwise `422` on `due_at`, using tel-011's `check_due`. Reschedule is `PATCH {due_at}`. Only a changed due time is checked, so an overdue follow-up's notes can still be edited |
| FU6 | Links | Optional `contact_id`: a contact of the same company, active when it is set or changed. Optional `job_id` (a requirement of the company) and `application_id` (an application to one of the company's jobs). When both are sent, the application must be for that job. A wrong link → `422`. The web form offers the contact. Requirement and application links are API-only until rec-007 and rec-017 add their pages |
| FU7 | Complete / cancel | Complete takes an optional `outcome` (≤ 500 characters). Cancel needs a `reason` (≤ 500). Neither works on a follow-up that isn't open (`409`) |
| FU8 | Cap | At most 50 open follow-ups per company (`409`), an abuse bound counted under the company lock |
| FU9 | Next follow-up | Derived, not stored. `next_follow_up_at` on the company (list row and detail) = the earliest open follow-up. On a contact = the earliest open follow-up linked to that contact. AC2 holds by construction |
| FU10 | Reasons | The 9 §18 values in source order. `new_requirement`, `jd`, `profile_feedback`, `interview_feedback`, `offer_status`, `joining_confirmation`, `new_openings`, `contract_mou`, `payment_commercial`. Notes ≤ 2000 |

## 2. Data

`recruiter_follow_ups` (`0112`) has these columns:
- `id`, `company_id` (FK, RESTRICT)
- `contact_id`, `job_id`, `application_id` (nullable FKs)
- `reason` (CHECK on the 9), `due_at` timestamptz, `notes` text
- `status` open/done/cancelled (CHECK)
- `outcome`, `completed_at`, `completed_by_user_id`, `cancelled_at`, `cancel_reason`
- `created_by_user_id`, `created_at`, `updated_at`

A state CHECK ties `done` to completed_at/by and `cancelled` to cancelled_at/reason (tel-011's).

Indexes:
- `(company_id, status, due_at)`
- a partial `(due_at) WHERE status = 'open'`
- `(contact_id)`

The migration is guarded for the 0001 fresh-build idiom. `downgrade()` refuses while rows exist.

## 3. API (§12AU)

Every route uses rec-003 `caller_scope` / `load_scoped`. Writes lock the company and then the follow-up, audit
`recruiter_follow_up.{create,update,complete,cancel}` (ids, the reason key and field names only), commit once, and log.

| Method/Path | Notes |
|---|---|
| `GET /recruiter/follow-ups?due=today\|overdue\|upcoming&limit&offset` | FU2. `{items, total, limit, offset, day, counts {today, overdue, upcoming}}`. The caller's scope: a recruiter's own companies, a manager's team plus unassigned, super_admin all, a BDM their linked companies. Other roles `403` |
| `GET /recruiter/companies/{id}/follow-ups` | Open by due time, then done/cancelled newest first; paged |
| `POST /recruiter/companies/{id}/follow-ups` | `{due_at, reason, contact_id?, job_id?, application_id?, notes?}` → `201` item |
| `PATCH /recruiter/follow-ups/{id}` | Partial: due_at (reschedule), reason, contact_id, job_id, application_id, notes. Null clears the optional fields; null on due_at or reason → `422` |
| `POST /recruiter/follow-ups/{id}/complete` | `{outcome?}` |
| `POST /recruiter/follow-ups/{id}/cancel` | `{reason}` |

**Item:**
- `id`, `company {id, code, name, assigned_recruiter}`, `contact {id, name}|null`, `requirement {id, title}|null`, `application_id`
- `reason`, `due_at`, `notes`, `status`, `overdue`, `outcome`
- `created_by`, `created_at`, `completed_at`, `completed_by`, `cancelled_at`, `cancel_reason`, `can_change`

**Additive:**
- The company row and detail gain `next_follow_up_at`.
- Each contact item gains `next_follow_up_at`.

## 4. Web

- `/recruiter/follow-ups`: Today / Overdue / Upcoming tabs with counts. The tab and page live in the URL. Each card links to its company.
  It is in the recruiter and manager navs.
- Company page: a **Follow-ups** section. Add (due IST, reason, contact, notes); each item has Done (optional outcome), Reschedule/edit
  and Cancel (reason). Actions follow `can_change`.
- The company Details list shows "Next follow-up". Each contact shows its next follow-up.
- Loading, empty, error and retry states; field-placed 422s; the session-ended link (the tel-011 component idioms).

## 5. Tests

- **Backend:** `test_rec_024_follow_ups.py` (scope, roles, the three lists, due rules, links, cap, complete/cancel state, next follow-up,
  reassignment, audit) and `test_rec_024_migration.py` (CHECKs equal the model, head).
- **vitest:** the lib helpers and the panel/section components.
- **e2e:** `rec-024-follow-ups.spec.ts` (add on the company, see it in Upcoming, complete, next follow-up moves).
