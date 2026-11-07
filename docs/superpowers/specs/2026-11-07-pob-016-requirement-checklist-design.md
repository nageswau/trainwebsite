# pob-016 — Requirement validation checklist and clarification tasks (DEC-SCOPE-419)

**Source:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` pob-016 (`UNVERIFIED` draft; Q-00 approved the backlog for build in waves).
**Depends on (merged):** pob-002 (requirement revisions, decision-maker), rec-007 (status machine), rec-024 (follow-ups).
**Builder's calls** are marked (B): recommended defaults taken without owner confirmation, which the owner can reverse.

**Evidence gap (`NEEDS_CONFIRMATION`):** the backlog says "§7.1 (8 checks)" but does not list them, and the source docx
(`Edusphere_Placement_Officer_Business_Development_CRM_Functional_Requirements.docx`) is not on this machine. C1's eight items are therefore a
proposal drawn from the §7 field groups the backlog traces (Appendix A), not the document's wording. They live in one constant, so correcting them is a
one-file change. Pob-020 recorded the same gap for §10.

## Goal

A Placement Officer or recruiter records, per requirement, whether the eight things needed to start sourcing are known. What is missing becomes a
follow-up with the client contact. Where the rule is switched on, a requirement cannot start sourcing until the checklist is complete or a Team Lead has overridden it with a reason.

**Non-goals:** a template or admin editor for the items; free-text notes on an item (C2); withdrawing an override; automation beyond §16's clarification trigger
(pob-027); a settings page (the rules sit on the card).

**Must not change:** with both rules off (the default) every status move behaves as today, so rec-007's transitions and hrc-007's approval order are untouched.

## Calls

- **C1 (B, `NEEDS_CONFIRMATION`) The eight items**, fixed in code as `(key, label, hint)`:
  `role_scope` Role and responsibilities; `skills_experience` Skills and experience; `openings` Number of openings; `location_work_mode` Location and work mode;
  `salary_budget` Salary budget; `hiring_process` Interview process and decision-maker; `commercial_terms` Commercial terms; `timeline` Joining date and turnaround.
- **C2 (B) States.** Each item is `confirmed`, `not_applicable` or `missing`. An item nobody has answered has no row and reads "Not reviewed" (it counts as
  incomplete but creates no follow-up, so a new requirement adds nothing to anyone's task list). There is no note: the spec names three states only, and a free-text note on `commercial_terms`
  could carry fee values past pob-001's gate to readers without `commercials.client.view`. The follow-up has its own notes.
- **C3 Complete** = all eight are `confirmed` or `not_applicable`.
- **C4 A missing item creates a follow-up** (AC1) through `recruiter_follow_ups.create`: new reason `clarification`, the requirement linked, the contact being the active decision-maker,
  else the company's active primary contact, else none. Due in 2 days (B). Static notes naming the requirement and the item. rec-024's cap of 50 open follow-ups applies: a 409 and nothing is saved.
- **C5 (B) Leaving `missing` closes its follow-up if still open:** `confirmed` completes it, `not_applicable` cancels it (both with a stated outcome/reason). Marking `missing` again makes a new one. A follow-up
  closed by hand leaves the item `missing`; re-saving the same status changes nothing (no follow-up, no audit).
- **C6 The rule (global or per company).** `requirement_checklist_settings` is one row (`id = 1`, no row = off). `companies.checklist_blocks_sourcing` is `NULL` (use the global rule), `true` or `false`. The company's value wins.
- **C7 The guard** is in `recruiter_requirements.change_status`, after the transition and approval checks, so `/workflows/it/jobs` is covered too. Nothing moves a requirement into a working status automatically.
  It refuses with `409 {message, code: "checklist_incomplete", missing: [{key, label, status}]}` (AC2). `message` lists the labels.
- **C8 (B) Skipping does not bypass it.** It guards every working status (`sourcing`, `shortlisting`, `profiles_shared`, `interviewing`, `selected`), because the status machine allows `requirement_received → shortlisting`.
- **C9 "Sourcing has started"** = the current status is a working status, `joined` or `filled`, or the history holds a move to a working status. A started requirement is never blocked (it can pause and resume, and a live requirement is not stopped by switching the rule on).
- **C10 After sourcing has started, editing an item only warns:** the checklist returns a `warning` while it is incomplete, and the edit and its follow-up still happen (backlog `E`).
- **C11 (B) The override** is its own step, because a Team Lead (`placement_manager`) is not a requirement writer and cannot make the status move. `POST .../checklist/override` with a reason records who, when and why; the owner can then move the requirement. Audited (AC3).
  Refused (409) when nothing is being blocked: rule off, complete, already started, already overridden, or cancelled. It lasts for the requirement. No withdrawal.
- **C12 Who.** Read: the requirement's readers (`load_scoped(officers=True)`; out of scope = 404). Answer items: `can_edit` (recruiter, placement officer, super admin, in scope). Override and the company rule: `placement_manager` in scope and super admin.
  The global rule: super admin only, as hrc-007's approval settings. On a requirement, scope (404) comes first, as everywhere in that router; the rule routes check the role (403) first.
- **C13 No `jobs.updated_at` bump** from the checklist: the requirement's fields did not change, so an open Edit form must not get a false stale-save conflict (hrc-003).
- **C14 Audit,** all in the write's transaction, shown in the requirement's History: `recruiter_requirement.checklist_item` (item, before/after labels), `recruiter_requirement.checklist_override` (reason, the incomplete items).
  The rules: `requirement_checklist.global_rule` and `requirement_checklist.company_rule`, each with before/after.

## Data model (migration `0298_requirement_checklist`, guarded per the 0001 `create_all` rule)

- `job_checklist_items`: PK `(job_id, item_key)`, `job_id` FK CASCADE, `status` CHECK, `follow_up_id` FK `recruiter_follow_ups` SET NULL, `updated_by_user_id`, timestamps. `item_key` has no CHECK: correcting C1 needs no migration.
- `job_checklist_overrides`: PK `job_id` FK CASCADE, `reason` text, `overridden_by_user_id`, timestamps.
- `requirement_checklist_settings`: `id` int PK, `block_sourcing` bool, `updated_by_user_id`, timestamps.
- `companies.checklist_blocks_sourcing` boolean NULL. A merge keeps the survivor's value (pob-006 moves named fields only).
- `ck_recruiter_follow_ups_reason` recreated with `clarification`. Downgrade: any `clarification` follow-up becomes `jd` first (the backlog's other named reason), then the check is restored, so no row is lost.

## API

| Route | Who |
| --- | --- |
| `GET /recruiter/requirements/{id}/checklist` | requirement readers |
| `PUT /recruiter/requirements/{id}/checklist/items/{key}` `{status}` | `can_edit` |
| `POST /recruiter/requirements/{id}/checklist/override` `{reason}` | manager in scope, super admin |
| `PUT /recruiter/companies/{id}/checklist-rule` `{block_sourcing: true/false/null}` | manager in scope, super admin |
| `PUT /recruiter/requirement-checklist/settings` `{block_sourcing}` | super admin |

The three requirement routes return the whole checklist: `items`, `summary`, `blocking`, `override`, `sourcing_started`, `warning`, and the `can_*` flags. The rule routes return the saved value.

## Web

`RequirementChecklist` card on the requirement page, after the JD: the summary, one radio group per item (a save on change, one at a time, focus kept), the follow-up's due date and contact, the
blocking state, the override form when `can_override`, and the rule selects for those who may change them. Loading, load-failure and save-failure states. Read-only readers see labels, not radios. `detailMessage` learns to read `{message}` from a structured detail,
so the status form (and `/workflows/it/jobs`' screen) show the 409's list rather than "Something went wrong." New `clarification` label in `lib/recruiterFollowUps.ts`.

## Regression risks

rec-007 transitions (default off); rec-024 reasons (web and API pins; 0116's frozen check test); pob-006 merge; rec-038 route matrix (five new rows); `detailMessage` on object details.

## Tests

`test_pob_016_checklist.py` (AC1-AC3, C4-C14, scope and roles), `test_pob_016_migration.py`, `pob016Checklist.test.tsx`, `pob-016-checklist.spec.ts`.
