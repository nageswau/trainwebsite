# tel-007 — Lead distribution rules, round robin, unassigned queue, manual (re)assignment (design)

Backlog: `docs/delivery/TELECALLER_CRM_BACKLOG.md` tel-007 (EVID-019 §17, Appendix A L560–L582; `DEC-SCOPE-073` T11, T18, T22, T23).
Dependencies tel-001, tel-002, tel-003 and tel-004 are merged (tel-004 PR #81 @ `69829a59`); branch `feature/tel-007` from `main` @ `3986958c`.
Decision: `DEC-SCOPE-087`. Migration: `0085_tel_distribution` (after `0084_bdm_onboarding`). API contract §12K. Drafted as `DEC-SCOPE-082` / `0082` / §12I;
re-chained on `main` @ `50838192` (bdm-025: 082 / 0082; tel-012: 083 / 0083 / §12I), `7afd4a4b` (tel-008: 084 / §12J) 
`9b395aaf` (bdm-018: 085 / `0084_bdm_onboarding`) and `a36b5b63` (bdm-021: 086, no migration).
**Merged** to `main` as PR #90 @ `595025e4` (2026-10-06).

## 1. Owner answers (2026-10-06, `EXPLICIT_APPROVAL`) and recorded defaults

| # | Question | Answer |
|---|---|---|
| DI1 (Q-07) | Who is eligible | **An active account only.** Role `telecaller`, `users.active`, on the lead's team. Deactivated telecallers are skipped by rules and by round robin. A manager "pause" is deferred (tel-025 owns deactivation and bulk reassignment). No new column |
| DI2 (Q-05) | Which intake distributes | **Website and BDM-entered leads**, in the intake transaction. The team is the lead's division. A lead with no product skips product rules (city rule, then round robin). Existing unassigned leads are **not** backfilled; they wait in the queue. tel-005/006 call the same function |
| DI3 | Who edits rules | **Any manager reads every rule of both teams, but creates, changes or deletes only a rule whose telecaller is one of their direct reports.** `super_admin`: all. The rule's telecaller must be an active telecaller on the rule's team (422). One rule per team + product and per team + city (case-insensitive; 409) |
| DI4 | Reassign UI | **One manager "Lead assignment" page with two tabs:** Unassigned (the queue of the teams of my reports) and Assigned to my team (my reports' leads, filter by telecaller). Bulk-select, then assign/reassign to a direct report |
| D1 (default) | Lead team | `enquiries.division` (`it`/`overseas`, T22). A lead whose product has no team (T18: Career Guidance, General Enquiry) goes to the unassigned queue. A product rule needs the product's team to equal the rule's team. tel-005 (manual create) keeps division = product team |
| D2 (default) | Round-robin order | Eligible telecallers ordered by user id; the next one after the team cursor's `last_user_id`, wrapping. The cursor row is locked (`FOR UPDATE`), so concurrent intakes serialise. A rule match and a manual assignment do not move the cursor |
| D3 (default) | Manual assignment | `POST /telecaller/leads/assign`: 1–100 distinct lead ids, all or nothing. Every lead must be in the manager's scope (tel-004 `scope`: reports' leads + the unassigned leads of their reports' teams; else 404). The target must be a direct report (else 403, AC5), active and on each lead's team (else 422). A lead already with that telecaller is left unchanged. Leads at any stage may be reassigned (the stage only moves `new → assigned`) |
| D4 (default) | History | Each assignment change writes one `AuditLog` (`lead.assign`, ids + method `product_rule`/`city_rule`/`round_robin`/`manual`), and the stage moves through `lead_pipeline.apply_event("assigned")` (stage history). No assignment table |
| D5 (default) | Alert | The "New Lead Assigned" alert is tel-020's (it fires on these same writes); tel-007 sends none |
| D6 (default) | Rule shape | No `active` flag: a rule is deleted to stop it (audited). PATCH changes only the telecaller; changing the match is delete + create |

## 2. Distribution order (`services/lead_distribution.distribute`)

For a new lead (status `new`, no telecaller) in team `T = lead.division`:
1. If the lead has a product: a product with no team → **unassigned**. Otherwise the product rule `(T, product)` whose telecaller is eligible.
2. Else the city rule `(T, lower(trim(lead.city)))` whose telecaller is eligible (only when the lead has a city).
3. Else round robin among the eligible telecallers of `T`.
4. Nobody eligible → **unassigned** (`telecaller_user_id` stays NULL).

A rule whose telecaller is inactive is skipped (AC3), so the lead falls through to the next step. Eligible = role `telecaller`, active,
`telecaller_profiles.team = T`. A division outside `it`/`overseas` → unassigned.

## 3. Data model (migration `0085_tel_distribution`)

`tel_distribution_rules`: `id` uuid PK; `team` varchar(20) CHECK `it`/`overseas`; `kind` varchar(10) CHECK `product`/`city`; `product_id`
FK `tel_products` NULL; `city` varchar(120) NULL; `telecaller_user_id` FK `users` NOT NULL; timestamps. CHECK shape
`(kind='product' AND product_id NOT NULL AND city NULL) OR (kind='city' AND city NOT NULL AND product_id NULL)`. Partial unique indexes
`uq_tel_distribution_rules_product (team, product_id) WHERE kind='product'` and `uq_tel_distribution_rules_city (team, lower(city)) WHERE
kind='city'`. Index on `telecaller_user_id`.

`tel_round_robin_cursors`: `team` varchar(20) PK CHECK; `last_user_id` FK `users` NULL; `updated_at`. Rows are created on first use
(`INSERT … ON CONFLICT DO NOTHING`), because 0001 builds a fresh database from the models without seeds.

Creation is guarded (skip if the tables exist). Downgrade refuses while any rule exists, then drops both tables.

## 4. Service (`app/services/lead_distribution.py`) — nothing in it commits

- `next_in_turn(candidates, last) -> id`: the pure round-robin step (the first candidate after `last`, wrapping).
- `distribute(db, lead) -> str | None`: §2; returns the method or None.
- `on_intake(db, lead)`: what `public.create_enquiry` and `bdm_leads.add_lead` call after the flush, in the same transaction. It runs
  `distribute` inside a SAVEPOINT; an unexpected error is logged and rolled back to the savepoint, so the enquiry is still saved, unassigned
  (a public enquiry is never lost to a distribution bug).
- `assign(db, lead, telecaller_id, method, actor)`: sets `telecaller_user_id`, fires `apply_event("assigned")`, adds the audit row, logs
  `lead_assigned` (ids and method only).
- `assignee(db, actor, user_id, *, lock)`: the target check shared by rules and manual assignment (not a telecaller / inactive → 422; a manager's
  non-report → 403). The profile is read `FOR SHARE` on writes so a concurrent manager change waits.

## 5. API (`API_CONTRACT.md` §12K)

All routes: `telecaller_manager` or `super_admin` (else 403; signed out 401). Lists are `{items, total, limit, offset}`.

- `GET /telecaller/distribution-rules?team&kind&telecaller_user_id&limit&offset` → item `{id, team, kind, product {id, name, active} | null, city,
  telecaller {id, full_name, active}, editable}` (`editable`: the caller may change it). Order: team, kind, product name / city.
- `POST /telecaller/distribution-rules` `{team, kind, product_id?, city?, telecaller_user_id}` (extra keys 422) → 201 item. 422: shape,
  inactive/unknown product, product team ≠ rule team, telecaller not active / not a telecaller / other team. 403: not a direct report.
  409: a rule for that product or city already exists on the team.
- `PATCH /telecaller/distribution-rules/{id}` `{telecaller_user_id}` → 200 item. 404 missing; 403 when the current or new telecaller isn't a
  direct report.
- `DELETE /telecaller/distribution-rules/{id}` → 204; 404 / 403 as PATCH.
- `GET /telecaller/leads/unassigned?team&q&limit&offset` → oldest first; item `{id, lead_code, name, division, city, product {id, name} |
  null, source, status, status_label, telecaller: null, created_at}`. `q` matches Lead ID, name or city.
- `GET /telecaller/leads/assigned?telecaller_user_id&team&q&limit&offset` → newest first; same item with `telecaller {id, full_name,
  active}`. Manager: their reports' leads (a non-report id → 404); super_admin: all assigned leads.
- `POST /telecaller/leads/assign` `{lead_ids, telecaller_user_id}` → 200 `{assigned, unchanged}` (D3).
- Static `/telecaller/leads/unassigned|assigned|assign` are declared on the telecaller router before any `/leads/{id}` route, so tel-008's
  `GET /telecaller/leads/{id}` cannot shadow them.

`POST /public/enquiries` and `POST /bdm/organizations/{id}/leads` are unchanged in shape; the returned `status` is `assigned` when a
telecaller was chosen.

## 6. Frontend

- Nav (`TELECALLER_MANAGER_NAV`): **Lead assignment** `/telecaller/manager/assignment`, **Distribution rules** `/telecaller/manager/distribution`.
- `TelecallerCataloguePage` gains an optional `eyebrow` (default "Settings"); both pages reuse it.
- `TelecallerRulesPanel`: the order explained in one line; a create form (team, rule type product/city, product picker narrowed to the team's
  active products, city, telecaller picker narrowed to my active reports on the team); the list with a team filter, loading / error+Retry /
  empty states, and per editable row **Change telecaller** (inline select, Save/Cancel, Esc) and **Delete** (inline confirm).
- `TelecallerAssignmentPanel`: two tabs (Unassigned / Assigned to my team, in the URL `?view=`), a telecaller filter on the Assigned tab,
  search, a table with a checkbox per row and "select all on this page", an assign bar (telecaller picker + "Assign n selected"), feedback,
  pager, loading / empty / error states. A double click posts once.

## 7. Acceptance criteria (testable)

1. AC1: rules apply in order — product rule, then city rule, then round robin.
2. AC2: round robin is even (3 telecallers, 9 leads → 3 each; `next_in_turn`), and consecutive intakes follow the cursor order.
3. AC3: a deactivated telecaller is skipped (rule and round robin).
4. AC4: no candidate (or a product without a team) → unassigned, stage `new`.
5. AC5: a manager assigning or reassigning to someone outside their reports → 403.
6. A rule pointing at another team's telecaller → 422; a duplicate rule → 409; a manager editing another manager's rule → 403.
7. Website and BDM intake assign in the same transaction: `telecaller_user_id`, stage `assigned`, one stage-history row, one audit row.
8. The queue lists only unassigned leads of the manager's teams; the Assigned tab only their reports' leads.

## 8. Security

Role first, then scope, then the write (2026-09-28 convention). Leads out of scope read as missing (404); targets outside the reports
are 403 (AC5). Pydantic forbids extra keys, so no client sets `method` or the actor. One audit row per changed lead (bulk included); logs
carry ids only (no names, phones or cities). ORM-bound queries; `q` goes through the escaped LIKE helper. Row locks: leads `FOR UPDATE`
(ordered by id), target profile `FOR SHARE`, cursor `FOR UPDATE`.

## 9. Regression risk

High: public intake (`test_pub_002_enquiry_crm`, `test_tel_003_intake`) and BDM lead create (`test_bdm_017_*`, bdm-004 lead tests) now
assign when an eligible telecaller exists in the shared test database, so a returned `status` may be `assigned`. Website latency grows by
a few indexed queries and one row lock per intake.
