# rec-028 — Company meetings (plan)

Spec: `docs/superpowers/specs/2026-10-08-rec-028-company-meetings-design.md`. Branch `feature/rec-028`. Each task uses TDD (red, then
green, then refactor) and runs only the focused tests.

1. **Data.** Add `RECRUITER_MEETING_*` constants, the `RecruiterMeeting`, `RecruiterMeetingParticipant` and `RecruiterMeetingEvent` models
   and the code sequence. Add migration `0117_recruiter_meetings`.
   - Test: `test_rec_028_migration.py` (CHECKs = model, single head, round trip, downgrade refusal).
2. **Schemas.** Add `RecMeetingCreate`, `RecMeetingUpdate`, `RecMeetingOutcome` and `RecMeetingCancel`. Reuse `BdmApptStart`,
   `LeadApptLink`, `_bdm_appt_optional`, the rec-024 multiline text type and `RecFollowUpReason`.
3. **Service and API.** Add `services/recruiter_meetings.py` and `api/recruiter_meetings.py` (router in `main.py`).
   - Create/list: `test_rec_028_meetings.py` (types, participants 422, roles/scope, AC1 stage).
   - Edit/reschedule: history events, past time 422, participants replace.
   - Outcome: before start 422, AC2 follow-up, next action needs due + reason, cap rolls back.
   - Cancel and final states (409); the lists and counts; recruiter options; audit has no free text.
4. **Web.**
   - Add `lib/recruiterMeetings.ts`, the `RecruiterCompanyMeetings`, `RecruiterMeetingForm`, `RecruiterMeetingItem` and
     `RecruiterMeetingsPanel` components, and the `/recruiter/meetings` page.
   - Wire the section into `RecruiterCompanyDetail` and add Meetings to the nav.
   - Tests: vitest for the lib, the section and the panel; update `navigation.recruiter.test.ts`.
5. **e2e.** Add `rec-028-meetings.spec.ts`.
6. **Docs.** Update API_CONTRACT §12AZ, RBAC_MATRIX §2.58, DATA_MODEL, DEC-SCOPE-132, the backlog status, SCREEN_CATALOG and
   ROLE_NAVIGATION.
7. **Checks.** Run lite backend (rec-003/004/005/007/024/028), vitest, tsc, eslint, next build, then e2e and browser QA.
