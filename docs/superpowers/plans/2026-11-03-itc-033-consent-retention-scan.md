# itc-033 plan — call consent, retention policy, resume malware scan

Design: `docs/superpowers/specs/2026-11-03-itc-033-consent-retention-scan-design.md`. TDD per task (RED → GREEN → refactor).

1. **Migration + model** — `0239_call_preference`: `notification_preferences.calls_opt_out` (bool, server default false) and
   `calls_opted_out_at` (timestamptz null). Test: columns exist, defaults, downgrade drops them (`test_itc_033_migration.py`).
2. **API** — schemas (`calls: StrictBool | None = None` in, `calls: bool` out); `account.py` GET/PUT/export; audit before/after.
   Tests in `test_itc_033_call_preference.py`; update the enh-014 exact-equality assertions for the additive key.
3. **Staff view** — `it_student_profiles.read` → `student.calls_allowed`; test counselor/admin see it.
4. **Scan hook** — `app/services/malware_scan.py` (clamd INSTREAM client, `settings.clamav_host/port/timeout`); called from
   `student_resumes.upload` after `_checked`, before `store`. Tests with an in-process fake clamd (clean / FOUND / down / unset).
5. **Web** — `NotificationPreferencesForm` "Phone calls from our team" checkbox; `isNotificationPreferences` accepts `calls`;
   `ItStudentProfilePage` notice. Vitest + e2e `itc-033-call-preference.spec.ts`.
6. **Docs** — `DATA_RETENTION_POLICY.md`, DEC-SCOPE, API §, RBAC §, backlog status, `.env.example` comment.
