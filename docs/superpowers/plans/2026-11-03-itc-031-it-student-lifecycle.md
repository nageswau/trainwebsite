# itc-031 plan — unified IT student lifecycle status and history

Design: `docs/superpowers/specs/2026-11-03-itc-031-it-student-lifecycle-design.md`. TDD per task (RED → GREEN → refactor).

1. **Migration + model** — `0240_enrollment_lifecycle` on `0239_call_preference`: `enrollment_lifecycle_history`; enrolment
   `lifecycle_override` (+ CHECK) and `lifecycle_override_reason`; `ck_enrollments_status` NOT VALID, validated when clean.
   Test `test_itc_031_migration.py`.
2. **Derivation** — `services/it_lifecycle.py`: `STAGES`, `LABELS`, `derive_many`, `safe`. Tests `test_itc_031_lifecycle.py`
   (each component, precedence, the newest-enrolment rule, the "+" Partially Paid → Paid case).
3. **History writer** — `sync`, `sync_students`, `sync_all`; hooks in fee record, `_mark_paid`, admin enrolment PATCH/approve/reject,
   enrolment create, consent, certificate issue, HR review moves, `applications.change_status`, the daily sweep.
   Tests: history rows with actor/time on each hook; no duplicate row when nothing changed.
4. **API** — lifecycle GET (counselor/admin), override PUT (admin), payload additions, admin PATCH status 422.
   Tests `test_itc_031_lifecycle_api.py` (scope 404, counselor override 403, Placed 409, not_placed/closed + history + audit).
5. **Web** — `ItLifecycleCard` (badge, components, history list, admin override form) on the 360; student safe badge.
   Vitest `Itc031Lifecycle.test.tsx`; e2e `itc-031-lifecycle.spec.ts`.
6. **Docs** — DEC-SCOPE-358, API §12JD, RBAC §2.258, backlog status.
