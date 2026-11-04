# hrc-003 implementation plan

Design: `docs/superpowers/specs/2026-11-04-hrc-003-concurrent-edit-protection-design.md` (`DEC-SCOPE-370`).

## Review notes (Phase 3)

- **API:** 409 + body token follows the existing `contract_changed` / `mou_changed` pattern (no If-Match/412 anywhere in the API).
  The token is checked under the row lock each route already takes, so two concurrent saves cannot both pass. Schemas with
  `extra="forbid"` get the new optional field; the field never reaches the column-apply loops.
- **Security:** `current` uses the GET serializer for the caller (no new data). `changed_by` is an internal user's name, shown only to
  internal editors already allowed to edit the record. Audit metadata holds field names only; no values are logged. Scope/role checks
  stay first (no existence oracle via 409).
- **Frontend:** the notice is `role="alert"`, takes focus, buttons are real `<button>`s, wraps on mobile; existing form styles.

## Tasks (TDD: failing test → minimum code → green)

1. `app/services/stale_guard.py`: `require_fresh(db, *, stored, expected, entity_type, entity_id, action_prefix, current)` raises
   409 `record_changed` with changes from audit rows. Test via the routes.
2. Requirement PATCH: schema field, check after `require(can_edit)`, touch `updated_at` on any change. Tests: stale 409 body, reload
   succeeds, no token unchanged, skills-only change bumps token, 404 before 409.
3. Candidate PATCH: schema field, check after writer/load. Tests: stale 409 + first edit kept.
4. Interview PATCH: `updated_at` in the shape, schema field, check before the decided rule. Tests: stale 409.
5. JD POST: `expected_version`, compared to the current version under the requirement lock. Tests: stale 409, `0` with existing JD 409.
6. Web: `lib/staleGuard.ts` (parser + re-apply helper) + `components/StaleRecordNotice.tsx`; vitest for both.
7. Wire the four forms + JD apply; component tests for the 409 → notice → Reload / Review flows.
8. Docs: API §12JP, `DEC-SCOPE-370`, backlog status.
