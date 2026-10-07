# bdm-022 — Agent performance drill-down (design)

- **Feature ID:** bdm-022 · **Decision:** `DEC-SCOPE-110` · **Migration:** none · **API:** 12AD · **RBAC:** 2.36 (drafted as `DEC-SCOPE-109` / 12AC / 2.35; renumbered on merging `main` @ `97b27deb`, where tel-024 holds them)
- **Backlog:** `docs/delivery/BDM_CRM_BACKLOG.md` §4 bdm-022 and Appendix B.5 rows A-01…A-06 (`DERIVED_BLUEPRINT`); source Agent §F
  (L743–L757, `EVID-016`).
- **Dependencies (verified on `main` @ `f4a13514`):** bdm-019 (`DEC-SCOPE-107`, `0098_bdm_agent_link`, merged PR #123); AGN-004
  (`DEC-SCOPE-042`), AGN-008 (`DEC-SCOPE-050`), AGN-012 (`DEC-SCOPE-057`), AGN-013, AGN-014 (`DEC-SCOPE-051`) — all merged with their
  tests on `main`. AGN-018 (`DEC-SCOPE-062`) and AGN-022 (`DEC-SCOPE-064`) supply the shared definitions.

## 1. Defaults taken (owner's standing instruction: proceed with the recommended answer; each is open to correction)

| # | Question | Default |
|---|---|---|
| B1 | Who sees the panel | `load_scoped` (bdm-019/020/021's rule): a `bdm` of the Agent module (Q-02: the module's organizations), a `bdm_manager` for the team's organizations, `super_admin` all. bdm-019 already shows Students / Applications / Enrollments to the same readers, so narrowing to "assigned only" would make the two panels disagree. Out of scope = 404; any other role 403. |
| B2 | A non-Agent organization | 404 "Agent performance is only for Agent organizations" (bdm-020's pattern). |
| B3 | "The counts equal the Agent CRM's own funnel" (AC1) | The **agency Master dashboard's** headline definitions (AGN-018), computed for the organization's members exactly as AGN-022 scopes an org: A-01 Students = active agency students; A-02 Applications = agency applications not withdrawn (School-bridged excluded); A-03 Offers = `offer_clause()` (stage at/after `offer`, legacy `offer_received`/`accepted` included, or an offer recorded — O5, `DEC-SCOPE-056`); A-04 Visa = distinct applications with an `approved` visa case; A-05 Enrolled = applications at `enrolled`. The definitions are **shared code**, not copies: `agent_dashboard` exposes one column builder used by both the agency dashboard and this panel; a parity test pins the org figures to a Master's own dashboard. |
| B4 | The "offer miscount" | Not reintroduced: the panel uses `offer_clause()`, never `status in {offer_received, accepted}`. The legacy `services/portal._agent` miscount is a separate defect and is **not** changed here (out of scope). |
| B5 | Revenue (A-06, Q-08 / D17) | **Not tracked**: `tracked: false`, `count: null`, definition "Not tracked: deposits pass through to universities and commission is not shown to BDMs (awaiting a decision)". No money figure reaches a BDM route (bdm-019 A6 stays `NEEDS_CONFIRMATION`). |
| B6 | Drill-down levels (aggregate lists) | **Applications by stage**: the seven confirmed stages in order, then `withdrawn`, then "Earlier stage names" for any legacy status (shown only when > 0). The non-withdrawn rows sum to A-02. **Visa**: visa applications (distinct applications with a case) beside approvals. Never a student, application or member row. |
| B7 | Unlinked organization | `200 {linked: false, agency: null, steps: [], applications_by_stage: [], visa_applications: null}` → "Not onboarded yet. Figures appear once Overseas Admin links the agent organization." |
| B8 | Suspended / rejected agency (edge case "counts frozen, flagged") | Figures are still returned (live; the agency's members cannot sign in, so they do not move). `agency.status` is returned and the panel shows a text flag: "Suspended — this agency's members can't sign in, so these figures are not changing." (Rejected: "Not approved"). |
| B9 | "In the manager drill-down" | The panel shows on both organization pages (`/bdm/organizations/[id]`, `/bdm/manager/organizations/[id]`). The bdm-024 performance drill-down will link to these pages; it is not built here. |
| B10 | Audit | Read-only aggregates: a structured info log with ids only (bdm-020's pattern), no audit row (no personal data leaves). |

## 2. API

`GET /bdm/organizations/{org_id}/agent-performance` → `BdmAgentPerformanceOut`

```
{ organization_id, linked: bool,
  agency: {name, prefix, status} | null,
  steps: [{key, label, definition, tracked, count: int|null}],   // students, applications, offers, visa, enrolled, revenue
  applications_by_stage: [{key, label, count}],
  visa_applications: int | null,
  as_of: datetime }
```

Order: 403 role → 404 scope/missing → 404 not Agent → unlinked 200 → figures. Read-only; no lock, no write. Query count is constant:
the org (`load_scoped`), the agency (`db.get`), one SELECT of scalar subqueries, one grouped SELECT for the stages.

## 3. Backend

- `services/agent_dashboard.py`: `funnel_columns(students_where, applications_where)` returns the six shared scalar subqueries
  (students, applications, offers, visa_applications, visa_approvals, enrollments). `headline_counts` builds its eight KPIs from it plus
  its two own (pending documents, pending actions) — same SQL, same payload.
- `services/bdm_metrics.py`: `agent_performance(db, org)` — scopes by `agent_network.members_of(org.agent_org_id)` and
  `NETWORK_APPLICATION`, the `AGENT_STEPS` definitions, the stage grouping.
- `api/bdm_metrics.py`: the route beside bdm-021's `/business`.
- `schemas.py`: `BdmAgentPerformanceOut` and children.

## 4. Frontend

- `lib/bdmAgentPerformance.ts` (type, URL, guard) and `lib/bdmAgentPerformanceServer.ts` (`firstAgentPerformance`, never rejects).
- `components/BdmOrganizationAgentPerformance.tsx`: "Agent performance" section — agency line and status flag; the chain as the
  `pipeline-funnel` list used by bdm-021 (count text + decorative bar sized against Students, definition under each step); Revenue shows
  the "Not tracked yet" badge; Visa notes "of N visa applications"; the Applications step has a "Show by stage" disclosure button
  (`aria-expanded`/`aria-controls`) revealing a table. Error state with "Try again"; unlinked state text.
- Both organization pages fetch it alongside the organization (Agent organizations only) and pass it to `BdmOrganizationDetail`, which
  renders it after the onboarding card.

## 5. Security

Aggregates only (AC4): the response model has no free-form fields; a test asserts a linked agency's student name, member name and email
never appear. Scope is `load_scoped`. No new write path, no CSRF surface, no user input beyond the UUID path parameter.

## 6. Tests

Backend `tests/test_bdm_022_agent_performance.py`: AC1 parity with the Master's own `/workflows/overseas/agent/crm/dashboard` figures; offers by `offer_clause`
(legacy `offer_received` counted, withdrawn-after-offer counted, pre-offer not); visa = approved only, visa applications distinct; stage
breakdown sums to applications; revenue not tracked; unlinked → `linked: false`; suspended → figures + status; non-agent 404; other BDM
module 404; manager outside team 404; other role 403; no PII. Reruns: `test_agn_018_*`, `test_agn_019_*`, `test_agn_022_*`,
`test_bdm_019_*`, `test_bdm_021_*`.

Web (vitest) `BdmOrganizationAgentPerformance.test.tsx`: linked figures, not-tracked revenue, disclosure, unlinked text, suspended flag,
error + retry. Playwright `bdm-022-agent-performance.spec.ts`: a BDM opens a linked Agent organization and sees the figures and the stage
breakdown; an unlinked one says "Not onboarded yet".

## 7. Risks

- `headline_counts` refactor (AGN-018 dashboard, high regression risk): pure extraction; AGN-018 tests rerun.
- Coupling to the Agent CRM schema: the parity test fails if the agency definitions drift.
