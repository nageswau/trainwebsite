# pob-009 — PO targets, territories, daily plans and daily/weekly reports (design)

Source: `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` pob-009 (§4 "Create daily activity plans and daily/weekly reports";
"Track outreach volume, response rate, meetings, requirements generated, vendor registrations and active accounts"; "Allow the manager to
assign target companies, territories and monthly activity targets") and Appendix B. Dependencies pob-004, pob-007, pob-010 are built
(DEC-SCOPE-411/417, 422, 420). The user asked the session to proceed on recommended answers, so every T-rule below is the **builder's call**
(`NEEDS_CONFIRMATION`).

## Intent
A Placement Officer (PO) sees monthly targets against live actuals, plans the day from due follow-ups and target companies, and submits a
daily and a weekly report (auto-computed counts + notes) to their Team Lead. The Team Lead sets targets, territories and target-company lists
and reads the team's reports. **Anti-goals:** a second, disagreeing count source (every figure comes from one `recruiter_metrics` function);
changing company ownership through target lists; touching rec-033/034 figures.

## Rules (builder's calls)
- **T1 Roles.** PO = `placement_team` (own data only, `recruiter_context`). Team Lead = `placement_manager` (direct reports, `team_filter`;
  a PO outside the team is 404). `super_admin` = every PO. Every other role 403; anonymous 401.
- **T2 KPIs** (credited to the person who did the work, IST half-open period):
  `outreach` = contact messages sent (email, WhatsApp, LinkedIn; `company_id` set) + outgoing contact calls;
  `responses` = distinct contacts reached by the PO in the period that have a reply logged (`replied_at`) in the period on a message the PO sent;
  `response_rate` = responses ÷ contacts reached (whole %; none when 0 reached) — not a target KPI;
  `meetings` = meetings completed by the PO; `requirements` = requirements created by the PO;
  `vendor_registrations` = vendor onboarding moves to `approved` made by the PO;
  `active_accounts` = a snapshot *now*: non-archived companies assigned to the PO with client status `active_client`/`repeat_business` and
  ≥1 open requirement; `placements` = offers joined in the period whose "joined" was recorded by the PO.
  All in one `recruiter_metrics.po_counts(db, user_ids, start, end)` statement for any number of POs (fixed query count).
- **T3 Targets.** `recruiter_targets(recruiter_user_id, month, kpi_key, target 0..100000)`, unique per PO/month/KPI. The Team Lead batch-saves
  (null clears). Editable: current month and 12 ahead; past months only by super_admin (bdm-016's rules reused). A mid-month change is an
  upsert audited with from/to; actuals are never stored, so % follows at once. Actual is none for a future month.
- **T4 Territory.** Free text (≤120) on `companies.territory` (company create/edit form, list filter `?territory=`, case-insensitive) and on
  `recruiter_profiles.territory` (set by the Team Lead on the PO's target page).
- **T5 Target companies.** `recruiter_target_companies(recruiter_user_id, company_id, month)`, unique. The Team Lead adds a batch by ids or by
  territory (every client, non-archived company in the Team Lead's company scope with that territory, at most 200) and removes one. Ownership
  (`assigned_recruiter_user_id`) is untouched. A company outside the Team Lead's scope is 404.
- **T6 Daily plan.** `recruiter_plan_items(recruiter_user_id, plan_date, follow_up_id | company_id, done_at)`. Only today's (IST) plan is
  editable; earlier days are read-only. Suggestions: the PO's open follow-ups due by the end of today, and this month's target companies
  not yet in the plan. Add / mark done / undo / remove. At most 50 items.
- **T7 Reports.** `recruiter_activity_reports(recruiter_user_id, period daily|weekly, period_start, counts JSON, note ≤2000, submitted_at)`,
  unique per PO/period/start. A week is Monday–Sunday IST (`period_start` must be a Monday, else 422). A period that has not started is 422.
  Before submission the counts are live; submit freezes them (plus daily plan planned/done for a daily report). A second submit is 409.
  No Team Lead comment (BDM's comment is not in pob-009's text).
- **T8 Drill-down (AC1).** `GET /recruiter/activity-contacts` lists the contacts reached in a period with outreach count and replied flag;
  `replied ÷ rows` equals the report's response rate.

## API (prefix `/api/v1/recruiter`)
`GET /targets?month`, `GET /manager/targets?month`, `GET /manager/targets/{user}?month`, `PUT /manager/targets`,
`PUT /manager/team/{user}/territory`, `POST /manager/target-companies`, `DELETE /manager/target-companies/{id}`,
`GET /daily-plan`, `POST /daily-plan/items`, `PATCH /daily-plan/items/{id}`, `DELETE /daily-plan/items/{id}`,
`GET /activity-reports/{period}/{start}`, `POST /activity-reports/{period}/{start}/submit`, `GET /activity-contacts?period&start&recruiter_id`,
`GET /manager/activity-reports?period&start`, `GET /manager/activity-reports/{user}/{period}/{start}`.

## UI
PO: **My Targets** (`/recruiter/targets`), **Daily Plan** (`/recruiter/daily-plan`), **Activity Reports** (`/recruiter/activity-reports`).
Team Lead: **Targets** (`/recruiter/manager/targets`, team table actual/target; `/recruiter/manager/targets/[userId]` edit sheet, territory,
target companies) and **Activity Reports** (`/recruiter/manager/activity-reports`, team status grid, report view with drill-down).
Company form gets a Territory field. Loading, empty and error states follow the existing recruiter pages.

## AC
1. Response rate = replies ÷ contacts reached, equal to the drill-down. 2. Target vs actual shown (PO and Team Lead). 3. Weekly report covers
Mon–Sun IST. +E: a mid-month target change takes effect immediately and is audited.
