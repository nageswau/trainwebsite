# mgmt-003 — Business snapshot: exploratory QA (2026-10-12)

Stack: isolated Docker Compose project `mgmt003` (web `localhost:13033`, api `127.0.0.1:18033`), seeded demo accounts, Chromium via
Playwright. Branch `feature/mgmt-003`.

## Coverage

| # | Check | Result |
|---|---|---|
| 1 | Happy path: partner → Command Center → Business Intelligence → "Business snapshot" | 15 tiles, §3 order, as-of date; breadcrumb back to the Command Center works |
| 2 | Invalid input | N/A (read-only GET, no parameters) |
| 3 | Empty state | A zero renders as `0` (unit test); every figure is computable, nothing "not available yet" (MS16) |
| 4 | Server error | A failed read shows the existing "Access unavailable" card with the API's message (unit test, 403 path) |
| 5 | Loading | Server-rendered page (the mgmt-001 idiom); no client loading state |
| 6–7 | Back / refresh | Back returns to `/management`; reload re-renders the figures |
| 8 | Duplicate submission | N/A; two parallel GETs → 200, 200 (partner) and 403, 403 (accountant) |
| 9 | Signed out | `/management/snapshot` → `/admin/login?next=%2Fmanagement%2Fsnapshot`; API `401` |
| 10 | Wrong role | Accountant: no entry; API `403` "Operational access required"; page shows "Access unavailable". IT admin / overseas admin / trainer `403` (pytest) |
| 11–13 | Desktop 1440 / tablet 820 / phone 390 | No horizontal overflow at any width |
| 14 | Navigation | Partner sidebar: Command Center + Business snapshot; super admin keeps its own sidebar and reaches the page from the pillar link |
| 15–16 | Messages | Refusal text from the API shown verbatim |
| 17 | Broken images | See QA-02 |
| 18–19 | Console / network | No console errors or warnings; no failed API calls (only aborted Next.js link prefetches during navigation) |
| 20 | Redirects | None unexpected |
| — | Data accuracy | Trainers 9, Active Agents 5, Partner Schools 5, Partner Companies 6 match independent SQL counts on the same database |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA-01 | Low | partner, super_admin | `/management/snapshot` at 390 px | Open the snapshot on a phone | A compact grid, as other tile pages here use on phones (`.agent-network`, `.pipeline-tiles`: 2 columns) | 15 full-width cards in one column, about 2,150 px of scrolling | Fixed: two columns at ≤ 640 px (`.metric-grid.snapshot-tiles`); re-verified at 390 px |
| QA-02 | Info | all | `/management` at 390 px | Probe `document.images` | — | The sidebar logo reports `naturalWidth 0`: the sidebar is `display:none` on phones, so its lazy image never loads | Existing `PortalShell` behaviour, not a defect; not changed |
