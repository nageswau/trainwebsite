# rec-004 Company contacts — Implementation Plan

> Execution: native (executing-plans) in worktree `.claude/worktrees/rec-004`, branch `feature/rec-004`.

**Goal:** many contacts per company with exactly one primary contact, the §3 business-contact view, and "+ Add Recruiter" (a company and
its first contact created in one step).

**Architecture:**
- A `company_contacts` table.
- A new `services/recruiter_contacts.py` (rules and output) and `api/recruiter_contacts.py` (routes). Both reuse rec-003's
  `load_scoped`, `permissions` and `audit`.
- `POST /recruiter/companies` gains an optional `contact`.
- The UI adds a Contacts section on the company detail page and a contact fieldset on the create form.

**Spec:** `docs/superpowers/specs/2026-10-08-rec-004-company-contacts-design.md`.

## Global Constraints
- Inline RBAC on `User.role` plus rec-003's scope helpers. No `require_*` dependencies.
- Numbering: migration `0108_company_contacts` (down revision `0107_candidates`), `DEC-SCOPE-123`, §12AQ, RBAC §2.49.
- No new dependencies. Logs and audit rows carry ids and field names only. They never carry names, phones or emails.

## Review Focus
1. Two concurrent "make primary" calls on one company → exactly one primary. The company row lock serialises them; there is a test.
2. Deactivating the primary while other active contacts exist → 409. Deactivating the only active contact → allowed, and it stops being
   primary.
3. PATCH on a contact of an out-of-scope company → 404, never 403. This avoids an id oracle.
4. A sent `null` for `name`, `is_primary` or `active` → 422.
5. Add Recruiter with an invalid contact → 422 and no company row is left behind.

## Tasks

### Task 1 — Model and migration
- Add `CompanyContact` and `COMPANY_CONTACT_CHECKS` to `models.py`. Create `0108_company_contacts.py`.
- Test file: `test_rec_004_migration.py`. It checks the chain and single head, that the models match the migration (columns, checks and
  indexes), and that downgrade refuses when rows exist (the rec-003 throwaway-database pattern).

### Task 2 — Schemas
- `RecContactIn`, `RecContactUpdate` (adds `is_primary` and `active`), `RecContactOut` and `RecContactList` in `schemas.py`.
- `RecCompanyCreate.contact: RecContactIn | None`.

### Task 3 — Service and routes (TDD, `test_rec_004_contacts.py`)
- `services/recruiter_contacts.py`:
  - `contacts_of(db, company_id)`
  - `require_editor(user, company)`
  - `check_role(db, role_id, stored)`
  - `set_primary(db, contacts, target)`
  - `add(db, user, company, payload, *, primary)`
  - `list_out(user, company, contacts)`
- `api/recruiter_contacts.py`: the GET and POST routes on companies, and the PATCH route on contacts. Register it in `main.py`.
- Change `recruiter_companies.create_company` to create the contact when one is sent.

### Task 4 — Frontend
- `lib/recruiterContacts.ts`: types, `CHANNEL_LABEL`, `businessContacts()` and `contactBody()`.
- `components/RecruiterContactFields.tsx` and `components/RecruiterCompanyContacts.tsx`.
- Mount the Contacts section in `RecruiterCompanyDetail`.
- `RecruiterCompanyForm` gains `withContact`. `RecruiterCompanyCreate`, `new/page.tsx` (`?with=contact`) and `RecruiterCompaniesPanel`
  gain the "Add recruiter" link.
- vitest: `tests/components/RecruiterCompanyContacts.test.tsx` and `tests/lib/recruiterContacts.test.ts`.

### Task 5 — E2E and docs
- `tests/e2e/rec-004-contacts.spec.ts`.
- Docs: DEC-SCOPE-123, API_CONTRACT §12AQ, RBAC §2.49, DATA_MODEL, and the backlog status.
