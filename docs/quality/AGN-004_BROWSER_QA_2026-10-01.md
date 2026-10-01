# AGN-004 — Browser QA, 2026-10-01

**Scope:** exploratory QA of AGN-004 (agency students with and without a login; Staff scope) in an isolated Chrome
(own profile, CDP port 9224) driven by Browser Use, against the isolated Compose project `agn004` (web 3004 / API 8004),
branch `feature/agn-004-agent-students`. QA data (isolated database only): agency `EDU` with Staff `EDU-S001`/`EDU-S002`, one
student assigned to each and one unassigned, a second agency + Master, an `overseas_student` login. No code changed during the
first pass; fixes followed on the owner's instruction ("Fix the issues").

## Findings and fixes

| ID | Severity | Role / page | Finding | Fix (commit) | Re-verified in the browser |
|---|---|---|---|---|---|
| QA-01 | Medium | Master, Staff / Students | Panel ~1,530 px (desktop) / ~1,860 px (mobile) down, below the old roster, squeezed into a 493 px half column | Owner decision: the page leads with a "Students" header and the panel, full width; then the roster; then Link student (`61ac716`, `cf4caed`) | Panel top 243 px, 1005 of 1005 px wide |
| QA-02 | Medium | Master, Staff / Students | Two "Students" lists; the top one only counts students with a login | The AGT-002 roster is retitled "Application status — students who have a login" (`61ac716`) | Headings "Students", "Application status" |
| QA-03 | Medium | Master, Staff / edit form | A sidebar link (and Cancel) discarded unsaved edits without asking | In-app link guard (the `PsychometricResultsForm` pattern) + Cancel asks while dirty (`cc4beac`) | Cancel and sidebar both asked; page kept |
| QA-04 | Medium | Master / Add student | `98450 12345` vs stored `+91 98450 12345` not warned | Owner decision: phones match on their last 10 digits; under 10 digits must match exactly (`44d83ee`) | `098450 12345` warns, both matches listed |
| QA-05 | Low | Master / edit form | Server 422 shown as a form alert without the field | A 422 is mapped onto its field (`aria-invalid`, description, focus) (`cc4beac`, `ab025b3`) | Error under Full name, red border |
| QA-06 | Low | Master, Staff / Students | Refresh/Back lost search, Show archived, page | Filters kept in the URL (`?q=&archived=1&page=`), the `AgentApprovalPanel` pattern (`cf4caed`) | `?q=Priya&archived=1` restored after refresh |
| QA-07 | Low | Master / 375–320 px | Add student, Previous, Next under 44 px | Every panel button 44 px on phones (`cf4caed`) | No panel button under 44 px at 320 px |
| QA-08 | Low | Master / duplicate warning | "Save student" stayed enabled beside "Save anyway" | Main Save disabled while the warning is open (`cc4beac`) | Disabled |
| QA-09 | Low | Master / detail | Detail 500 had no Retry | Retry button on the detail error (`cf4caed`) | Retry reopened the detail |
| QA-10 | Cosmetic | Master / cards | Emails broke mid-word | Break points after `@` and `.` (`<wbr>`) (`cf4caed`) | 3 break points in the first card |

## Passed without change (first pass)

Happy path (add, search, view, edit, save, announced messages); client validation (focus to first invalid field, nothing
sent); triple-click Save → one POST; archive/unarchive with focus moves; Staff: Team/Commissions hidden, assigned-only list,
other Staff's / unassigned student `404`, archive/assign `403`, server-owned field `422`, Team/Commissions pages "Access
unavailable"; other agency's Master `404` + empty list; signed out → login with `next=`, API `401`; student login → `403`;
list network failure → message + working Retry; failed save keeps the entry; loading states; no horizontal overflow at 1366 /
768 / 375 / 320 px; logo loads; no console errors or uncaught exceptions; every 4xx/failed request in the log was induced.

## Limits of this environment (stated, not hidden)

The isolated Chrome window does not run `requestAnimationFrame` (measured: paused even with the tab activated) and CDP key
events did not reach the page. Focus moves (they use the project's `lib/focus.refocus`, which waits for a frame) and
keyboard-only operation could therefore not be observed here. They are covered by vitest (`AgentStudentForm.test.tsx`,
`AgentStudentsPanel.test.tsx`, which wait for the frame) and the Playwright keyboard-only test (`agn-004-agent-students.spec.ts`).

## Evidence after the fixes

Web vitest 113 files / 1194 tests; `tsc` 0; `eslint .` 0 errors / 31 warnings (baseline); `npm run build` 0. API: AGN-004 files +
`test_agt_002_referrals` + `test_enh_031_lookups_students` 132 passed. Playwright (`--workers=1`) AGN-004 + agt-002 + agn-001 +
enh-031 + agt-004: 13 passed. Screenshots: `.superpowers/sdd/2026-09-30-agn-004-agent-students/qa-shots/` (git-ignored).
