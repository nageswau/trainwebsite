# tel-013 — exploratory browser QA (2026-10-07)

- **Build:** `feature/tel-013` @ `d57712e4`, isolated stack `tel013` (web :3113, API :8113), Edge 154 over CDP :9313 (Chrome was in use by
  other sessions). wa.me navigation was intercepted in the page so no external tab opened; the Playwright spec stubs wa.me the same way.
- **Data:** one telecaller manager, one IT telecaller and three leads assigned to the telecaller: Priya (mobile only, a product other
  than the template's), Rahul (mobile plus a +44 WhatsApp number) and Nora (no number). One WhatsApp template is linked to Cyber Security.
- **Role:** telecaller, unless a row names another role.

## Scenarios

| # | Scenario | Result |
|---|---|---|
| 1 | Header **WhatsApp** opens the composer; the picker lists active WhatsApp templates plus "Custom message" | Pass |
| 2 | Template render fills name + product; text editable; counter shown | Pass ("Hi Priya Sharma! Digital Marketing starts soon…", 73/1000) |
| 3 | Another product's template → warning, still sendable (D4) | Pass functionally; style issue QA-01 |
| 4 | Open WhatsApp → wa.me with +91 mobile and URL-encoded text (AC1); emoji and `&` encoded | Pass (`wa.me/919791350242?text=…%26…%F0%9F%99%82`) |
| 5 | WhatsApp number preferred over mobile (AC1) | Pass (`wa.me/447700900123`) |
| 6 | Confirm "Yes, record as sent" → "WhatsApp send recorded." and row "WhatsApp sent – 7 Oct 2026 – 10:48 AM · template · sender · text" (AC2) | Pass |
| 7 | Cancel closes the composer and logs nothing | Pass |
| 8 | Lead with no number → Send WhatsApp disabled with its reason, no header button (AC3) | Pass |
| 9 | Mobile 375 px: composer and list fit, no side scroll | Pass |
| 10 | Duplicate submission: two quick activations of "Yes, record as sent" | **Fail: QA-03** |
| 11 | Keyboard focus when the composer opens / after recording | **Fail: QA-02, QA-04** |
| 12 | Refresh, Not sent, delete, manager read-only, 409 on a no-number lead, console errors | Pass (Playwright `tel-013-whatsapp.spec.ts`, no console errors) |

## Issues

| ID | Severity | Page | Steps | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|
| QA-01 | Low | Lead detail → Messages | Pick a template for another product | A warning style (`form-warning`, the app's existing class) | Green success style (`form-message`) | Screenshot of the composer at desktop width |
| QA-02 | Low (a11y) | Lead detail | Press the header **WhatsApp** button with the keyboard | Focus moves into the composer (Template) | Focus stays on the header button; the composer opens further down the page with no cue | `document.activeElement` |
| QA-03 | Medium | Lead detail → Messages | Open WhatsApp, then activate "Yes, record as sent" twice in quick succession | One send recorded | Two rows, 14 ms apart (`GET …/messages` → two "Double click test" rows) | API response |
| QA-04 | Low (a11y) | Lead detail → Messages | Record a send | Focus lands on a stable control (Send WhatsApp) | Focus falls to `<body>` after the composer unmounts | `document.activeElement` = BODY |
| QA-05 | Info | Composer | Type emoji near 1000 characters | — | The textarea's `maxLength` counts UTF-16 units (an emoji = 2) while the API counts code points, so the client is the stricter side. No fix: the API never refuses what the UI allows | — |

All four defects are caused by tel-013 and are in scope; they are fixed in Phase 6 (see below).

## Fixes

Each fix had a failing vitest first (`tests/components/LeadMessages.test.tsx`). The browser scenario was then re-run in Edge on the rebuilt web
container, and the Playwright spec was re-run (pass).

| ID | Fix | Re-test |
|---|---|---|
| QA-01 | The mismatch note uses `form-warning` | Amber text (`rgb(180, 83, 9)`), class `form-warning` |
| QA-02 | The composer focuses its Template picker on open. The picker is no longer disabled while templates load ("Custom message" is valid then) | `document.activeElement` = the Template `SELECT` |
| QA-03 | `record()` is guarded by an in-flight ref | Two quick activations → 1 row |
| QA-04 | Focus returns to Send WhatsApp when the composer closes | `document.activeElement` = `BUTTON Send WhatsApp` |
