# ccrm-006 Lead stages + loss capture — implementation plan

Spec: `docs/superpowers/specs/2026-10-25-ccrm-006-lead-stages-loss-design.md` (DEC-SCOPE-261, 0183, §12FN, §2.175).

1. **Catalogue + schema** — `lead_stages.py` (`duplicate`, "Invalid Contact", `LOSS_STAGES`), `LeadLostReason` model, Enquiry columns
   and CHECKs, migration `0183_lead_loss_capture` (guarded, seeds when empty, downgrade maps duplicate→lost). Tests:
   `test_ccrm_006_migration.py` (model = migration, round trip); `test_tel_004_migration` compares 0081's frozen copy to the pre-0183 list.
2. **Engine** — `lead_pipeline.person_move(..., closure)` validates D3/D4/D5, stores, clears on reopen (D7). Schemas gain the three
   optional fields; the three routes pass them. Tests: `test_ccrm_006_loss_capture.py` (422s, happy paths, reopen clears, counselor,
   admin PATCH, call-logged close unchanged).
3. **Lead rows** — `bdm_leads.admin_rows/admin_out` gain `duplicate_of`, `lost_reason`, `lost_to`.
4. **Reason list** — `GET/POST/PATCH /telecaller/lost-reasons` on the tel-002 helpers. Tests in the same file.
5. **Reports** — tel-024 `lost` kind; mgmt TC9 excludes Duplicate. Tests in the same file.
6. **Web** — `leadStages.ts` mirror; `LeadStageControl` closure fields; `LeadClosure` line on the three detail views; manager page +
   nav; reports tab. Vitest for lib + control; Playwright `ccrm-006-loss-capture.spec.ts`.
7. **Docs** — decision register, API contract, RBAC matrix, RTM, backlog status.

Lite backend set: ccrm-006 files + tel-004 (pipeline/routes/migration), tel-002 products, tel-024 reports, tel-010 calls,
ccrm-003 counselor lead actions, mgmt telecalling test, tel-018/admin leads tests that read the lead row.
