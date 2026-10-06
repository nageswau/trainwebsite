# tel-008 — Telecaller lead workspace: My Leads, lead detail, priority (design)

Backlog: `docs/delivery/TELECALLER_CRM_BACKLOG.md` tel-008 (EVID-019 §2 field display, §8 priority L314–L330, §22 "View assigned leads";
`DEC-SCOPE-073` T19, T23). Dependencies tel-003 (PR #75) and tel-004 (PR #81) are merged. Branch `feature/tel-008` from `main` @ `3986958c`.
Decision: `DEC-SCOPE-084`. **No migration** (the tel-003 indexes and the AGN-015 `ix_audit_logs_entity` index serve every read). API contract §12J.

## 1. Owner answer (2026-10-06, `EXPLICIT_APPROVAL`) and recorded defaults

| # | Question | Answer |
|---|---|---|
| W1 (AC3) | Where does a priority change "appear on the timeline" before tel-015 exists? | **An audit row and an Activity list on the detail page.** Each change writes `audit_logs` `lead.priority_change` `{from, to}` in the same transaction. The detail page shows an Activity list that merges stage history and priority changes, newest first, from `GET /telecaller/leads/{id}/timeline`. tel-015 adds its sources to the same endpoint |
| D1 (default) | What "handed over" means before tel-018 | `owner_id IS NOT NULL`. It is the assigned counselor (tel-003 Appendix A L56 and the CNS-001 meaning). A **telecaller's** writes on such a lead are refused with 403: the PATCH and the tel-004 stage move. Managers and `super_admin` keep write access. The read returns `read_only` for the caller, and the page shows a "with the counselor" notice with no edit controls (T19, AC4) |
| D2 (default) | Editable fields (`PATCH`) | Contact fields `name`, `email` (required, valid), `phone`, `whatsapp_number`, `city` and `state`, plus `product_id` (an active product, or null; Appendix A L100) and `priority`. Every other key is a 422: `telecaller_user_id`, `owner_id`, `status`, `source`, `campaign_id` and the qualification fields (tel-009). The duplicate check on a changed phone or email is tel-005's (T12) |
| D3 (default) | List filters | `status` (stage), `priority`, `product_id`, `campaign_id` and `q` (Lead ID, name, phone, WhatsApp, email). "Due follow-up" arrives with tel-011's follow-ups, because nothing to filter on exists yet. The list is newest first, 50 rows per page, and `limit` is at most 100 |
| D4 (default) | Action buttons | Only the ones that work today: **Call** (a `tel:` link, T7; logging is tel-010) and **Change stage** (tel-004 D4). WhatsApp, email, follow-up, booking and Assign to counselor arrive with tel-013, tel-014, tel-011, tel-016 and tel-018. There are no placeholder buttons |
| D5 (default) | Manager view | Managers use `/telecaller/manager/leads` and `/telecaller/manager/leads/{id}`, with the same components plus a Telecaller column. Scope is `lead_pipeline.scope`: direct reports' leads plus their teams' unassigned queue (T23). `super_admin` sees all |
| D6 (default) | tel-012 C2 | **Script panel built here** once tel-012 merged (`DEC-SCOPE-083`): the active call script of the lead's product, from tel-012's `GET /telecaller/scripts?product_id=&active=true&limit=1`, re-read when the product changes. Its states are no product, loading, none and failed. `GET /telecaller/leads/{id}/render` goes to tel-013 (backlog) |

## 2. API (`app/api/telecaller.py`)

Scope for every route comes from `lead_pipeline.scope(user)`. Other roles get 403. A lead outside scope, or one that doesn't exist, is 404
(IDOR: every `{id}` is read with the scope filters in the WHERE).

| Route | Behaviour |
|---|---|
| `GET /telecaller/leads` | `{items, total, limit, offset}`. Each item is `bdm_leads.admin_out` (the admin row shape) plus `read_only`. Filters are ANDed with scope, so they can only narrow it. `priority` is a Literal (anything else is 422) |
| `GET /telecaller/leads/{id}` | The same row plus `message` (the enquiry text) and `read_only` |
| `PATCH /telecaller/leads/{id}` | `TelecallerLeadUpdate` (extra keys 422). The row is locked `FOR UPDATE` with the scope filters, so a lead reassigned while the page was open is 404. A telecaller on a handed-over lead gets 403. Changed values only. A priority change writes the `lead.priority_change` audit `{from, to}`; a contact change writes `lead.contact_update` `{fields}` (field names only, never values). Nothing changed means no audit. Returns the detail |
| `GET /telecaller/leads/{id}/timeline` | `{items, total, limit, offset}`, newest first: `UNION ALL` of `lead_stage_history` (kind `stage`) and the lead's `lead.priority_change` audit rows (kind `priority`). Item `{id, kind, at, actor {id, full_name} or null, from_value, from_label, to_value, to_label, reason}` |
| `POST /telecaller/leads/{id}/stage` (tel-004) | Gains D1: a telecaller on a handed-over lead gets 403 |

## 3. Web

- `lib/telecallerLeads.ts`: types, URLs, `PRIORITY_LABEL` and the §8 help text (Hot "Ready to join / immediate requirement.", Warm
  "Interested but needs follow-up.", Cold "Long-term / low interest.").
- `components/TelecallerLeadTable.tsx` (client): search, filters, page and URL state, the admin panel idiom (refresh and Back keep the place).
  It has loading, empty, filtered-empty and error-with-retry states. Each name links to the detail page.
- `components/LeadDetailPanel.tsx` (client): the §2 fields, the stage with its control, the priority control (radio group with help text),
  the contact edit form, Call, and the Activity list. Read-only renders the notice and no controls.
- `AdminLeadStage.LeadStageControl` gains an optional `move` prop (the telecaller route's body is `{to_stage, reason}`) and `canReopen`.
  The admin keeps its defaults.
- Pages: `/telecaller/leads`, `/telecaller/leads/[id]`, `/telecaller/manager/leads` and `/telecaller/manager/leads/[id]`. The nav gets
  "My Leads" (telecaller) and "Leads" (manager).

## 4. Acceptance criteria (testable)

1. A telecaller's list holds only leads with `telecaller_user_id = me`. A manager's list holds reports' leads plus the teams' queue.
2. Another telecaller's lead id (GET, PATCH, timeline) is 404, a random id is 404, and other roles get 403.
3. A priority change is saved, writes `lead.priority_change {from,to}`, and is listed on the timeline (and in the page's Activity list).
4. A handed-over lead (`owner_id` set) reads with `read_only: true`. Telecaller PATCH and stage are 403, and the page shows no edit controls.
5. PATCH `telecaller_user_id` / `status` / `owner_id` gives 422. An invalid email or priority gives 422. An inactive product gives 422.
6. Filters narrow (stage, priority, product, campaign, q). Pagination totals are exact.

## 5. Risks

Generalising `LeadStageControl` touches the admin panel, so tel-004's vitest and e2e run again. The D1 guard on the tel-004 stage route
changes behaviour only for leads with `owner_id` set. The priority change and the audit row commit together.
