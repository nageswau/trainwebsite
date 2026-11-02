# itc-006 — Auto-assign by source and workload (design + plan)

**Feature:** `itc-006` (`docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md`), wave W1. **Decision:** DEC-SCOPE-337. **Dependencies:** none.
**Authority:** owner Q-01 (2026-11-01) approved all phases in waves; Q-06 (rule precedence) was open, and the owner's standing
instruction for this session is to proceed with the recommended answer. The recommended answer is recorded below as the build
default and stays reversible (`NEEDS_CONFIRMATION` for configurable precedence).

## Intent
New IT (and overseas) leads should reach the right telecaller without a manager's hand: by the lead's **source**, and, when no rule
matches, to the telecaller with the **least open work** instead of strictly in turn (source PDF §9, §3 step 2).

## As built before itc-006
`services/lead_distribution.py`: T18 guard (product without a team → queue) → product rule → city rule → round robin → unassigned.
Rules map one match to one telecaller (`tel_distribution_rules`, unique per team + match). Round robin serialises on
`tel_round_robin_cursors` FOR UPDATE.

## Decisions (build defaults — my calls, reversible)
| # | Decision |
|---|---|
| D1 | **Q-06 answer:** fixed precedence `T18 guard → source rule → product rule → city rule → team fallback strategy → unassigned`. Configurable precedence is deferred (`NEEDS_CONFIRMATION`); it would need a rule-order model nobody has asked for yet. |
| D2 | A **source rule** maps one of the 13 fixed lead sources (`app/tel_sources.py`) to **one** telecaller, like product/city rules (unique per team + source). "Pool" in the backlog is read as "the telecaller the rule names"; several telecallers per source is out of scope. Campaigns already route through their product, so no campaign rule. |
| D3 | A per-team **fallback strategy** `round_robin` (default, today's behaviour) or `workload`, stored as `tel_settings.distribution_strategy` (one seeded row per team already exists). |
| D4 | **Workload** = fewest open leads (status not in `lead_stages.CLOSED`) among the team's eligible telecallers (role telecaller, active, on the team); ties go to the next tied telecaller after the round-robin cursor, and the cursor moves. The same cursor row lock serialises concurrent intakes, so two intakes never read the same stale counts. Counting uses the existing `ix_enquiries_telecaller_status`. |
| D5 | Audit: `lead.assign` metadata keeps `from/to/method` and adds `rule_id` when a rule matched (AC4). New methods: `source_rule`, `workload`. |
| D6 | Strategy AuthZ: `telecaller_manager` with at least one direct report on that team, or `super_admin` (backlog: "manager or admin of the same team"); others 403, unknown team 404. No new grant; `it_admin` keeps no access to telecaller distribution (unchanged). Rule AuthZ unchanged (tel-007 DI3/AC5). |

## API (additive; API §12II)
- `POST /telecaller/distribution-rules`: `kind` gains `"source"`, body gains `source` (one of the 13). Shape errors 422
  (`Choose a source`, `A source rule has no product or city`); duplicate (team, source) 409 like the others. A telecaller on the other
  team stays 422 (existing `assignee`).
- `GET /telecaller/distribution-rules`: `kind` filter gains `source`; each item gains `source` (null for other kinds).
- `GET /telecaller/distribution-strategy` → `{items: [{team, team_label, strategy, editable}]}` (any telecaller manager / super_admin).
- `PUT /telecaller/distribution-strategy/{team}` `{strategy}` → 200 item; audited `telecaller.strategy_update` with from/to.

## DB (migration 0222, data-preserving)
- `tel_distribution_rules.source VARCHAR(30) NULL`; kind CHECK → `('product','city','source')`; shape CHECK gains the source arm;
  `uq_tel_distribution_rules_source (team, source) WHERE kind='source'`; source CHECK against the frozen 13.
- `tel_settings.distribution_strategy VARCHAR(20) NOT NULL DEFAULT 'round_robin'` + CHECK.
- Idempotent (`IF NOT EXISTS` / drop-then-add) because 0001 builds fresh DBs from current models. Downgrade refuses while source rules
  exist (no silent data loss), else drops both columns and restores the old CHECKs.

## UI
- Distribution page: rule form "Rule type" gains **Source** with a source picker; list shows `Source: Instagram`; explanatory text names
  the new order.
- New "When no rule matches" card per team (select Round robin / Fewest open leads + Save), loading / error+retry / saved / read-only
  states; reuses the alert-settings card pattern.
- Lead timeline method labels gain Source rule, City rule (existing gap: backend emits `city_rule`), Workload.

## Acceptance criteria → tests
| AC | Test |
|---|---|
| AC1 source rule wins over product rule | `test_itc_006_distribution::test_source_rule_wins_over_product_and_city` |
| AC2 workload picks fewest open leads (closed leads not counted; ties in turn) | `::test_workload_picks_fewest_open_leads`, `::test_workload_ties_go_in_turn` |
| AC3 inactive telecallers never picked | `::test_workload_skips_inactive`, `::test_inactive_source_rule_falls_through` |
| AC4 audit names the rule | `::test_audit_names_the_rule` |
| − rule to overseas telecaller for IT → 422 | `test_itc_006_api::test_source_rule_for_other_team_telecaller_is_422` |
| E all inactive → unassigned | `::test_workload_with_nobody_eligible_leaves_unassigned` |
| API shape / dup / strategy authz | `test_itc_006_api` |
| UI | `TelecallerRulesPanel.test.tsx` (source), `TelecallerStrategyPanel.test.tsx`, e2e `itc-006-distribution.spec.ts` |

## Plan (TDD, small tasks)
1. Model + migration 0222 + update pinned shape tests (tel-007/tel-020 migration tests).
2. Service: source rule, strategy, workload, `rule_id` in audit (RED tests first).
3. API: rule create/list with source; strategy GET/PUT (RED tests first).
4. Web: lib types/labels; rules panel source option; strategy panel; timeline labels (vitest first).
5. Docs: DEC-SCOPE-337, API §12II, RBAC §2.239, RTM, backlog status.
6. Docker QA (browser + Playwright e2e), fixes, simplify, verify, merge.

## Regression risks
Every intake path (website, BDM, manager, CSV import) calls `on_intake` — default strategy keeps round robin, so behaviour is unchanged
until a manager adds a source rule or switches to workload. tel-007 audit-metadata test gains `rule_id`.
