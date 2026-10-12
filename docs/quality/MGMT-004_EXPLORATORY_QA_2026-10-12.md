# mgmt-004 — Management ledger — exploratory browser QA (2026-10-12)

- **Build under test:** `feature/mgmt-004` (production web image, isolated stack `mgmt004`, `http://localhost:13404`, API `:18404`).
- **Tools:** Playwright (Chromium, isolated contexts per role) driven by a scripted exploratory pass (51 checks), plus the
  committed spec `tests/e2e/mgmt-004-ledger.spec.ts`. Console errors, page errors and 5xx responses were captured on every page.
- **Roles:** accountant (`accountant@`), partner one and two (`partner.one@`, `partner.two@`), super admin, IT admin.
- **Viewports:** 375×800, 768×1000, 1280×900 (list, new entry, entry, categories).

## Covered

Happy path (record → receipt → edit → submit → reject with reason → fix → resubmit → approve → reverse → second partner approves the
reversal → list shows −amount); empty form, negative / 3-decimal / too-large amounts, future date (each message on its field); empty
state; malformed filters and ids; unknown entry; cancel / back / forward / refresh; double-click submit (one POST); concurrent approval
by two partners (one "Entry approved.", the other 409 "Only a submitted entry can be approved or rejected"); a partner cannot decide
their own reversal; accountant has no Approve; duplicate and deactivated categories; super admin refused on every ledger page and has no
Ledger entry in the Command Center; signed-out and IT admin sent to sign-in; receipt download name built server-side; no horizontal page
overflow, no broken images, no console errors, no 5xx at any viewport.

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA-01 | Low | accountant, partner | `/management/ledger/{id}` | Submit a draft (accountant), or approve a reversal (partner) | "Submitted for approval." / "Entry approved." confirmation | The actions card rendered nothing once the refreshed entry left no action, so the confirmation vanished (status pill did update) | **Fixed** — the card stays while it has a message (`LedgerEntryActions`; vitest "keeps the confirmation…") |
| QA-02 | — | accountant | `/management/ledger/{id}/edit` | Edit a rejected entry | "Saving a change returns this rejected entry to draft." hint | Script asserted before the client navigation finished | **Withdrawn** (QA script timing; hint shown) |
| QA-03 | Low | all | `/management/ledger` at 375 px | Open the list on a phone | Readable rows | The Entry column squeezed to one word per line | **Fixed** — the table scrolls sideways in its own focusable region (min width 720 px) |
| QA-04 | Low | all | `/management/ledger/{id}` | Open an entry tagged with a channel | "Exhibition/Event" | The raw key `exhibition_event` | **Fixed** — `SOURCE_LABEL` (vitest asserts the label) |

Re-run after the fixes: **0 failing of 51** exploratory checks; Playwright mgmt-001/002/004 **11 passed**.

## Not in scope / observations

- The shared QA database holds many pytest categories ("Cat xxxxxxxx") and entries; they appear in the lists. Test data only.
- The IT admin cannot sign in at `/admin/login` (signs in at `/it/login`); the API-level 403 for `it_admin` is covered by pytest AC3.
