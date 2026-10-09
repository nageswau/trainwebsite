# upc-012 — University calls, message templates, WhatsApp and email (plan)

Spec: `docs/superpowers/specs/2026-10-09-upc-012-university-comms-design.md` (DEC-SCOPE-140, UC1–UC10).
Branch `feature/upc-012`. TDD per task: write the test, see it fail for the expected reason, implement, see it pass.

## Backend
1. **Models + migration 0125.** `PARTNERSHIP_MESSAGE_*` / `UNIVERSITY_CALL_*` constants and checks; `PartnershipMessageTemplate`,
   `UniversityCall`, `UniversityMessage`. Migration guarded, downgrade refuses with rows. Test: `test_upc_012_migration.py` (checks equal
   the models', single head, downgrade refusal).
2. **Schemas.** `PartnershipTemplateCreate/Update`, `UniversityCallCreate`, `UniversityWhatsAppCreate | UniversityEmailCreate`;
   `UniversityContactOut` + `whatsapp_to`, `last_interaction_at`.
3. **Service `services/university_comms.py`.** Template rules (UC4/UC5), the contact as party (UC3), call create (UC1), message create
   (UC6–UC8), lists, last interaction (UC10), audit/log (UC9).
4. **Routes `api/university_comms.py`** + `main.py`. Tests `test_upc_012_comms.py` (see spec §6).
5. **Contacts.** `contact_out` takes `whatsapp_to` + `last_interaction_at`; list and detail compute them.
6. **Worker.** `notifications/university_email.py`, `dispatch.enqueue_university_email`, worker tasks + beat; conftest fixture.
   Test `test_upc_012_delivery.py`.

## Web
7. **`lib/partnershipComms.ts`** + test.
8. **Templates panel `library` prop** (recruiter default unchanged) + `/partnership/head/templates` page + head nav. Tests: the existing
   `RecruiterTemplatesPanel.test.tsx` and a partnership-library case; nav test.
9. **`UniversityCallForm` + `UniversityCalls`** + test.
10. **`UniversityMessages`** (reusing the composers and `MessageItem`) + test.
11. **University page + `UniversityContacts` last interaction**; page test stubs.

## Verify and document
12. Focused pytest + vitest + tsc + eslint + ruff/mypy on touched files; `next build`.
13. Playwright `upc-012-university-comms.spec.ts`; browser QA (desktop/tablet/mobile).
14. Docs: DEC-SCOPE-140, API §12BH, RBAC §2.66, DATA_MODEL, SCREEN_CATALOG, backlog status.
