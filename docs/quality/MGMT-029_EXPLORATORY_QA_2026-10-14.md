# mgmt-029 — Management meetings + minutes chain — exploratory QA (2026-10-14)

- **Build:** `feature/mgmt-029` after merging `origin/main` (mgmt-015, mgmt-026), Docker Compose project `mgmt029`
  (web `localhost:13029`, api `localhost:18029`), seeded demo accounts. Browser: Playwright Chromium (isolated; no shared Chrome).
- **Roles exercised:** partner (`partner.one@edusphere.local`), super admin, accountant, a fresh partnership-head staff user, signed out.
- **Spec:** `docs/superpowers/specs/2026-10-14-mgmt-029-management-meetings-design.md` (MM1–MM14), `DEC-SCOPE-214`.

## Scenarios (33 scripted checks + the e2e flow, all PASS on the final build)

| Area | Checked | Result |
|---|---|---|
| Happy path (AC) | Schedule → minutes → decision → task → staff completes task → "1 of 2 completed" (`tests/e2e/mgmt-029-meetings.spec.ts`) | PASS |
| Invalid input | Empty form (title / time errors), `javascript:` link refused in the browser, start in 2029 shows the API's field message | PASS |
| Duplicate submission | Double-clicking "Schedule meeting" sends one POST | PASS |
| Not started | A future meeting says "Minutes can be recorded once the meeting has started." | PASS |
| Refresh / back | Reload keeps the meeting; Back from Month returns to Week | PASS |
| Edit | Location change saved and shown; only the changed field is sent | PASS |
| Cancel | Dismissing the confirm keeps the meeting; accepting cancels it; no Edit afterwards; `/edit` says it can't be changed | PASS |
| Calendar | Week lists every day; month lists the meeting; bad `view`/`date` fall back to this week | PASS |
| Not found | Unknown and malformed ids show "This meeting does not exist." | PASS |
| Roles | Accountant and staff user → "Access unavailable"; super admin sees meetings and the Command Center entry; signed out → `/admin/login?next=…` | PASS |
| Participant slice | Staff user sees the meeting in Management tasks → Meetings, never the minutes | PASS |
| Layout | Desktop 1366, tablet 820, mobile 375: no horizontal scroll on the list, month view, new form and detail page | PASS |
| Console / network | No page errors, no 5xx. The only console line is the browser's log of the deliberate 422 (invalid-window check) | PASS |
| Images | No broken images | PASS |

## Issues found

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA29-01 | Low (UX) | partner | `/management/meetings/{id}` | Add a decision from the minutes; look at its row | The link to the decision reads distinctly from its status | The "Open" status badge sat next to an "Open" link ("Open Open") | **Fixed** — the links read "View" (accessible names unchanged); unit test + browser re-check |

Found during implementation (before QA) and fixed: two Python names that shadowed existing ones (`MeetingCreate`, `_meeting_text` in
`schemas.py`), renamed to `MgmtMeeting*` / `_mgmt_meeting_text`; a `components/MeetingForm.tsx` overwrite, restored from git (the new
form is `ManagementMeetingForm.tsx`).
