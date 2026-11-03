# itc-005 — Admin-configurable IT lead and student status labels (design + plan)

Source: `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` `itc-005` (PDF §3 "Statuses should be configurable by an administrator. Status changes
should record who changed them and when."). Scope approved by the owner 2026-11-01 (backlog Q-01: all phases). Q-05 is open; the builder
defaults below are `NEEDS_CONFIRMATION`. Decision: `DEC-SCOPE-362`. API §12JH. RBAC §2.262. Migration `0244_it_status_labels`.
Dependencies: itc-004 (`DEC-SCOPE-338`, final lead stage set — built) and itc-031 (`DEC-SCOPE-359`, lifecycle set — built).

## Intent

The IT team wants its own words on the lead and student statuses ("Course Interested" instead of "Interested", the PDF's names) and wants to
hide statuses it does not use, without a code change and without breaking the rules (alerts, metrics, conversion) that hang off each state.

## Decisions (builder defaults, Q-05 recommended answer)

- **S1 — labels, order and enable/disable of the fixed system states, per team.** The state machines (`lead_stages.py` EVENTS/ORDER,
  `it_lifecycle` derivation) are unchanged; only the IT team (`team = 'it'`) is configurable now. Overseas labels are unaffected (E case).
- **S2 — two kinds:** `lead` (the 18 lead stages of `lead_stages.STAGES`) and `lifecycle` (the 13 itc-031 stages).
- **S3 — storage = override rows only.** `it_status_labels (team, kind, code)` PK with `label`, `sort_order`, `enabled`, `updated_by_user_id`,
  `updated_at`. No row = the code default (label from the catalogue, order = catalogue position × 10, enabled). Stages added to the code later
  appear automatically. No existing row changes.
- **S4 — what may be disabled:** only states a person *chooses*. Lead: the telecaller/counselor manual targets and the closed outcomes
  (`MANUAL ∪ COUNSELOR_MANUAL ∪ CLOSED`) except `follow_up` (the reopen and return target). Lifecycle: the two IT-Admin overrides
  (`not_placed`, `closed`). Every other state is label + order only (`can_disable: false`; disabling it is `422`).
- **S5 — disabling a state in use is allowed** (Q-05 "or allowed"); the admin page shows the count of IT leads in the stage (lead) / of
  enrolments carrying the override (lifecycle) so the admin decides knowingly. Existing rows keep their stage and still show its label (AC2).
- **S6 — a disabled state cannot be chosen:** the API refuses a person's move of an IT lead to a disabled stage (`422` at `to_stage`) and an
  IT-Admin override to a disabled lifecycle stage (`409`, the override endpoint's refusal code); the pickers do not offer it (the current
  stage stays visible). Filters still list it (history). Clearing an override is always allowed.
- **S7 — labels:** trimmed, 1–60 characters, unique per kind (case-insensitive) among the effective labels → `422` on a clash.
- **S8 — where labels are resolved:**
  - *Lifecycle* — server side: `it_lifecycle` reads the team's labels once per call (`views_for`, `staff_lifecycle`), so every payload's
    `stage_label`/history labels carry the configured words, including the student's safe view (itc-031 lib note: "labels come from the API").
  - *Leads* — client side: the lead payloads' `status_label` stays the canonical label (API contracts and the fixed-query-count tests are
    unchanged); every IT lead chip, picker and filter reads the configured catalogue (`GET /api/v1/it/status-labels`, one fetch per page)
    through `useStageCatalogue(division)`. CSV exports keep the canonical names (`NEEDS_CONFIRMATION`).
- **S9 — audit:** every save writes one `audit_logs` row `it.status_label.update` (entity `it_status_label`, id `kind:code`) with the
  before/after of label, order and enabled (`audit_change`), so "who changed it and when" is in the IT audit log (AC3).
- **S10 — access:** read — any IT staff user (division `it`, not a student) and `super_admin`; write — `it_admin` only (403 otherwise).
  Students never read the catalogue (it holds staff-only wording such as "At risk").

## API (§12JH)

- `GET /api/v1/it/status-labels` → `{lead: [Entry], lifecycle: [Entry]}`, each ordered by `sort_order`, then catalogue position.
  `Entry = {code, label, default_label, sort_order, enabled, can_disable}`.
- `GET /api/v1/admin/it/status-labels` (IT Admin) → the same with `in_use` and `updated_at`/`updated_by` per entry.
- `PUT /api/v1/admin/it/status-labels/{kind}/{code}` (IT Admin) body `{label, sort_order (0–9999), enabled}` → `200` Entry (admin shape).
  `404` unknown kind/code; `422` invalid body, label clash, or disabling a state that cannot be disabled. Idempotent upsert; concurrent saves
  serialise on the row (`INSERT … ON CONFLICT DO UPDATE`).

## Acceptance criteria (testable)

1. Renaming a label changes every IT screen: the IT catalogue returns it; IT lead lists/detail/pickers/filters show it; the lifecycle payloads
   (staff 360 + student profile) carry it. Overseas leads keep the default.
2. A disabled state cannot be chosen (API 422/409 + not offered in pickers) but still shows on historical rows (label resolved, filters list it).
3. Changes are audited (action, actor, time, before/after).
- + IT Admin renames "interested" to "Course Interested".
- − disabling `contacted` (a system state) → 422; a non-admin write → 403; a student read → 403.
- E: overseas labels are unaffected; reset by saving the default label.

## Plan (TDD, small steps)

1. Model `ItStatusLabel` + migration `0244_it_status_labels` (+ migration test).
2. Service `services/status_labels.py`: catalogue, labels, update (validation, audit), `require_enabled`. Tests via API.
3. Routes `api/it_status_labels.py` (read + admin), registered in `main.py`; portal header-only section `status-labels`.
4. Guards: `lead_pipeline.person_move` (IT lead, disabled → 422); `it_lifecycle.set_override` (disabled → 409); lifecycle labels.
5. Frontend: `lib/statusLabels.ts` (`useStageCatalogue`), `leadStages.ts` pickers accept a disabled set; IT lead chips/pickers/filters;
   `ItStatusLabelsPanel` on `/it/admin/status-labels`; nav entry. Vitest.
6. E2E `itc-005-status-labels.spec.ts`: admin renames Interested → Course Interested and it shows on the IT lead list; disable hides it from
   the picker; desktop + phone.
7. Docs: DEC-SCOPE-362, API §12JH, RBAC §2.262, backlog status.

## Regression risks

`lead_pipeline.person_move` (shared IT/overseas — the guard runs for IT leads only), the lifecycle query-count test (+1 query per call,
constant), stage picker tests (new optional parameter, default unchanged).
