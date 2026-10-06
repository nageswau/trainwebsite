# bdm-011 implementation plan

Spec: `docs/superpowers/specs/2026-10-06-bdm-011-trip-appointments-design.md` (`DEC-SCOPE-085`, migration `0084_bdm_appointment_trip`).

Test command (isolated stack `bdm011`, code bind-mounted):

```bash
docker compose -p bdm011 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps \
  -v "$(pwd -W)/apps/api:/app" api-test python -m pytest -q -p no:cacheprovider <files>
```

Lite tests only (owner's standing choice): bdm-011 files + bdm-006 / bdm-007 / bdm-010 suites + touched web tests.

## Engineering review (Phase 3) folded in

- **API:** every change additive (new optional request fields, new response fields, new GET routes). Status codes follow the
  existing modules: scope miss 404, state conflict 409, rule violation 422. `trip_id` unset vs null distinguished with
  `exclude_unset` like every other PATCH field. Report reuses `BdmTripOut` — no second shape to keep in sync.
- **Transactions:** one commit per route (unchanged). Link: appointment `FOR UPDATE` → trip `FOR SHARE`. Trip date edit / cancel
  keep their trip `FOR UPDATE`, so they serialise with a link.
- **Security:** IDOR — the trip is loaded `WHERE bdm_user_id = caller` (404); managers cannot link (owner-only PATCH); report routes
  reuse `load_own_trip` / `load_team_trip`. No new free text; React renders text only (no HTML). Logs: ids/counts. Audit rows for
  link, unlink and auto-unlink. No new public endpoint; existing cookie auth and CSRF handling unchanged.
- **Frontend:** reuse `kpi-grid`/`kpi-tile`, `table`, `FormMessage`, existing section/card pattern; itinerary is a real `<table>`
  with `<caption>` and `scope="col"`; links are keyboard reachable; table scrolls inside its card on phones (no page sideways scroll).
  Loading: pages are server-rendered (existing `loading.tsx`); the trip choices come from the server page (no client loading state); a failed read shows a note and booking still works.

## Tasks

1. **Model + migration** — `BdmAppointment.trip_id` + index; `0084_bdm_appointment_trip`; `test_bdm_011_migration.py` (one head,
   additive, chained after 0083). Update bdm-005 "single head" test only if it pins the head name.
2. **Link rules (API)** — `services/bdm_travel.py`: `trip_ref`, `load_linkable_trip`, `in_range`; `bdm_appointments` create/PATCH
   accept `trip_id`; reschedule auto-unlink; `appointment_out.trip`. Tests `test_bdm_011_links.py` (AC1, 404s, L2, L4, auto-unlink,
   audits) written first.
3. **Itinerary + metrics** — `trip_out` adds `itinerary` and `metrics` (L1, L3); trip date edit guard; `GET /bdm/trips?linkable=true`.
   Tests `test_bdm_011_metrics.py` first.
4. **Report routes** — owner + manager, 409 until completed. `test_bdm_011_report.py` first.
5. **Web lib + trip page** — types; `TripItinerary`, `TripProductivity`; section ids; report link. Component tests first.
6. **Report pages** — `/bdm/travel/[id]/report`, `/bdm/manager/trips/[id]/report`. Component test first.
7. **Appointment form trip picker + detail row + reschedule notice** — tests first.
8. **Playwright** `bdm-011-trip-itinerary.spec.ts`; browser QA; docs (backlog status, decision register, RTM line).
