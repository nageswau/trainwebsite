# mgmt-027 — Discussions & decisions — exploratory browser QA (2026-10-12)

- **Stack:** isolated Docker Compose project `mgmt027` (web `http://localhost:13027`, api `127.0.0.1:18027`), `python -m app.seed`, plus
  two QA-only users (an overseas `partnership_manager` "Uma University BDM" and an inactive telecaller).
- **Tool:** Playwright (Chromium) script, 34 checks, desktop 1280, tablet 768, mobile 375. Then `tests/e2e/mgmt-027-discussions.spec.ts`.
- **Roles:** partner, super admin, accountant, the responsible staff member, signed out.

## Findings

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA-01 | Medium | partner | `/management/discussions/new`, attachments | Fill the form, click "Save discussion" twice before the page re-renders (two synchronous clicks) | One discussion | Two discussions with the same topic (`rows=2`); the busy state only disables the form after a re-render. Same for Upload | Fixed: an in-flight ref guard in `DiscussionForm` and `DiscussionAttachments`; vitest + browser re-test (`rows=1`) |
| QA-02 | Low | partner | discussion form | Submit with a responsible person and no decision, then type the decision | The decision error goes away | The old error stayed until the next submit | Fixed: changing a field drops its error; vitest |

## Checked and passing (after the fixes)

Signed-out redirect to `/admin/login?next=…` and the sign-in card on `/account/management-decisions`; Command Center link; empty-topic
and decision-before-responsible errors; inactive staff not offered; Japan example saved with participants, decision, responsible,
deadline, status; shareable + private attachments; wrong file type explained (415); refresh, filter, back and cancel; Pending
decisions panel; no horizontal page scroll on list/form/detail/my-decisions at 768 and 375; no broken images; the responsible person
sees only "decision — deadline — status" and the shared file (no topic, notes or private file), updates the status (persists after
refresh), downloads the shared file; the responsible person, the accountant are refused the list (access card) and the notes API (403);
super admin sees the list and the updated status; unknown and malformed ids show "Discussion not found".

Console/network: only the expected 401 (signed-out session check) and 415 (the deliberate wrong-file upload). No 5xx, no page errors.
On phones the discussions table scrolls sideways inside its own focusable region (the ledger's convention), not the page.
