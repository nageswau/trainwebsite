# itc-010 — IT counseling record (design + plan)

**Status:** built under `DEC-SCOPE-343` (migration `0227_lead_counseling_records`, API §12IO, RBAC §2.244).
**Source:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` §itc-010 (PDF §4 "Counseling", §3 step 5). Classification `UNVERIFIED` source;
Q-01 answered by the owner (all phases in waves). The owner's standing instruction is "proceed with recommended answers", so every open
choice below is a **builder call, `NEEDS_CONFIRMATION`**.

## Intent
An IT counselor records each counseling conversation with a lead in a structured way (recommended course, objections, fee quoted,
joining date, decision-maker, outcome, next follow-up, notes) instead of free-text notes. itc-011 (conversion) and itc-030 (counselor
dashboard) read it later. Telecallers and their managers can read it on the lead they handed over.

## Decisions (builder calls)
| # | Decision | Why |
|---|---|---|
| C1 | **Q-08: one record per counseling session** (append), each editable later (PATCH). | The backlog says "records one or more counseling sessions"; history is kept; edit covers the "one record edited over time" use. |
| C2 | The PDF's 9 counseling fields map to: career goal + current skills = the **existing qualification card** (`career_objective`, `it_skill_level`, not duplicated); the record holds recommended course, objections (list + free text), fee quoted, expected joining date, decision-maker, outcome, next follow-up date, notes. | Reuse; one source per value. |
| C3 | `outcome` is required; every other field is optional. | A session with no outcome says nothing. |
| C4 | `next_follow_up` is a date stored on the record. It does **not** create a `LeadFollowUp`. | The follow-ups panel is on the same page; auto-creation is itc-030/itc-009 territory. |
| C5 | Outcome `enrolled` never moves the stage or converts the lead. | Conversion is itc-011. |
| C6 | Objections list = `lead_counseling_objections`, the lost-reason catalogue pattern: managed by `telecaller_manager`/`super_admin`, read by the catalogue readers; seeded with 6 defaults when empty. | Same owners as the other lead catalogues (lost reasons). |
| C7 | Writes (POST/PATCH): the lead's current owner counselor, who must be an **IT** counselor (403 otherwise); out of scope is 404; a closed lead is 409. Any record on the lead can be edited by its current owner (an admin owner change keeps the history editable); `author` stays, `updated_by` records the editor. | Backlog AuthZ: "owner counselor (404 out of scope)". |
| C8 | Reads: counselor (same scope) and `GET /telecaller/leads/{id}/counseling` for the telecaller / manager / super_admin scope of tel-004. A returned lead keeps its records, read-only for the telecaller. | Backlog edge case E. |
| C9 | Validation: product must be an active `TelProduct` with `product_group='it'` when set or changed (else 422); objections must exist and be active when newly added; fee `0 ≤ fee ≤ 99,99,999.99`; joining and next-follow-up dates today (IST) or later when set or changed; notes ≤ 4000, objection notes ≤ 1000. | AC2, AC3, "−" case. |
| C10 | Timeline: one `counseling` entry per save, from the audit rows `lead_counseling.create` / `lead_counseling.update` (ids, outcome and field names only; itc-001 `audit_change` for the update diff, notes as "changed"). | AC4; nothing copied (tel-015 D2). |
| C11 | Never shown to students; nothing logged except ids and field names. | Backlog Security. |

## Data
- `lead_counseling_objections(id, name ≤120 unique lower, active, sort_order, created_at, updated_at)`.
- `lead_counseling_records(id, lead_id → enquiries RESTRICT, author_user_id, updated_by_user_id, recommended_product_id → tel_products
  NULL, objection_notes, fee_quoted NUMERIC(12,2) NULL ≥0, expected_joining_date, decision_maker, outcome, next_follow_up, notes,
  created_at, updated_at)`, CHECKs on fee, decision_maker (`self, parent, spouse, employer, other`), outcome (`interested, needs_time,
  not_interested, enrolled`), lengths; index `(lead_id, created_at)`.
- `lead_counseling_record_objections(record_id → records CASCADE, objection_id → objections RESTRICT)`, PK both.
- Migration 0227 creates when missing (0001 builds from models), seeds objections when empty, downgrade refuses while records exist.

## API (§12IO)
- `GET /counselor/leads/{id}/counseling?limit&offset` → `{items, total, limit, offset}` newest first.
- `POST /counselor/leads/{id}/counseling` → 201 record. `PATCH /counselor/leads/{id}/counseling/{record_id}` → 200 record (fields sent
  replace; `objection_ids` replaces the set).
- `GET /telecaller/leads/{id}/counseling` → same page, read-only.
- `GET/POST /telecaller/counseling-objections`, `PATCH /telecaller/counseling-objections/{id}` (lost-reason semantics).
- Record out: `id, recommended_product{id,name}|null, objections[{id,name}], objection_notes, fee_quoted (string), expected_joining_date,
  decision_maker, outcome, next_follow_up, notes, author{id,full_name}, updated_by, created_at, updated_at`.

## Frontend
- `components/LeadCounseling.tsx`: section "Counseling" — list of sessions, "Record counseling" form, per-record Edit; loading / empty /
  error states; `readOnly` hides the controls. Shown on `CounselorLeadDetail` for IT leads (writable while the lead is open) and
  read-only on the telecaller/manager `LeadDetailPanel` for IT leads.
- Manager page `/telecaller/manager/counseling-objections` reusing `LostReasonsPanel` (parametrised by URL and nouns) + nav entry.
- Timeline label `counseling` in `lib/leadTimeline.ts`.

## Plan (TDD, one slice at a time)
1. Model + migration + migration test (RED: table missing / model mismatch).
2. Service + counselor routes: create/list/patch with validation, scope, 403/404/409/422, audit + timeline (RED API tests first).
3. Telecaller read route + objections catalogue routes (RED tests first).
4. Web: lib types, `LeadCounseling` component + vitest, wire into both detail pages, objections page + nav, timeline label.
5. Docs: decision register DEC-SCOPE-343, API §12IO, RBAC §2.244, RTM, backlog status.
6. Browser QA (Playwright e2e for the counselor flow and the telecaller read-only view).

## Regression risks
Timeline union (every lead view) — covered by existing tel-015/ccrm-004 tests; `LostReasonsPanel` parametrisation — its vitest; migration
head tests of sibling items (chain-safe form).
