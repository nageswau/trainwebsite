# nehn-039 implementation plan

Spec: `docs/superpowers/specs/2026-10-27-nehn-039-school-document-statuses-design.md`.

1. **API test (RED)** `apps/api/tests/test_nehn_039_school_document_statuses.py`: fixtures from `enh005_helpers` + a bridged
   application with a checklist (passport marked, transcripts missing, "Financial documents" hidden).
2. **Service** `services/application_checklists.item_statuses(db, application_id)` — public wrapper over `_items`/`_status`
   returning name/required/status/sensitivity.
3. **Route** `app/api/school_documents.py` + schemas `SchoolDocumentStatusesOut`; register the router in `app/main.py`.
   Role gate (403), `_load_readable_student` with 403→404, financial filter, audit row, one commit.
4. **Web** `components/SchoolDocumentStatusesCard.tsx` + vitest; add it to the four student pages.
5. **E2E** `apps/web/tests/e2e/nehn-039-school-document-statuses.spec.ts`.
6. **Docs**: DEC register, API contract §, RBAC §, backlog status, feedback tracker — numbers taken after merging main.
