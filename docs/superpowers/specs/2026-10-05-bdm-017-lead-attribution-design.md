# bdm-017 — Student lead attribution to organizations (`enquiries`) — Design

**Status:** design approved in-session on 2026-10-05 (structured questions L1–L8, then the full design reviewed against the
`api-and-interface-design`, `frontend-ui-engineering` and `security-and-hardening` skills). The owner asked to proceed to
implementation with this design.

**Branch:** `feature/bdm-017-lead-attribution`, fast-forwarded to `origin/main` @ `2e057b3a` (after bdm-009 #59).

**Backlog:** `docs/delivery/BDM_CRM_BACKLOG.md` §4 bdm-017 (line 843). Depends only on bdm-002 (merged).

**Source:** backlog D5b (leads are attributed `enquiries` rows; funnel/revenue from real records), Q-14/D23 (the BDM enters each
lead individually; "students contacted" = leads entered), D3 (division derived: college → `it`, agent/school → `overseas`),
Q-02/D11 (read own type, edit assigned). All `EXPLICIT_APPROVAL` in `DEC-SCOPE-055`.

**Decision record:** **`DEC-SCOPE-072`** (provisional number; renumber on merge if taken, as earlier BDM entries were).
Migration **`0074_enquiry_bdm_attribution`** after `0073_bdm_pipeline` (bdm-004 and bdm-007 branches each carry their own
`0072`; whichever merges later re-chains).

**Gate:** `APPROVAL_GATES.md` GATE-09.

**Backlog correction:** the backlog cites the Telecaller extension as "`DEC-SCOPE-036` D3"; `DEC-SCOPE-036` is ENH-017 and no
Telecaller decision exists. bdm-017 therefore defines the `enquiries` extension; the Telecaller item rebases on it.

---

## 1. Scope

In scope:
- The organization's assigned BDM enters a student lead against the organization (name, email, optional phone, interest,
  optional note). It is an `enquiries` row with `source='bdm'`, the organization and the BDM.
- Everyone who can read the organization sees its leads and the exact count.
- Admins see the organization (and attributing BDM) on the existing admin lead list and can filter by organization.
- A division admin explicitly links a lead to one student account, and can undo the link.
- BDM leads go through the existing CRM sync task, payload unchanged.

Out of scope (YAGNI / later items): bulk entry or referral links (Q-14), a lead-count column on the organization list,
organization in the CRM payload, funnel/revenue (bdm-021), BDM editing or deleting a lead (status/routing stay admin-only,
ADM-002), any change to the public enquiry form.

## 2. Decisions (owner, 2026-10-05)

| # | Question | Answer |
|---|---|---|
| L1 | Who performs the explicit conversion | **Division admin** (`it_admin`/`overseas_admin`/`super_admin`) from the admin lead list |
| L2 | Link target and undo | **Active student of the lead's division** (`it_student` for `it`, `overseas_student` for `overseas`); **undoable** (audited). Linking sets `status='converted'`; unlinking leaves status as is |
| L3 | CRM sync of BDM leads | **Yes, same task, payload unchanged** (`source='bdm'` identifies them) |
| L4 | Existing admin counts (dashboard "Enquiries", reports summary "leads", RPT-001 funnel) | **Include BDM leads** — no change to those queries |
| L5 | Lead fields | **Name, email, phone (optional), interest → `subject`, note (optional) → `message`**; a blank note stores `"Lead entered by BDM at <organization name>"` |
| L6 | Who adds / sees | **Mirror activities (bdm-009 V1/V5):** add = the organization's assigned BDM, not archived; see = anyone who can read the organization |
| L7 | `PATCH /admin/leads/{id}` status `converted` | **Unchanged.** Status stays an admin label; only the link counts as a conversion |
| L8 | Same email twice in one organization | **Warn, acknowledge to save** (409 `possible_duplicate`, resubmit with `acknowledge_duplicate=true`) |
| L9 | One student linked to several leads | **No — one lead per user**, enforced by a partial unique index (first conversion wins) |

Defaults (design, not separately asked): the BDM daily cap of 200 leads (409, bdm-009 V10's bound); the conversion target is
named by the student's account email typed by the admin and matched exactly (explicit; never inferred from the lead's own
email); conversion is allowed on any lead in the admin's division (website leads too), so L9 holds across sources.

## 3. Data model — migration `0074_enquiry_bdm_attribution`

`enquiries` gains five nullable columns:

| Column | Type | FK |
|---|---|---|
| `bdm_organization_id` | uuid | `bdm_organizations.id` ON DELETE RESTRICT |
| `bdm_user_id` | uuid | `users.id` ON DELETE RESTRICT |
| `converted_user_id` | uuid | `users.id` ON DELETE RESTRICT |
| `converted_at` | timestamptz | — |
| `converted_by_user_id` | uuid | `users.id` ON DELETE RESTRICT |

