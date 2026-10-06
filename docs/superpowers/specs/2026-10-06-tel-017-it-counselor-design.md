# tel-017 — Counselor role in the IT division + IT counselor workspace (design)

- **Backlog item:** `docs/delivery/TELECALLER_CRM_BACKLOG.md` → tel-017 (T3, Q-23). Dependency tel-001 is merged (PR #68).
- **Decision:** `DEC-SCOPE-076` (provisional; tel-003 holds 075). No migration.
- **Branch:** `feature/tel-017` from `origin/main` @ `784738e7`.

## 1. Understanding

The owner's answer T3 says a qualified IT lead goes to the existing `counselor` role, which is now allowed in the IT division. Each
counselor belongs to either `it` or `overseas`. tel-017 only makes IT counselors *exist and work safely*. Handover (tel-018) and lead
appointments (tel-016) build on it later.

Owner answer **C1** (2026-10-06, Q-23 scope): the IT workspace has **Dashboard + My Leads** only. tel-016 adds Appointments and
tel-018 adds the student link, both to the same nav.

Facts verified in code (not assumed):

- `User.division` cannot change after creation, because `PATCH /admin/users` never writes it. The backlog edge case "changing a
  counselor's division → 422" therefore has no path. Nothing is added; this spec records the fact.
- Login already refuses the wrong portal (`auth.py:104`), so an IT counselor signs in at `/it/login`.
- `/portal/{division}/{role}/{section}` already refuses a division mismatch (403).
- All 14 counselor routes in `workflows.py` already call `_require(..., "overseas")`, so they refuse an IT counselor today.
- Ten counselor-admitting routes check the **role only**. They are safe today only because every counselor is overseas:

| Route | Leak for an IT counselor if left alone |
|---|---|
| `GET /overseas-admin/school-students/lookup` | resolves any School student by code |
| `POST /overseas-admin/school-students/{id}/applications` | **creates an overseas application** |
| `GET /overseas-admin/school-applications` | empty (scoped by `counselor_id`), but overseas-only |
| `GET /lookups/overseas-students` | empty (scoped), overseas-only |
| `GET /lookups/overseas-applications` | empty (scoped), overseas-only |
| `GET /lookups/schools` | **every partner school** |
| `GET /lookups/school-students` | **one school's students** |
| `GET /inbound/university-email` | **every unmatched university email** |
| `PATCH /inbound/university-email/{id}/match` | scoped by `counselor_id`, overseas-only |
| `POST /communications/notify` | already same-division only, so an IT counselor notifying IT users is fine. **Unchanged.** |

## 2. Approaches

1. **Division gate on each overseas-only route (chosen).** Add the same rule `_require` already uses: anyone but `super_admin`
   whose `division != "overseas"` gets 403 "Wrong EduSphere division". For `lookups._allow` this is a `division` argument, mirroring
   `workflows._require`. `admin.py` and `inbound.py` get the extra condition inline. Every legitimate caller of these routes
   (`overseas_admin`, `counselor`, `university_rep`, `agent`, `overseas_student`) is overseas, so their behaviour is unchanged. This
   follows the inline-authorization convention.
2. Narrow the gate to `role == "counselor" and division != "overseas"`. This is the same effect with a more specific condition, but
   it leaves the next IT-capable role to repeat the mistake. Rejected.
3. A global dependency or middleware that blocks IT counselors from `/overseas*` paths. The paths are not prefixed consistently
   (`/lookups`, `/inbound`), so this is fragile and cuts across the inline convention. Rejected.

## 3. Design

### Backend
- `admin.create_user`: `allowed_by_division["it"]` gains `counselor`.
- `services/portal.py`: the IT counselor gets its own small handler, `_it_counselor(db, user, section)`, which is dispatched from
  `section_payload` before `_operations`. It serves:
  - `dashboard`: title "Counselor Dashboard", the five most recent routed leads, and metrics *Leads routed to you* and *New leads*
    (`status == "new"`).
  - `leads`: "My Leads", which is `Enquiry.division == "it" AND owner_id == user.id`, newest first, with the same columns as the
    overseas version.
  - any other section: `None` → 404 "Workspace not found".

  The two leads queries share one helper, `_routed_leads(db, user)`, filtered by `user.division`. The overseas `leads` branch calls it
  too, with identical output. The overseas counselor block is otherwise untouched.
- Overseas-only route gates, per §2 approach 1.
- No schema, no migration, no new endpoint, and no response-shape change.

### Frontend
- `WorkflowPanel` `ROLES_BY_DIVISION.it` gains `counselor` (mirrors the server allow-list).
- `lib/navigation.ts`:
  - `PORTAL_NAV["it/counselor"]` = Dashboard, Leads.
  - `PORTAL_NAV["it/admin"]` gains `counselors` after `trainers`, for parity with the overseas admin. The section is already generic
    on the server (`services/portal.py` `role_map`) and in `AdminUserManagementPanel`.
  - New `dashboardPathFor({role, division})`: it returns `/it/counselor/dashboard` for an IT counselor and otherwise
    `ROLE_DASHBOARD_PATH[role]`. Every consumer that has a division uses it: LoginForm, HeaderAuthActions, AccessUnavailable, and the
    account profile and password pages. The map itself is unchanged.
- `middleware.ts`: `it/counselor` joins the protected IT paths.
- New pages `app/it/counselor/dashboard/page.tsx` and `app/it/counselor/[section]/page.tsx`, mirroring the overseas ones.
- `PortalPage` label `"it/counselor": "Counselor"`.

### Error and edge states
- An IT counselor on `/overseas/counselor/*` sees the existing access-unavailable card (portal 403), whose home link is the IT
  dashboard via `dashboardPathFor`.
- An overseas counselor on `/it/counselor/*` gets the same card the other way round.
- My Leads with no routed leads shows the existing PortalSection empty state.
- An unknown section in the URL (`/it/counselor/visa`) is a 404 page: PortalPage calls `notFound()` before any fetch, because the
  section isn't in the IT nav. The API would also return 404 "Workspace not found".

## 4. Acceptance criteria (testable)

1. AC1: `it_admin` creates a `counselor` in `it` (201). `overseas_admin` still creates one in `overseas`, and still gets 403 for
   `it`. A super admin can create either.
2. AC2: an IT counselor's `GET /portal/it/counselor/leads` returns only IT leads whose `owner_id` is them, not other counselors'
   leads, not unrouted ones, and not overseas leads with their id. The dashboard counts match.
3. AC3: every counselor-admitting overseas route returns 403 for an IT counselor: the 14 `workflows.py` routes plus the 9 gated
   routes above. `GET /portal/overseas/counselor/*` also returns 403.
4. AC4: overseas counselor behaviour is unchanged. The CNS-001, I-19, UNI-001, SCH-010 and AGN lookup tests pass, and an overseas
   counselor calling `/portal/it/counselor/*` gets 403.
5. UI: an IT counselor signs in at `/it/login`, lands on `/it/counselor/dashboard`, sees the Dashboard and Leads nav items, and opens My
   Leads. The IT admin Users form offers Counselor.

## 5. Risks
- **High:** the shared `_operations` counselor block. Mitigation: the IT counselor never enters it, and the overseas output is
  identical (existing tests).
- The new division gate on `lookups`/`inbound`/`overseas-admin` would affect any non-overseas caller that relied on the role check
  alone. Only `super_admin` qualifies, and it is exempt.
- Out of scope, recorded as follow-ups: `PATCH /admin/leads` accepts any `owner_id` (tel-018 adds the real "Assign to Counselor").
  An overseas application's `counselor_id` was unvalidated. Branch review R1 found that an IT counselor's id there would route the
  student's counselor-chat and update notices to IT. **Fixed:** `POST`/`PATCH /workflows/overseas/applications` now require an overseas
  `counselor` (422 "Choose an overseas counselor"; an unknown id used to be a 500).

## 6. Tests
- Backend: `tests/test_tel_017_it_counselor.py` covers creation (AC1), the leads/dashboard scope (AC2), a parametrised 403 sweep over
  all 23 routes plus the portal (AC3), and the overseas counselor's reverse portal 403 (AC4). Lite regression: CNS-001, I-19,
  UNI-001, SCH-010 bridge, the lookups tests, the inbound tests, `test_rbac.py`, and the tel-001 provisioning tests.
- Web: vitest for `dashboardPathFor`, `PORTAL_NAV`, and the WorkflowPanel role options. A Playwright spec `tel-017-it-counselor.spec.ts`
  covers sign-in → landing → My Leads, the overseas URL refusal, and the IT admin role option.
