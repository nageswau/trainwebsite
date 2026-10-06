# tel-002 implementation plan

Spec: `docs/superpowers/specs/2026-10-06-tel-002-catalogue-design.md`. TDD per task (RED → GREEN → refactor); lite tests only.

1. **Migration + models** — `TelProduct`, `TelCampaign` in `models.py`; `0076_tel_catalogue.py` (guarded create, idempotent seed,
   refusing downgrade). Test `test_tel_002_migration.py`: single head after 0075, model ↔ migration, 18 seed rows/teams (AC1), seed
   idempotent, CHECKs (team/group, program IT-only, dates), round trip, downgrade refusal.
2. **Products API** — schemas (`TelProductCreate/Update/Out/Page`), `services/telecaller_catalogue.py` (readers/manager role sets,
   integrity → 409, product/program checks, audit), `api/telecaller_catalogue.py` GET/POST/PATCH products; register router.
   Test `test_tel_002_products.py`: read roles + active-only for readers (P1, AC2), manager CRUD, 403 for non-managers (AC5), 409
   duplicate per group case-insensitive, P2 team rules (AC7), program link, rename keeps id (AC6), 404, audit row.
3. **Campaigns API** — schemas + GET/POST/PATCH campaigns. Test `test_tel_002_campaigns.py`: source enum (AC3), active product
   required on create/move but unchanged inactive product editable (P4), dates (AC4, merged-row check on PATCH), 409 duplicate name,
   filters, reader active-only, 403.
4. **Frontend** — `lib/telecallerCatalogue.ts`, nav entries, pages `/telecaller/manager/products|campaigns`, Panels + Rows. Vitest for
   the panels/rows (create, validation error shown, edit/Esc, deactivate confirm, empty/error states) and nav.
5. **Playwright** — `tel-002-catalogue.spec.ts`: manager sees the seeded products, creates a campaign (AC example "Sep 2026 Cyber
   Security", Instagram), end<start error, deactivate product → absent from the campaign form's picker; telecaller gets 403 on POST.
6. **Docs** — `DEC-SCOPE-074` (P1–P4), `API_CONTRACT.md`, `RBAC_MATRIX.md`, `ROLE_NAVIGATION.md`, `SCREEN_CATALOG.md`, backlog status.
