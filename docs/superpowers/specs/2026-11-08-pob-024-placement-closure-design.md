# pob-024 — Placement closure record and invoice trigger (design + plan)

Source: `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` §pob-024 (DERIVED_BLUEPRINT). Dependencies pob-001 (`DEC-SCOPE-403`),
pob-002 (`DEC-SCOPE-407`) and itc-002 (`DEC-SCOPE-348`) are built. The owner asked for the recommended answers without a question round,
so every call below is the builder's (`NEEDS_CONFIRMATION`); Q-17 is answered "yes, a draft only — a human issues it", as the item says.

## Intent
Today an accepted offer and a joining leave no single closure record, the joining confirmation is one free-text field, and invoices are
typed by hand with no reminder. pob-024 adds one **placement** per accepted offer, separate candidate and client confirmations, an
**invoice draft** created on joining that a person reviews and issues, and a due/overdue notice.

## Goals (AC)
1. Accepting an offer creates exactly one placement.
2. Joining creates exactly one invoice draft.
3. Issuing the draft creates an ordinary rec-031 invoice, so it feeds the receivables, revenue figures and ledger as they are.
4. A due-date notice is sent once (and an overdue notice once).
Edge: a Did Not Join with a draft discards the draft.

## Non-goals
No invoice PDF/GST/sync (R9 still holds); no accountant access to recruiter screens; no replacement guarantee (pob-025) or survey (pob-026).

## Builder's calls (P1–P14)
- **P1** A placement is created when an offer moves to Accepted (new and legacy routes), one per offer (unique `offer_id`); it is also
  created on Joined if missing (offers accepted before this item). Idempotent.
- **P2** Snapshot at creation: application, requirement, candidate, client (the requirement's company), vendor (`jobs.via_vendor_id`),
  role (`offer.position`, else the requirement title), recruiter owner (`jobs.assigned_recruiter_user_id`) and PO owner (the company's
  `assigned_recruiter_user_id`, the BD owner). Source is read live (`submitted_source_id`, else the candidate's source).
- **P3** Package = the offer's compensation + currency, shown only with `candidates.compensation.view` (hrc-001).
- **P4** Expected fee, the draft and the invoice actions need the rec-031 revenue gate: role `placement_team`/`placement_manager`/`super_admin`
  and `commercials.client.view` (pob-001). Without it the commercial block is `null`.
- **P5** Candidate and client confirmations, each `{by, on, via}`; `via` ∈ call, email, whatsapp, in_person, other; `on` ≤ today (IST);
  writers (`applications.WRITERS`) edit them; a Did Not Join placement is read-only.
- **P6** The PO owner is changed by a Team Lead (`placement_manager`) or super_admin only, to an active `placement_team` user.
- **P7** The placement's status is the offer's joining status (pending / joined / did_not_join), read, never stored twice.
- **P8** On Joined: the expected fee is re-priced from the current terms (rec-031 `_fee`/`_hire_fee`, pob-002 per-requirement override) and
  a draft is made — amount = expected fee (null when unpriced: entered on issue); due date = actual joining date, plus `payment_days` when
  the requirement's trigger is `days_after_joining`.
- **P9** `invoice_status`: none → draft → issued | discarded; the draft is set only from `none` under the placement row lock (exactly one).
- **P10** Issue = the rec-031 invoice create rules (number unique ignoring case, dates) on the placement's requirement; the placement keeps
  `invoice_id`; the notice markers re-arm for the invoice's own due date.
- **P11** Discard = a reason (2–500 chars); Did Not Join discards an open draft automatically.
- **P12** Daily beat sweep (08:45 IST), bounded `FOR UPDATE SKIP LOCKED` batches: a draft, or an issued invoice still owed, whose due date is
  today or past gets `it.recruitment.invoice_due` once; past due and still owed gets `it.recruitment.invoice_overdue` once.
- **P13** "Finance and the owner": recipients are the recruiter owner, the PO owner and their Team Leads (reporting managers; every active
  `placement_manager` when none). The accountant role has no recruiter access today, so it is not notified (NEEDS_CONFIRMATION).
  Fixed preview-safe text (itc-002): never an amount, a name or a date.
- **P14** Read scope = the requirement's (rec-007 `caller_scope`): recruiter, manager, assigned BDM (read only), super_admin; out of scope
  = 404. Every write is audited with ids/amounts only.

## API (`/api/v1/recruiter`)
- `GET /placements?view=pending|joined|did_not_join|invoice_drafts&limit&offset` — page + counts.
- `GET /placements/{id}`
- `PATCH /placements/{id}` — `candidate_confirmation`, `client_confirmation`, `po_owner_user_id` (each optional).
- `POST /placements/{id}/invoice-draft/issue` — `{invoice_number, invoice_date, due_date, amount, note}` → 201 with the placement.
- `POST /placements/{id}/invoice-draft/cancel` — `{reason}`.
- The offer read (`GET /recruiter/applications/{id}/offer`, `/offers/...`) gains `placement_id`.

## DB — migration `0312_placements` (guarded)
`placements`: id, offer_id (unique FK), application_id, job_id, candidate_id, company_id, vendor_company_id, role, recruiter_user_id,
po_owner_user_id, expected_fee, candidate_confirmed_by/on/via, client_confirmed_by/on/via, invoice_status (CHECK), draft_amount,
draft_due_date, draft_created_at, draft_discard_reason, invoice_id (FK recruiter_invoices), due_notified_at, overdue_notified_at,
created_by_user_id, timestamps. Index on (invoice_status) for the sweep and on job_id.

## Web
`/recruiter/placements` (tabs by view, reusing the joinings panel style), `/recruiter/placements/[id]` (summary, two confirmation forms,
PO owner for Team Leads, the invoice draft review with Issue and Discard), a "Placements" nav entry, and an "Open placement" link on
the offer's joining section.

## Plan (TDD, focused tests)
1. Model + migration + migration test (`test_pob_024_migration.py`).
2. Service `placements.py`: ensure on accept (hook in `offers._apply_status` / `legacy_status`), draft on joining, discard on Did Not Join
   (hook in `joinings._side_effects`); tests for AC1/AC2/edge.
3. Extract rec-031's invoice insert into `recruiter_revenue.add_invoice` (route behaviour unchanged); issue/cancel endpoints; AC3 test
   (receivables count + outstanding include it).
4. PATCH confirmations / PO owner; RBAC tests (bdm read-only, commercials hidden, out-of-scope 404, writer 403).
5. Sweep + events + beat; AC4 test (run twice → one notice each).
6. rec-038 route matrix rows; nav test; vitest for the panel; e2e spec.
7. Docs: DEC-SCOPE-432, API §12LY, RBAC §2.323, DATA_MODEL, RTM, backlog status.

Regression risks: rec-022/023/031 tests, ledger, nav test, rec-038 route matrix, single-head migration tests.
