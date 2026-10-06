# bdm-021 — College business tracking: student funnel + revenue (design)

**Feature ID:** `bdm-021` · **Backlog:** `docs/delivery/BDM_CRM_BACKLOG.md` §4 bdm-021 · **Depends on:** bdm-017 (`DEC-SCOPE-072`,
merged on `main`, migration `0074_enquiry_bdm_attribution`) · **Decision:** `DEC-SCOPE-086` (proposed in this spec) · **Migration:** none.

## 1. Understanding

- **Outcome:** on a College-module organization's profile, the BDM, their manager and super_admin see the organization's student
  funnel (Contacted → Leads → Registrations → Training → Certification → Internship → Placement) and its revenue lines (training,
  internship, placement, other), computed live from attributed records (D5b), with untracked stages labelled, never a fabricated 0.
- **Source (`ORIGINAL_REQUIREMENT` via the backlog):** College §E (student funnel, 4 revenue lines); Q-08/D17 (revenue = paid
  payments of attributed students; internship / placement / other revenue "not tracked"); Q-14/D23 ("students contacted = leads
  entered"); bdm-017 L9 (one lead per student account: the first conversion wins).
- **Owner direction for this session (2026-10-06):** "proceed with recommended answers, ask only if blocking". The choices in §2 are
  recommendations made under that standing direction. They are recorded as such in `DEC-SCOPE-086`, and the owner can override any of them.

## 2. Decisions (B1–B8, recommended)

| # | Question | Recommendation | Why |
|---|---|---|---|
| B1 | Which organizations have a business view | Every organization of the **College module** (`bdm_type = 'college'`, any `org_type`). Any other module → **404**, the same as a missing one | Q-03: university / corporate / other organizations created by a College BDM belong to the College module; their leads are IT leads |
| B2 | Who sees the funnel | Everyone who can read the organization (`load_scoped`: College BDMs by type, the team's manager, super_admin) | Same audience as the lead list (bdm-017 L6); counts only |
| B3 | Who sees revenue | The **assigned BDM**, a `bdm_manager` (team scope already applied) and `super_admin`. Any other College BDM gets `revenue: null`, and the panel says who can see revenue | The backlog's security note: revenue is business-sensitive, visible to the owning BDM, the manager and super_admin only |
| B4 | Period | **All time**, computed live on every request (no snapshot, no cache) | No period in the source; bdm-024 owns period views |
| B5 | Contacted | **= Leads** (Q-14: "students contacted = leads entered"), shown with that definition | D23 |
| B6 | Stage counting | Each stage counts **distinct students** independently by its definition (not "furthest stage"); bars are sized against Leads | Definitions stay literal and checkable (AC1) |
| B7 | Training revenue | Sum of the registered students' payments with status `paid` or `succeeded` (`payments.PAID_STATUSES`), currency `INR`, excluding `agent_deposit` (pass-through, D17 consequence). Any date. Refunded / pending / failed / overdue are excluded by status | Q-08 "paid fees only"; AC4 |
| B8 | Untracked | Internship stage, internship / placement / other revenue: `tracked: false`, `count`/`amount` `null`, labelled "Not tracked yet" | Backlog: IT internship is not modelled; Q-08 |

## 3. Stage definitions (AC1 — written once, shown in the API and the UI)

`S` = the set of distinct `enquiries.converted_user_id` (not null) among the organization's leads (`enquiries.bdm_organization_id = org`).

| Key | Label | Definition |
|---|---|---|
| `contacted` | Contacted | Leads entered by BDMs for this organization (Q-14) |
| `leads` | Leads | Enquiries attributed to this organization (bdm-017) |
| `registrations` | Registrations | Distinct students linked to one of these leads (the explicit conversion link) |
| `training` | Training | Students in `S` with at least one enrollment that is not withdrawn |
| `certification` | Certification | Students in `S` with at least one issued certificate |
| `internship` | Internship | Not tracked: "Internships are not recorded in EduSphere." (the badge carries "Not tracked yet"; QA21-01) |
| `placement` | Placement | Students in `S` with an accepted or joined job offer |

A student linked to leads of two organizations can't exist: L9's `uq_enquiries_converted_user` allows one lead per student (first
conversion wins). Unlinking a lead removes the student from every later stage on the next read (live).

## 4. API

`GET /api/v1/bdm/organizations/{org_id}/business` → 200

```json
{
  "organization_id": "uuid",
  "currency": "INR",
  "funnel": [{"key": "contacted", "label": "Contacted", "definition": "…", "tracked": true, "count": 420}, …,
             {"key": "internship", "label": "Internship", "definition": "…", "tracked": false, "count": null}, …],
  "revenue": {"lines": [{"key": "training", "label": "Training fees", "definition": "…", "tracked": true, "amount": "125000.00"},
                        {"key": "internship", …, "tracked": false, "amount": null}, {"key": "placement", …}, {"key": "other", …}]}
}
```

- `revenue` is `null` when B3 hides it. `amount` is a decimal string (the trip / appointment money convention).
- Errors: 401 unauthenticated; 403 for a role outside BDM / manager / super_admin, or an inactive or profile-less BDM (`bdm_context` / `caller_scope`, unchanged);
  404 for an unknown organization, one outside the caller's scope, or a non-College organization (B1); 422 for a malformed id.
- Read-only: no transaction is opened for writing, and no audit row is written. It runs **one** aggregate query, with scalar subqueries over `S`
  (bounded, constant query count). Indexes used: `ix_enquiries_bdm_org_created`, the `student_id` / `user_id` indexes on
  `enrollments`, `certificates`, `job_applications` and `payments`.
- AC3: the response carries only counts and sums. It has no student id, name, payment id or per-payment row.
- Files: `app/services/bdm_metrics.py` (definitions + `college_business`), `app/api/bdm_metrics.py` (router), schemas
  `BdmBusinessStage`, `BdmRevenueLine`, `BdmBusinessRevenue`, `BdmBusinessOut`; the router is registered in `app/main.py`.

## 5. Frontend

- `components/BdmOrganizationBusiness.tsx`: a "Business" section (`action-card wide`) on both organization profiles (BDM and
  manager), rendered only when `organization.bdm_type === "college"`. It reuses ENH-017's `.pipeline-funnel` markup: the count is the
  text, and the bar is decoration (`aria-hidden`) sized against Leads. Each stage shows its definition as muted text. Untracked stages and
  lines show the "Not tracked yet" badge (no number). Revenue uses `formatInr` (`lib/bdmAppointments.ts`). When `revenue` is null:
  "Revenue is visible to the organization's assigned BDM and their manager."
- Loaded on the server alongside the organization (the `firstMou` pattern): `lib/bdmBusinessServer.ts#firstBusiness` never rejects.
  A `null` gives a `role="alert"` error with "Try again", which re-fetches on the client. A non-college organization doesn't request it.
- Empty state: zero leads → "No leads yet. The funnel starts when leads are added." The tracked stages still read 0 (real zeros).
- `lib/bdmBusiness.ts`: types, `orgBusinessUrl`, `isBusiness` guard.

## 6. Security

- Authorization reuses `load_scoped` (type / team / super_admin). B1's module check runs after scope, so a School BDM asking about a
  College organization is a 404 from scope, and a super_admin asking about a School organization is a 404 from B1. Neither reveals
  existence.
- Revenue visibility (B3) is decided on the server only. The client renders whatever it is sent.
- No input other than the path UUID (FastAPI-validated), so there is no injection surface. SQL is built with SQLAlchemy expressions only.
- No new logging of PII. Nothing is logged on a read (the same as the other bdm GETs).
- Rate limiting: none added (an authenticated read, the same as every bdm GET).

## 7. Acceptance criteria → tests

| AC | Test |
|---|---|
| AC1 counts match the definitions on seeded data | `test_bdm_021_business.py::test_funnel_counts_match_definitions`, which seeds leads, conversions, withdrawn and active enrollments, issued and revoked certificates, and accepted, joined and offered offers |
| AC2 untracked labelled | API `tracked:false` + `null`; component test for the badges |
| AC3 no per-student data | API test asserts the exact key sets (no ids beyond the organization's own) |
| AC4 INR, paid only | API test with paid, succeeded, pending, refunded, USD and agent_deposit payments → only paid + succeeded INR summed |
| Negative: a School BDM → 404; a non-college organization → 404; another College BDM → `revenue: null`; the manager / super_admin see revenue; an outsider role → 403 | `test_bdm_021_business.py` |
| UI | `BdmOrganizationBusiness.test.tsx`, the page tests, Playwright `bdm-021-college-business.spec.ts` |

## 8. Out of scope

Period filters, export, per-student drill-down (bdm-024), and internship / placement revenue data models (Q-08 keeps them untracked).
