# rec-001 implementation plan

Spec: `docs/superpowers/specs/2026-10-08-rec-001-recruiter-roles-design.md`. TDD for every task: write the test, see it fail, implement,
see it pass. Lite backend runs in the api-test container. Web runs in the web-test container.

| # | Task | Tests first | Files |
|---|---|---|---|
| 1 | Model + migration 0100 (table, idempotent backfill, guarded downgrade) | `test_rec_001_migration.py` | `models.py`, `alembic/versions/0100_recruiter_profiles.py` |
| 2 | Schemas + `services/recruiter.py` | `test_rec_001_service.py` | `schemas.py`, `services/recruiter.py` |
| 3 | `admin.create_user` / `update_user` branches; rbac; ADMIN_PORTAL_ROLES | `test_rec_001_provisioning.py`, `test_rec_001_update.py` | `admin.py`, `rbac.py`, `provisioning.py` |
| 4 | `/recruiter/*` + `/admin/recruiters`, `/admin/placement-managers`; main.py | `test_rec_001_reads.py` | `api/recruiter.py`, `main.py` |
| 5 | Seed manager + profile | (seed run in QA) | `seed.py` |
| 6 | Web: lib/recruiter, navigation, middleware | `navigation.recruiter.test.ts`, `middleware.test.ts` | `lib/*`, `middleware.ts` |
| 7 | Web: recruiter pages + profile card + team table + phone-form reuse | `RecruiterTeamTable.test.tsx`, `TelecallerPhoneForm.test.tsx` (still green) | `app/recruiter/**`, components |
| 8 | Web: Recruiter Staff admin page | `AdminRecruiterCreateForm.test.tsx`, `AdminRecruiterRow.test.tsx`, `AdminRecruiterPanel.test.tsx` | `components/AdminRecruiter*`, `app/admin/recruiter-staff`, `app/it/admin/recruiter-staff` |
| 9 | WorkflowPanel global role, admin sign-in copy; e2e landing updates + `rec-001-recruiter-roles.spec.ts` | e2e | as named |
| 10 | Docs: DEC-SCOPE-116, API §12AI, RBAC §2.42, backlog status | — | `docs/**` |

## Phase 3 review notes (folded into the tasks)
- **API:**
  - The `/admin/users` body stays an untyped dict, which is the existing contract. Only the new nested key is validated.
  - The new reads use typed `response_model`s.
  - A manager missing or of the wrong role is 422; a duplicate is 409; a wrong role is 403. Every refusal happens before any write.
  - Each route has one commit.
- **Security:**
  - Routes are scoped by session (no IDOR).
  - The manager row takes `FOR SHARE` against a concurrent deactivation.
  - `overseas_admin` is refused on the admin list (403).
  - Logs carry ids only.
  - The phone is validated by the shared `BdmLeadPhone` rule.
  - React escapes all output (no `dangerouslySetInnerHTML`).
  - CSRF uses the existing SameSite cookie, and every write is a POST or PATCH.
- **Frontend:**
  - Reuse PortalShell, SearchableSelect, sendJson, welcomeLinkFeedback and CreateJumpLink.
  - Each page has loading, error with Retry, and empty states.
  - Rows become labelled cards on mobile (`.telecaller-list` CSS class reused).
  - Focus moves to the feedback message.
  - A double submit is guarded with a ref.
