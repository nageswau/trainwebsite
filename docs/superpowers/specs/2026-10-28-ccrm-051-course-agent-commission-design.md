# ccrm-051 — Course-level agent-Master commission (overrides the university)

Source: `docs/delivery/COUNSELOR_CRM_BACKLOG_2.md` §ccrm-051 (owner answers Q5/Q6, A8). Decision: DEC-SCOPE-327. Depends on ccrm-050
(merged, PR #390). Builds on dtu-001 (DEC-SCOPE-209) and ccrm-050 (DEC-SCOPE-323).

## Intent

The owner wants the agent-Master commission (what EduSphere pays an agent Master) settable per course as well as per university, with
the course value overriding the university value. The agent Master sees, per course, the commission that actually applies and where it
comes from.

## Goals

- Super Admin / Overseas Admin set, change and clear an agent-Master commission on the Add / Edit course form.
- The agent Master's Partner University detail shows, per course, the **effective** commission: the course's if set, else the
  university's, labelled "(course)" / "(university)"; "—" when neither is set.
- Every change is audited with before/after (same rule as the university value, DEC-SCOPE-209 §6).

## Non-goals / anti-goals

- No change to U2's course `commission_*` (university → EduSphere) or to who sees it. The two figures are never mixed.
- No exposure on public catalogue endpoints, to agent staff, to partnership roles, counselors or students.
- No change to the university-level card / form (ccrm-050), the dtu-001 loader or the course CSV import.

## Design

**Database** — migration `0217_course_agent_commission`: `overseas_courses.agent_commission_percent NUMERIC(5,2)`, `_amount
NUMERIC(12,2)`, `_currency VARCHAR(3)`, `_note VARCHAR(300)`, all nullable, no backfill; four CHECKs mirroring the university ones
(`ck_overseas_courses_agent_commission_{one,percent,amount,currency}`), kept as their own model constant
`COURSE_AGENT_COMMISSION_CHECKS` (COURSE_CHECKS is pinned by an older migration test). Guarded upgrade (0001 builds fresh DBs from
models). Downgrade refuses while any course agent commission exists (0157's rule: never silently drop commercial data).

**API** — `CourseIn` / `CourseUpdate` gain `agent_commission: AgentCommissionIn | None` (the university's input type: percent XOR
amount+currency, note ≤ 300; 422 otherwise). Semantics as ccrm-050: omitted = unchanged, null = clear, object = set. Anyone but
`can_edit_agent_commission` (super_admin; overseas_admin in the overseas division) sending the key — even null — gets 403 *before any
write*, after the existing read/write gates. Saved in the course write's transaction; the audit row `university_course.agent_commission`
stores `{university_id, before, after}`; the course create/update audit `fields` never names it. Log events carry ids only.

Course payloads (`course_out`) carry `agent_commission` only for `can_view_agent_commission` callers (editors; agent Masters never reach
these partnership routes). `GET .../agent/crm/partner-universities/{id}` courses carry `agent_commission_effective`
(`{percent, amount, currency, note, source: "course"|"university"} | null`) only for viewers (the Master); staff get no key.

**Web** — `CourseForm` gets `canEditAgentCommission`; when true it shows an "Agent Master commission" fieldset reusing
`AgentCommissionFields` / `agentCommissionDraft` / `agentCommissionBody` (ccrm-050). `AgentCommissionFields` gains an `idPrefix` so the
university page's card and an open course form never share ids or a radio group. On create the key is sent only when a rate is entered;
on edit only when the value changed (blank = null = clear). `UniversityCourses` shows an "Agent Master commission" fact when the API sent
the key. The agent panel's course table gains an "Agent commission" column for a Master when any course carries the key.

**Calls (mine, NEEDS_CONFIRMATION with the owner):** 403 (not ignore) for a non-editor sending the key; downgrade refuses while data
exists; the effective value carries the source's note; a course on an inactive university keeps the existing 409.

## Acceptance criteria → tests

| AC | Test |
|---|---|
| AC1 course 12% overrides university 10% for the Master | pytest `test_ac1_*`, panel vitest, e2e |
| AC2 course unset → 10% "(university)"; neither → "—" | pytest `test_ac2_*`, panel vitest |
| AC3 public course APIs never include it | pytest `test_ac3_*` + upc-033 sweep |
| AC4 partnership roles never see it; sending it is 403 | pytest `test_ac4_*`, CourseForm vitest |
| AC5 audit on change (before/after), none when unchanged | pytest `test_ac5_*` |
| AC6 migration up/down; down refuses with data | pytest `test_ccrm_051_migration` |

## Plan

1. Model columns + checks; migration 0217 + migration test (RED → GREEN).
2. Schemas + access helpers (`agent_commission_out` for courses, `effective_agent_commission`).
3. Course routes: gate, apply + audit; `course_out` viewer key (pytest RED → GREEN).
4. Partner-universities detail: effective value per course (pytest).
5. Web: `AgentCommissionFields` idPrefix; `CourseForm` fieldset; `UniversityCourses` fact + page prop; panel column; types (vitest).
6. Playwright e2e: admin sets 12% on a course → Master sees 12% (course) and another course 10% (university).
7. Docs: decision register, API contract, RBAC matrix, RTM, backlog status.
