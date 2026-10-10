# upc-013 — University communication history (timeline) (design)

Status: draft for DEC-SCOPE-163 · API §12CE · RBAC §2.89 · **no migration**. Branch `worktree-upc-013` (pushed as `feature/upc-013`),
cut from main @ `1aa70166`.

## 1. Evidence and intent

- **Source:** `EVID-020` §12 (L437–L451, backlog Appendix A): "Every email/call/WhatsApp/meeting should be stored against the university",
  the example timeline (05 Sep Email sent · 07 Sep Call completed · 10 Sep Meeting scheduled · 12 Sep Meeting completed · 14 Sep Proposal
  sent · 18 Sep Follow-up · 22 Sep Commercial discussion) and "This means the Partnership Manager never loses the history."
- **Backlog:** `UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §upc-013 and U10 ("Everything appears on the university timeline",
  `EXPLICIT_APPROVAL` 2026-10-08). Expected behaviour: a read-only `UNION ALL` of stage history, calls, messages, meetings, visits, agreement
  events, follow-ups and documents for one university, newest first, paginated. AC: the §12 example sequence renders in order with actor
  and summary. Negative: out of scope → 404. Edge: ties on timestamp.
- **Dependencies:** upc-007, upc-009, upc-010, upc-012, upc-014 — all merged on main (and upc-020 tasks, upc-026 documents).
- **Reusable:** tel-015 `services/lead_timeline.py` (the branch builder and ordering) and `components/LeadTimeline.tsx` (the `.jtl` list,
  paging, loading / empty / error states).

## 2. Recommended answers (TL1–TL10, `NEEDS_CONFIRMATION` at sign-off)

Applied under the owner's standing instruction for the build session ("proceed with the recommended answers").

| # | Question | Answer |
|---|---|---|
| TL1 | Endpoint | `GET /partnership/universities/{id}/timeline?limit(1–100, 50)&offset` → `{items, total, limit, offset}` |
| TL2 | Who reads | The communications readers (upc-012 UC3): `partnership_manager` (with a profile), `partnership_head`, `super_admin`. `overseas_admin` and every other role → `403`; anonymous `401` |
| TL3 | Which universities | Every university, active or not (upc-003 UM9: each read role reads every row). Unknown → `404`; non-UUID → `422` |
| TL4 | Sources | Stage history, calls, messages, meeting events, visit events, agreement events, tasks / follow-ups (created, done, cancelled), document versions (§1) |
| TL5 | Order | `at DESC, rank DESC, seq DESC, id DESC`. Rank puts one transaction's rows in causal order, newest first: activity 1 < stage 2 < task 3 (a signed agreement's stage move shows above it, and the move's auto-task above the move) |
| TL6 | Free text | Excerpt of 200 characters (tel-015 TM2); the full text stays in its own section |
| TL7 | Commission | Documents use upc-026's `visibility(user)` (no commission agreement for a non-commission role). Agreement events carry no commission terms. Every TL2 reader is a commission role today, so nothing is hidden in practice |
| TL8 | Audit / logs | Read-only; not audited; nothing logged |
| TL9 | Web | A "Communication history" section on the university detail page for the TL2 readers, server-rendered first page, "Show older entries" |
| TL10 | Freshness | Writes on the page already `router.refresh()`; the section is keyed on the first page (total + newest row), so it remounts with fresh data |

## 3. Design decisions

- **D1 — one service, one route.** `services/university_timeline.py` builds the union; the route lives with the other §12 reads in
  `api/university_comms.py` (`require_reader`, then `unis.load` → 404). No `main.py` change.
- **D2 — derived, no new table.** Every branch filters on an indexed university column (or joins its parent on its university index).
  Two queries per page (count + rows) whatever the data (fixed query count).
- **D3 — row shape.** The tel-015 columns (`lead_timeline._branch`): `id, kind, at, actor{id, full_name}|null, event, from_value,
  from_label, to_value, to_label, subject, status, reason, duration_seconds, scheduled_for`. Keys, not labels, except the stage labels
  (server catalogue), the call outcome label (server catalogue) and person / contact names.

  | kind | source | at | actor | event | from | to | subject | status | other |
  |---|---|---|---|---|---|---|---|---|---|
  | `stage` | `university_stage_history` | `created_at` | actor | `move` / `lost` / `reopened` | stage key + label | stage key + label | — | — | seq = position, reason = note |
  | `call` | `university_calls` | `occurred_at` | caller | direction | outcome key + label | — / contact name | — | — | duration, reason = notes |
  | `message` | `university_messages` | `sent_at` | sender | channel | template name (`""` = custom) | — / contact name | email subject | delivery status | reason = body |
  | `meeting` | `university_meeting_events` ⋈ meetings | event `created_at` | actor | meeting event | meeting type | — | meeting code | — | seq = position, scheduled_for = new or current start, reason |
  | `visit` | `university_visit_events` ⋈ visits | event `created_at` | actor | action | from status | to status | visit code | — | reason |
  | `agreement` | `university_agreement_events` ⋈ agreements | event `created_at` | actor | `create` / `update` / `status` / `renew` | from status | to status | MoU number | agreement type | seq = position, reason = note |
  | `task` | `partnership_tasks` ×3 | created / completed / cancelled at | creator / `partnership_task.complete`·`cancel` audit user | `scheduled` / `done` / `cancelled` | task kind | due date / assignee name | title | source | reason = notes or cancel reason |
  | `document` | `university_document_versions` ⋈ documents | `uploaded_at` | uploader | `uploaded` (v1) / `new_version` | document kind | version | title | — | — |

- **D4 — backward compatibility.** `lead_timeline._branch` gains an optional `rank` override; the lead timeline is unchanged.
  `LeadTimeline` gains optional `entryOf` / `actorOf` props (defaults: the lead mappers); its three lead callers are unchanged.
- **D5 — web.** `lib/universityActivity.ts` maps a row to `{badge, tone, title, meta, when, detail}` reusing each section's own labels
  (meetings, visits, agreements, documents, tasks, telecaller email titles). `components/UniversityActivity.tsx` is a thin client wrapper
  around `LeadTimeline` (functions cannot cross the server → client boundary, so the wrapper owns them).

## 4. Error handling

`403` wrong role (before the id is read); `404` unknown university; `422` bad paging / non-UUID. The page's first read never rejects
(`null` → "Unable to load the activity." with Retry); "Show older entries" failure keeps the rows already shown.

## 5. Testing

- API `tests/test_upc_013_timeline.py`: the §12 chain (email, call, meeting scheduled, meeting completed, stage → Proposal Sent, follow-up,
  stage → Commercial Discussion) newest first with actor and summary; every kind present; equal-timestamp causal order (stage above its
  agreement, task above its stage) and stable paging; excerpt ≤ 200; overseas_admin / counselor 403, anonymous 401, unknown 404, bad id
  422, manager without profile 403; another university's rows never appear; commission-document filter honoured.
- Regression: `test_tel_015_timeline.py` (the `_branch` change).
- Web (vitest): `universityActivity` titles per kind; `UniversityActivity` renders through `LeadTimeline`; the detail page shows the
  section for the readers only; `LeadTimeline` existing tests.
- e2e `upc-013-timeline.spec.ts`: a manager logs a call and an email, schedules and completes a meeting, moves the stage; the section lists
  them newest first; mobile width; overseas_admin sees no section.
