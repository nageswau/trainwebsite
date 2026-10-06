# tel-005 implementation plan

Spec: `docs/superpowers/specs/2026-10-06-tel-005-lead-intake-design.md`. TDD on every task: RED → GREEN → refactor.

1. **Migration + model.** Test `test_tel_005_migration.py`: email nullable, `lead_enquiries` columns/CHECK/index, downgrade round-trip.
   Implement `0085_lead_enquiries.py`, `models.LeadEnquiry`, and `Enquiry.email` nullable.
2. **Intake service + manual create.** Test `test_tel_005_intake.py`:
   - create → 201, Assigned to the telecaller, and the audit row;
   - a manager → New/unassigned;
   - the R5 product/campaign/division rules;
   - a duplicate by mobile in another format, by email in another case, and on a closed lead → 409 panel without phone/email;
   - `in_scope`;
   - roles 401/403.
   Implement `services/lead_intake.py` and the schemas `TelecallerLeadCreate`, `LeadEnquiryCreate`, and the routes.
3. **Duplicate check + add enquiry.** Tests:
   - GET check (match / none / 422);
   - POST enquiries on another telecaller's lead and on a closed lead (it stays closed) → 201, 404 unknown;
   - the timeline shows the enquiry row.
4. **Website attach.** Test `test_tel_005_public.py`:
   - a known email or phone attaches: no new lead, same keys, status "new", no CRM queue;
   - an unknown one creates as before;
   - the newest match wins.
   Rewire `public.create_enquiry`.
5. **Frontend.** Vitest for `NewLeadForm` (submit payload, 409 panel, add enquiry, division visibility) and the timeline enquiry row. Implement the lib types/helpers, `NewLeadForm.tsx`, the new pages, the New lead button, the `LeadDetailPanel` enquiry row and email-required tweak, and `AdminLeadManagementPanel` email null-safety.
6. **Playwright** `tel-005-lead-intake.spec.ts`: create → detail; a duplicate → panel → add enquiry; mobile layout.
7. **Docs:** DEC-SCOPE-087, API contract §12K, backlog status, data model note.

Lite backend set: tel_005_*, tel_003_intake, tel_003_admin_leads, tel_004_*, tel_008_workspace, pub_002_enquiry_crm, bdm_017_leads.
