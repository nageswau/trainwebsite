# pob-015 — implementation plan

Design: `docs/superpowers/specs/2026-11-07-pob-015-vacancy-sharing-campus-design.md` (DEC-SCOPE-426).

| # | Task | Test first |
|---|---|---|
| 1 | Migration `0307_institution_vacancy_shares` (guarded) + `InstitutionVacancyShare` model + schemas | `test_pob_015_migration.py` (guard, round trip, model = migration) |
| 2 | `services/campus_placement.py`: shares view, outcomes (V7), calendar (V8), summary (V10), share/respond rules | `test_pob_015_vacancy_sharing.py` AC1–AC3, V2–V7 |
| 3 | `api/recruiter_campus.py` mounted on `recruiter_drives.router`; ICS response | same file: routes, 403/404/409/422, ICS body |
| 4 | rec-038 matrix rows for the six routes | `test_rec_038_matrix` route coverage |
| 5 | Web: `lib/campusPlacement.ts`, `CollegeVacancies`, `CampusCalendar`, two pages, nav entries | vitest for both components, nav pins |
| 6 | Playwright `pob-015-vacancy-sharing.spec.ts` | share → listed → respond; calendar shows drive + batch |
| 7 | Docs: register, API contract §12LS, RBAC §2.317, data model, RTM, backlog status | — |

Phase-3 review outcomes folded in: share/response IDOR (child row must belong to the org → 404), requirement read scope before the
visibility check (no existence oracle), template must be usable by the caller (404) and `college_tpo` (422), counts use the pob-014
viewer predicate, ICS text escaped by `calendar_ics`, every list bounded, double submit = 409 from the unique index, buttons disabled while
busy, loading/empty/error states, stacked tables on phones.
