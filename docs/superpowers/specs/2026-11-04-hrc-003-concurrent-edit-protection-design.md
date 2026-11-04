# hrc-003 — Concurrent-edit protection and "changed since you opened it" (design)

- **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-003` (PDF §4.1 "Prevent silent overwriting … show the latest
  version and offer reload/reconcile", §12 "Warn users if a record changed since they opened it", §17 QA #3; PDF `UNVERIFIED`).
  Scope approved by the owner 2026-11-01 (backlog Q-00). Dependencies: none.
- **Decision:** `DEC-SCOPE-370`. The owner said to proceed with the recommended answers, so S1–S8 are **the builder's calls
  (`NEEDS_CONFIRMATION`)**.

## Intent

Two recruiters open the same requirement, candidate, interview or JD. Today the second save silently overwrites the first (the job
PATCH locks the row but compares nothing; the candidate edit form even sends every field). After this item the second save is refused
with 409, the user is told who changed what and when, and chooses **Reload** (discard mine) or **Review my changes** (re-apply mine on
top of the latest, then save again). Nothing is merged automatically.

Non-goals: guarding status moves, reschedule, feedback, skill weights, uploads (each is an explicit, already-validated action, not a
form of stale field values); the legacy `/workflows/it/*` and employer `/employer/jobs` writes (S6).

## Builder's calls

- **S1 (Q-05) token = `updated_at`.** `TimestampMixin.updated_at` is `timestamptz` (microseconds) set by `onupdate=now()`; no version
  column, no migration. A write that changes only the requirement's skills (a child table) now touches `jobs.updated_at` too, so it is
  seen. Non-user writes that bump `updated_at` (placement-pool contact sync, offer joining closing a job) are real changes; a 409 after
  them is a safe false positive, never a silent overwrite. The **JD** is append-only versions with no `updated_at`; its token is the
  current **version number** (`expected_version`; `0` = "there was no JD when I opened it").
- **S2 (Q-05) optional now, required later.** Absent = no check (older clients and other callers keep working). Every CRM form sends
  it. Making it required is a follow-up once no client omits it.
- **S3 409 body.** `detail = {code: "record_changed", message: "This record changed since you opened it", changed_by: {id, full_name} |
  null, changed_at, changed_fields: [..], current: <the GET shape for that record>}`. `current` goes through the same serializer as GET,
  so field visibility is unchanged.
- **S4 who / what / when** come from the record's own audit rows written after the client's token (`audit_logs` is indexed by
  `(entity_type, entity_id, created_at)`): fields = each row's `metadata.fields`, else the action's last segment (`status`, `archive`,
  `reschedule` …); by = the newest row's actor; at = the newest row's time, else the stored `updated_at`. A change with no audit row
  shows no name and no fields.
- **S5 order of checks.** Scope (404) and role (403) first, then the token (409 `record_changed`), then the business rules (the archived
  / decided 409s, 422s). A matching token with a no-op body is unchanged behaviour.
- **S6 scope.** `PATCH /recruiter/requirements/{id}`, `POST /recruiter/requirements/{id}/jd`, `PATCH /recruiter/candidates/{id}`,
  `PATCH /recruiter/interviews/{id}`. The interview GET shape gains `updated_at`. Legacy and employer job routes are unchanged
  (optional token, their UIs do not send it; follow-up when they are retired or reworked).
- **S7 UI.** One shared `StaleRecordNotice` (an alert region in the form, not a modal) and a `staleConflict()` parser in
  `lib/staleGuard.ts`. Text: "This record changed since you opened it (by X at T, IST). Changed: A, B." Buttons **Reload** and
  **Review my changes**. Review re-bases the form on `current` and re-applies the fields the user had edited; the notice then lists
  each of them as "yours → now on record" (flagging those someone else also changed) and the user saves (with the new token) or edits
  further. The token is passed back as the exact string the API sent (never through `Date`, which drops microseconds).
- **S8 "Update requirement from JD"** sends the requirement token; on 409 the page takes `current` and the message asks the user to
  check the changes and apply again.

## Acceptance (testable)

1. Two users edit the same job: the second save gets 409 `record_changed` with `changed_fields`, `changed_by`, `changed_at`, `current`.
2. After reload (the new token), the second save succeeds.
3. No silent overwrite: the first user's values are still stored after the refused save (job, JD, candidate, interview).
4. A single editor saves normally; a request without a token behaves exactly as before.
5. Out-of-scope still 404, wrong role still 403, before any 409.
6. The UI shows the notice with Reload / Review my changes on all four forms.

## Numbering

No migration. API §12JP. No RBAC change.
