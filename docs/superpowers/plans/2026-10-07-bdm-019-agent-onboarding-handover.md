# bdm-019 implementation plan

Spec: `docs/superpowers/specs/2026-10-07-bdm-019-agent-onboarding-handover-design.md`. TDD per task: write the test, see it fail for the expected reason, implement the minimum, rerun.

## Tasks

1. **Migration + model.** `0097_bdm_agent_link`: two nullable FK columns, unique link, the three CHECK strings (§3), a guarded downgrade. Model: columns and `BDM_ONBOARDING_CHECKS`. Tests: `test_bdm_019_migration.py` (chain/head, CHECK parity, round trip, downgrade refusal). Update `test_bdm_018_migration.test_checks_equal_the_model` to compare 0084's frozen strings with the model plus 0097's replacements, and add `agent_org_id` to its FK map.
2. **Request rule per kind.** `bdm_onboarding.check_request` / `add_request` / `org_onboarding_out`. Tests: `test_bdm_019_request.py` (agent before Agreement Signed → 422; at it → 201 with `kind='agent'`; college 422; pending / linked 409; manager 403; out of scope 404; admin notice text).
3. **Admin queue + link-agent + reject.** `queue_page(kind)`, `items_out` (`kind`, `agent_org`), `lock_pending(kind)`, `agent_by_code`, `complete` for agent orgs, `outcome_notice` per kind; routes `link-agent`, the `/link` and School-create kind guard. Tests: `test_bdm_019_admin.py` (default queue school-only, `kind=agent`, every link refusal, the 1:1 rule, reject notice, non-admin 403, audit row).
4. **Live stages.** `bdm_pipeline.live_status` (agent), `pipeline_out` (counts, Inactive). Tests: `test_bdm_019_live.py` (pending only; linked pending org; Master; staff; active; suspended → Inactive; counts from `org_counts`; unlinked unchanged).
5. **AC4.** `test_bdm_019_pii.py`: a BDM and a manager get 403/404 on every agency student path, and no agency student name or email appears in the detail, list or queue responses.
6. **Web.** `lib/bdmOnboarding.ts` types; `BdmOrganizationOnboarding` (agent states); `AdminSchoolOnboardingRequests` `kind` prop; mount on `WorkflowPanel` `agents`; `BdmOrganizationPipeline` count; `BdmOrganizationProfileDetails` live staff + commission note. Vitest for each.
7. **E2E.** `tests/e2e/bdm-019-agent-onboarding.spec.ts`: request → admin links by code → the BDM sees the live steps.
8. **Docs.** `DEC-SCOPE-106`, API 12Y, RBAC 2.31, DATA_MODEL, backlog status, QA record.

## Phase 3 review notes (applied to the tasks above)

- **API:** `kind` defaults to `school`, so the bdm-018 queue contract is byte-compatible. Response fields are additive (`kind`, `agent_org`, `onboarding.agent`, `steps[].count`). `link-agent` mirrors `/link` (POST action, 200 item) with its own typed body rather than an either/or body. Status codes follow bdm-018: 422 for a wrong target or unknown code, 409 for state conflicts.
- **Transactions/concurrency:** one transaction per write. Lock order organization → request → agency (`lock_org`). AGN-001's `transition_org` locks only the agency row, so there is no lock cycle. Two links to one agency race on `uq_bdm_organizations_agent_org` → 409 `agent_org_linked` (IntegrityError mapped, as bdm-018).
- **Frontend:** reuse the bdm-018 queue and card (no new component). Labels stay visible; the queue keeps its loading, empty, error and paging states; status text, never colour alone; the pipeline count is plain text, which works at 320 px.
- **Security:** no new BDM access to agency tenancy; aggregates only (`org_counts`); member names and emails are never returned to BDM routes. Audit metadata and logs carry ids only. Admin routes check the role before any lookup (no existence leak). CSRF/session handling is unchanged: the same `sendJson` path as bdm-018.
