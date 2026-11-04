# hrc-012 Candidate ownership — implementation plan

Design: `docs/superpowers/specs/2026-11-04-hrc-012-candidate-ownership-design.md` (DEC-SCOPE-382, API §12KA, RBAC §2.279, migration 0259).

## Tasks (TDD: red → green → refactor)
1. **Tests (red)** `apps/api/tests/test_hrc_012_ownership.py`: create sets owner (recruiter) / unassigned (manager); list `owner=me|
   unassigned` and `owner` on items; detail `ownership`; PUT by owner, manager, super_admin (200), other recruiter / hr_team (403);
   inactive or wrong-role target 422; collaborators refused while the setting is off, accepted when on, owner-as-collaborator 422, cap 10;
   history rows + audit `candidate.assign`; notice to the new owner, not to the actor; archived 409; settings GET/PUT rights; assignees
   lookup; rec-037 reassign moves candidates and counts them; deactivation refused while owning a candidate; officer dashboard count.
   `test_hrc_012_migration.py`: models match 0259, backfill rule, downgrade.
2. **DB**: models (`Candidate.owner_user_id`, `placement_officer_user_id`, `CandidateCollaborator`, `CandidateAssignmentHistory`,
   `CandidateOwnershipSetting`) + migration `0259_candidate_ownership.py` (down 0256), indexes on both owner columns.
3. **Service** `app/services/candidate_ownership.py`: eligibility, `change()` (lock, diff, history, audit, notify), `my_filter`, outputs,
   settings, `move_owned()` for rec-037. Event `it.candidate.assigned`.
4. **Routes**: `recruiter_candidates.py` (filter, PUT ownership, assignees), settings router, `recruiter_lifecycle` (+candidates),
   `portal._recruitment_role` officer count, schemas (`CandidateItem.owner`, `CandidateDetail.ownership`, work/moved `candidates`).
5. **rec-038 matrix rows** for the new routes.
6. **Web (vitest red first)**: `lib/recruiterCandidates.ts` types + `ownerLabel`; `RecruiterCandidateOwnership.tsx` (card + editor);
   list Owner column/filter + `RecruiterOwnershipSetting.tsx`; team table Candidates column + `workText`.
7. **e2e** `apps/web/e2e/hrc-012-candidate-ownership.spec.ts`: recruiter creates → owner chip; manager reassigns; My candidates filter.
8. **Docs**: decision register, API contract, RBAC matrix, RTM, backlog status.

## Phase 3 review notes (applied above)
- API: PUT (idempotent full-state per key) rather than several POSTs; partial keys; 409 for archived/merged (state conflict), 422 for
  ineligible ids, 403 before any body is read; additive response fields only (`response_model_exclude_unset` kept).
- Concurrency: candidate row FOR UPDATE, target users FOR SHARE (rec-003 lock order: row then user); the deactivation check locks the
  user row first (RC11) so a concurrent assign is either counted or sees an inactive user.
- Security: no reading widened; assignee lookup capped and only for callers who may assign; ids only in logs; notices fixed text.
- Frontend: reuse `SearchableSelect`, `sendJson`, `useFocusAfterRender`, `.badge`; loading/empty/error states; 375px layout via existing
  flex-wrap patterns; keyboard (Escape cancels, error focus).
