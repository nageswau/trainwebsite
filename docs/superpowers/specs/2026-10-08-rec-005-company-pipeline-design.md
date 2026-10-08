# rec-005 — Company B2B pipeline engine + stage history (design)

**Feature ID:** rec-005 · **Decision:** DEC-SCOPE-127 (provisional) · **Migration:** `0112_company_pipeline` (provisional) · **API:** §12AU ·
**RBAC:** §2.53 · **Depends on:** rec-003 (merged, PR #152).
**Evidence:** `EVID-018` §5 (lines 218–270), lead field "Status" (line 116), "genuine prospect" (line 122); `RECRUITER_CRM_BACKLOG.md`
§rec-005 (AC1–AC4). Module scope `DEC-SCOPE-116` (R1–R15).

## 1. Intent

Every recruiter company (the lead and the company are one `companies` row, R3) carries one stage of the §5 B2B pipeline. Recruiters move
the early, relationship stages by hand; the later stages follow requirement progress through one engine that later items (rec-007,
rec-008, rec-017, rec-019, rec-020, rec-022, rec-023, rec-024, rec-028) call. Every change is in an append-only history. Managers see a
board of companies per stage.

Success: AC1 every stage change writes history (from, to, actor, reason); AC2 manual moves only to manual stages; AC3 driven stages update on
requirement events; AC4 Lost needs a reason. Plus: reopening is manager-only; concurrent moves serialise on the row lock.

## 2. Decisions taken (owner said "proceed with the recommended answers")

These are recommended defaults, **UNVERIFIED** until the owner confirms them (the rec-003 D1–D6 precedent).

| # | Point | Answer |
|---|---|---|
| P1 | Stage count | The source lists **13** stages (lines 222–270); the backlog's "14" is a miscount. Lost is a flag, not a stage |
| P2 (Q-06) | Stages after Requirement Received | **Driven by events only**, forward along the order, so the company sits at its furthest-progressed requirement. The caller decides when an event fires (e.g. rec-007 fires `requirement_closed` only when no open requirement is left). Nobody sets a driven stage by hand (422) |
| P3 (Q-06) | Can a company go back? | Manual stages: yes, among the four manual stages, with a reason. Driven stages: only one system path back -- a new requirement on a company at Requirement Closed returns it to Requirement Received. Once a company is at a driven stage, manual moves are refused (422) |
| P4 | Manual stages | Contacted, Interested, Meeting Scheduled, Requirement Discussion (backlog). New Lead is the start and is never chosen by hand |
| P5 | Lost / reopen | Lost is a flag with a reason on top of the stage, which is kept (the bdm-004 pattern). The assigned recruiter (or super_admin) marks lost. **Only a placement manager or super_admin reopens** (tel-004 T13), with a reason; the company is back at the stage it was lost at. Events never move a lost or archived company |
| P6 | Who moves | The `can_edit` holders of rec-003: the assigned recruiter and super_admin. Managers have no edit (rec-003 D6) but reopen. The assigned BDM reads only (R10) |
| P7 | Board | `/recruiter/pipeline` for recruiters (own), managers (team + unassigned) and super_admin (all): a count tile per stage plus Lost, and one page of companies. Archived companies are left out |
| P8 | Events defined now | `call_logged`, `meeting_scheduled`, `requirement_received`, `jd_received`, `candidates_sourcing`, `profiles_shared`, `interview_scheduled`, `candidate_selected`, `candidate_joined`, `requirement_closed`. No caller exists yet; later items wire them |

## 3. Data (migration `0112_company_pipeline`)

`companies` gains:
- `stage` varchar(30) NOT NULL, server default `'new_lead'`, CHECK `ck_companies_stage` (the 13 keys; frozen copy in the migration, parity
  test). Existing rows become `new_lead` through the default; EMP-001 and `/workflows/it/jobs` inserts are unchanged.
- `stage_changed_at` timestamptz NOT NULL, server default `now()`; existing rows backfilled from `created_at`.
- `lost_at` timestamptz NULL, `lost_reason` varchar(500) NULL; CHECK `ck_companies_lost` (both or neither).
- Index `ix_companies_stage_recruiter (stage, assigned_recruiter_user_id)`.

`company_stage_history` (append-only, no stage CHECK so it survives a catalogue change): `id`, `company_id` FK RESTRICT, `from_stage`,
`to_stage`, `event` (`manual`, `lost`, `reopen` or an engine event), `actor_user_id` NULL = system, `reason` varchar(500), `position`
identity, `created_at`. Index `(company_id, position)`.

Every create is guarded (0001 builds from the models). Downgrade refuses while any history row exists or any company is past New Lead or lost.

## 4. Backend

- `app/recruiter_stages.py` — constants only: `STAGES` (key, label, kind ∈ start/manual/driven), `ORDER`, `MANUAL`, `EVENTS`
  (event → (from-set, to)), `label()`.
- `app/services/company_pipeline.py` — the single writer. `apply_event(db, company, event, actor=None, reason=None) -> bool` (caller holds
  the row lock; KeyError on an unknown event = caller bug), `person_move`, `mark_lost`, `reopen`, `pipeline_out`, `history_page`,
  `board`. Nothing commits; the route owns the transaction.
- `app/api/recruiter_pipeline.py` (router prefix `/recruiter`):
  - `POST /companies/{id}/stage` `{from_stage, to_stage, reason?}` → company envelope. 403 not `can_edit`; 409 archived; 409 `company_lost`;
    409 `stage_changed` (stale `from_stage`, body names `current_stage`); 422 unknown / start / driven / same stage, past the manual
    stages, backward without a reason.
  - `POST /companies/{id}/lost` `{reason}`; 409 already lost.
  - `POST /companies/{id}/reopen` `{reason}`; 403 not manager / super_admin; 409 archived; 409 `company_not_lost`.
  - `GET /companies/{id}/stage-history?limit&offset` newest first; actor null = system.
  - `GET /pipeline?stage&limit&offset` → `{stages:[{key,label,kind,count}], lost_count, items, total, limit, offset}`; 422 unknown stage.
- Every `{id}` resolves through `recruiter_companies.load_scoped` (out of scope = 404), writes lock the row. Audits
  `recruiter_company.stage_changed|lost|reopened` (keys and flags, no reason text); logs ids and keys only.
- Company output: detail gains `pipeline {stage, stage_label, stage_changed_at, lost {at, reason} | null, can_move, can_reopen, steps
  [{key,label,kind,state}]}`; list rows gain `stage`, `stage_label`, `lost`. `permissions` is unchanged (backward compatible).

## 5. Frontend

- `lib/recruiterPipeline.ts` — types, URLs; reuses `stageChanged` / `fieldErrors` from `lib/bdmPipeline`.
- `RecruiterCompanyPipeline` — the stepper (`jny-*`, state as text), Lost banner, Move form (manual stages only, reason required when
  moving back), Mark lost / Reopen with a reason. A stale move refreshes the company and says why.
- `RecruiterStageHistory` — newest first, "Show more", reloads after a write.
- Company detail renders both; the company list gets a Stage column (with a Lost badge).
- `/recruiter/pipeline` page + `RecruiterPipelineBoard` (the `BdmPipelineBoard` look; filters in the address, plain links).
- Nav: "Pipeline" for recruiters and managers; "Recruiter Pipeline" for super admin.

## 6. Security

Scope through `load_scoped` (IDOR → 404); role checks server side; reasons are plain text rendered as text (no HTML); Pydantic
`extra="forbid"`, stage keys pattern-validated; no new secrets; audit in the same transaction (fail closed).

## 7. Tests

Backend `test_rec_005_pipeline.py` (AC1–AC4, reopen 403/409, stale 409, lost freeze, scope 404, board counts/scope, events incl. the
reopen-after-closed path, concurrency via lock) and `test_rec_005_migration.py` (chain, parity, round trip in a throwaway DB).
Vitest for the pipeline component + board; Playwright `rec-005-pipeline.spec.ts`; regression: `test_rec_003_*`, `RecruiterCompanies`.
