# ccrm-041 — Go-live verification: permission matrix and sample journey (design)

Decision `DEC-SCOPE-278`, RBAC §2.192, **no migration, no API change, no product code**. Source: `docs/delivery/COUNSELOR_CRM_BACKLOG.md`
`ccrm-041` (Counselor CRM Specification §2 "every role and permission should be tested before go-live", §17, Appendix B, AC 1–12;
`UNVERIFIED`). Dependencies: every item it covers, ccrm-001 … ccrm-040 — all merged on main @ `19edc627` (verified 2026-10-25: the last
four, ccrm-038/039/040/032, are PRs #337/#338/#339/#340). The owner pre-authorised recommended defaults; every G-row is the builder's
call, `NEEDS_CONFIRMATION`.

## 1. Requirement (backlog)

Tests and docs only:

1. a route-inventory / RBAC test for every new counselor route (the tel-026 pattern);
2. one end-to-end journey: enquiry → convert → three applications → A missing transcript, B conditional offer, C rejected → accept B →
   visa → enrolment, asserting A and B never change when C is rejected; notifications fired on seeded deadlines.

## 2. Existing behaviour (main @ `19edc627`)

- Each ccrm item pins its own roles in its own test file (`test_ccrm_0NN_*.py`), but nothing checks that **every** route the CRM added
  has a role row, or that a route added later gets one.
- `tests/test_tel_026_matrix.py::test_every_telecaller_crm_route_has_a_row` **fails on main**: its prefixes (`/telecaller/`,
  `/counselor/leads`, `/admin/leads`) now also cover 25 routes added by ccrm-002/003/004/005/006/008 (lead notes, counselor lead actions,
  calls / messages / meetings, qualification, lost reasons, convert) that have no row there.
- The OpenAPI diff between `37f087fa` (the backlog commit, before ccrm-001) and `19edc627` is **118 added operations, none removed** —
  the counselor CRM surface this item verifies.

## 3. Decisions (defaults, `NEEDS_CONFIRMATION`)

| # | Question | Default |
|---|---|---|
| G1 | Which routes | The 118 operations ccrm-001…040 added (§2), one matrix row each. A guard fails when a route appears under the counselor CRM prefixes (§4) with no row in this matrix or in tel-026, or a row has no route. |
| G2 | Which roles | 12 cells per route: anonymous; the overseas counselor who owns the records (`cns`); another overseas counselor (`cns_out`); an IT counselor; the Overseas Admin; the IT Admin; Super Admin; the lead's telecaller; their telecaller manager; the direct student; the agency Master; a management partner. |
| G3 | Expected values | Taken from RBAC_MATRIX §2.153–§2.191 (each item's owner-approved rules), never from what the code returns. An unlisted signed-in role must get 403 and anonymous 401. A mismatch is a finding, not a test edit. |
| G4 | tel-026 overlap | tel-026 keeps its own rows; its inventory leaves out the routes this matrix owns, so each route has exactly one row and tel-026 is green again. |
| G5 | 2xx cells | A write cell runs on its own fresh world (one cell's write never changes what another sees); refused / hidden cells and reads share one world (tel-026 PM3). |
| G6 | Journey | One API-level pytest (deterministic, every step asserted) plus one Playwright spec that walks the same journey through the counselor's pages. Enquiry = a telecaller lead handed to the counselor (tel-018). |
| G7 | "A and B never change" | A snapshot of A and B — stage, sub-status, outcome, offers, checklist, history length, `updated_at` — taken before C is rejected must equal the one after (AC 3, AC 9). |
| G8 | Notifications | Deadlines seeded on B (offer deadline, open condition, required deposit, then a visa appointment) inside the ccrm-030 windows; one reminder run notifies the counselor (and the student where RM6 says so); a second run sends nothing (AC 12). |
| G9 | Defects found | A product defect found while building is reported in §6. Fixed in this item only when it breaks an owner-approved rule of a covered item and the fix is local; otherwise recorded as a follow-up. |
| G10 | super_admin on application routes | Passes as the Overseas Admin — the overseas workflow's existing access (F3). |

## 4. Route inventory (`tests/test_ccrm_041_matrix.py`)

`CCRM_PREFIXES`: `/counselor/`, `/overseas-admin/checklists`, `/overseas-admin/reminder-rules`, `/overseas/me/`, `/calendar/feeds/`,
`/management/crm-reports`, `/workflows/overseas/applications/{}/…` sub-resources, `/workflows/overseas/documents/{}/versions`,
`/workflows/overseas/visa/{}/lifecycle`, plus the lead-notes / lost-reason / agency sub-status / agency profile routes by name. Routes
under these prefixes that predate ccrm (tel-018, csc-001…005, AGN) are listed once as `EARLIER` with the test that owns them.

Tests: `test_every_counselor_crm_route_has_a_row`, `test_matrix_row[...]` (one per route, every role), and tel-026's inventory
(updated, G4).

## 5. Sample journey

`tests/test_ccrm_041_journey.py` (API) and `apps/web/tests/e2e/ccrm-041-sample-journey.spec.ts` (UI):

1. A telecaller's overseas lead is handed to the counselor → ccrm-030 first-contact task; the counselor moves it to Qualified (ccrm-003)
   and converts it (ccrm-008): student, link, profile.
2. Three applications for the student, all assigned to the counselor, codes unique (ccrm-011).
3. A: a block-mode admission checklist with a required Academic transcript; Ready for Submission is refused (409) listing the transcript
   (ccrm-019).
4. B: offer letter + conditional offer with a condition, deposit and deadlines (ccrm-023/024/025).
5. C: outcome Rejected with a reason (ccrm-015). A and B are unchanged (G7); the history row names the counselor (AC 6).
6. Reminder run → offer deadline / condition / deposit notices; a second run sends nothing (G8).
7. The student accepts B (ccrm-025, sub-status Offer accepted); A and C unchanged.
8. Visa on B: case opened, appointment booked inside the window → visa reminder; submitted → approved (ccrm-026).
9. Enrolment confirmed on B with the confirmation document (ccrm-027) → stage Enrolled; A and C still unchanged.

## 6. Findings

| # | Finding | Resolution |
|---|---|---|
| F1 | tel-026's inventory test failed on main: 25 ccrm routes under its prefixes had no row. | G4 — those routes are rowed here; tel-026 leaves them out. |
| F2 | tel-026's `GET /telecaller/templates` row still said counselors 403; ccrm-004 (§2.173) opened it to them. | Row updated to the approved rule. |
| F3 | `super_admin` passes the application-level ccrm routes while their RBAC sections only say "Others 403". | Not a defect: the overseas workflow's existing super_admin access, kept by every item (ccrm-022 SD3). Made explicit as G10 / RBAC §2.192. |
| F4 | No route returned a cell that contradicts its owner-approved rule; the journey ran end to end; browser QA found no defect. | — |

Added `G10`: `super_admin` on application-level routes passes as the Overseas Admin (F3).

## 7. Out of scope

Product behaviour changes; new roles (CC2); MFA (CC6); retention (PRD 15/85); the full repository regression (separate session).
