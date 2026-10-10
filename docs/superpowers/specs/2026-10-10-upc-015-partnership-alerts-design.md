# upc-015 — Partnership alerts engine (design)

**Feature:** upc-015 · **Decision:** DEC-SCOPE-162 · **API:** §12CD · **RBAC:** §2.88 · **Migration:** none
**Evidence:** `EVID-020` §14 (L499–L513: 90 / 60 / 30 / 7 days before expiry; "⚠️ ABC University partnership expires in 30 days. Renewal
action required."), §6 (L242: "automatically highlight delayed milestones"), §20 (L673–L693: Overdue band), §32 ("🔔 Alerts");
`UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §3.1 U11 (`EXPLICIT_APPROVAL` 2026-10-08: in-app + email, daily IST beat, once each by dedupe key,
to the primary manager + backup/head per kind), Q-11, Q-17 and §4 upc-015.
**Status:** AL1–AL14 (including Q-17) are recommended answers applied under the owner's standing instruction for the build session
("proceed with the recommended answers; ask only if genuinely blocking"). **Not** separately confirmed: `NEEDS_CONFIRMATION` at sign-off.
**Dependencies (merged):** upc-008 (milestones, DEC-SCOPE-143), upc-014 (agreements, DEC-SCOPE-142), upc-020 (tasks, DEC-SCOPE-141).

## 1. Intent

Partnership managers must not miss an agreement expiry, a slipped milestone or overdue follow-ups. The system tells them once, in the app
and by email, and keeps a list they can come back to.

## 2. Decisions

| # | Question | Answer |
|---|---|---|
| AL1 | Storage (backlog: "`partnership_alert_log` or reuse dedupe keys") | **Reuse `notifications`.** Each alert is one notification per recipient with `dedupe_key = upc015:<kind>:…`; the partial unique index is the "sent" record (bdm-012 R1). No new table, no migration |
| AL2 | Kinds | `agreement_expiry`, `milestone_delayed`, `overdue_digest` |
| AL3 | Schedule (Q-17 send hour) | Beat `crontab(minute=30)` UTC = every IST hour on the hour; the service acts only from **09:00 IST** (U11 "IST morning"). Later runs that day are no-ops (dedupe), and a worker restart during the day still sends that day's alerts |
| AL4 | Expiry thresholds | An agreement whose stored status is `signed` or `active` (upc-014 AG4: renewed rows are excluded) on an **active** university, with `expiry_date − today (IST)` **exactly** 90, 60, 30 or 7. One alert per (agreement, threshold, recipient). An agreement signed already inside 30 days therefore gets only the thresholds still ahead (the backlog edge case); an expired one gets none |
| AL5 | Expiry text | Title "Agreement expires in N days". Body starts with the source sentence exactly: "⚠️ {University} partnership expires in {N} days. Renewal action required." then "{MOU-number} ({type}) expires on {DD Mon YYYY}." Link: the university's Agreements section |
| AL6 | Milestone "newly delayed" | upc-008's own status rule (`partnership_milestones._items`, Q-11 MS3: not achieved, manual or derived, and target before today). Newly = the target date is between today−7 and yesterday (a 7-day catch-up, and older delays never flood the first run, tel-020 AL10). One alert per (milestone row, target date, recipient); moving the target re-arms it |
| AL7 | Milestone text | Title "Milestone delayed". Body "{University}: the {Milestone} milestone was due on {date} and is not complete." Link: the university's Partnership timeline |
| AL8 | Overdue digest | Once per IST day per assignee with at least one open partnership task (follow-up or task, upc-020 TK13 "overdue" = open and due before today): "You have N overdue follow-ups or tasks. The oldest was due on {date}." Link `/partnership/tasks?band=overdue` |
| AL9 | Q-17 recipients | Expiry: active primary manager, active backup manager, and the primary manager's active reporting head. Milestone: active primary + backup. Digest: the active assignee. A user appears once per alert; nobody active → counted `skipped`, logged with ids |
| AL10 | Channels | In-app + email (U11). Email over SMTP through the existing outbox (`queue_deliveries`, context kind `partnership_alert`, rendered like bdm-012's reminder with one link); WhatsApp / SMS never |
| AL11 | Failure handling | Each alert in its own savepoint; a failure is counted and logged (ids only), never stops the run; commit per chunk of 200 rows |
| AL12 | `GET /partnership/alerts` | The caller's **own** alerts only (recipients only), newest first, `kind` filter (`all` default, else one of AL2; other values 422), `limit` 1–100 (25), `offset`; returns `items`, `total`, `unread`. Readers: partnership_manager (with a profile), partnership_head, super_admin (who receives none: an empty list); every other role 403 |
| AL13 | Read state | The existing `PATCH /workflows/notifications/{id}/read` (the list opens an unread alert after marking it read) |
| AL14 | UI | Page `/partnership/alerts` (§32 "Alerts" goes live for managers; heads gain it in their nav), kind tabs, the shared notification list. The unread count is the Alerts entry's badge on the Alerts page, the manager dashboard and the head's team page |

## 3. Components

- `app/services/partnership_alerts.py` — `send_partnership_alerts(db, *, now)` (three passes + counts log), `run_partnership_alerts()`,
  and the list query `page(db, user, kind, limit, offset)`. Reuses `bdm_reminders._chunks / clean / INDIA` and
  `partnership_milestones._rows / _derived / _items`.
- `app/api/partnership_alerts.py` — `GET /partnership/alerts`.
- `app/worker.py` — `send_partnership_alerts_task` + `upc015-alerts` beat entry.
- `app/notifications/delivery.py` — `partnership_alert` joins the bdm/tel SMTP email branch.
- Web: `lib/partnershipAlerts.ts`, `app/partnership/alerts/page.tsx`, nav (`navigation.ts`), badge on the dashboard and head team page.

## 4. Data flow

beat → task → service: for each kind, read candidates in keyset chunks → build alert → per recipient `INSERT … ON CONFLICT DO NOTHING
RETURNING id` in a savepoint → if new, `queue_deliveries(email)` → commit per chunk. The outbox publishes after commit (ENH-014).

## 5. Errors and edge cases

- An agreement renewed (status `renewed`), still a draft or expired → no alert. An inactive university → no alert.
- A milestone achieved by an event (e.g. the first application) is not delayed, the same as on the timeline.
- Re-running the job (same day or later) sends nothing new (AC2). A new day re-runs the digest (a digest each day while overdue).
- No recipient → skipped and counted. Bodies carry names, MoU numbers and dates only; logs carry counts and ids only.

## 6. Acceptance criteria

1. An agreement expiring in exactly 30 days produces one alert per recipient with the source text pattern (AC1).
2. Re-running the job creates nothing new (AC2).
3. The 90-day alert fires at 90 days and the 60-day alert at 60 days (positive).
4. An expired agreement produces no alert (negative). An agreement signed 20 days before expiry gets only the 7-day alert (edge).
5. A milestone whose target was yesterday and is not achieved produces one alert to the primary and backup; an achieved one none.
6. An assignee with overdue tasks gets one digest per day.
7. Before 09:00 IST the job sends nothing.
8. `GET /partnership/alerts` returns only the caller's alerts, filters by kind, pages, counts unread; other roles 403; a bad kind 422.
9. The Alerts page lists them with kind tabs, loading/empty states, and the badge; it is responsive and keyboard accessible.

## 7. Testing

pytest (service with an injected `now` dated 2034 so other tests' rows stay out of the windows; route); vitest (page, nav lists);
Playwright e2e (seeded alert visible, open marks it read, tabs); browser QA at desktop / tablet / mobile.
