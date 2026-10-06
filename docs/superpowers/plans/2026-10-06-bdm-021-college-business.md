# bdm-021 — College business tracking: implementation plan

Spec: `docs/superpowers/specs/2026-10-06-bdm-021-college-business-design.md`. Branch `feature/bdm-021-college-business`.
Tests run for real, lite set only; the owner runs the full suites separately. Isolated compose project `-p bdm021`.

```
# backend (lite)
MSYS_NO_PATHCONV=1 docker compose -p bdm021 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm \
  -v "<WT>/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q -p no:cacheprovider <PATHS>"
# web: vitest / tsc / eslint in apps/web
```

## Tasks (TDD: each RED first)

1. **Schemas + service + route (backend).**
   - RED: `tests/test_bdm_021_business.py`, covering AC1 counts, AC4 payments, AC2 untracked shape, AC3 key sets, B1 404s, B3 revenue
     visibility, 401 / 403.
   - GREEN: `app/services/bdm_metrics.py` (`STAGES`, `REVENUE_LINES`, `college_business(db, org, show_revenue)`, one SELECT of
     scalar subqueries), `app/api/bdm_metrics.py` (`GET /bdm/organizations/{id}/business`), schemas, and registration in `main.py`.
2. **Frontend lib + server loader.** `lib/bdmBusiness.ts` (types, url, guard), `lib/bdmBusinessServer.ts` (`firstBusiness`).
   RED / GREEN through the component tests.
3. **Component.** RED: `tests/components/BdmOrganizationBusiness.test.tsx`, covering the funnel numbers, definitions, the Not tracked
   badges, INR revenue, the revenue-hidden note, the empty state, and the load failure → Try again → success.
   GREEN: `components/BdmOrganizationBusiness.tsx`.
4. **Wire into the profile.** `BdmOrganizationDetail` gains the `business` prop and renders the section for college organizations;
   both `[id]/page.tsx` read `firstBusiness` only when needed. RED: extend `BdmOrganizationPages.test.tsx` and `BdmOrganizationDetail.test.tsx`.
5. **Playwright.** `tests/e2e/bdm-021-college-business.spec.ts`: the College BDM sees the funnel and revenue, and the manager sees it.
6. **Docs.** `DEC-SCOPE-086` in the decision register, the backlog status line, and RTM / traceability where earlier bdm items recorded theirs.

## Regression risks

- `BdmOrganizationDetail` / the pages, which are shared by every bdm item. The section is additive and the prop optional.
- `main.py` router list (additive).
