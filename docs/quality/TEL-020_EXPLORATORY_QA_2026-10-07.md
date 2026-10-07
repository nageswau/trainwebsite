# tel-020 — exploratory QA (2026-10-07)

Stack: isolated `tel020` (web :3120, API :8120, migration head `0098_tel_settings`, seeded; SMTP deliberately unset, so email deliveries
record `not_configured`). Browser: isolated Edge (CDP :9420, own profile) driven by Browser Use; Playwright `tel-020-alerts.spec.ts`.

## Scenarios

| # | Role | Scenario | Result |
|---|---|---|---|
| 1 | super_admin → telecaller | Manual assignment of a website lead → "New lead assigned" notice, Notifications nav badge | PASS (badge "1 unread"; body `Alert Lead … (LD-000264) is now assigned to you.`; no phone) |
| 2 | worker (Celery) | Live beat task twice on an aged hot, first-call-pending lead with a follow-up due in 10 min | PASS: run 1 `created 7`, run 2 `created 0, duplicate 7`; Follow-up due, Lead not contacted (24 h), Hot lead pending (4 h) each once, each with one `tel_alert` email delivery |
| 3 | telecaller | Open a notice → lead page; return → badge 3 → 2 | PASS |
| 4 | telecaller | Mobile 390 px / tablet 820 px notifications page | PASS (no horizontal scroll; screenshot reviewed) |
| 5 | telecaller | `/telecaller/manager/alerts` and `GET /telecaller/settings` | PASS (page "Telecaller manager role required" + dashboard link; API 403) |
| 6 | manager | Alert settings: 0, 169, blank, 2.5 | PASS (native validation message, no request sent) |
| 7 | manager | Save 36 / 6 → success message; reload → persisted, "Last changed by …" | PASS |
| 8 | manager | Bypass the form: PUT 2.5 and `"<script>"` | PASS (422 "…Input should be a valid integer") |
| 9 | manager | Mobile 390 px settings page | PASS (no horizontal scroll; screenshot reviewed) |
| 10 | both | Console errors / failed requests (Playwright listener over both journeys) | PASS (none) |
| 11 | panel | Loading, load failure + retry, refused save, dropped connection, double click | PASS (vitest `TelecallerAlertSettingsPanel.test.tsx`) |

Defaults restored afterwards (`PUT` 24 / 4 for both teams → 200).

## Issues

| ID | Severity | Where | Finding | Disposition |
|---|---|---|---|---|
| QA-T1 | test-only | `tel-020-alerts.spec.ts` | The "no phone on the page" regex matched the 13-digit stamp in names | Fixed: assert the exact phone string is absent |
| QA-T2 | tooling | Browser Use `fill_input` | Does not update React-controlled inputs (login form, settings inputs); native setter + `input` event used instead | Not an app defect (Playwright `fill` works) |
| — | observation | shared `TelecallerCataloguePage` | Large gap between the intro and the first card on mobile | Pre-existing layout shared by every manager page; out of tel-020 scope |

No tel-020 defects open.
