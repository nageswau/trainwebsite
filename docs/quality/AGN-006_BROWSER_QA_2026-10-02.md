# AGN-006 — Agent Student Counseling Record: Browser QA (2026-10-02, first pass)

**Scope:** independent exploratory QA of the Counseling section on the agency student detail (Students page), first pass — no code
changed. **Environment:** compose project `agn006` (web http://localhost:3006, API 8006, built from `b86cc3b`, `python -m app.seed`
applied), branch `feature/agn-006-counseling-record`. Isolated Chrome 154 (own throw-away profile, CDP 9306) driven by browser-use with
trusted CDP mouse/keyboard input; a page probe recorded console errors, page errors, unhandled rejections and every `fetch` with its status.
**Test data** (created through the real API): agency A = demo agency (Master `agent@edusphere.local`; staff S1 `EDU-S001` and S2
`EDU-S002`; students "QA Asha" assigned to S1, "QA Unassigned", "QA Archived" (archived), a long-name student, the seeded student with a
login); agency B ("QA Beta Overseas", its own Master and one student).

**Tooling notes (not product findings):** (1) submitting the password form left Chrome's password-save prompt holding CDP input, so
sessions were signed in through the real `POST /api/v1/auth/login` from inside the page (same cookie; the login screen is not AGN-006);
(2) `requestAnimationFrame` does not run in a non-active headless tab — after activating the tab, focus moves behaved as designed;
(3) the first probe version mis-read Next.js prefetch `URL` objects and produced false "Failed to fetch RSC payload" errors — fixed in
the probe, excluded below.

## Findings

| ID | Severity | Role | Page | Finding |
|---|---|---|---|---|
| QA6-02 | Medium | Master / Staff | Students → detail → Counseling form | Expired session on Save shows the raw API text "Not authenticated"; no way to sign in again |
| QA6-01 | Minor (UX / hierarchy) | All agents | Students → detail → Counseling | The "Counseling" section heading (and the form title) render at 12.45 px — smaller than the 15 px field labels under them |
| QA6-03 | Minor (UX) | Master / Staff | Students → detail → Counseling form | Student archived elsewhere while the form is open: Save → "Unarchive this student first", but the panel still shows the student as active with no way to act on the message |

### QA6-02 — Expired session shows "Not authenticated" (Medium)
- **Steps:** sign in as the Master → Students → open "QA Unassigned" → Record counseling → type a career interest → the session ends
  (cookies cleared, as after expiry or sign-out in another tab) → Save counseling.
