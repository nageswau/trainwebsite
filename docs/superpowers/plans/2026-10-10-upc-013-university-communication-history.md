# upc-013 University Communication History — Implementation Plan

**Goal:** one read-only, paginated timeline of everything kept on a university (§12), shown on the university detail page.
**Spec:** `docs/superpowers/specs/2026-10-10-upc-013-university-communication-history-design.md` (TL1–TL10, D1–D5). No migration.

## Task 1 — API: the timeline service and route (TDD)
- RED: `apps/api/tests/test_upc_013_timeline.py` — the §12 chain newest first with actors; every kind; causal tie order + stable paging;
  excerpt; 401 / 403 (overseas_admin, counselor, manager without profile) / 404 / 422; no other university's rows; commission documents
  hidden for a non-commission role (service-level).
- GREEN: `lead_timeline._branch(rank=...)`; `services/university_timeline.py` (`_sources(university_id, user)`, `page(...)`);
  `GET /partnership/universities/{id}/timeline` in `api/university_comms.py`.
- Regression: `tests/test_tel_015_timeline.py`.

## Task 2 — Web: row mapping (TDD)
- RED: `tests/lib/universityActivity.test.ts` — title / badge / meta per kind, System actor, excerpt ellipsis.
- GREEN: `lib/universityActivity.ts` (`UNIVERSITY_ACTIVITY_READERS`, `universityTimelineUrl`, `ActivityRow`, `activityEntry`, `activityActor`).

## Task 3 — Web: component + page (TDD)
- RED: `tests/components/UniversityActivity.test.tsx`; detail page test (section for readers only, keyed first page).
- GREEN: `LeadTimeline` optional `entryOf` / `actorOf`; `components/UniversityActivity.tsx`; `firstTimeline` in `lib/universitiesServer.ts`;
  the "Communication history" section on `app/partnership/universities/[id]/page.tsx`.
- Regression: `LeadTimeline`, `LeadDetailPanel`, `CounselorLeadDetail`, `AdminLeadStage`, `UniversityDetailPage` tests.

## Task 4 — e2e + docs
- `tests/e2e/upc-013-university-timeline.spec.ts` (desktop + mobile; overseas_admin has no section).
- DEC-SCOPE-166, API §12CH, RBAC §2.92, backlog status.
