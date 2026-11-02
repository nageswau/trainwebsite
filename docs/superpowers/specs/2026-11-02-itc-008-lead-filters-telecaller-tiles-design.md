# itc-008 — Lead list filters and telecaller dashboard tiles (design)

- **Requirement:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` `itc-008` (PDF §11 lead list, §8 telecaller dashboard, §12 AC10;
  Appendix B "Contact rate"). Source classification `UNVERIFIED`; the owner approved building the backlog in waves (backlog Q-01).
- **Dependencies:** none (backlog). No migration, no RBAC change, no new route.
- **Calls below marked (B) are builder defaults — `NEEDS_CONFIRMATION`** (the session was run "proceed with recommended answers").

## Intent

A telecaller (and their manager) can narrow the lead list by where a lead came from and by when it was last contacted / is next due,
and the telecaller dashboard shows three more figures for today — contact rate, qualified leads and handovers — that agree with the
manager's Telecaller Report for the same day.

## Existing behaviour (verified on `main@1d6d37de`)

- `GET /api/v1/telecaller/leads` (+ `.xlsx`) filters: status, priority, product, campaign, follow_up (today/overdue), owner, created
  range, `q` (`api/telecaller.py::_lead_query`). The admin list already has `source`. The Excel twin already computes **Last contact**
  (latest `LeadCall.occurred_at` / `LeadMessage.sent_at`) and **Next follow-up** (earliest open `LeadFollowUp.due_at`) in
  `services/lead_list.py::table`. The on-screen telecaller table shows neither column (the backlog text says it does; it does not).
- Dashboard tiles B1–B10: `services/telecaller_metrics.py::tiles`, labels in `web/lib/telecallerMetrics.ts::TILES`.
- Telecaller Report (`telecaller_reports.ACTIVITY`) = `flow_counts_by_user` over the range — the same counts the tiles use.

## Decisions

- **F1 — Source filter** `source=<TEL_SOURCES key>` on the telecaller list and its Excel twin; an unknown key is 422 (typed Literal,
  as the admin list).
- **F2 — Last-contact range** `last_contact_from` / `last_contact_to` (YYYY-MM-DD, IST days, inclusive). "Last contact" = the later of
  the lead's latest logged call and latest message — the Excel column's definition. A lead never contacted matches no range. (B)
- **F3 — Next-follow-up range** `next_follow_up_from` / `next_follow_up_to`: the earliest **open** follow-up's due time (any author) —
  the Excel column's definition. "Next follow-up = tomorrow" is from = to = tomorrow. (B)
- **F4 —** each range: from > to → **422** with the existing `DATE_ORDER` sentence; a malformed date → FastAPI 422. Every filter is
  ANDed with the caller's scope (T23), so it can only narrow. The Excel audit row names the new filters (values are dates/keys, no PII).
- **F5 — Web:** a Source select and two date-range pairs on My Leads / Team leads; all live in the URL (refresh/back keep them);
  a reversed pair shows the existing "Choose a start date on or before the end date." without calling the API. `LeadCreatedRange` is
  generalised to take its two keys and labels (default: created), so all three ranges share one component.
- **T1 — Contact rate (today)** = distinct leads the telecaller called today with ≥1 *connected* call ÷ distinct leads they called
  today, as a % to one decimal; no calls → `null`, shown "—". "Connected" = outcome not in `NOT_CONNECTED` (tel-021 D2; there is no
  literal `connected` outcome). Computed inside the existing calls query (no extra statement).
- **T2 — Qualified (today)** = tel-021 D11 `qualified_leads` (stage moves to Qualified by the telecaller today) — the report's existing
  "Qualified" column, so the two agree. Appendix B's "(or later)" wording is not adopted, to keep one definition. (B)
- **T3 — Handovers (today)** = `lead.handover` audit rows whose actor is the telecaller, today (a manager's handover is credited to the
  manager, as every other flow count is by actor). (B)
- **R1 — Telecaller Report** appends `contact_rate` "Contact rate (%)" and `handovers` "Handovers" (existing columns untouched). Each
  row's rate is its own; the Total row's rate is Σconnected-leads ÷ Σcalled-leads over the rows, never a sum of rates.
- Tile API keys are additive: `contact_rate`, `qualified`, `handovers`. The dashboard keeps a fixed statement count (+1 grouped
  handover query per `flow_counts` call).

## Non-goals

Showing Last contact / Next follow-up columns in the on-screen table; the admin list's new filters; changing tel-021 definitions;
the counselor or manager dashboards (itc-030/032).

## Plan (TDD, focused tests)

1. API RED → GREEN: `tests/test_itc_008_lead_filters.py` — source, last-contact range, next-follow-up range (incl. tomorrow, IST edge,
   never-contacted, reversed → 422, unknown source → 422, scope still applies, Excel audit names them).
2. API RED → GREEN: `tests/test_itc_008_tiles.py` — the three tile values on fixtures; tiles == Telecaller Report row for today
   (AC2); Total contact rate from sums; dashboard route returns the keys.
3. Web RED → GREEN: `TelecallerLeadTable.test.tsx` (URL round-trip of the new filters, reversed pair), `TelecallerDashboard.test.tsx`
   (13 tiles, "—" for null rate), `LeadCreatedRange` defaults unchanged.
4. e2e `itc-008-lead-filters-tiles.spec.ts`: filters round-trip through the URL; tiles visible.
5. Docs: DEC-SCOPE, API addendum, RTM, backlog "Built" line — written after merging main (numbers taken then).

## Regression risks

`test_tel_021_*`, `test_tel_024_reports.py`, `test_nehn_013_crm_reports.py`, `test_tel_023_performance.py`, `test_mgmt_019_telecalling.py`
(flow_counts consumers — additive keys only); `TelecallerDashboard.test.tsx` pins the ten tile labels (updated: 13, new ones appended);
admin `LeadCreatedRange` use (defaults keep it identical).