- **Expected:** a plain message that the session has expired and a way to sign in again (the AGN-021 QA-03 fix: "Your session has
  expired. Sign in again"), the entry kept.
- **Actual:** `role="alert"` "Not authenticated" (the API's raw text); the entry is kept; no sign-in link; Save keeps failing.
- **Evidence:** `PUT /api/v1/workflows/overseas/agent/crm/students/{id}/counseling → 401 {"detail":"Not authenticated"}`; no console error.
  Screenshot `23-expired-session.png`.

### QA6-01 — Section heading smaller than its labels (Minor)
- **Steps:** open any student with a counseling record (desktop or phone).
- **Expected:** the "Counseling" heading reads as the section title — at least the size of the student-detail heading (15 px) and
  clearly above the field labels.
- **Actual:** `h5` with no app style → browser default 12.45 px bold; labels (`dt`) are 15 px bold, the panel's `h4` 15 px. On a
  320 px phone "Counseling" and "Edit counseling for …" look like fine print with a large gap (20.8 px margins) between them.
- **Evidence:** computed styles `H5 12.45px/700`, `DT 15px/700`, `H4 15px/700`; no other `h5` exists in the app. Screenshots
  `11-mobile320-form.png`, `10-mobile375-view.png`.

### QA6-03 — Archived while editing: message not actionable in place (Minor)
- **Steps:** Master opens "QA Unassigned" → Record counseling → types → the student is archived (another tab / another Master) → Save.
- **Expected:** the user learns the student was archived and the panel reflects it (or the form closes read-only).
- **Actual:** `409` "Unarchive this student first" in the alert; entry kept; the panel still shows the student as active with Edit /
  Record counseling; there is no Unarchive control in the panel, and a staff member cannot unarchive at all.
- **Evidence:** `PUT …/counseling → 409 {"detail":"Unarchive this student first"}`. Screenshot `24-archived-meanwhile.png`.
  (Also raised as Minor #5 by the whole-branch review.)

## Checklist

| # | Check | Result |
|---|---|---|
| 1 | Happy path | ✅ Master records all six fields; "Counseling saved for QA Asha …"; record shows "Yes — 02 Oct 2026, by Global Admissions Agent", ₹25,00,000.00 (typed "25,00,000"), remarks with line breaks; one `PUT … 200`. Assigned staff edits; the completed stamp is kept (yes → yes) |
| 2 | Invalid inputs | ✅ UI: "-500" → "Budget cannot be negative"; "1500,50" → "Use a full stop for decimals…"; "12.345", "100000000", "abc", "1e5" → range/decimals message; 2001-char remarks → "2001 / 2000" + "Must be 2000 characters or fewer"; each focuses the field with `aria-invalid`, **no request sent**. API (tampered client): negative 422, "1500,50" 422, server-owned `completed_by` 422 |
| 3 | Empty states | ✅ "Counseling not recorded yet." + Record counseling; login student → "Counseling is recorded only for students without a login." (no action); archived → read-only, no action |
| 4 | Server errors | ✅ 500 → "Unable to save counseling.", entry kept, focus back on Save · ⚠️ 401 → QA6-02 · 409 → message shown (QA6-03) |
| 5 | Loading states | ✅ 3 s latency: button "Saving…", fieldset disabled, `aria-busy="true"`, entry kept; success after |
| 6 | Cancel / back | ✅ unchanged Cancel closes and returns focus to "Edit counseling"; Cancel with changes asks "You have unsaved counseling changes. Leave without saving?" and keeps the form on No; unchanged Save sends nothing |
| 7 | Refresh | ✅ with unsaved input the browser's leave-site dialog appears (input kept on Stay); after save + reload the record reads back exactly |
| 8 | Duplicate submission | ✅ two trusted clicks → exactly one `PUT` |
| 9 | Unauthorized user | ✅ logged out: page → `/overseas/login?next=…`, API `401`; other agency's Master → `404`; other staff (S2) does not see the student, API `404`; S1 on an unassigned student → `404`; unknown id → `404` |
| 10 | Incorrect role | ✅ overseas student → "Access unavailable", API `403 "This role cannot perform this operation"` |
| 11 | Desktop layout (1424) | ✅ no overflow; budget amount + currency side by side; checkbox row 44 px · ⚠️ QA6-01 heading size |
| 12 | Tablet layout (768) | ✅ no overflow; budget side by side |
| 13 | Mobile layout (375, 320) | ✅ no overflow; budget stacks; checkbox row 44 px; Save 44 px tall · ⚠️ QA6-01 |
| 14 | Navigation | ✅ Tab order: completed → career → course → country → amount → currency → remarks → Save → Cancel; Escape does not close the panel while the form is open; sidebar link with unsaved input asks first; View another student with unsaved input asks first (review #2 fix) and keeps the input on No |
| 15 | Success messages | ✅ "Counseling saved for {name}." in the list's existing status region; focus moves to the Counseling heading |
| 16 | Error messages | ✅ field messages + alert texts above · ⚠️ QA6-02 raw "Not authenticated" |
| 17 | Broken images | ✅ the only image (portal logo, `/_next/image?url=/brand/logo-dark.png`) loads (`naturalWidth > 0`) |
| 18 | Console errors | ✅ none from the app across the pass (probe artefact excluded, see tooling note 3) |
| 19 | Failed network calls | ✅ only the deliberate ones (offline `PUT` → "The request did not complete… your entry is kept.", then a successful retry; the expected 401/404/409/422 checks) |
| 20 | Unexpected redirects | ✅ none; logged-out redirect keeps `next=` |

**Staff Activity (C7):** S1's save is listed for the Master as "Recorded counseling" — subject "QA Asha …", fields `["remarks"]`; the
response contains no remark text. **Not AGN-006 (noted only):** the sidebar logo renders very small inside its white tile (shared
portal shell).

**Status:** first pass complete — 1 Medium, 2 Minor; nothing fixed (as instructed). Screenshots are in the session scratchpad
(`shots/`), not committed.
