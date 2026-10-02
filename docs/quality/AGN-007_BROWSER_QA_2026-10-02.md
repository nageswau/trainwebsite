# AGN-007 — Agency Universities and Student Shortlist: Browser QA (2026-10-02)

**Scope:** exploratory browser QA and final browser verification of `AGN-007` (`DEC-SCOPE-049`): the agent portal's Universities
page (agency-private university list) and the Shortlist section on the agency student detail. **Environment:** compose project
`agn007` (web http://localhost:3007, API 8007, built by the owner from the branch at each stage below), branch
`feature/agn-007-student-shortlist`. Isolated headless Chrome (own throw-away profile under `%TEMP%\agn007-qa\chrome-profile-*`,
CDP 9237) driven by browser-use with trusted CDP mouse/keyboard input; a page probe recorded console errors, page errors, unhandled
rejections and every `fetch` with its status. Scripts, screenshots and data lived in the throw-away QA workspace
`%TEMP%\agn007-qa\` (not committed).

**Test data** (created through the real API): agency A (Master, an activated Staff member; students Assigned to that Staff member,
Unassigned, Archived, Linked (with a student login) and Paging (50 entries)); agency B (its own Master and one student); the
seeded demo `counselor@edusphere.local` for the wrong-role check. Fresh agencies were created for each pass.

**Tooling notes (not product findings):** a JS value setter bypassed React's input tracking (switched to real typing); off-screen
clicks missed (added `scrollIntoView`); an em-dash encoding mismatch in a text match; the server lowercases emails.

## Pass 1 — exploratory (at `121f188`, no code changed during the pass)

Happy path (Master and Staff), invalid input, empty states, simulated 5xx + Retry, offline save (entry kept), slow loading, cancel
and Escape, refresh, duplicate submission (3 clicks → 1 row), unauthenticated (redirect + 401), wrong role (403), Staff read-only
Universities + 404 for an unassigned student, cross-agency 404, archived 409, 375/820/1440 px with no horizontal overflow, no
broken images, no console errors — passed. Findings:

| ID | Severity | Role | Page | Finding | Fix (test-first, `478e993`) |
|---|---|---|---|---|---|
| QA-01 | Medium | Master / Staff | Shortlist / university form | Save `disabled` while focused dropped keyboard focus to `<body>`; Escape then did nothing | Save is `aria-disabled` with an in-flight guard |
| QA-02 | Medium | Master / Staff | Both panels | Focus after a save missed its target: the animation frame ran before React committed the post-`await` state | `lib/useFocusAfterRender.ts` (focus applied after the commit) |
| QA-03 | Minor | All agents | Universities | A search with no match said the agency "hasn't added any" | "No universities match “q”." + Clear search |
| QA-04 | Minor | All agents | Shortlist card | Catalogue link styled as plain text by the global `a` rule | Brand colour + underline |
| QA-05 | Minor | Master / Staff | Shortlist form | Dangling "Name —" when the city is empty | `optionLabel` |
| QA-06 | Minor (UX) | Master / Staff | Shortlist form | 1,288-option university select (owner chose a filter box) | "Filter universities" box narrowing both groups, current choice kept |
| QA-07 | Minor | All agents | Both panels | Section/form headings smaller than their labels | 18 px / 16 px (levels unchanged) |
| QA-08 | Minor | All agents | Both panels | Raw 5xx text shown | "The server couldn't complete this. Please try again in a moment." |

**Re-verified in the browser** (owner rebuilt web at `af4533c`): QA-01 focus stays on Save after a 409 and Escape closes the form
(focus to Add); QA-02 focus returns to Edit / Add as designed after each save; QA-03 message + Clear search; QA-04 rgb(7,85,185)
underlined; QA-05 0 dangling dashes; QA-06 "Trinity QA" → "1 of 1290 universities"; QA-07 h5 18 px / h6 16 px; QA-08 wording;
375/820 px overflow 0, broken images 0, console errors 0, failed calls 0.

## Pass 2 — final verification (after merging `main` @ `8f0000d` (AGN-006) at `27efed8`)

All acceptance criteria passed except AC12 → **QA-09** (Low, Master, Team → staff Activity): the three shortlist actions showed as
"Other activity" because `lib/agentStaff.ts` `ACTIVITY_LABELS` had no labels for them. Fixed test-first in `f8b2e1f`
(`AgentStaffActivity.test.tsx`: shortlist labels + "every allow-listed action has a label"; RED 2 → GREEN). Re-verified at
`f8b2e1f`: "Removed a university from a shortlist / Edited a shortlist entry / Added a university to a shortlist · Final Assigned
…", 0 "Other activity" rows (`46fc620`).

## Pass 3 — verification-before-completion run (at `46fc620`, script `f07_verify.py`)

| AC | Browser behaviour observed | Result |
|---|---|---|
| AC01 catalogue entry saves | Catalogue university + its course saved; the card shows the course | PASS |
| AC02 free-text entry saves | Agency university + typed course "Typed V…" saved and shown | PASS |
| AC03 course must belong to the university | Three invalid bodies (other university's course; both universities; catalogue course on an agency university) → `[422, 422, 422]`, entry total unchanged | PASS (DB CHECKs: schema tests only) |
| AC04 invisible to other agencies | Agency B: name not on its Universities page; student shortlist `404`; PATCH of A's university `404` | PASS |
| AC05 invisible to `/public` | Public universities page and `/public/universities`, `/public/overseas-courses`, `/public/countries` contain neither the name, its country, nor the typed course | PASS |
| AC06 Master Full / Staff View / Add Master-only | Master added "Verify Uni V16648" ("… added."); Staff sees it, no Add button, `POST` → `403` | PASS |
| AC07 Staff writes only for assigned students | Staff added an entry for the assigned student; unassigned student `404` and not listed | PASS |
| AC08 archived read-only, linked writable | Archived `GET 200`, `POST 409`; linked `POST 201` | PASS |
| AC09 duplicates / in-use | Same name+country in another case → 409 message; deleting an in-use university → 409 message, nothing removed | PASS |
| AC10 caps | 51st entry → `422` | PASS (500-university cap and concurrent adds: backend tests only) |
| AC11 paging | "Showing 1–20 of 50" | PASS |
| AC12 audit / staff activity | "Added a university to a shortlist …", 0 "Other activity" rows | PASS |
| AC13 responsive / accessible | Horizontal overflow 0 on Universities and student detail at 375, 820 and 1440 px; broken images 0 | PASS |
| — unauthenticated / wrong role | `GET` universities `401` and the page redirects to sign-in; counselor `403` | PASS |
| — console / network | 0 console errors, 0 page errors, no unexpected failed calls | PASS |

**NOT TESTABLE in a browser** (covered by backend tests): AC03 database CHECK constraints (`test_agn_007_schema.py`), the
500-university cap and concurrent adds (`test_agn_007_universities.py`, `test_agn_007_isolation.py`).

**Open findings:** none.
