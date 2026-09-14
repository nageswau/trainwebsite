# Pending — Zoho Recurring Live Classes, Auto-Invite, Auto-Attendance

Session-derived planning note (Claude Code session, 2026-09-03/04). Origin: user-stated requirement
in conversation, classified `ORIGINAL_REQUIREMENT` per `CLAUDE.md` — not yet an `EXPLICIT_APPROVAL`
of scope, and not one of the formal `prompts/NN_*` generated artifacts. Written so a **new session**
can recover this state without re-deriving it from chat history.

**Status: planning only for this file's own recurring/auto-invite/auto-attendance scope. No
schema, API, or frontend changes for §4-§6 below have been made.** Still blocked on someone
with real Zoho account access answering §2's capability questions before any of that can move
toward the coding gate (`APPROVAL_GATES.md` GATE-09).

**Update 2026-09-09 (`RAID.md` I-20):** §1's own blocking prerequisite — real Zoho account
access — is now confirmed **met**. Real credentials landed in `.env` at some point after this
file was written and were verified directly against the live API on request: OAuth token
refresh and real session creation both succeed through the account's actual data center. This
only unblocks §1 itself (account access exists); §2's capability questions still need someone
with that access to check Zoho's own docs/support, and §4's Decision IDs are still unconfirmed.

**Update 2026-09-09 (`RAID.md` I-22):** worked through as many of §2's remaining capability
questions as are answerable from Zoho's own public documentation (plus two checked directly
against the live token endpoint, not docs) — **6 of 11 now answered** (items 1, 2, 6, 7, 10,
12), leaving 4 genuinely open (items 3, 4, 5, 8, 9 — the last three of those need either a
support conversation or checking the account's own subscription page directly, not more
document-reading). The single most important finding: item 2 confirms Zoho's Participant
Report API *does* expose per-participant `joinTime`/`leaveTime`/`duration` — `DEC-ATT-001`'s
auto-attendance rule is technically feasible — but it's a pull/report endpoint queried after
the fact, not a push webhook (item 3's still-unconfirmed answer), so the design should assume
**polling**, matching `§7`'s own already-proposed Beat-task approach.

---

## 1. Blocking prerequisite — RESOLVED 2026-09-09

~~Zoho account/API-console access.~~ `INTEGRATION_CONTRACTS.md:91` already flagged provider
account ownership ("who holds the Zoho login") as unresolved — real credentials now exist in
`.env` and were verified working against the live API (`RAID.md` I-20). Whoever holds that
account should now answer §2 so §3 (already partly done, see below) can be finished.

---

## 1b. New requirement batch, 2026-09-09 (user chat, `ORIGINAL_REQUIREMENT`, screenshot-driven)

The user shared a screenshot of the generic Admin "Live Sessions" table (raw `Join`/`Recording`
columns as plain text/links, the exact `§6` gap below) and asked for six things together. Split
here before touching any code, per `CLAUDE.md` NO-ASSUMPTION MODE:

| # | Ask (as stated) | Classification |
|---|---|---|
| a | "join should be a button not direct link" | **FIXED 2026-09-09.** New shared `JoinSessionButton.tsx`, wired into both `LiveClassesPanel.tsx` (already a button before, now the same shared component) and, per `§6`'s own plan, into `DataTable` via a new server-declared `type: "join"` column kind (`_payload()` now accepts an optional 3rd column-tuple element, a plain string, never a function — see `§6` below for detail). While touching the trainer's own `live-sessions` row, also fixed an adjacent inconsistency: the "meeting" cell now prefers `host_url` over the plain `meeting_url`, matching `LiveClassesPanel`'s own already-established precedent |
| b | "if the user clicks on the button 15 minutes earlier then it should display pop-up too early to join" | **FIXED 2026-09-09**, UI-only as predicted — the 15-minute figure is the same one already sourced from `EVID-008`. Honest limitation confirmed unchanged: gates EduSphere's own button only, not the raw URL (`§2` item 11 still unconfirmed) |
| c | "similarly if after the end time and closing of session it should pop-up completed" | **FIXED 2026-09-09** — same mechanism as (b), gates on `ends_at` |
| d | "Zoho authentication button to override the default id's for a particular session if required" | **Deliberately moved to pending, at the user's own request 2026-09-09 — not scheduled next.** Confirmed as `§3.B`/`§5`'s `TrainerZohoAccount` per-trainer OAuth-connect flow: real new infrastructure (new table, OAuth authorize/callback endpoints, encrypted token storage), not a small fix. Tracked here and in `pending.md`; pick up only when explicitly asked for again |
| e | "When student joins it should ask name, email and then allows to join" | **FIXED 2026-09-09, clarified interpretation confirmed by the user**: a "Join as {name} ({email})?" confirmation using the already-logged-in student's own EduSphere account, shown before the real link opens — never a guest-identity form, and no new Zoho capability needed. Applies only to a joining participant, never the host (a trainer setting up early shouldn't be asked to confirm their own identity) |
| f | "some predefined setting like mute all student, don't allow to speak etc." | **CANNOT be built as asked — confirmed 2026-09-09 against Zoho's own public API docs (`§2` item 12).** Zoho's Meeting API has no mute/audio/participant-permission field anywhere (checked the create-session, schedule-session, and full attribute-schema docs) — "mute all" and "control who can unmute" are documented only as live, in-meeting moderator actions taken by the human host inside Zoho's own client, never a schedulable or API-settable property. Nothing EduSphere's backend does at session-creation time can pre-configure this. Not a temporary blocker to revisit later — this is Zoho's real, documented feature boundary. |

