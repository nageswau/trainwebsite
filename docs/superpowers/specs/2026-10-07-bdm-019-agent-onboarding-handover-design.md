# bdm-019 — Agent onboarding handover + Agent Organization link (design)

- **Feature ID:** bdm-019 · **Decision:** `DEC-SCOPE-107` · **Migration:** `0098_bdm_agent_link` (after `0096_bdm_targets`) · **API:** 12AA · **RBAC:** 2.33
- **Backlog:** `docs/delivery/BDM_CRM_BACKLOG.md` §4 bdm-019 (`DERIVED_BLUEPRINT`); `DEC-SCOPE-055` D7, D32; `DEC-SCOPE-071` S3/S4; `DEC-SCOPE-085` (bdm-018, the template).
- **Dependencies (verified on `main` @ `b1495fa2`):** bdm-004 (COMPLETE, `0073`), bdm-005 (merged, `0079`; open items are owner-level only, as bdm-018 recorded), AGN-001 (`0046_agent_orgs`), AGN-002 (`0047_agent_org_staff`), bdm-018 (`0084_bdm_onboarding`). The backlog's "ang-001 … Not built" line (§1 table) is stale: AGN-001 shipped as `DEC-SCOPE-038`.

## 1. Defaults taken (owner's standing instruction: proceed with the recommended answer; each is open to correction)

| # | Question | Default |
|---|---|---|
| A1 | How the admin resolves an agent request | **Link an existing Agent Organization by its code (`agent_orgs.prefix`), or reject.** Admins create agencies through the existing paths (self-registration, or *Users → create agent*, AGN-001 D11), which already create a pending organization; approval stays AGN-001's Approve. No new create path, so the AGN-001 approval flow is untouched (regression risk in the backlog). Covers the edge case "agent self-registered before the BDM request". |
| A2 | "A request needs Agreement Signed" (AC1) | The stored manual stage is `agreement_signed` (the last manual Agent stage; bdm-005 M5 moves it there when the MoU is Signed). Otherwise 422 "The agreement must be signed to request onboarding". The School rule (MoU Signed/Active) is unchanged. |
| A3 | Live Agent stages (D7, D32) | Per-step evidence, the bdm-018 H2 rule: Agent Onboarding = linked; Master Login Created = ≥1 active Master member; Staff Logins Created = ≥1 active staff member; Active Agent = organization `status = 'active'`. A pending request alone: all four not done, Agent Onboarding current. |
| A4 | Volume steps (Students, Applications, Enrollments) | When linked, counted with AGN-022's `agent_network.org_counts` (the same definitions as the agency dashboard): each step carries `count`; `done` when > 0, else `upcoming`. Unlinked: unchanged `not_tracked`. |
| A5 | Agent status "Inactive" (S4) | Linked organization `suspended` or `rejected` → `Inactive`. Otherwise linked/pending → `Onboarding` until Active Agent is done → `Active`. No link and no request → the stored-stage mapping (unchanged). |
| A6 | Commission (NEEDS_CONFIRMATION from bdm-003 P10) | **Not exposed.** No commission or money figure reaches any BDM route. Once linked, the profile note reads "Commission: Not shown to BDMs (awaiting a decision)". Stays NEEDS_CONFIRMATION (bdm-022 / owner). |
| A7 | What a BDM sees of the agency | Name, code, status label, whether a Master exists, active staff count, and the three aggregate counts. **No member names/emails, no student, application or document rows** (AC4). |
| A8 | Notices | In-app only (bdm-018 H7). Active `overseas_admin` users get "Agent onboarding requested" (link `/overseas/admin/agents`); the assigned BDM gets "Agent onboarded" or "Agent onboarding not approved" with the reason. |
| A9 | Linking a rejected or suspended agency | Allowed; the pipeline then shows Inactive (backlog edge case "the org is suspended"). An agency already linked to another BDM organization → 409 `agent_org_linked` (1:1, AC2). |
| A10 | No unlink; no change to T-A6 (bdm-014) / M-15 (bdm-015) "Not tracked" | Out of scope; logged as follow-ups. |

## 2. Scope

**In:** widen the request `kind` to `agent`; the link column; the agent request rule; the queue `kind` filter; `link-agent`; reject for both kinds; the live Agent stages, volume counts and Inactive status; the BDM card for Agent organizations; the admin agent queue on the Agents page; the agent profile's live staff count and commission note.

**Out:** creating agencies from a request; unlinking; commission/revenue (bdm-022); T-A6 / M-15 counts.

## 3. Data — migration `0098_bdm_agent_link` (additive + CHECK widening)

