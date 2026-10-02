# AGN-017 — Agent Notifications + Deadline Reminders — Design

- **Feature:** `AGN-017` (backlog item `ang-017`, `docs/delivery/AGENT_CRM_BACKLOG.md` §4).
- **Decision:** `DEC-SCOPE-058` (provisional number — next free on `main` @ `e0395d6`), answers N1–N10 below (`EXPLICIT_APPROVAL`,
  owner in-session 2026-10-02). Channels were already settled by `DEC-SCOPE-035` **D19** (in-app + email to agency Masters/Staff;
  students get nothing).
- **Evidence:** `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) names only "Notifications" (§4) and "Monitor
  deadlines" (§2). `AGENT_CRM_BACKLOG.md` ang-017 (`DERIVED_BLUEPRINT`) proposed the event list and a daily job — a proposal, not
  authority. Every rule below comes from the owner's answers.
- **Requirement:** "Notifications" (§4); "Monitor deadlines" (§2).
- **Owner acceptance:** each event produces exactly one notification to the right person; reminders are not sent twice for the same
  deadline/day; a failed email is recorded, never raised.
- **Dependencies (merged):** AGN-001…004 (tenant, staff, matrix, students + assignment), AGN-008 (applications with
  `agent_student_id`, `application_deadline`, `offer_deadline`), AGN-009 (document requests, reject reasons), AGN-013 (enrollment),
  AGN-016 (tasks, `due_at`), ENH-014 (delivery queue, worker, beat).
- **Impact analysis (2026-10-02):** the graphify graph is an ENH-023 snapshot (before AGN-001…016), so the agency source was read
  directly. No code path notifies agency staff today; `Notification` has no dedupe column; deadline columns are unindexed; beat runs
  only the ENH-014 sweeper.

## 1. Decisions (N1–N10)

| # | Question | Answer |
|---|---|---|
| N1 | "Task assigned" (tasks have no assignee, AGN-016 T1) | **On create by someone else.** Creating a task notifies the student's recipient (§2) unless that is the creator. Reassigning a student sends one "student assigned" notice that states how many open tasks moved with it — never one per task. Task edits/close notify nobody. |
| N2 | Recipients | **Assigned staff, else Masters.** The student's assigned member if its membership is `active` and its user `active`; otherwise every active Master of the org. The actor is always removed. Inactive org → nobody. |
| N3 | "Status change by someone else" | **Agency and EduSphere actors.** The CRM status route, AGN-013 enrollment, and the counselor/admin/university-rep `PATCH`/`advance` in `workflows.py` — for applications that have an agency record. Students' existing notifications are unchanged. |
| N4 | Reminder windows | **3 days, 1 day, due today** for application and offer deadlines. Overdue open tasks: **one digest per recipient per IST day** ("You have N overdue tasks") — revised from "one per task per day" after the security review (email volume), owner-approved 2026-10-02. Day boundary `Asia/Kolkata`. No catch-up for a missed run. |
| N5 | Email path | **Existing ENH-014 queue, email only:** `_notify_user(..., channels=["email"])` — no WhatsApp/SMS even if opted in (D19). No delivery code change. |
| N6 | Exactly-once mechanism | **Approach A:** nullable `notifications.dedupe_key` + partial unique index; reminders insert with `ON CONFLICT DO NOTHING`. Events need no key (same transaction as the change). |
| N7 | API | Reuse `GET /workflows/notifications` and `PATCH …/{id}/read` unchanged; add `GET /workflows/notifications/unread-count`. No `/agent/notifications` duplicate. |
| N8 | Frontend | A `notifications` section in the agent `PortalPage` (the Applications/Documents/Tasks pattern) for Masters and Staff, plus an unread badge on its nav item. No "mark all read". |
| N9 | Document events | "Rejected" covers `rejected` **and** `changes_required`. The previous assignee is not told on reassignment. |
| N10 | Stage rules for deadlines | Same as `nearest_deadline`: none once `withdrawn`/`enrolled`; from `offer` on, only the offer deadline. A submitted application still gets application-deadline reminders (consistent with the UI). |

## 2. Recipient rule — `app/services/agent_notifications.py` (new)

One function decides who hears about an agency student:

```
recipients(db, record: AgentStudent, actor: User | None) -> list[User]
  org = record's org (via record.agent_id's membership); org.status != "active" -> []
  member = record.assigned_member_id -> AgentOrgMember (+ its User)
  base = [member.user]  if member and member.status == "active" and member.user.active
         else active Masters of the org (existing notification_recipients semantics, same org)
  return [u for u in base if actor is None or u.id != actor.id]   # de-duplicated by id
