# hrc-020 — Saved searches and restricted export (design)

- **Decision:** `DEC-SCOPE-401` (Q-21 and the open points below answered by the builder's recommended calls X1–X12, `NEEDS_CONFIRMATION`).
- **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` hrc-020 (§8.1 "Save common searches and filter presets; restrict exports to
  authorised users"; §15 "Record who … exported"). Dependencies hrc-019 (`DEC-SCOPE-399`) and hrc-002 (`DEC-SCOPE-374`) are merged.
- **Migration:** `0277_saved_candidate_searches`. **API:** §12KT. **RBAC:** §2.294.

## Acceptance criteria (backlog)
1. A saved search restores its filters exactly.
2. An export without the grant returns 403.
3. The export is audited (filters and row count).
- **E:** a saved search refers to a filter that was removed later — it is ignored, with a notice.

## Rules
| # | Rule |
|---|---|
| X1 | A new table `saved_candidate_searches`: owner, name (1–80, unique per owner case-insensitively → 409), `filters` JSON, `shared` flag, timestamps. Owner FK `RESTRICT` (users are deactivated, never deleted). |
| X2 | `filters` is the Find Candidates request body (`CandidateSearch`, sort included), validated on save with the search's own 422 sentences and stored canonically (`model_dump(mode="json", exclude_defaults=True)`). Restoring = the same body, so the same results (AC1). |
| X3 | Who: every Find Candidates reader (`candidates.READERS`: recruiters, placement managers, super_admin, hr_team). Others 403 before the body is read. |
| X4 | Visibility: a user lists their own searches plus every `shared` one. Rename / change / delete: the owner, or super_admin. Someone else's personal search is a 404; a shared one they do not own is a 403 on write. |
| X5 | Compensation: saving (or updating to) filters that use package fields or the package sort needs `candidates.compensation.view` (403, the search's own rule). A shared search read by a user without the grant comes back with those fields removed and named in `ignored`. |
| X6 | Removed filters (edge case): on read, keys `CandidateSearch` no longer declares are dropped and named in `ignored`; the page shows "Some filters in this saved search are no longer available and were ignored: …". Values the API now refuses surface as the search's normal 422 when the search runs. |
| X7 | A cap of 50 saved searches per owner (422). |
| X8 | Export: `POST /recruiter/candidates/search/export?format=csv\|xlsx` with the same body. Order: reader role → `candidates.export` grant (403 "Your role cannot export candidates") → body (422) → compensation (403) → `crm_exports.export` (per-user lock, the 30-per-10-minutes throttle → 429, the row cap, the audit row, the commit, then the file). |
| X9 | Row cap (Q-21): 5,000 rows, `crm_exports.ROW_CAP`; more → 422 "narrow the filters", nothing written. |
| X10 | Columns: Candidate ID, Name, Preferred role, Current company, Experience (years), Location, Notice (days), Skills, Source, Status, Engagement (the search card's facts, so the card contract is unchanged); plus Expected salary (₹ a year) **only** with the compensation grant. No contact details or identity documents (ccrm-035 E4). Every text cell goes through `_safe_cell` (CSV/XLSX formula guard). Rows in the search's own sort order. |
| X11 | Audit: one `crm.export` audit row (entity `candidate_search`, key `find_candidates`) with `{format, filters (the body), rows}`. The log line names only which filters were set and the row count, never skill/resume text. |
| X12 | Default grant: `candidates.export` → `placement_manager` (super_admin implicitly). Recruiters, hr_team and others get it through Roles & permissions. HR Manager cannot read candidates today (hrc-002), so it is not seeded. |

## Design
- **Backend:** `services/saved_searches.py` (load/visible/out/ignored); routes in `api/recruiter_candidates.py` under
  `/recruiter/candidates/saved-searches` (declared before `/{candidate_id}`) — no `main.py` change. `candidate_search` gains `where()`
  (shared by `search` and export) and `export_table()`; the export calls `crm_exports.export`.
- **Frontend:** `lib/recruiterCandidateSearch.ts` gains `stateOfBody()` (the inverse of `searchBody`, re-validated through
  `stateOf(paramsOf())`) and the saved-search/export helpers; a small `RecruiterSavedSearches` component (load select, Save / Update /
  Delete, shared checkbox, ignored notice); an Export CSV / Excel pair in the results header for holders of `candidates.export`.
- **Alternatives rejected:** storing the URL query string (the server could neither validate it nor strip removed/compensation filters);
  reusing `talent_pools` (manager-owned pool rules, not personal presets); a streamed export (5,000 rows fit in memory; `crm_exports`
  already gives lock/throttle/cap/audit).

## Reviews (Phase 3)
- **API:** 201 create, 200 update/list, 204 delete, 404 for invisible ids (no IDOR), 409 duplicate name, 422 validation, 403 role/grant.
  `extra="forbid"` bodies. One transaction per write.
- **Frontend:** loading/empty/error states for the saved list; the export button shows "Exporting…" and the API's message on failure;
  keyboard-accessible native controls; wraps on mobile.
- **Security:** IDOR (visible-only queries), grant before body, compensation stripped/refused, CSV injection guard, throttle,
  audit before the file, no PII in logs. Names are rendered as text (React escapes).

## Tests
- Backend `tests/test_hrc_020_saved_searches.py` (CRUD, visibility, compensation strip, removed-filter notice, cap, AC1 round trip),
  `tests/test_hrc_020_export.py` (403 without the grant, override allow, csv/xlsx content, compensation column, formula guard, cap 422,
  audit row), `tests/test_hrc_020_migration.py` (chain, round trip, seed).
- Frontend `tests/components/hrc020SavedSearches.test.tsx`, `tests/lib/hrc020SearchBody.test.ts` (state → body → state is exact).
- e2e `e2e/hrc-020-saved-searches.spec.ts`.
