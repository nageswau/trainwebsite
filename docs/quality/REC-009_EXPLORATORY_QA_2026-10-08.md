# rec-009 Candidate master — exploratory browser QA (2026-10-08)

## Setup
- **Stack:** compose project `rec009` (web `:3109`, API `:8109`), seeded with `python -m app.seed`.
- **Browser:** an isolated Microsoft Edge 154 with a throwaway profile, driven over CDP `:9333` by a Playwright script. The
  `browser-use` CLI was blocked by Windows Application Control.
- **Accounts:**
  - `placement@edusphere.local` (recruiter)
  - `placement.manager@edusphere.local`
  - `hr@edusphere.local` (hr_team)
  - `student.it@edusphere.local`
- **Viewports:** 1366×900, 768×1024 and 375×812.
- **Scenarios covered:**
  - The happy path, invalid inputs, the empty state, refresh, Back, Cancel and a double click.
  - The duplicate panel (on blur and on save).
  - Archive and restore (the confirm dismissed, then accepted).
  - Resume uploads: no file, PNG, PDF v1, then v2. The download name.
  - Role checks: signed out, HR, student, manager.
  - A malformed id, horizontal overflow, console errors and failed requests.

## First pass (no code changed): 41 checks passed and 5 issues were found

| ID | Severity | Role | Page | Steps | Expected | Actual | Fixed |
|---|---|---|---|---|---|---|---|
| QA-01 | Low | recruiter | candidate edit | Clear the mobile of a candidate with no email → Save changes | "Enter a mobile number or an email." | "Enter the a mobile number or an email." | Yes: `missingRequired` wording plus unit cases |
| QA-02 | Low | recruiter | add candidate | Passing year 1800 → Add candidate | One plain sentence | "Passing year: Input should be greater than or equal to 1950" (pydantic wording); the same for experience, notice period and salaries | Yes: `_whole`/`_salary` validators ("… must be between 1950 and 2100") plus exact-message tests |
| QA-03 | Medium | hr_team | candidate list | HR opens Candidate Master | A list with working filters, no errors | Console `403` from `/recruiter/catalogue/candidate-sources` (closed to hr_team by rec-002 C3); the Source filter holds only "All sources" | Yes: read-only roles get no source picker and no catalogue call (`sourceFilter`); rows still show the source. C3 is not widened |
| QA-04 | Low | recruiter | add candidate | Look at the form at 1366 px | The inputs of a row line up | Hints sat between the label and the input, so the inputs were out of line and fields without hints stretched taller | Yes: hints moved under the inputs and the grid top-aligned (first-row input tops 271/271/271/271) |
| QA-05 | Low | recruiter | add → detail | Add a candidate, then press Back | Back returns to the list | Back showed the blank create form again | Yes: `router.replace` to the new candidate |

Not issues:
- The `422` and `415` "Failed to load resource" console lines are the browser logging refused requests. The page shows the API's
  sentence.
- `ERR_ABORTED` on the catalogue request when an edit is cancelled is the form's fetch being aborted on unmount.

## Re-run after the fixes: 47 checks passed, 0 failed
- The five checks above now pass.
- The rest of the pass still holds:
  - A double click creates one candidate.
  - A salary reads `4,50,000`.
  - The duplicate panel appears on blur and opens the existing candidate.
  - An archived candidate has no edit or upload, and is hidden from the default list but listed under "Show archived only".
  - There is no horizontal page scroll at 768 or 375 px on the list, the add form or the detail.
  - HR is read-only.
  - A student gets "Your role cannot view candidates".
  - A signed-out visit goes to `/it/login`.
- **Screenshots:** in the session scratchpad. They are not committed: they hold demo data only, and the e2e spec covers the flow.
