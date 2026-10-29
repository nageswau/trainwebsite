# ccrm-050 — Agent-Master commission on the Add/Edit University form (design)

Source: `docs/delivery/COUNSELOR_CRM_BACKLOG_2.md` `ccrm-050` (owner lines A8, A9; answer Q5). Evidence class
`MEETING_TRANSCRIPT_REQUEST`-equivalent. The owner pre-authorised recommended answers; every builder's call below is `NEEDS_CONFIRMATION`.

## Intent

Today the dtu-001 agent-Master commission (what EduSphere pays an agent Master per university) can only be set from the
`AgentCommissionCard` on the university detail page, after the university exists. The owner wants it on the Add/Edit University form,
visible only to the people who set it (Super Admin, Overseas Admin) and, as today, readable only by an agent Master.

## Goals / non-goals

- Goal: an "Agent Master commission" fieldset (percent **or** amount + currency, optional note) on `UniversityForm`, create and edit,
  prefilled on edit, for `AGENT_COMMISSION_EDITORS` only.
- Goal: the API accepts an optional `agent_commission` object on `POST /partnership/universities` and `PATCH /partnership/universities/{id}`.
- Non-goal: course-level commission (ccrm-051), any change to who **views** the commission, the agent Partner Universities view, U2
  `commission_*` (university → EduSphere), migrations.
- Anti-goal: the value ever reaching a non-viewer (partnership manager / head, agent staff, public).

## Decisions (builder's calls, `NEEDS_CONFIRMATION`)

- **D1 one request, one transaction.** On create the commission columns are set on the inserted row and audited in the same commit (no
  follow-up PUT, so no "created without its commission" half state).
- **D2 refusal.** If the body carries the `agent_commission` key at all (even `null`) and the caller cannot edit agent commission
  (`can_edit_agent_commission`), the request is **403** "Only a super admin or an overseas admin can change the agent commission" before any
  write; nothing is created or changed.
- **D3 PATCH semantics.** Omitted = unchanged; an object = set (same `AgentCommissionIn` validation: one of percent/amount, amount needs a
  currency → 422); `null` = clear (same as `DELETE .../agent-commission`). On create, `null`/omitted = no commission.
- **D4 audit.** A change writes the existing `university.agent_commission` audit row with `{before, after}` (dtu-001 §6) and the existing
  structured log events; an unchanged value writes nothing. The create audit's `fields` list does not include `agent_commission`.
- **D5 inactive.** Unchanged: `PATCH` on an inactive university is already 409 (UM10), so the commission cannot change there either.
- **D6 UI gate.** The page passes `canEditAgentCommission`: add page `AGENT_COMMISSION_EDITORS.has(role)`; edit page the same **and** the
  API sent the `agent_commission` key (so an overseas_admin outside the overseas division never sees it). The form sends the key only when
  the fieldset is shown; blank rate on edit = clear.
- **D7 reuse.** The radio + percent / amount + currency + note inputs and their client checks move into a shared
  `AgentCommissionFields` + `agentCommissionBody()`; `AgentCommissionCard` uses them unchanged in look and ids.

## Acceptance criteria (from the backlog)

- AC1 Overseas Admin creates a university with 10% → stored + audited (`university.agent_commission`, before null, after 10.00).
- AC2 Partnership manager never sees the fieldset; the API rejects the field (403) on create and edit.
- AC3 Agent Master sees 10% in Partner Universities after publish.
- AC4 Agent staff never see it.
- EDGE both percent and amount → 422; inactive → 409 kept; edit prefills; blank on edit clears (audited).

## Plan (TDD, focused tests)

1. RED/GREEN backend `tests/test_ccrm_050_form_commission.py`: AC1–AC4, D2 (null too), D3 (set / unchanged no audit / clear), 422, 409.
   Change `UniversityCreate`/`UniversityUpdate` (+ `agent_commission: AgentCommissionIn | None = None`) and the two routes.
2. RED/GREEN web: `UniversityForm.test.tsx` cases (hidden without prop; shown + sends percent on create; prefilled; blank clears; amount
   without currency is a client error) and `AgentCommissionCard.test.tsx` stays green after the extraction.
3. Pages pass the prop. e2e `ccrm-050-university-form-commission.spec.ts`.
4. Docs: DEC-SCOPE, API §, RTM, backlog status.

Regression set: `test_dtu_001_*`, `test_upc_003_universities.py`, `test_upc_004_duplicates.py`, `test_upc_033_commission_sweep.py`,
`UniversityForm.test.tsx`, `AgentCommissionCard.test.tsx`.
