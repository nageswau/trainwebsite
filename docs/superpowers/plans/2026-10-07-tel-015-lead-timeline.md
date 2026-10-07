# tel-015 Lead Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One merged, newest-first, paged timeline of everything that happened to a lead, readable by every role that can read the lead.

**Architecture:** Extend the existing W1 reader `telecaller_leads.timeline_page` (a SQL `UNION ALL`) with the remaining event sources; add
an admin route on the same service; replace the two hand-rolled "Activity" lists and the admin stage-only History with one `LeadTimeline`
component (the `.jtl` CSS timeline).

**Tech Stack:** FastAPI + SQLAlchemy 2 async (PostgreSQL), Pydantic v2; Next.js 15 / React 19, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-07-tel-015-lead-timeline-design.md`

## Global Constraints

- No migration; no new table (D2). Existing route paths and W1 row fields unchanged (D5).
- Excerpt = first 200 characters (TM2). Logs: ids only (D7).
- Order: `at DESC, rank DESC, seq DESC, id DESC` (D4). Ranks: created 0, enquiry 1, assignment/handover/student_link 2, others 3, stage 4.
- Numbers: DEC-SCOPE-114 · API §12AH · RBAC 2.40 (re-check origin/main before merge).
- Lite tests only (user's standing choice); tests run in docker (`api-test` / `web-test`, Windows-form mount path).

## Review Focus

- A lead created by the website with no audit row: `created` actor null → client shows "Website form" (website) / "System" (others).
- An assignment to "unassigned" (tel-025 deactivation: `to` null) → "Unassigned", not a crash on a null UUID cast.
- Email with no template and WhatsApp custom text → "Custom message"; email shows subject + delivery status.
- A message/remark longer than 200 characters → exactly 200 + ellipsis on the client; never the full body.
- Two events in one transaction (intake: created + assigned + stage) → identical order on every read and no row duplicated/skipped across
  pages (`id` tiebreak).

---

### Task 1: API — the merged timeline (service, schema, admin route)

**Files:**
- Modify: `apps/api/app/services/telecaller_leads.py` (`timeline_page`)
- Modify: `apps/api/app/schemas.py` (`LeadTimelineRow`)
- Modify: `apps/api/app/api/admin.py` (new `GET /admin/leads/{lead_id}/timeline`)
- Modify (route docstrings only): `apps/api/app/api/telecaller.py`, `apps/api/app/api/lead_handover.py`
- Test: `apps/api/tests/test_tel_015_timeline.py` (new); update `test_tel_008_workspace.py` (two timeline asserts now include `created`)

**Interfaces:**
- Produces: `timeline_page(db, lead_id, limit, offset) -> {"items": [row], "total", "limit", "offset"}`; row =
  `{id, kind, at, actor: {id, full_name}|None, from_value: str, from_label: str, to_value: str, to_label: str, reason: str|None,
  event: str|None, subject: str|None, status: str|None, duration_seconds: int|None, scheduled_for: datetime|None}`.
  `kind ∈ {created, enquiry, stage, priority, assignment, handover, student_link, call, message, follow_up, appointment, milestone}`.

- [ ] **Step 1: failing tests** (`test_tel_015_timeline.py`), one lead driven through the real routes where they exist:
  - `test_full_chain_every_kind_has_actor_and_time` — manager-created lead (POST /telecaller/leads, assigned) → call (POST …/calls,
    `interested`) → WhatsApp (POST …/messages) → follow-up (POST …/follow-ups) → appointment booked → handover → counselor links a
    student with an active enrolment. Assert the set of kinds ⊇ {created, assignment, stage, call, message, follow_up, appointment,
    handover, student_link, milestone}; every non-milestone/non-system row has `actor`; every row has `at`; the conversion stage row
    (`event == "converted"`) is present.
  - `test_reassigned_lead_keeps_previous_telecallers_events` (AC2) — tel A logs a call and a WhatsApp; manager reassigns to tel B; tel B's
    timeline still lists A's call and message with actor A; tel A now gets 404.
  - `test_equal_timestamps_order_is_stable_and_causal` (AC3) — the intake transaction rows share `at`; two reads give identical id lists;
    paging with `limit=1` across the whole total yields the same ids as one big page, no duplicates; `created` is the last row.
  - `test_system_events_have_no_actor` — round-robin assignment (actor null) and a milestone row have `actor is None`.
  - `test_excerpts_are_capped` — a 1000-char WhatsApp body and 600-char call remarks come back as 200 chars.
  - `test_unlink_removes_milestones` — after the admin unlink, no `milestone` rows; a `student_link` row with `event == "unlinked"`.
  - `test_scope` — other telecaller 404; unassigned counselor 404 on /counselor/leads/{id}/timeline; it_admin on an overseas lead 403;
    it_admin on own division 200; super_admin 200; unknown id 404 on the admin route.
- [ ] **Step 2: run** — `docker compose -p tel015 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm -v "C:/…/worktrees/tel-015/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q tests/test_tel_015_timeline.py"` → FAIL (kinds missing, admin route 404/405).
- [ ] **Step 3: implement.** Schema: widen `kind` Literal, add the four optional fields (default None). Service: one `select` per source
  with the same 14 labelled columns `(id, kind, rank, at, seq, actor_id, from_value, from_label, to_value, to_label, reason, event,
  subject, status, duration_seconds, scheduled_for)`; names for assignment/handover/link come from `aliased(User)` outer joins inside the
  branch; `func.left(col, 200)` for excerpts; follow-up cancel actor = outer join on `AuditLog(action="lead_follow_up.cancel",
  entity_id=cast(LeadFollowUp.id, String))`; milestones join through `Enquiry.converted_user_id`. Stage / priority labels keep `_label`.
  Admin route: copy `lead_stage_history`'s 404/403 then `timeline_page`.
- [ ] **Step 4: run** the new file + `test_tel_008_workspace.py test_tel_005_intake.py test_tel_018_handover.py test_tel_018_return.py`
  → PASS after updating the two tel-008 asserts to exclude `created`.
- [ ] **Step 5: commit** `feat(tel-015): merged lead timeline (all event kinds) + admin route`.

### Task 2: Web — `lib/leadTimeline.ts` + `LeadTimeline` component

**Files:**
- Create: `apps/web/lib/leadTimeline.ts` (types `TimelineRow`, `TimelineKind`; `timelineEntry(row) -> {title, detail: string[], tone}`;
  `actorName(row)`; `excerpt`), `apps/web/components/LeadTimeline.tsx`
- Modify: `apps/web/lib/telecallerLeads.ts` (re-export `TimelineRow` from the new lib; `activityTitle` removed after Task 3)
- Test: `apps/web/tests/lib/leadTimeline.test.ts`, `apps/web/tests/components/LeadTimeline.test.tsx`

**Interfaces:**
- Produces: `<LeadTimeline url={string} initial={Page<TimelineRow> | null | undefined} version={number} />` — `url` is the timeline
  base (`…/timeline`), the component appends `?limit=50&offset=n`. `undefined` initial → fetch on mount; `null` → error state.
- Titles: created "Lead created" (+ source label); assignment "Assigned to {to}" / "Unassigned" / "Reassigned from {from} to {to}";
  call "{Outgoing|Incoming} call: {outcome label}" + duration "m:ss"; message "WhatsApp sent" / "Email {status}" + template or "Custom
  message" + subject; follow-up "Follow-up scheduled: {reason label}" (+ due) / "Follow-up done" / "Follow-up cancelled"; appointment
  "Counselling appointment {booked|confirmed|rescheduled|completed|cancelled|no-show}" + type + time; handover "Handed over to {to}";
  student_link "Student linked: {to}" / "Student unlinked"; milestone "{IT enrolment|Overseas application|Visa case}: {to}" + status;
  stage `event=returned` "Returned to the telecaller", `event=converted` "Converted", otherwise "Stage: a → b"; priority, enquiry as today.
- Actor: `actor.full_name`, else created/enquiry from website → "Website form", else "System".

- [ ] Step 1 failing tests (titles per kind incl. the Review Focus cases; component: renders rows in `ol[aria-label="Lead activity"]`,
  empty "No activity yet.", error + Retry, "Show older" appends the next page and hides at the end, reload on `version` change).
- [ ] Step 2 run in `web-test` → FAIL. Step 3 implement. Step 4 PASS. Step 5 commit.

### Task 3: Web — wire the three surfaces

**Files:** `components/LeadDetailPanel.tsx`, `components/CounselorLeadDetail.tsx`, `components/AdminLeadStage.tsx` (History panel → admin
timeline URL), their tests; `LeadMessages` gains an optional `onChanged` so a sent/deleted message refreshes the timeline; calls and
follow-ups already notify the panel.

- [ ] Step 1 update tests to the new markup/titles (failing). Step 2 run → FAIL. Step 3 replace each Activity section / history list with
  `<LeadTimeline …/>`, bump `version` where `reloadActivity()` was called and after a call/message/follow-up change. Step 4 run the three
  component tests + `tsc` + `eslint` → PASS. Step 5 commit.

### Task 4: e2e + documentation

- Create `apps/web/tests/e2e/tel-015-timeline.spec.ts`: seed via API a lead with call, WhatsApp, follow-up; telecaller sees the entries
  with actor names; admin History shows the same; 390 px viewport has no horizontal scroll.
- Docs: `PRODUCT_DECISION_REGISTER.md` DEC-SCOPE-114 (TM1–TM3, D1–D8); `API_CONTRACT.md` §12AH; RBAC matrix 2.40 (admin timeline row);
  backlog tel-015 status; RTM row if the tel items have one.
- Commit `docs(tel-015): …`.
