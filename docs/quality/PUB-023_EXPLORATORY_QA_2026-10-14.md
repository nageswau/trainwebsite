# PUB-023 Country flags — exploratory QA (2026-10-14)

Stack: worktree `../pub-023`, compose project `pub023`, web :3023, api :8023, seeded with `app.seed`. The database also holds
leftover pytest rows (`Testland`, `Dtuland …`, no ISO code), which list first on several screens.
Method: a throwaway Playwright script (not committed) visited each screen. It counted `img.country-flag`, checked each image
decoded (`naturalWidth > 0`), and took a screenshot, and the screenshots were reviewed by eye.

| # | Screen (spec §3.1) | Role | Result |
|---|---|---|---|
| 1 | /overseas/countries cards (search "Germany") | public | PASS: `/flags/de.svg` in the card tile (large) |
| 2 | /overseas/countries/germany heading | public | PASS: `/flags/de.svg` in the `<h1>` |
| 3 | /overseas home destination cards | public | PASS: 2 flags (AU, CA) among the first 8 cards; the other cards are code-less test countries with the name only (F3) |
| 4 | /overseas/courses (search "Sweden") | public | PASS: 2 × `/flags/se.svg`. Unfiltered page 1 shows only code-less test courses (no flag, by F3) |
| 5 | Agent partner universities list | agent (`agent@edusphere.local`) | PASS: 8 flags, all loaded |
| 6 | University Master table | super admin | PASS: 13 flags; code-less test countries show the name only |
| 7 | Partnership search | super admin | PASS: 13 flags |
| 8 | University detail (a US university) | super admin | PASS: `/flags/us.svg` in the Country row. A code-less test university shows the name only (F3) |
| 9 | Partnership map, table view | super admin | PASS: 9 flags |
| 10 | Global dashboard country rows | super admin | PASS: 9 flags; other count tables unchanged |
| 11 | University form country picker, typing "Jap" | super admin | PASS: the Japan option shows `/flags/jp.svg` (white flag visible thanks to the hairline border) |
| 12 | 375px phone width, countries page | public | PASS: flag shown, no horizontal overflow |

Broken images: 0 across all screens. `python scripts/check_flag_assets.py`: `All 249 ISO codes from migration 0101 have a flag SVG.`

Playwright: `upc-002-country-master.spec.ts` (with the PUB-023 case) passed in full. `ovs-001-discovery.spec.ts` had 2 failures,
"country list shows a seeded destination" and "university list is searchable". Both are data, not code: the shared test
database holds 75 visible countries (pytest leftovers), so "Germany" and the seeded university are not on page 1. This is the
known worktree issue in the project notes, and flags don't change ordering or paging.

Findings: none in PUB-023 scope.
