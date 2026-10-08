# rec-004 — Company contacts (design)

- **Feature:** `rec-004` (`docs/delivery/RECRUITER_CRM_BACKLOG.md` §rec-004). **Dependency:** rec-003, merged as PR #152 @ `22319014`.
- **Evidence:** EVID-018 §2 (the person fields Recruiter Name, Designation, Mobile, Email and LinkedIn Profile, plus the quick action
  "+ Add Recruiter"), §3 Business Details (HR Contact, Talent Acquisition Contact, Hiring Manager, HR Email, HR Phone) and §4 Recruiter
  Contact Management (lines 176–216). The owner's R3 answer: a new `company_contacts` table.
- **Numbering:** `DEC-SCOPE-124`, migration `0109_company_contacts` (after upc-006's `0108_university_contacts`), API §12AR and RBAC §2.50. All of these
  were re-checked on `origin/main` @ `215e3e2e` (rec-009 took `0107` / 122 / §12AP / §2.48; upc-006 took `0108` / 123 / §12AQ / §2.49).

## 1. Decisions (recommended defaults, UNVERIFIED)

The backlog item has no Q-xx questions. The user's standing instruction for this session was "proceed with recommended answers", so the
following defaults are recorded in `DEC-SCOPE-124` as **UNVERIFIED**:

- **C1 — who writes:** contacts follow the company's `can_edit` right: the assigned recruiter or `super_admin`. This matches rec-003 D6 and
  R10 ("recruiters do every write"). `placement_manager` and the assigned BDM read only. An archived company's contacts are read-only
  (`409 Restore this company first`).
- **C2 — deactivate, never delete:** a contact gets `active=false` and stays on the record.
  - The primary contact cannot be deactivated while another active contact exists (`409 Make another contact primary first`).
  - The last active contact can be deactivated, and it then stops being primary.
  - A newly added or reactivated contact becomes primary when the company has no primary contact. So a company with at least one active
    contact always has exactly one primary.
  - An inactive contact cannot be made primary (`409 Reactivate this contact first`).
- **C3 — fields:**

  | Field | Rule |
  |---|---|
  | `name` | Required, at most 200 characters |
  | `designation` | At most 120 characters |
  | `department` | At most 120 characters |
  | `role_id` | An active `rec_contact_roles` row. A stored inactive role may be kept |
  | `mobile` | At most 40 characters, and it must normalise (`notifications.phone.normalise_phone`) → `mobile_normalized` |
  | `email` | At most 255 characters, matches `_EMAIL_SHAPE`, lower-cased |
  | `linkedin_url` | At most 300 characters, http(s) only; a bare domain becomes `https://` |
  | `preferred_channel` | `call`, `whatsapp` or `email` |
  | `notes` | At most 2000 characters, multi-line |

  No field other than `name` is required.
- **C4 — cap:** a company holds at most 50 contacts, active and inactive together (`409`). This bounds the response, which is not paginated.
- **C5 — §3 Business Details:** these are shown from the contacts and are not stored.
  - HR Contact = the active contacts whose role is "HR Manager" or "HR Head".
  - Talent Acquisition Contact = "Talent Acquisition Manager".
  - Hiring Manager = "Hiring Manager".
  - HR Email and HR Phone = the primary contact's when the primary holds an HR role, otherwise the first active HR contact's.

  Roles are matched by their seeded names, case-insensitively, in the UI (a pure helper).
- **C6 — Last contacted:** `last_contacted_at` is returned as `null` until calls, messages and meetings exist (rec-025, rec-026,
  rec-028). Acceptance criterion 3 is deferred to rec-025. Next follow-up is rec-024's.
- **C7 — "+ Add Recruiter":** `POST /recruiter/companies` accepts an optional `contact` object. The company and its first contact (which
  is primary) are created in one transaction. The companies list shows "Add recruiter" next to "Add company". It opens
  `/recruiter/companies/new?with=contact`, where the form starts with a "Recruiter contact" section holding name, designation, role,
  mobile, email and LinkedIn.
- One person who works for two companies is two rows. There is no duplicate check on contacts. No export (PII).

## 2. Data

`company_contacts` (migration `0109_company_contacts`):

- `id`, `company_id` (FK companies, RESTRICT), `position` (identity: insertion order)
- `name`, `designation`, `department`, `role_id` (FK rec_contact_roles), `mobile`, `mobile_normalized`, `email`, `linkedin_url`,
  `preferred_channel`, `notes`
- `is_primary` (default false), `active` (default true), `created_by_user_id`, `created_at`, `updated_at`

Constraints and indexes:
- CHECK `preferred_channel IS NULL OR preferred_channel IN ('call','whatsapp','email')`.
- CHECK `NOT is_primary OR active`.
- Index `ix_company_contacts_company (company_id)`.
- Partial unique index `uq_company_contacts_primary (company_id) WHERE is_primary`.
- Index `ix_company_contacts_mobile (mobile_normalized)`, for rec-025 and later lookups.

`downgrade()` refuses while any row exists.

## 3. API (§12AR)

| Route | Who | Result |
|---|---|---|
| `GET /recruiter/companies/{id}/contacts` | the company's read scope (rec-003) | `{items, can_edit}`: primary first, then active, then by position |
| `POST /recruiter/companies/{id}/contacts` | C1 | `201 {items, can_edit}` |
| `PATCH /recruiter/contacts/{contact_id}` | C1 on the contact's company | `{items, can_edit}`; `is_primary: true` and `active` are allowed |
| `POST /recruiter/companies` (+ `contact`) | rec-003 creators | `201 {company}`; the contact is created as primary |

Rules that apply to every route:
- Out of scope, or missing, is a 404 ("Company not found" or "Contact not found").
- A wrong role is a 403, and a wrong state is a 409.
- Unknown fields are a 422 (`extra="forbid"`).
- Every write locks the company row (`load_scoped(lock=True)`), changes the contacts, writes an audit row
  (`recruiter_company.contact_create` or `recruiter_company.contact_update`, with the contact id and field names only) and commits once.
- A primary switch clears the old primary and flushes before it sets the new one, so the partial unique index is never violated.

## 4. UI

- **Contacts section:** `RecruiterCompanyContacts.tsx` is a section on the company detail page.
  - It starts with a "Business contacts" summary (C5), then lists the contacts as cards with Primary and Inactive badges.
  - Actions are Edit, Make primary, Deactivate (confirmed first) and Reactivate. They render only when `can_edit` is true.
  - The editor is inline and shares `RecruiterContactFields` with the create form.
  - It has a loading state, an error state with Retry, and an empty state.
- **Create form:** `RecruiterCompanyForm` takes `withContact`. Contact field errors map from `loc ["body","contact",<field>]`.

## 5. Tests

- **pytest:**
  - `test_rec_004_contacts.py`: create with every field, 422s, scope 404s, BDM and manager read with write 403, archived 409, the primary
    rules, the cap, the audit row, and Add Recruiter.
  - `test_rec_004_migration.py`.
- **vitest:** `RecruiterCompanyContacts` and the Business-contacts helper.
- **Playwright:** `rec-004-contacts.spec.ts`.
