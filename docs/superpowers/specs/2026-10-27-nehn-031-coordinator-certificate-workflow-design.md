# nehn-031 — Coordinator certificate workflow (design)

- **Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-031` (§11 L237-248, §10 L231; `UNVERIFIED` backlog);
  `DEC-ROLE-003` (CONFIRMED_CURRENT 2026-09-12: new distinct role, **exclusive** issuance, old path removed only once the coordinator
  flow exists). Dependencies merged: nehn-030 (`DEC-SCOPE-293`, the role and portal) and nehn-005 (`DEC-SCOPE-281`, the matrix).
- **Decision:** `DEC-SCOPE-296`. **API:** §12GT. **RBAC:** §2.207. **Migration:** `0203_certificate_workflow`.

## Intent

Certificates are issued only when the student is eligible, by the Coordinator, not by any trainer or admin. A trainer, who knows the
learner, can recommend a learner or flag them as not ready; the coordinator works a queue and issues one or many at once. Issuing a
learner who is not eligible needs a separate, revocable permission and a written reason, and is audited. Admins tune the thresholds.

## Builder's defaults (owner pre-authorised the recommended answers; `NEEDS_CONFIRMATION`)

| # | Open question | Default in place |
|---|---|---|
| W1 | Thresholds per course or global? | Global: one `certificate_rules` row with `min_progress_percent` (100) and `min_attendance_percent` (75). The other conditions (all published assignments graded, all assessments passed, no pending/overdue IT fee) stay fixed. |
| W2 | Who edits thresholds? | The new grant `certificates.configure`, default `it_admin` (super_admin implicitly). Audited. Applies to the next evaluation. |
| W3 | Who issues? | The grant `certificates.issue`, default **coordinator only**. Trainer and it_admin lose it (403) — the cut-over. super_admin holds every key implicitly (engine P5) but has no queue UI. |
| W4 | Who may override eligibility? | The grant `certificates.override`, default coordinator. A Super Admin can revoke it on the matrix. Reason required (≤ 1000 chars), stored on the certificate snapshot and the audit log. |
| W5 | Is a trainer recommendation required before issue? | No. The queue shows every un-certified enrolment that is eligible **or** has a trainer recommendation/flag; the recommendation is shown next to it. |
| W6 | Recommendation rules | Trainer of the enrolment's batch only. `recommended` (comment optional) or `not_ready` (comment required); a later call replaces it (one per enrolment). Not allowed once the certificate is issued (409). |
| W7 | Duplicate issue | 409 (was: 201 returning the existing certificate). The enrolment row is locked (`SELECT … FOR UPDATE`) while issuing, so two concurrent issues cannot both create one. |
| W8 | Bulk issue | `POST /it/certificates/issue` with 1–50 enrolment ids; each is checked and issued on its own; the answer lists `issued` and `failed` (with the reason) per enrolment, 200. PDFs are generated in the request, as today (no worker job). |
| W9 | Revocation / reissue, email | Out of scope (`NEEDS_CONFIRMATION`). The existing in-app "Certificate issued" notification stays. |

## Design

**Matrix.** `rbac.CATALOGUE["certificates"]` actions become `view, issue, override, configure`. `DEFAULT_GRANTS`: coordinator gets
`certificates.view/issue/override`; it_admin gets `certificates.configure`. Migration 0202 seeds those rows (frozen copy).

**Tables.** `certificate_rules` (id = 1 only, two integer thresholds 0–100, `updated_by_id`, timestamps), seeded with 100/75.
`certificate_requests` (enrollment_id unique, status `recommended|not_ready|issued`, comment, recommended_by_id, certificate_id,
timestamps). Downgrade drops both and deletes the seeded grants.

**Eligibility.** `_certificate_eligibility` reads the rules row (falls back to 100/75) and adds `rules` to its result, so the
certificate snapshot records the thresholds used. The GET eligibility route also admits the coordinator.

**Routes (all under `/workflows`).**
- `GET /it/certificates/rules` (it_admin, super_admin, coordinator, trainer) · `PUT /it/certificates/rules` (`certificates.configure`).
- `POST /it/certificates/{enrollment_id}/recommend` `{status, comment}` (batch trainer) → 200 with the request.
- `GET /it/certificates/queue` (`certificates.issue`) → `{can_override, items:[{enrollment_id, student, program, batch, eligible,
  criteria, recommendation}]}`; enrolments without a certificate that pass the progress threshold or carry a request (cap 200).
- `POST /it/certificates/issue` (bulk, `certificates.issue`) `{enrollment_ids, override, override_reason}`.
- `POST /it/certificates/{enrollment_id}/issue` stays (same contract) but now needs `certificates.issue`; duplicate → 409.
Override with `override: true` and no `certificates.override` → 403 (whole request). Not eligible without override → 409 (single) or a
failed item (bulk). Eligibility is re-evaluated at issue time.

**Web.**
- Trainer: the "Issue certificate" card in `TeacherWorkspaceActions` becomes "Recommend for certificate" (learner, live eligibility
  summary, Recommend / Not ready, comment).
- Coordinator `/it/coordinator/certificates`: `CoordinatorCertificateQueue` above the issued table — checkbox per row and select all,
  eligibility and recommendation per row, "Issue selected"; the override reason appears when a selected row is not eligible and the
  caller may override. Loading, empty and error states.
- Admin `/it/admin/certificates`: `AdminCertificatePanel` (issue form) is replaced by `CertificateRulesPanel` (two thresholds).

## Acceptance criteria (testable)

1. AC1 Only a `certificates.issue` holder (coordinator) issues; trainer and it_admin get 403 on both issue routes.
2. AC2 Not eligible + override without `certificates.override` → 403; with it, a blank reason → 422; a reason is stored on the
   snapshot and in the audit log.
3. AC3 A threshold change by it_admin applies to the next eligibility evaluation; a non-holder gets 403; out-of-range → 422.
4. AC4 Bulk issue of 30 eligible enrolments creates 30 certificates with unique numbers and PDFs.
5. AC5 The trainer's recommendation (status, comment, trainer) appears in the coordinator's queue; another batch's trainer gets 403.
6. AC6 A duplicate issue → 409 (single) / a failed item (bulk).

## Review notes (Phase 3)

- **API:** additive routes; the single issue route keeps its shape. Bulk returns per-item results (no partial-failure 4xx). Pydantic
  bodies with `extra="forbid"`, bounded lists and strings.
- **Security:** least privilege on the matrix; the override is a separate grant; IDOR — recommend checks batch ownership, issue is
  division-wide by design for the coordinator; row lock against double issue; reasons/comments rendered as text (React escapes).
- **Frontend:** existing `action-card`/`table`/`form` classes; no new dependency.
- **Regression risk:** existing certificate tests and e2e that issue as trainer/admin are moved to the coordinator deliberately
  (`DEC-ROLE-003`), not to make a draft test pass.