Constraints and indexes:
- `ck_enquiries_bdm_attribution`: `(bdm_organization_id IS NULL) = (bdm_user_id IS NULL)`.
- `ck_enquiries_conversion`: `(converted_user_id IS NULL) = (converted_at IS NULL) AND (converted_user_id IS NULL) = (converted_by_user_id IS NULL)`.
- `ix_enquiries_bdm_org_created` on `(bdm_organization_id, created_at)` — the organization list and its exact count.
- `uq_enquiries_converted_user` unique on `converted_user_id WHERE converted_user_id IS NOT NULL` — L9.

Additive: existing rows keep NULLs (AC2). Organizations and users are never hard-deleted on `main`, so RESTRICT blocks no real
path. `downgrade()` refuses while any row is attributed or converted (0061's idiom), so it never silently drops attribution.

Nothing outside the BDM create route writes the attribution columns, and nothing outside the conversion routes writes the
conversion columns: `EnquiryIn` (public) has no such fields and Pydantic ignores extras; `update_lead` keeps its
`("status", "owner_id")` allow-list.

## 4. BDM API — `app/api/bdm_leads.py`, `app/services/bdm_leads.py`

### `GET /api/v1/bdm/organizations/{org_id}/leads?limit&offset` → `BdmLeadPage`
- `load_scoped` (out of scope or unknown → 404; other roles → 403 from `caller_scope`).
- `{items, total, limit, offset}`, `created_at DESC, id DESC`; `limit`/`offset` are `app.api.bdm.LIMIT`/`OFFSET`.
- `total` = exact `COUNT(*) WHERE bdm_organization_id = :org` (AC4).
- Item: `id, name, email, phone, interest, status, bdm{id, full_name}, converted (bool), created_at`. The linked account is
  never exposed to BDMs.

### `POST /api/v1/bdm/organizations/{org_id}/leads` → 201 `BdmLeadOut`
One transaction, in this order:
1. `bdm_context` (not a BDM → 403).
2. `load_scoped(lock=True)` (out of type → 404). The organization row lock serializes concurrent adds to one organization.
3. Assigned BDM only → 403 `"Only the organization's assigned BDM can add leads"` (logged `bdm_lead_write_refused`).
4. Archived → 422 `"This organization is archived"`.
5. Daily cap: ≥ 200 leads by this BDM on the IST day → 409 `"You've added 200 leads today"` (soft across organizations).
6. Duplicate: `lower(email)` already a lead of this organization and not `acknowledge_duplicate` → 409
   `{"message": "This student is already a lead of this organization", "code": "possible_duplicate", "matches": [{id, name, created_at}], "total"}` (bdm-002's shape; at most 10 matches).
7. Insert with server-owned fields: `division = BDM_DIVISION[org.bdm_type]`, `source='bdm'`, `status='new'`,
   `crm_sync_status='pending'`, `bdm_organization_id`, `bdm_user_id`; audit `bdm_lead.created`; commit.
8. After commit: `sync_enquiry_to_crm_task.delay(id)` inside `try/except` — a broker failure logs
   `bdm_lead_crm_enqueue_failed` and the lead stays `pending` (a 500 after commit would invite a duplicate retry).

### Schema `BdmLeadCreate` (`extra="forbid"`)
`name` 1–160 (required, no control chars), `email` ≤255 (required, email shape, stored lower-case), `phone` ≤40 optional
(digits, spaces, `+ - ( )`), `interest` ≤180 required, `note` ≤5000 optional multi-line, `acknowledge_duplicate` StrictBool
(default false). Labels: "Student name", "Email", "Phone", "Interest", "Note".

## 5. Admin API (additive)

### `GET /api/v1/admin/leads`
- New optional `bdm_organization_id: UUID` filter, ANDed with the existing division scope (can only narrow).
- Each row gains `organization: {id, code, name} | null`, `bdm: {id, full_name} | null`,
  `converted_user: {id, full_name, email} | null` (LEFT OUTER JOINs). Every existing key, the 500-row cap and the ordering are
  unchanged. Website rows carry `null`s (AC2).

### `POST /api/v1/admin/leads/{lead_id}/conversion` body `{"student_email": str}` → 200 lead row
1. `ensure_admin`. 2. Lead `FOR UPDATE` (missing → 404). 3. Wrong division (non-super_admin) → 403 `"Wrong division"` (as
`update_lead`). 4. Already linked → 409 `"Unlink the current student first"`. 5. Target `FOR SHARE` by `lower(email)`; invalid
(missing, inactive, role ≠ `{lead.division}_student`, division ≠ lead's) → one 422
`"Enter the email of an active student account in this lead's division"` (no probing). 6. Target already linked to another
lead → 409 `"This student is already linked to another lead"`. 7. Set `converted_user_id`, `converted_at=now()`,
`converted_by_user_id`, `status='converted'`; audit `lead.convert` (ids only); commit. An `IntegrityError` on
`uq_enquiries_converted_user` (two admins at once) → the same 409 as step 6.

### `DELETE /api/v1/admin/leads/{lead_id}/conversion` → 200 lead row
Same lock / 404 / 403; not linked → 409 `"This lead is not linked to a student"`; clear the three columns, keep status; audit
`lead.unconvert` (ids only); commit.

`PATCH /api/v1/admin/leads/{lead_id}` is unchanged (L7).

## 6. Frontend

- **`BdmOrganizationLeads.tsx`** (bdm-009 `BdmActivityTimeline` pattern) after Activity on both organization profile pages
  (`/bdm/organizations/[id]`, `/bdm/manager/organizations/[id]`). The server page reads the first page alongside the
  organization. Heading "Leads (N)" with the exact total. States: load error (`role="alert"` + Try again), empty
  ("No leads yet."), list, "Load more". Rows: name + email/phone detail line, interest, status, added by, added (date).
- **`BdmLeadForm.tsx`**: shown by "Add lead" only on the BDM view when `permissions.can_edit` (assigned, not archived).
  Labelled inputs (`type="email"`, `type="tel"`, `autoComplete="off"`), field errors from a 422 tied with
  `aria-describedby`, duplicate 409 lists the matches and offers "Save anyway" through `BdmConfirm`, network loss keeps the
  entry (`NOT_COMPLETED`). Saved → the profile's one live region says "Lead added." and takes focus (bdm-009 QA9-01: the form that
  held focus is gone); Cancel → focus returns to "Add lead".
- **`AdminLeadManagementPanel.tsx`**: an Organization column (`code · name`, or "Website" for unattributed rows), an
  Organization filter `<select>` built from the loaded rows (client-side, like the search), and per row a "Link student"
  inline form (email + Link) or, when linked, the student and an "Unlink" action. Messages stay in the row's `role="status"`.
  Existing search, status select and loading/empty texts are unchanged. Browser QA (QA17-02, QA17-03): the panel is shown to the
  Overseas Admin as well (their division's School / Agent BDM leads), spans the action grid (`.lead-management`) and uses
  `.table-scroll`, as the organization's lead table does (QA17-01: row headers keep their case).
- **`lib/bdmLeads.ts`**: types, URL builder, `isLead` guard; writes use `lib/apiErrors.sendJson`.

All text renders through React (no `dangerouslySetInnerHTML`).

## 7. Security

| Concern | Control |
|---|---|
| Authentication | existing `get_current_user` cookie (httpOnly, SameSite=Lax); unchanged |
| CSRF | JSON-only bodies under SameSite=Lax (`account.py` rationale) |
| Authorization / IDOR | `load_scoped` 404; assignee 403; admin division 403; conversion target validated server-side |
| Mass assignment / escalation | `extra="forbid"`; source, division, attribution and conversion are server-set; public form and PATCH cannot set them (tested) |
| Injection | SQLAlchemy expressions only |
| PII in logs | logs and audit rows carry ids, route, status and counts — never name, email, phone, interest or note |
| Abuse | 200 leads / BDM / IST day; no public endpoint added |
| Enumeration | one 422 for every invalid conversion target |

## 8. Acceptance criteria → tests

| AC | Test |
|---|---|
| AC1 BDM lead carries organization + BDM, appears in admin list | `test_bdm_017_leads.py::test_created_lead_is_attributed_and_listed_for_admin` |
| AC2 website form / existing leads unaffected | `test_public_enquiry_ignores_attribution_fields`, `test_patch_cannot_set_attribution`, admin row nulls |
| AC3 explicit link to exactly one user | `test_bdm_017_conversion.py` (link, unlink, wrong division, invalid target, second lead same student, already linked) |
| AC4 exact counts per organization | `test_org_lead_total_is_exact_across_pages_and_orgs` |
| Negative: out-of-scope org 404, invalid email 422 | `test_bdm_017_scope.py`, `test_bdm_017_schemas.py` |
| Migration additive / downgrade refusal | `test_bdm_017_migration.py` |

Frontend: Vitest for `BdmOrganizationLeads`, `BdmLeadForm`, `AdminLeadManagementPanel`; Playwright
`bdm-017-lead-attribution.spec.ts` (BDM adds a lead → admin filters by organization → links the student).

Lite runs only in this session (the owner runs the full suites separately). Regression set to run lite: `test_pub_002`,
`test_adm_002`, `test_cns_001`, `test_rpt_001`, bdm-002/009 scope.

## 9. Regression risks

- `enquiries` is shared by the public form, admin list, counselor routed leads, CRM worker, admin dashboard/reports and the
  RPT-001 funnel. Only additive columns; none of those queries change (L4).
- Admin list rows gain keys (additive); the generic `/admin/[module]` table picks columns explicitly, so it is unaffected.
- Migration number collides with the bdm-004 / bdm-007 branches' `0072`; re-chain on merge.
