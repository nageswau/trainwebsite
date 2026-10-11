# rec-027 — Company timeline (+ candidate timeline) — design

- **Feature:** `rec-027` (`docs/delivery/RECRUITER_CRM_BACKLOG.md` §rec-027; EVID-018 §19 L794 "Every communication should appear in the
  company timeline"). Evidence class: `DERIVED_BLUEPRINT` scoped by R1–R15 (`EXPLICIT_APPROVAL`, 2026-10-07). Gate: `APPROVAL_GATES.md` GATE-09.
- **Dependencies (verified on `main`):** rec-005 (#162), rec-019 (`0142_profile_shares`), rec-024 (#168), rec-025 (#172), rec-026 (#176),
  rec-028 (#174), rec-030 (#208). All merged.
- **Decisions:** TL1–TL10 below are recommended defaults, recorded as `UNVERIFIED` in the DEC-SCOPE block (the user asked for the
  recommended answer instead of a question).
- **No migration, no new table, no write path.**

## 1. Behaviour

### TL1: company timeline sources
`GET /api/v1/recruiter/companies/{id}/timeline` runs one `UNION ALL` over the tables that already record each event. Nothing is copied:

| kind | source | `at` | actor |
|---|---|---|---|
| `stage` | `company_stage_history` | `created_at` | `actor_user_id` (NULL = System) |
| `call` | `recruiter_calls` (contact calls of the company) | QA15-01 call time | `caller_user_id` |
| `message` | `recruiter_messages` (contact messages of the company) | `sent_at` | `sender_user_id` |
| `meeting` | `recruiter_meeting_events` | `created_at` | `actor_user_id` |
| `follow_up` | `recruiter_follow_ups`: up to three entries (scheduled / done / cancelled) | created / completed / cancelled | creator / completer / the cancel audit row |
| `share` | `profile_shares` | `created_at` | `shared_by_user_id` |
| `share_response` | `profile_share_items.responded_at` (the current response) | `responded_at` | `responded_by_user_id` |
| `requirement` | `job_status_history` of the company's requirements | `created_at` | `changed_by_user_id` |
| `contract` | `recruiter_contract_events` | `created_at` | `actor_user_id` |

Out of scope: assignment changes (they are not communication, and the company page already lists them), revenue (rec-031 hides it from the
BDM), and interviews and offers (they sit on the candidate timeline).

### TL2: candidate timeline sources
`GET /api/v1/recruiter/candidates/{id}/timeline` covers `call`, `message` (the candidate's own), `application` (from
`job_application_status_history`), `interview` (`interview_events`), `offer` (`job_offer_events`), `share` (one entry per
`profile_share_items` row: the candidate was shared with a company) and `share_response`. Each candidate entry names its requirement in
`subject` and its company in `context`.

### TL3: readers and scope
- **Company timeline:** `recruiter_companies.load_scoped`. That covers the assigned recruiter, the manager (their team plus the
  unassigned queue), super_admin and the assigned BDM. Out of scope or missing is 404. Any other role gets 403.
- **Candidate timeline:** `candidates.require_reader` (recruiter, manager, super_admin, hr_team), then `candidates.load` (the pool
  filter, so a student who has not opted in is 404). This is the same rule as `/candidates/{id}/calls` and `/applications`: every candidate
  reader sees every row (R11).

### TL4: masking ("must not leak masked fields to a BDM")
The rows are built from explicit columns only:
- Candidates appear by name and code, never by mobile or email.
- Document and letter keys, share tokens, contract fee values and contract field lists are never selected.
- Free text (call notes, message body, reasons, feedback) is a 200-character excerpt (tel-015 TM2).

### TL5: order
Newest first, so the order is total and pages never repeat or skip a row: `at DESC, rank DESC, seq DESC, id DESC`.
- Rows written in one transaction share `at`. The rank then shows the effect above its cause. Activity is rank 1. A follow-up created by a
  call or meeting outcome, and an application move caused by a share, interview or offer, are rank 2. A stage move is rank 3.
- `seq` is the source's `position` where one exists.

### TL6: deleted calls
Calls are hard-deleted (rec-025, CA4), so a deleted call simply drops out of the union.

### TL7: paging
`limit` (1–100, default 50) and `offset` follow the house `LIMIT`/`OFFSET`. Each page takes two queries (count + page), whatever the data.

### TL8: labels
- **Server:** stage, requirement status, application status, interview status, offer status, contract status and call outcome.
- **Web client:** meeting type, follow-up reason, message channel and template, share channel and share response. Each label comes from
  the section that already owns it.

### TL9: audit and logging
Read only. Nothing is audited or logged (upc-013 TL8).

### TL10: UI
- A **Timeline** section on the company page and on the candidate page, built on the shared `LeadTimeline` list. It brings loading,
  empty, failure + Retry and "Show older entries".
- On the company page, every write callback (call, follow-up, meeting, message, contract, pipeline) bumps a `version`, which re-reads the
  first page.

## 2. Response
`RecTimelinePage {items, total, limit, offset}`. Each item has: `id`, `kind`, `at`, `actor {id, full_name} | null`, `event`, `from_value`,
`from_label`, `to_value`, `to_label`, `subject`, `status`, `reason`, `context`, `duration_seconds` and `scheduled_for`. This is the upc-013
row plus `context`.

## 3. Files
- **API:**
  - `app/services/recruiter_timeline.py` (new; reuses `lead_timeline._branch` / `_excerpt`)
  - `app/api/recruiter_timeline.py` (new router)
  - `app/main.py` (register the router)
  - `app/schemas.py` (`RecTimelineRow`, `RecTimelinePage`)
- **Web:**
  - `lib/recruiterTimeline.ts` (row type, URLs, `entry` / `actor` mappers)
  - `components/RecruiterTimeline.tsx` (a `LeadTimeline` wrapper section)
  - `RecruiterCompanyDetail.tsx` and `RecruiterCandidateDetail.tsx` (mount the section)
- **Tests:**
  - `tests/test_rec_027_timeline.py`
  - `tests/lib/recruiterTimeline.test.ts`
  - `tests/components/RecruiterTimeline.test.tsx`
  - `e2e/rec-027-timeline.spec.ts`
- **Docs:** DEC-SCOPE, API_CONTRACT §, RBAC_MATRIX §, and the backlog status line. These take the next free numbers, which are checked
  against `main` right before the push.

## 4. Plan (TDD, one slice at a time)
1. **API RED:** a call and then an email appear in order with time, actor and summary (AC1). Every company kind appears. The tie order is
   stable (AC2). Out of scope is 404, and the wrong role is 403. The BDM reads, with no candidate contact and no document key. A deleted
   call is excluded. Paging is total. The query count is fixed. Then the candidate timeline: every kind, its readers, and pool-hidden is 404.
2. **API GREEN:** the service, schema, router and registration.
3. **Web RED, then GREEN:** the mapper unit tests (each kind's title and badge), then the component tests (renders, empty, failure +
   Retry), then mount the section on both pages.
4. **E2E:** a recruiter logs a call and sends a WhatsApp, and the company timeline shows both newest first. The candidate timeline shows
   the call.
5. **Docs.**

## 5. Risks
- `main.py` and the shared docs conflict with parallel sessions. Resolve them main-first.
- Existing detail-page unit tests that stub `fetch` may need to tolerate the new timeline request.
