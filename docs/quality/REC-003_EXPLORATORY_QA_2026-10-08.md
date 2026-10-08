# rec-003 — Exploratory QA (2026-10-08)

Stack `rec003` (web :3123, API :8123, `docker compose -p rec003 -f docker-compose.yml`), seeded demo data. Browser: an isolated Edge
(CDP :9333, temporary profile) driven by browser-use, plus a temporary Playwright sweep (console errors, failed requests, horizontal
overflow, full-page screenshots at 1366 / 820 / 390 px for recruiter, placement manager and super admin; deleted after the pass).

## Covered
| Area | Result |
|---|---|
| Happy path (recruiter create → detail, code `CMP-…`, assigned to self) | Pass |
| Invalid input: empty name, `javascript:` website, `12a` employees | Pass — client checks for name/number, server 422 shown at the Website field with `aria-invalid` |
| Duplicate name (other case) → warning, Go back keeps the entry | Pass |
| Double submit (two clicks) | Pass — one company created |
| Refresh after create | Pass — "created" notice not repeated |
| Cancel / leave with unsaved input | Pass — leave guard asks first |
| Edit, archive, archived hidden, Show archived | Pass |
| Manager: unassigned create, assign to a report, history | Pass |
| Assigned BDM picker → BDM read-only view (no actions; Add refused) | Pass after QA-04 |
| Wrong roles (hr_team, it_admin, it_student) | Pass — "Recruiter role required" on list and add |
| Signed out | Pass — `/it/login?next=…` |
| Unknown / malformed company id | Pass — "Company not found" |
| Console errors, failed network calls, broken images | None |
| Horizontal overflow at 1366 / 820 / 390 | None |

## Issues
| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA-01 | Low | all | `/recruiter/companies` (desktop) | Open the list | Table uses the card width | Table shrink-wrapped to its content | Fixed: `width: 100%` |
| QA-02 | Medium | all | `/recruiter/companies` (390 px) | Open the list on a phone | Readable rows | Columns squeezed until words broke per character; right columns clipped | Fixed: the house `.telecaller-list` card layout (labelled cells) — vitest + screenshot re-check |
| QA-03 | Low | super_admin | `/recruiter/companies` | Open as super admin | A heading for all companies | "Your team's companies" | Fixed: per-role heading and intro |
| QA-04 | Low | bdm | `/recruiter/companies[/id]` | Open as the Assigned BDM | The BDM's own menu and a read-only intro | Empty sidebar; recruiter wording | Fixed: BDM menu, read-only intro |

After the fixes: rec-003 vitest 13/13, Playwright rec-003 3/3 and neighbours (rec-001, rec-002, EMP-001…005, ADM-007, RPT-001) 29/29.

## Not changed (outside rec-003)
- `tests/lib/dateZoneSweep.test.ts` already fails on `main` with 27 findings in other modules; rec-003 adds none.
- Existing employer self-registered companies keep no lead source (only new registrations get "Website", D3); they are in the unassigned queue.
