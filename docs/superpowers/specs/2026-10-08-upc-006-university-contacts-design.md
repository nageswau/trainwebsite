# upc-006 — University contacts + relationship strength (design + plan)

**Status:** design written 2026-10-08. The owner's standing instruction for this session is "proceed with the recommended answers;
ask only if genuinely blocking". So the item answers CT1–CT14 (§1) are **recommended defaults accepted under that instruction**
(`NEEDS_CONFIRMATION` as separate per-question approvals) and are registered that way in `DEC-SCOPE-122`.

**Branch:** `feature/upc-006`, cut from `origin/main` @ `593e9b9c` (after #151, upc-003).
**Backlog:** `docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-006. Dependency upc-003 (`0105`, `DEC-SCOPE-120`) is merged on
main — verified in code (`University`, `services/partnership_universities.py`, `/partnership/universities/[id]`).
**Source:** `EVID-020` §1 contact rows (lines 20–25), §10 (contacts: 7 example roles, 11 fields), §11 (relationship strength, 7 values).
**Numbering:** migration `0107_university_contacts`, `DEC-SCOPE-122`, API §12AP, RBAC §2.48. Drafted as `0106` / `DEC-SCOPE-121` / §12AO /
§2.47; renumbered on merging `main` @ `035c99ad` (rec-003 took those numbers first).
**Gate:** `APPROVAL_GATES.md` GATE-09.

## 1. Decisions (recommended defaults)

| # | Question | Answer |
|---|---|---|
| CT1 | Q-15 auto-suggest Dormant / At Risk | **No.** Relationship strength is set by hand (backlog). No interactions are recorded yet (meetings upc-009, calls/email upc-012/013), so there is nothing to compute it from |
| CT2 | Contact role catalogue | Table `university_contact_roles` (`code` PK, `label`, `position`), seeded by the migration with the union of §10 and §1 (International Director listed once): International Director, International Recruitment Manager, Regional Manager, Admissions Manager, Marketing Manager, Application Officer, Finance Contact, International Office, Partnership Contact, Recruitment Contact, Application Contact, Country Manager. Read-only in this item (`GET /partnership/contact-roles`); no catalogue admin UI. A contact's role is optional, one per contact |
| CT3 | Preferred communication values | The channels the record holds: **email, phone, whatsapp, linkedin** (optional) |
| CT4 | Relationship values (§11, exact) | `new, developing, good, strong, strategic, at_risk, dormant` → New, Developing, Good, Strong, Strategic, At Risk, Dormant. Optional on both the university and the contact (not assessed yet = blank) |
| CT5 | Who writes contacts | `partnership_manager` (primary/backup of the university), `partnership_head` (unowned or team universities), `super_admin`: the master's `can_edit` scope minus `overseas_admin`. Backlog roles line: overseas_admin **reads shareable contacts only** and does not write. Counselors read via upc-030 (AC3 "once upc-030 lands"); no counselor route here |
| CT6 | Primary contact | At most one per university (partial unique index). The first contact added becomes primary; `is_primary: true` moves it; `is_primary: false` is a 422 ("make another contact primary instead"); deleting the primary while others remain is a 409 |
| CT7 | Delete | `DELETE /partnership/contacts/{id}` (hard delete, audited with ids only). Not in the backlog's API line, added because contacts are PII and wrong entries must be removable |
| CT8 | Limits / duplicates | ≤ 50 contacts per university (AC1 needs 7+). The same email twice at one university → 409; the same person at two universities is two rows (edge case) |
| CT9 | Last interaction / next follow-up | Not stored or returned yet: last interaction is computed once interactions exist (upc-009/012/013), next follow-up comes from upc-020 |
| CT10 | Inactive university | Contacts become read-only (409 "Reactivate this university first"), like the master |
| CT11 | University relationship strength | `universities.relationship_strength` (nullable, CHECK) in the master's create/PATCH (`can_edit`), on the list row (badge + `relationship_strength` filter) and the detail header |
| CT12 | `shareable` default | **false** (PII stays internal unless a manager marks it shareable) |
| CT13 | LinkedIn | http(s) URL ≤ 300; a bare `linkedin.com/in/x` gets `https://` (the website idiom) — no `javascript:` hrefs |
| CT14 | Notes | ≤ 2000, multi-line; **not returned** to the shareable slice (overseas_admin, later counselors) — internal remarks stay internal |

## 2. Data model — migration `0107_university_contacts`

- `universities.relationship_strength` String(12), nullable, CHECK `ck_universities_relationship_strength`.
- `university_contact_roles` (`code` String(40) PK, `label` String(80) NOT NULL, `position` SmallInteger NOT NULL); seeded with
  `ON CONFLICT DO NOTHING` (0001 builds an empty table from the models on a fresh database).
- `university_contacts`: id, university_id FK RESTRICT, name String(200) NOT NULL, designation/department String(120), role_code FK →
  roles (nullable, RESTRICT), email String(255), phone/whatsapp String(30), linkedin String(300), preferred_channel String(10) CHECK,
  relationship_strength String(12) CHECK, notes Text, is_primary bool default false, shareable bool default false, created_at/updated_at.
  Indexes: `ix_university_contacts_university`, `uq_university_contacts_primary` (university_id WHERE is_primary),
  `uq_university_contacts_email` (university_id, lower(email) WHERE email IS NOT NULL).
- Downgrade refuses while any contact row or any university with a relationship strength exists.

## 3. Backend

`services/university_contacts.py` (functions, no commit) and `api/university_contacts.py` (prefix `/partnership`).

- **Access** reuses upc-003: `require_reader` (the four master roles), then per role:
  - full view (`partnership_manager`, `partnership_head`, `super_admin`): every contact with notes;
  - `overseas_admin`: `shareable` contacts only, `notes` = null.
- `permissions()` gains **`can_edit_contacts`** (`partnership_*`/`super_admin` and in the `can_edit` scope and active). `require(...,
  "can_edit_contacts")` gives the 403/409 split for free.
- **Routes:**

| Route | Who | Notes |
|---|---|---|
| `GET /partnership/contact-roles` | master readers | `{items:[{code,label}]}` by position |
| `GET /partnership/universities/{id}/contacts` | master readers | `{items,total,limit,offset}`, primary first, then name, id; `limit` ≤ 50. Unknown university → 404 |
| `POST /partnership/universities/{id}/contacts` | `can_edit_contacts` | 201 `{contact}`; first contact → primary; ≤ 50; `is_primary: true` moves the primary |
| `PATCH /partnership/contacts/{id}` | `can_edit_contacts` on its university | only sent fields; equal values are not changes |
| `DELETE /partnership/contacts/{id}` | same | 204; primary with others left → 409 |

- Every write: university row `FOR UPDATE` (serialises primary/limit/email checks per university), change, `AuditLog`
  (`university_contact.<action>`, ids + field names only), one commit, structured log (ids only). Unknown contact → 404.
- Validation (422): name required; email shape; phone/WhatsApp digits + spaces + `+-()`; LinkedIn http(s); role must exist in the
  catalogue; enums per CT3/CT4; `extra="forbid"`.

## 4. Frontend

- `lib/universities.ts`: `RELATIONSHIP_STRENGTHS`, `CONTACT_CHANNELS`, `UniversityContact`, `ContactRole`, URLs;
  `University.relationship_strength`; `permissions.can_edit_contacts`.
- `[id]/page.tsx`: fetches contacts (+ roles when `can_edit_contacts`) beside the university; relationship badge in the header and a
  Profile row; new wide **Contacts** section.
- `UniversityContacts.tsx` (client): contact cards (mobile-friendly blocks, like BDM contacts); add / edit form (all §10 fields), make
  primary, delete with `BdmConfirm`; double-submit guard; 422 field errors; success notice (`role=status`); `router.refresh()`.
- `UniversityForm.tsx`: relationship-strength select. `UniversityTable.tsx`: "Relationship" column. `UniversityFilters.tsx`: filter.

## 5. Acceptance criteria

| AC | Statement | Proven by |
|---|---|---|
| AC1 | 7+ contacts per university, exactly one primary | `test_upc_006_contacts.py`; e2e |
| AC2 | Relationship values match §11 exactly (university and contact) | tests (schema + labels), vitest |
| AC3 | Non-partnership readers (overseas_admin now, counselors in upc-030) see only shareable contacts, without notes | tests |
| P1 | Add "Regional Manager – India" | tests; e2e |
| N1 | Invalid email → 422 (also phone, LinkedIn scheme, unknown role, unknown field) | tests |
| E1 | One person at two universities = two rows; same email twice at one university → 409 | tests |
| R1 | Non-owner manager / overseas_admin write → 403; inactive university → 409; unknown → 404 | tests |

## 6. Tasks (TDD, in order)

1. Migration + models + parity test (`test_upc_006_migration.py`).
2. University `relationship_strength` in schemas/row/detail/filter + `can_edit_contacts` (extend upc-003 tests' expectations).
3. Contact schemas + service + routes: read/slice tests, then create/patch/primary/delete/limits tests, then code.
4. Frontend lib + page + `UniversityContacts` + form/table/filter, vitest.
5. Playwright `upc-006-university-contacts.spec.ts`; docs (DEC-SCOPE-122, API §12AP, RBAC §2.48, DATA_MODEL, SCREEN_CATALOG, backlog).

## 7. Regression set (lite)

`test_upc_003_*`, `test_upc_002_*`, `test_upc_001_*`, the upc-003 vitest files, `upc-003-university-master.spec.ts`.