---

## 2. Open Zoho capability questions — must be answered before implementation

None of these can be verified by reading this codebase; they require Zoho's own API docs for the
specific product/plan in use, or a support conversation.

| # | Question | Why it matters |
|---|---|---|
| 1 | ~~Does the Zoho Meeting API support creating a native *recurring* session (one series, many occurrences), or must each occurrence be created as a separate one-off session?~~ | **ANSWERED 2026-09-09, from [Schedule a Session](https://www.zoho.com/meeting/api-integration/sdk/schedule-a-session.html) — no.** A created session's own response includes `"isRecurring": false`; the create-session request has no recurrence/repeat/frequency parameter of any kind. Zoho Meeting's *web client* has a user-facing recurring-meeting UI (daily/weekly/monthly, end-by-date-or-count), but that's not exposed through the documented REST create-session endpoint. **Confirms `DEC-LIVE-002`'s own assumption**: recurrence expansion must live in EduSphere's own scheduler (the already-proposed `ClassSchedule` entity + Beat task expanding it into individual one-off `LiveSession`/Zoho-session-creation calls per `§7`), not in a single Zoho API call. |
| 2 | ~~Does the API expose per-participant join/leave time or total duration per session?~~ | **ANSWERED 2026-09-09 — yes.** [Meeting Participant Report](https://www.zoho.com/meeting/api-integration/meeting-api/participant-report.html): `GET /api/v2/{zsoid}/participant/{meetingKey}.json` (scope `ZohoMeeting.meeting.READ`, paginated via required `index`/`count`) returns `joinTime`, `leaveTime`, `duration`, `inAndOutTime`, `role`, `email`, `memberId` per participant of a specific completed meeting. **This directly backs `DEC-ATT-001`'s >50%-presence auto-attendance rule** — technically feasible via this endpoint. It's a pull/report API (queried by `meetingKey` after the fact), not a push notification — see item 3. |
| 3 | Does Zoho support outbound webhooks (session ended, participant joined/left)? | **Still unconfirmed, but evidence leans "no."** Exhausted public search: no Zoho Meeting webhook documentation exists anywhere (unlike Zoho CRM/Desk, which do have documented webhooks) — one Zoho community thread literally asks "where is zoho meeting api or webhooks?" with no official answer given. Combined with item 2's confirmed *pull*-style report API, the design should assume **polling, not webhooks**: a post-session Beat task calling the participant-report endpoint on a delay after `ends_at`, exactly `§7`'s own already-proposed design (c). Treat this as the working assumption, not a hard "no" — a support conversation could still surface an undocumented/beta webhook feature. |
| 4 | How many sessions can run concurrently under one org/presenter? | **Still unconfirmed** — no public documentation found. (One irrelevant hit: Zoho *Accounts'* own 50-concurrent-*login*-session limit is a different concept entirely — account sign-ins, not Meeting sessions — not applicable here.) Needs a real support conversation or a direct test (schedule two overlapping sessions under the same presenter and see what happens) once the three schedule patterns' actual intended overlap is clarified (`DEC-LIVE-004`, also still open). |
| 5 | Is one shared presenter acceptable, or does each trainer need their own Zoho Meeting seat? | **Still unconfirmed** — tied to item 4 and to the account's actual plan/tier (item 9), neither discoverable from public docs alone. |
| 6 | ~~When `participants` is passed at session creation, does Zoho itself email invitees, or must EduSphere send its own invite?~~ | **ANSWERED 2026-09-09 — Zoho does.** Per Zoho's own "Create Meeting" API description: an invitation email (title, date, time, RSVP, one-click join link) is sent automatically to every participant listed at creation, with a documented mail-sending toggle to suppress it if not wanted. EduSphere's existing `_notify_user` call on the same event would be a **second, separate notification** on top of Zoho's own — not wrong, but worth being deliberate about (both, or suppress one) rather than assuming only one exists. |
| 7 | ~~What timezone identifiers does the session API accept?~~ | **PARTIALLY ANSWERED 2026-09-09.** Zoho's own sample request in the "Create a Meeting" docs uses the exact literal value `"Asia/Calcutta"` — matching this codebase's current hardcoded value exactly (`meetings.py:134`). No full accepted-list or format spec (e.g. whether "Asia/Kolkata" or arbitrary IANA zones also work) is documented beyond that one example — low risk as long as this stays the only zone in use, but not fully resolved for a multi-timezone future. |
| 8 | What are the API rate limits? | **Still unconfirmed** — no Zoho Meeting-specific rate-limit page exists publicly (other Zoho products like Creator/Books document their own limits, e.g. 50-100 calls/minute, but these don't necessarily transfer to Meeting). Needs a support conversation, or empirical observation once beat-driven polling (item 3) is actually built. |
| 9 | Which plan/tier will the org be on (Free/Starter/Professional/Enterprise)? | **Still unconfirmed — genuinely not answerable from public docs at all.** This requires checking the actual account's own subscription/billing page directly, something only whoever holds the account login can do. |
| 10 | ~~Does the OAuth token response include the presenter/user ID directly, or does it need a separate "get current user" call?~~ | **ANSWERED 2026-09-09, checked directly against the real live token endpoint (not docs) — no, it doesn't.** The real response is exactly `{access_token, scope, api_domain, token_type, expires_in}` — no presenter/user ID field. A per-trainer OAuth-connect flow (`§1b` item d, `§5`) will need a separate call to resolve the connecting trainer's own Zoho user/presenter ID after token exchange — not yet confirmed which endpoint provides that (a real gap for whoever builds `§1b` item d next). |
| 11 | Does Zoho/Google Meet support a server-side lobby lock (block join before/after a window)? | EduSphere can only gate its own "Join" button — without provider-side enforcement, a user with the raw URL can bypass the 15-minute-early / no-late-join rule entirely |
| 12 | ~~Does the session-creation API (or a separate settings call) support default participant controls — mute-on-entry, disable-unmute/"can't speak," etc.?~~ | **ANSWERED 2026-09-09, from Zoho's own public API docs — no, it does not.** Checked all three real sources: (1) [Create a Meeting](https://www.zoho.com/meeting/api-integration/meeting-api/create-a-meeting.html) and (2) [Schedule a Session](https://www.zoho.com/meeting/api-integration/sdk/schedule-a-session.html) — both document only `topic`/`agenda`/`presenter`/`startTime`/`duration`/`timezone`/`participants`, matching exactly what `meetings.py` already sends; neither has any mute/audio/permission parameter. (3) The full Meeting-object [attribute schema](https://www.zoho.com/meeting/api-integration/meeting-api.html) (`meetingKey`/`presenter`/`offset`/`timezone`/`accessCode`/`creatorZuid`/`agenda`/`startLink`/`duration`/`topic`/`sessionType`/`dialinUrl`/`startTime`/`endTime`) has no such field either. [Zoho's own host-controls page](https://www.zoho.com/meeting/host-controls.html) confirms "mute all"/"decide whether participants can unmute and speak" is described purely as a live, in-meeting moderator action taken by whoever is hosting inside the Zoho Meeting client — not a schedulable or API-settable property at all. **Conclusion: `§1b` item (f) cannot be built as asked.** EduSphere's own session-creation call has no field for it, and nothing server-side can pre-configure it; only the human hosting the live session, using Zoho's own client UI, can mute participants or restrict who can unmute — after the meeting has started, not before. |

---

## 3. Credentials/config checklist required

### A. Org-level — RESOLVED 2026-09-09, real values now in `.env` (`RAID.md` I-20)

`ZOHO_CLIENT_ID`, `ZOHO_CLIENT_SECRET`, `ZOHO_REFRESH_TOKEN`, `ZOHO_ORGANIZATION_ID`,
`ZOHO_PRESENTER_ID` all now hold real values and were verified working. The predicted region
risk **did occur** — `ZOHO_MEETING_BASE_URL` was `https://meeting.zoho.com` while this account's
OAuth tokens are issued by `https://accounts.zoho.in` (an India-data-center account); the
Meeting API call failed with a real `401 INVALID_OAUTHTOKEN` until corrected to
`https://meeting.zoho.in`. Confirmed directly against the live API, not assumed — see `RAID.md`
I-20 for the full verification trail. If a future trainer/org turns out to be on a different
data center, re-check this same value against that account specifically.

### B. Per-trainer (new — needed for trainer presenter-override)

Each trainer who connects their own Zoho account needs their own `zoho_presenter_id` and
`zoho_refresh_token` (stored encrypted, one row per trainer). `ZOHO_CLIENT_ID`/`ZOHO_CLIENT_SECRET`
stay shared (same registered OAuth app).

### C. Conditional on §2 answers

Webhook signing secret (only if item 3 above is "yes" — every inbound webhook in this codebase must
be signature-verified per `INTEGRATION_CONTRACTS.md` §6). Exact OAuth scope list to request at
consent time.

### D. Test/sandbox

A full duplicate of set A against a non-production Zoho org/account, so CI never touches production
quota or sends real invites.

---

## 4. Proposed new Decision IDs (UNCONFIRMED — format matches `DECISION_REGISTER_TEMPLATE.md`)

| Decision ID | Topic | Options / Conflict | Evidence | Proposed Recommendation | Status |
|---|---|---|---|---|---|
| `DEC-LIVE-002` | Recurring class scheduling model | `Batch.schedule` today is a free-text string (`models.py:92`), not machine-parseable. Needs a structured recurrence model — and the three stated patterns require **multiple concurrent recurrence rules per batch**, not one | User chat, this session | New `ClassSchedule` entity (days-of-week, start/end time, timezone, effective range), 1-to-many against `Batch` | UNCONFIRMED |
| `DEC-LIVE-003` | Auto-invitation trigger & audience | Invite once at pattern creation vs. per-occurrence; "all students" = active `Enrollment`s at send time, including later joiners? | User chat, this session | TBD — needs user answer | UNCONFIRMED |
| `DEC-ATT-001` | Auto-attendance from presence duration | **Conflicts with an existing, cited invariant**: `DATA_MODEL.md:172-174` / `STU-006-AC02` states a missing `Attendance` row *is* "not yet marked" and is never auto-created. Auto-marking `present` from Zoho duration data changes this | User chat, this session; conflicts `STU-006-AC02` | Auto-mark `present` only (>50% threshold), never auto-mark `absent`; tag provenance (`source: auto` vs `manual`) so trainers can still correct via existing `AttendanceCorrection` flow | UNCONFIRMED |
| `DEC-LIVE-004` | Schedule-pattern overlap | As literally stated, "every day 7–8 PM" + "Mon/Wed/Fri 7–8 PM" + "Tue/Thu 6:30–8 PM" overlap on every weekday — almost certainly not the intended pattern | User chat, this session | Needs clarification: is the daily pattern meant to be weekends only? | UNCONFIRMED |
| `DEC-LIVE-005` | Join-window enforcement scope | 15-min-early / no-late-join can only be enforced as an EduSphere UI button state unless the provider also supports a lobby lock (`§2` item 11) | User chat, this session | TBD pending `§2` item 11 answer | UNCONFIRMED |

---

## 5. Data model deltas (planned, not built)

- **`TrainerZohoAccount`** (new): `user_id`, `zoho_presenter_id`, `zoho_refresh_token` (encrypted),
  `connected_at`. Backs the "trainer overrides the default presenter" flow.
- **`LiveSession`** (`models.py:715`) additions: `class_type` (`one_time | recurring`),
  `recurrence_id` (nullable FK to the new `ClassSchedule` entity), and a snapshotted
  `presenter_zoho_id` (resolved at creation time, so a trainer's later override/disconnect doesn't
  retroactively alter historical sessions).
- **`ClassSchedule`** (new, per `DEC-LIVE-002`): the structured recurrence entity — `batch_id`,
  `days_of_week`, `start_time`, `end_time`, `timezone`, `effective_from`/`effective_to`.
- **`Attendance`** (`models.py:137`) provenance: add `source` (`manual | auto`) so auto-created rows
  from `DEC-ATT-001` are distinguishable from trainer-marked ones, without changing the existing
  "missing row = not yet marked" semantics for anything auto-detection doesn't cover.

---

## 6. Frontend gap identified — FIXED 2026-09-09

`DataTable.tsx:9-13` (`displayValue()`) stringified every cell — no link/button column concept,
which is why the trainer's own "Live Sessions" table rendered the join URL as plain text (per the
screenshot shared 2026-09-09). Fixed exactly as proposed: `_payload()` (`services/portal.py`) now
accepts an optional 3rd element per column tuple (a plain string `type`, e.g. `"join"` — never a
function, since columns cross a JSON boundary); `DataTable.tsx` renders any `type: "join"` cell via
the new shared `JoinSessionButton.tsx` instead of stringifying it. The trainer's `live-sessions`
section declares its "meeting" column this way and carries `ends_at`/`host_url` as extra
(non-displayed) row fields for the button's own time-window/host logic. `LiveClassesPanel.tsx` was
switched to the same shared component (previously a plain `<a>`, not gated on timing at all) rather
than keeping two separate join implementations. See `§1b` items a/b/c/e above for the full user
request this closed, and `RAID.md` I-21 for the verification trail.

---

## 7. Infra already available — no new dependency needed

Celery + Redis are already in this stack: `docker-compose.yml` runs `worker` and `beat` services;
`app/worker.py` has an established outbox-task pattern (`sync_enquiry_to_crm_task`) to mirror for:
(a) a Beat periodic task expanding `ClassSchedule` rows into concrete `LiveSession` rows on a
rolling window, (b) a per-session task creating the Zoho session + sending invites, (c) a
post-session task fetching participant duration and applying the `DEC-ATT-001` threshold.

---

## 8. Traceability status

Per `APPROVAL_GATES.md`: nothing in this file proceeds past GATE-02 (Product Decisions) until §4's
Decision IDs are confirmed. No Feature ID has been assigned yet (GATE-05, Feature Catalogue) — this
whole initiative is pre-Feature-Catalogue. Coding (GATE-09) is blocked behind all of GATE-01–08,
which in turn is blocked behind §1 (Zoho account access) and §2 (capability answers).

---

**Related:** `PRD_OPEN_ITEMS.md` item 37 (live-session join-link cadence) and `DEC-LIVE-001` (Zoho
Meeting confirmed as default provider) are the closest existing entries — this file is the detailed
working note behind a new pointer row added there.