- `bdm_organizations.agent_org_id` uuid NULL FK `agent_orgs.id` RESTRICT, unique `uq_bdm_organizations_agent_org`.
- `bdm_onboarding_requests.agent_org_id` uuid NULL FK `agent_orgs.id` RESTRICT.
- CHECKs replaced (model `BDM_ONBOARDING_CHECKS` and the migration keep identical strings):
  - `ck_bdm_onboarding_requests_kind`: `kind IN ('school', 'agent')`
  - `ck_bdm_onboarding_requests_completed`: `status <> 'completed' OR (resolution IS NOT NULL AND (school_id IS NOT NULL OR agent_org_id IS NOT NULL))`
  - new `ck_bdm_onboarding_requests_target`: `(kind = 'school' AND agent_org_id IS NULL) OR (kind = 'agent' AND school_id IS NULL)`
- No row is written. Every existing row is `kind = 'school'` with a NULL `agent_org_id`, so the new CHECKs hold. Downgrade refuses while any agent request or agent link exists, then restores the 0084 strings.

## 4. API (all writes are one transaction with audit and notice; lock order organization → request → agent org)

1. `POST /bdm/organizations/{id}/onboarding-request` — unchanged route and body. Order: 404 scope → `require(can_edit)` → type: `college` 422 "Onboarding requests are for School or Agent organizations" → Lost 409 → linked 409 `already_linked` (message per kind) → pending 409 → School: MoU 422 (unchanged); Agent: stage 422 (A2). Inserts `kind = bdm_type`.
2. `GET /overseas-admin/bdm-onboarding-requests?kind=school|agent` (default `school`, so bdm-018 callers are unchanged). Items gain `kind` and `agent_org {id,name,prefix,status} | null`.
3. `POST …/{id}/reject` — both kinds; the notice wording follows the kind.
4. `POST …/{id}/link` (School ID) and `POST /overseas-admin/schools` with `bdm_onboarding_request_id` refuse an agent request: 422 "This request is for an Agent organization".
5. **New** `POST /overseas-admin/bdm-onboarding-requests/{id}/link-agent` `{agent_code: 1–8}` → 200 item. 403 non-admin; 404 unknown; 422 a School request; 409 `request_resolved`; 409 `already_linked`; 422 "No agent organization has that code"; 409 `agent_org_linked`. Audit `bdm_onboarding_request.linked` with `agent_org_id`.
6. `BdmOrganizationOut.onboarding` — now also for Agent organizations: `{request, school: null, agent: {name, prefix, status, master_login: bool, staff_count, counts: {students, applications, enrollments}} | null, can_request}`.
7. `pipeline.steps[].count: int | null` (additive); `agent_status` per A5.

Unchanged: the AGN-001 approve/reject/suspend/reinstate routes, `/overseas-admin/agent-orgs/*`, every `/agent/*` route, the stage-move route (live/volume keys still 422).

## 5. Frontend

- `BdmOrganizationOnboarding` renders for Agent organizations too ("Agent onboarding"): Linked (agency name, code, status, Master login, staff), Pending, Rejected, None (hint "Available once the agreement is signed").
- `AdminSchoolOnboardingRequests` takes a `kind`; for `agent` it shows "Agent onboarding requests", hides "Use for new school", and links by "Agent code". Mounted above `AgentApprovalPanel` on `/overseas/admin/agents`.
- `BdmOrganizationPipeline` shows a volume step's count ("Students · 12").
- `BdmOrganizationProfileDetails`: when linked, "Number of staff" shows the live count with the entered value kept; the commission note per A6.

## 6. Security

- BDM routes: `load_scoped` (404 out of scope) + `can_edit`. Admin routes: `overseas_admin`/`super_admin` (403).
- AC4 (tested): the detail response carries aggregates only; a BDM gets 403 on `/overseas-admin/agent-orgs/{id}/students|applications` and on `/agent/students`, and 404 on any `/bdm/organizations/{id}/students`-style path; a linked agency's student name never appears in any BDM response.
- `agent_code` is a trimmed, upper-cased equality lookup; lengths capped by Pydantic.

## 7. Tests

Backend `tests/test_bdm_019_*.py`: migration (round trip, CHECKs, downgrade refusal); request rules per kind and order; queue kind filter (default school-only); link-agent (all refusals, 1:1 race via the unique constraint); reject notice; live steps, counts and Inactive; AC4 PII. Reruns: all `test_bdm_018_*`, `test_bdm_004_*`, `test_agn_001_*`, `test_agn_022_*`; `test_bdm_018_migration` is updated only where 0084's frozen strings now differ from the model (schema evolution, not behavior).

Web (vitest): card agent states; queue agent mode (no "Use for new school", link by code); pipeline counts; profile staff/commission. Playwright: BDM requests → admin links the agency → BDM sees Agent Onboarding and Master Login Created done.

## 8. Risks

- bdm-018 queue: the `kind` default keeps it school-only; tested.
- `organization_out` adds queries for Agent organizations only (detail view; ≤ 4 statements).
- AGN-001 approval path: not modified; its tests rerun.
