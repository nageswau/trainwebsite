# pob-014 plan — institution student pool

Spec: `docs/superpowers/specs/2026-11-07-pob-014-institution-student-pool-design.md` (DEC-SCOPE-425). TDD per task; focused tests only.

1. **Model + migration 0306** — `InstitutionDataPermission`, `InstitutionDataPermissionUser`, candidate columns, batch column; guarded
   migration with frozen checks. Test: `test_pob_014_migration.py` (columns, guard, model parity).
2. **Visibility predicate** — `services/institution_pool.visible_to(entity, viewer_id)`; `candidates.pool_filter(viewer_id=None)`,
   `load(..., viewer_id=None)`; recruiter routes pass `user.id` (list, detail and sub-resources, notes/tasks, calls, messages, timeline,
   skills, applications, search). Duplicate queue + `find_matches` redaction. Tests: AC2 (outsider 404 on detail, absent from list and
   search), fail-closed (talent-pool / no viewer).
3. **Permissions API** — create / patch / revoke (manager-only, scope 404, validation 422, audit). Pool view GET with filters and
   placement status. Tests: role matrix, validation, AC3 (expired hides; revoke hides), pool filters.
4. **Import** — `institution_permission_id` + `notice_status` on preview/commit; stamping; replay rule; report redaction. Test: AC1.
5. **Sharing** — purpose + visibility check in `profile_sharing._candidates`. Test: AC3 not shareable, purpose 422.
6. **Search** — `institution_id`. Test.
7. **Web** — `lib/institutionPool.ts`, `InstitutionStudentPool.tsx` on the college page, import wizard permission mode; vitest.
8. **Docs** — DEC-SCOPE-425, API §12LR, RBAC §2.316, DATA_MODEL, RTM rows, backlog status; rec-038 matrix rows.
9. **E2E** — `pob-014-institution-pool.spec.ts`: manager creates permission → recruiter imports → pool shows → outsider 404.
