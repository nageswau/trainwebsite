# mgmt-029 — Management meetings + minutes chain — implementation plan

Spec: `docs/superpowers/specs/2026-10-14-mgmt-029-management-meetings-design.md` (MM1–MM14). TDD: each task starts with its failing test.

1. **Data** — `models.py` (`MEETING_KINDS`, `MEETING_STATUSES`, `ManagementMeeting`, `ManagementMeetingParticipant`,
   `ManagementDiscussion.meeting_id`), migration `0159_management_meetings`, audit kind `mgmt.meeting`.
   Test: `test_mgmt_029_migration.py` (chain, model ↔ migration, round trip, refusal).
2. **Schemas** — `MeetingCreate/Update`, `MeetingMinutesIn`, `MeetingDecisionIn`, `MeetingTaskIn`, `MeetingOut/Detail/Page`,
   `MyMeetingOut/Page`; `DiscussionOut.meeting_id`.
3. **Service + API** — `services/management_meetings.py`, `api/management_meetings.py`, registered in `main.py`.
   Test: `test_mgmt_029_meetings.py` (spec §6), written first, run red, then green.
4. **Web lib** — `lib/managementMeetings.ts` + `tests/lib/managementMeetings.test.ts`.
5. **Web components/pages** — calendar, form, chain, staff section; `/management/meetings*`; Command Center href; staff page section;
   discussion page "From meeting". Test: `tests/components/ManagementMeetings.test.tsx`.
6. **E2E** — `tests/e2e/mgmt-029-meetings.spec.ts`.
7. **Docs** — DEC-SCOPE, API §12DZ, RBAC §2.137, backlog status, QA report.

Risks: the new `management_discussions` column (nullable, additive); `main.py` router tuple (one-line append, no reformat); the shared
staff page (one more parallel read — a failed meetings read must not break tasks/decisions).