```

Resolving the agency record: an application → `agent_student_id`; a document → `agent_student_id`, else its application's
`agent_student_id`; a document request / task → its `agent_student_id`. **No agency record (legacy rows) → no agency notification.**
An archived record still gets event notices (its writes are already refused where AGN rules say so) but never reminders.

Sending: `notify(db, users, title, body, action_url, *, dedupe_key=None)` — for each user, `_notify_user(db, u, …, channels=["email"])`
for events; for reminders the insert in §4. It never commits; the caller's transaction owns it.

## 3. Events — hooks (each before the route's existing `commit`, after its existing locks)

| Event | Hook | Fires when | Title / body (no names, emails, phones, passport data) | `action_url` |
|---|---|---|---|---|
| Assigned / reassigned | `api/agent_students.assign_student` | `changed` and the new assignee is not null; recipient = the new assignee only (not N2's fallback) unless they are the actor | "Student assigned to you" / "A student is now assigned to you. N open task(s) moved with them." (count omitted when 0) | `/overseas/agent/students` |
| Document requested | `api/agent_documents.create_request` | after the request row is flushed | "Document requested" / "{document type label} was requested for one of your students." | `/overseas/agent/documents` |
| Document needs attention | `workflows._agent_document_review` and the counselor/admin branch of `verify_document` | new status ∈ {`rejected`, `changes_required`} and the document has an agency record | "Document needs attention" / "{document type label}: {rejected / changes required}." | `/overseas/agent/documents` |
| Status changed | `api/agent_applications.change_status`; `workflows.update_overseas_application`; `workflows.advance_overseas_application` | the status actually changed and the application has an agency record | "Application status changed" / "{university}: {old stage label} → {new stage label}." | `/overseas/agent/applications` |
| Enrolled | `api/agent_applications.save_enrollment` (when confirming); the `PATCH`/`advance` paths when the new status is `enrolled` | as status changed, **minus anyone `_maybe_trigger_agent_commission` notified in the same transaction** | as status changed | `/overseas/agent/applications` |
| Task created | `api/agent_tasks.create_task` | always (recipient rule removes the creator) | "New task" / "A new task on one of your students is due {IST date}." (the free-text title is **not** included — §8) | `/overseas/agent/tasks` |

Self-assignment on record creation (`services/agent_students.create_record`, legacy `add_agent_student`) notifies nobody: the actor
is the assignee. Re-assigning the current assignee is already a no-op (no notice).

For AC3, `_maybe_trigger_agent_commission` (called by `save_enrollment`, `update_overseas_application` and
`advance_overseas_application`) is not changed. Each of those hooks reads whether an `AgentCommission` row exists for the
application **before** the trigger call and again after it; if none existed before and one exists after, the trigger has just
notified `notification_recipients(agent)`, and those users are removed from the status-change recipients.

## 4. Daily reminders

- **Schedule:** `app/worker.py` gains `send_daily_reminders_task` and a beat entry `agn017-daily-reminders` at
  `crontab(hour=2, minute=30)` (UTC; = 08:00 IST). The ENH-014 sweeper entry is unchanged. The task runs through the existing
  `_run_with_fresh_pool`.
- **Function:** `services/agent_notifications.send_daily_reminders(today: date, now: datetime) -> dict` (tests call it directly).
  - *Deadlines:* `overseas_applications` with `agent_student_id IS NOT NULL`, record `active`, org `active`, status not
    `withdrawn`/`enrolled`, and (`application_deadline` or `offer_deadline`) ∈ {today, today+1, today+3}; from `OFFER_STAGES_ON`
    only `offer_deadline` counts. Title "Deadline in 3 days" / "Deadline tomorrow" / "Deadline today"; body "{university}:
    {application|offer} deadline {date}."; key `agn017:deadline:{app_id}:{kind}:{date}:{days_left}:{user_id}`.
  - *Overdue tasks (digest):* `agent_tasks.status = 'open' AND due_at < now`, record `active`, org `active`, grouped by recipient
    (§2). One notice per recipient per IST day: title "Overdue tasks"; body "You have N overdue task(s)."; key
    `agn017:overdue:{today}:{user_id}`. N is computed at send time; a later run the same day creates nothing (the count is not
    updated).
  - *Recipients:* §2 with `actor=None`, cached per student record for the run (a record's recipients are resolved once, however many
    deadlines and tasks it has). *Implementation note (2026-10-02):* this replaced "one query per chunk" — simpler, same bound in practice.
- **Never twice:** each reminder is `INSERT INTO notifications … ON CONFLICT (dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING
  RETURNING id`; `queue_deliveries` runs only for a returned row. A rerun, a second beat process, or a concurrent run creates nothing
  new. A moved deadline has a new key, so its reminders fire for the new date.
- **Batches and failures:** candidates in chunks of 200 by primary key; each item in a savepoint (`begin_nested`) — an exception
  is logged with ids only and the item skipped; each chunk commits. Returns `{"created": n, "duplicate": n, "failed": n}`.
- **Time:** `now = datetime.now(UTC)`; `today = now.astimezone(INDIA).date()` with a module constant `INDIA = ZoneInfo("Asia/Kolkata")`
  (a service must not import `app.api.schools`; `reporting/pdf.py` already keeps its own `INDIA` the same way). Both are parameters of
  `send_daily_reminders` so tests pin them.
- **Insert mechanics:** reminders do not go through `_notify_user` (it cannot skip on conflict). They use
  `sqlalchemy.dialects.postgresql.insert(Notification).values(...).on_conflict_do_nothing(index_elements=["dedupe_key"],
  index_where=Notification.dedupe_key.isnot(None)).returning(Notification.id)`, then `queue_deliveries(db, row, user,
  channels=["email"])` for a returned row only.

## 5. Data — migration `0064_agent_notifications` (after `0063_agent_visa_details`; drafted as `0061`)

Additive only; no row is read or rewritten; downgrade drops exactly what it added.

| Change | Detail |
|---|---|
| `notifications.dedupe_key` | `VARCHAR(200) NULL`; existing rows stay `NULL` |
| `ux_notifications_dedupe_key` | unique on `dedupe_key` `WHERE dedupe_key IS NOT NULL` |
| `ix_overseas_applications_agent_application_deadline` | on `application_deadline` `WHERE agent_student_id IS NOT NULL` |
| `ix_overseas_applications_agent_offer_deadline` | on `offer_deadline` `WHERE agent_student_id IS NOT NULL` |
| `ix_agent_tasks_open_due` | on `due_at` `WHERE status = 'open'` |

`models.py`: `Notification.dedupe_key` (nullable) and the three `Index(...)` declarations with `postgresql_where`, mirroring the
migration so `create_all` (0001) and the migration agree.

## 6. API

- `GET /api/v1/workflows/notifications` and `PATCH /api/v1/workflows/notifications/{id}/read`: **unchanged** (fields, limit, 404 for
  another user's id). `dedupe_key` is never returned.
- **New** `GET /api/v1/workflows/notifications/unread-count` → `NotificationUnreadCount {unread: int}`; `get_current_user`; counts
  `user_id = caller AND read = false` (uses `ix_notifications_user_id`). Any signed-in role.

## 7. Transactions, concurrency, authorization

- Event notices are written in the request's transaction after its locks (org lock, then row lock), so a `409`/`403`/`422`, a
  rollback or a no-op writes none; emails are published only after commit (ENH-014 `after_commit`).
- Duplicate requests (double click): already serialized by the existing locks and `expected_status`/"already reviewed"/duplicate
  request checks — the losing request gets `409` and no notice.
- Reminders: the unique index is the guarantee; nothing depends on beat running once.
- Authorization: recipients come only from the record's own org (§2), so no cross-org notice is possible; reading is restricted to
  the caller's own rows by the existing endpoints; the new count is the caller's only. No new role checks.
- Deactivated members get nothing (N2); their earlier rows remain theirs (unreadable while deactivated, as today).

## 8. Errors, logging, security

- A failed or unconfigured email is recorded on `NotificationDelivery` (status/error/attempts) and retried by the existing worker;
  nothing raises into the request or the job.
- A reminder item failure is logged as `agn017_reminder_failed` with ids only; the job logs `agn017_reminders_done` with counts.
- Bodies carry no names, emails, phones or passport data and **no free text typed by users** (task titles, custom document labels,
  notes, reasons) — such text can contain personal data and the email leaves the system through the webhook. Bodies are built only
  from: fixed strings, the document **type** only when it is one of `schemas.AgentDocumentType`'s values (request types are that
`Literal`; an uploaded `StudentDocument.document_type` is free `str(80)`, so any other value becomes "A document"; never
`document_label`), stage labels
  (`stage_label`), the university name and dates. The university name is the only stored text; it is passed through one helper that
  removes control characters (CR/LF) and caps it at 120 characters, so no value can break an email subject/header downstream.
- `action_url` is always one of four fixed internal paths (§3); never built from input, so no open redirect.
- Email is the only external channel; WhatsApp/SMS are never queued for these notices.

## 9. Frontend

- `lib/navigation.ts`: `"notifications"` appended to `PORTAL_NAV["overseas/agent"]` after `tasks`; `NavItem` gains optional
  `badge?: number`.
- `components/PortalShell.tsx`: for an item with `badge > 0`, render after the label
  `<span className="badge nav-badge">{n > 99 ? "99+" : n}<span className="visually-hidden"> unread</span></span>` — the link's
  accessible name becomes "Notifications 3 unread" (visible text, not an `aria-label` on a span, which screen readers may skip); the
  unread state is text, never colour alone. `PortalMobileNav` receives the label "Notifications (3 unread)". One CSS rule in
  `globals.css`: `.portal-nav .nav-badge{margin-left:8px;padding:1px 8px}` (existing `.badge` colours: #0755b9 on #e8f1ff, ≥ 4.5:1).
  No other portal sets `badge`, so their markup is unchanged.
- `components/PortalPage.tsx`: `agentNotifications` joins the "portal-payload 404 tolerated" set (the payload call stays the
  role/approval gate); for agents it also fetches `unread-count` (failure → no badge, never a broken page) and sets it on the
  Notifications nav item.
- `services/portal.py` gains a header-only `notifications` section for agents — the page's role/approval gate, as Tasks (without it the
  payload would 404 and `PortalPage` would show "Access unavailable" to agency members).
- `components/AgentNotificationsSection.tsx` (new, presentational): the existing agent page header (`portal-title`, eyebrow "Workspace",
  one `h1` "Notifications", a one-line intro per role, as `AgentTasksSection`), then a `card` with the list. *Implementation note
  (2026-10-02):* `PortalPage` fetches the list in its existing `Promise.all` (beside the payload and the unread count, one round trip)
  and passes `items` (null when it failed) — replacing the streamed async child under Suspense, which this repo's component tests
  cannot render; there is no separate "Loading notifications…" text (the route transition keeps the previous page until it renders).
  States:
  - empty: "No notifications yet. You'll be told here about assignments, document requests, status changes, new tasks and upcoming
    deadlines.";
  - list failure (non-401): `SectionUnavailable` ("This section couldn't load. Refresh to try again.", `role="status"`);
  - 401 (session expired): the existing `accessUnavailable` login card (`PortalPage` rethrows a 401 from the list);
  - document type "Other" is shown as "A document" (its label is user-typed) — implementation note, 2026-10-02;
  - exactly 100 rows: a muted line "Showing your latest 100 notifications." (the existing endpoint's window — the badge may count
    unread items older than the window);
  - non-agency viewer (Super Admin): a note, as Tasks.
- `components/SchoolNotificationList.tsx`: optional `localTime?: boolean` prop (default `false` → today's
  `formatDate(…, SCHOOL_TIME_ZONE)`, so school pages are byte-identical); `true` renders the existing `LocalTime` (`time`) — the
  hydration-safe viewer-zone timestamp other agent screens use. No other change: it is already a `ul.link-list` that stacks at
  375 px, unread items carry the text badge "new", and each "Open" link is a real `<a>` named "Open: {title}" (keyboard and
  screen-reader reachable).
- Reading: the existing "Open" link marks a notice read (fire-and-forget `keepalive` PATCH); every AGN-017 notice has an
  `action_url`. The badge reflects the count at the next server render; it is not live-updated (no polling — YAGNI).
- No forms are added; no client-side state beyond the existing component.

## 10. Acceptance criteria

| ID | Criterion |
|---|---|
| AC1 | Each of the six events (§3) creates exactly one notification per recipient: the active assignee, else active Masters; never the actor, a deactivated member, another org's user, or a student. |
| AC2 | No notification on a refused/failed/no-op write: `409`, `403`, `422`, rollback, same-assignee re-assign, a `PATCH` that does not change status. |
| AC3 | Confirming enrollment gives each person at most one notice (commission notice **or** status notice). |
| AC4 | Reminders at 3/1/0 days for application and offer deadlines per N10, by IST date; one overdue-task digest per recipient per IST day with the correct count; none for archived records, inactive orgs, withdrawn/enrolled applications, done/cancelled tasks. |
| AC5 | Running the job twice (sequentially or concurrently) on one IST day creates no duplicate reminder. |
| AC6 | A failed or unconfigured email is recorded on `NotificationDelivery` and never raises into the request or the job; one failing reminder does not stop the rest. |
| AC7 | Only the email channel is queued; bodies carry no name, email, phone, passport data or user-typed free text (task title, document label, notes); stored text (university name) is stripped of control characters and capped; `action_url` is one of four fixed paths. |
| AC8 | `unread-count` returns the caller's unread count only; list/read contracts unchanged (including 404 for another user's id). |
| AC9 | Agent Notifications page in the nav for Master and Staff with list/empty/error/session-expired states; badge only when count > 0; keyboard and screen-reader accessible; usable at 375 px. |
| AC10 | `0064` upgrades and downgrades cleanly with one head; existing notification rows unchanged. |

## 11. Tests (written first)

- API: `test_agn_017_events.py` (AC1–AC3, AC7 — including a task title / document label / note containing an email address and a
  CR/LF never appearing in any title or body, and logs carrying no text), `test_agn_017_reminders.py` (AC4, AC5 sequential, IST
  boundary at 18:29/18:31 UTC, deadline moved, digest count and a second same-day run creating nothing), `test_agn_017_concurrency.py` (AC5 concurrent; concurrent status changes → one notice),
  `test_agn_017_delivery.py` (AC6 with the `enqueued` fixture and `drain`), `test_agn_017_api.py` (AC8), `test_agn_017_migration.py`
  (AC10), beat schedule entry test.
- Web (vitest): `PortalPage.agentNotifications.test.tsx` (section, tolerated 404, badge set, count failure → no badge),
  `AgentNotificationsSection.test.tsx` (list, empty, error, 401, 100-row note, Super Admin note), `PortalShell` badge (accessible name
  "Notifications 3 unread", "99+", absent at 0, other portals unchanged) + mobile label, `SchoolNotificationList` default zone
  unchanged and `localTime` path.
- E2E: `agn-017-notifications.spec.ts` — Master assigns a student → Staff sees badge and notice → opens it → badge clears.
- Regression re-runs: `test_enh_014_*`, `test_not_001_*`, `test_agn_003_*`, `test_agn_008_*`, `test_agn_009_*`, `test_agn_013_*`,
  `test_agn_016_*`, single-head migration tests, `PortalPage.*` and `SchoolNotificationList` vitest, `agn-0*` and `sch-007` e2e.

## 12. Regression risks

| Risk | Mitigation |
|---|---|
| `workflows.py` shared verify/PATCH/advance routes | Additive hook calls only; tests assert students' existing notices unchanged |
| Enrollment commission notice | AC3; `_maybe_trigger_agent_commission` output unchanged |
| First crontab job / multiple beat processes | Idempotent by unique key; one beat entry |
| `PortalShell` / `NavItem` used by every portal | Optional field; vitest proves other portals' markup unchanged |
| Migration chain | `0064` after `0063`; single-head tests updated |
| Existing tests counting `Notification` rows (`test_agn_001_tenancy`, `test_agn_003_verify`, `test_agn_008_create`) | Re-run; update only where the new agency notice is the legitimate cause, noted per test |

## 13. Engineering reviews (2026-10-02, before the plan)

### 13.1 API and interface design (`api-and-interface-design`)

| Check | Result |
|---|---|
| Contract first | `GET /workflows/notifications/unread-count` → `NotificationUnreadCount {unread: int}` (Pydantic `response_model`); no input, no query params. Existing list/read: unchanged contracts (Hyrum's law — the school pages and the e2e specs depend on the newest-100 plain array and `{ok: true}`). |
| Additive only | New nullable column never serialized (the list builds explicit dicts); new route; optional `NavItem.badge`; optional `localTime` prop. No field removed or retyped. |
| HTTP semantics | `GET` count is safe and cacheable-never (callers use `no-store`); existing `PATCH …/read` is idempotent (re-marking read is `200`). No new state-changing endpoint, so no idempotency key is needed at the API. |
| Errors | FastAPI's existing `{"detail": …}` shape; `401` from `get_current_user`; no new error codes. |
| Pagination | The existing list stays a 100-row window (changing it would break its consumers); the UI says so at 100 rows. Not paginated in AGN-017 — recorded, not solved. |
| Idempotency of reminders | Key derived from the intent (item/deadline/window/recipient or day/recipient), never from the attempt; claimed atomically by the partial unique index (`ON CONFLICT DO NOTHING RETURNING`) — no `SELECT`-then-`INSERT`; retained forever (rows are not deleted), so it outlives every retry path (Celery redelivery, manual rerun). |
| Celery semantics | The task is at-least-once; re-execution is harmless because of the key. Email delivery keeps ENH-014's claim-then-send. |
| Transactions | Event notices inside the route's transaction after its locks; reminders commit per chunk with a savepoint per item. |
| DB usage | Partial indexes match the reminder predicates; recipients batched per chunk; `unread-count` uses `ix_notifications_user_id`. |
| Layering | The service does not import `app.api.*` (own `INDIA` constant); hooks call the service, the service calls `_notify_user`'s building blocks (`Notification`, `queue_deliveries`). `_notify_user` itself is reused for events unchanged. |

### 13.2 Frontend (`frontend-ui-engineering`)

Reuse: `PortalPage` section pattern, `PortalShell`, `SchoolNotificationList`, `LocalTime`, `SectionUnavailable`, `accessUnavailable`,
`.badge`, `.visually-hidden`, `.link-list`; one new section component and one CSS rule. Hierarchy: one `h1`, intro, card; unread
marked by text. Responsive: `.link-list` stacks at 375 px; the badge sits inline in the sidebar and as text in the mobile menu.
Accessibility: badge count in the link's accessible name; "Open: {title}" links; `role="status"` loading/error text; no colour-only
state; no focus traps or new widgets. Loading: streamed list under Suspense with the established text. Empty/error/expired/at-window
states listed in §9. Forms: none. Perceived performance: header renders before the list; the count is one indexed `COUNT`
fetched in parallel with the page payload; failure hides the badge, never the page.

### 13.3 Security (`security-and-hardening`)

| Area | Finding / control |
|---|---|
| Authentication | All three endpoints use `get_current_user`: an inactive user or a stale `session_version` (deactivation, reset) is refused, so a deactivated staff member cannot read their old notices. The job has no HTTP surface. |
| Authorization / IDOR | List, read and count filter by `user_id = caller`; `PATCH` of another user's id is `404` (existing, retested). Recipients are resolved server-side from the record's own org; no client input names a recipient, so no cross-org notice and no IDOR in sending. |
| Role escalation | No new write endpoint; no role or permission is granted; hooks run after the routes' existing role/scope checks. |
| Input validation | Count: no input. Read: `UUID` path param (FastAPI `422` otherwise). Event hooks use already-validated, already-persisted values. |
| XSS | React escapes title/body; no `dangerouslySetInnerHTML`; `action_url` fixed internal paths; bodies hold no user free text (§8). |
| CSRF | Session cookie is `httponly`, `samesite=lax`; CORS allows only `settings.frontend_url`. The only state change (`PATCH …/read`) is unchanged; `GET` count changes nothing. |
| SQL injection | ORM / SQLAlchemy Core only; the dedupe key is built from UUIDs, dates and fixed words and bound as a parameter. |
| Token / session | No change to tokens or cookies. |
| Secret exposure | No new secret; the email webhook URL stays in settings; nothing about delivery config is returned to clients. |
| Sensitive logs | Logs carry ids and counts only (`agn017_reminder_failed`, `agn017_reminders_done`); never titles, bodies, emails or names (the ENH-014 log test pattern is reused). |
| Data minimisation | Email leaves through the webhook, so bodies exclude user-typed text (§8). |
| Rate limiting / abuse | Event notices are bounded by the existing write throttles and the 100-open-task cap (T7); reminders by the per-day keys and the overdue digest (N4), so a recipient receives at most one digest plus three reminders per deadline. `unread-count` is a cheap indexed read behind authentication; no new limiter. |
| Audit | Notifications are not security events: the triggering actions are already audited (`assign`, `document_request.create`, `document.verify`, `advance`/`withdraw`/`enroll`, `task_add`). The job is logged, not audited. |
| Races | A reassignment committed while the job runs may route that day's reminder to the previous assignee once (read-committed snapshot); accepted and documented. |
| Out of scope (recorded, not changed) | the data-request export (`GET …/data-requests/{id}/export`, `api/account.py`) does not include notifications today (pre-existing, `SEC-002`); there is no notification retention policy. Both predate AGN-017. |

## 14. Numbering and parallel lanes

Drafted as `DEC-SCOPE-055` and `0061_agent_notifications` (next free on `main` @ `e0395d6`). On merging `main` @ `ff27fa4` (bdm-001,
AGN-010, AGN-012 hold `055`–`057` and `0061`–`0063`) they became `DEC-SCOPE-058` and `0064_agent_notifications` after
`0063_agent_visa_details` (precedent: `DEC-SCOPE-051`…`054`).
