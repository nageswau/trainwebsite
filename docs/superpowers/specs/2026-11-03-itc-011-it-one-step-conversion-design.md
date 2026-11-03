# itc-011 — One-step IT conversion (lead → student → enrolment → fee plan → onboarding) (design)

Source: `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` §itc-011 (PDF §3 step 6, §9, §12 AC2; PDF classified `UNVERIFIED`). Dependencies
itc-003 (`DEC-SCOPE-337`), itc-010 (`DEC-SCOPE-343`) and itc-013 (`DEC-SCOPE-346`) are merged. Q-09 and Q-10 are open; the owner said to
proceed with the recommended answers, so C1–C10 below are **the builder's calls (`NEEDS_CONFIRMATION`)**. The decision, API and RBAC
numbers are taken after merging main (see the register / API_CONTRACT / RBAC_MATRIX blocks naming itc-011).

## 1. What exists (Graphify discovery)

| Piece | Where | Reused as |
|---|---|---|
| Overseas one-step convert (ccrm-008) | `services/lead_conversion.convert`, `POST /counselor/leads/{id}/convert` | shape of the flow; untouched |
| Account + welcome token, mail budget | `services/counselor_students.create_student` / `deliver_link` (csc-002) | gains a `division` argument (IT student, no overseas counselor row) |
| Lead → student link, stage move, itc-003 counselor | `services/lead_handover.link_student` / `commit_link` | called as is |
| Enrolment checks + insert | `api/workflows.create_enrollment` | checks/insert moved to `services/it_enrollments.seat`; the route calls it (same behaviour) |
| Fee rows / account | `Payment(enrollment_fee)`, `_ensure_invoice`, `services/fee_accounts.account` | fee rows written here; account read back |
| Counseling prefill | `LeadCounselingRecord.fee_quoted`, `recommended_product_id → TelProduct.program_id` | dialog defaults |
| Checklist engine (ccrm-018/019) | overseas application checklists (country/university scoped) | **not** reused (C1) |

MUST CHANGE: new `services/it_conversion.py`, new `services/it_enrollments.py`, `api/lead_handover.py` (counselor routes), `api/admin.py`
(IT admin routes), `api/workflows.py` (calls `seat`; new onboarding routes), `services/counselor_students.py` (division argument),
`services/lead_handover.permissions` (`convert_it`) and `detail` (`it_conversion`), `schemas.py`, `models.py`, a migration, web
`components/ItConvertForm.tsx`, `components/ItOnboardingChecklist.tsx`, `lib/itConversion.ts`, `CounselorLeadDetail.tsx`,
`AdminLeadManagementPanel.tsx`.
SHOULD NOT CHANGE: overseas conversion behaviour, consent activation, fee maths, link/unlink rules.
HIGH REGRESSION RISK: `workflows.create_enrollment` (shared hub; itc-031 hooks it too), `counselor_students.create_student` (csc-002,
ccrm-008), the lead detail payload (`permissions` dict).

## 2. Behaviour

`POST /counselor/leads/{id}/convert-it` (owner IT counselor) and `POST /admin/leads/{id}/convert-it` (IT Admin), header
`Idempotency-Key` (required), body:

```
{ "student": {full_name, email, phone?}  |  "student_id": <existing IT student>,
  "batch_id": ..., "fee": >= 0, "installments": [{amount > 0, due_date >= today IST}, ...]? }
```

In **one transaction**, on the locked lead:

1. refusals first (nothing written): not convertible (closed / linked / before Qualified / Application onwards) → 409; batch missing →
   404, not an open IT batch or full → 409 (batch row locked, as `create_enrollment`); installment sum ≠ fee → 422; a new account whose
   email or mobile matches an active IT student → 409 `student_exists` (the dialog offers "link existing"); an email used by any other
   account → 409 without naming it;
2. creates the `User(it_student)` (csc-002 rules: unusable password, Student ID, welcome token, mail budget) **or** takes the chosen
   existing active IT student (C3);
3. links lead → student (`link_student`: stage → Application/Enrollment, itc-003 counselor = lead owner);
4. seats the enrolment (`pending_consent`, C2);
5. writes the fee rows: none for fee 0; one pending `enrollment_fee` row without installments; else one row per installment
   (`installment_no`, `due_date`) — invoices issued as today;
6. copies the active onboarding template into the enrolment's checklist;
7. records an `it_conversions` row (lead, key, actor, student, enrolment) and an audit row;
8. commits once (`commit_link` turns the unique-student race into 409); then mails the welcome link (new accounts only).

Answer 201: `{student, enrollment, fee_account, checklist, lead, email_status?}`. A retry with the same key on that lead answers 200
with the same shape from the stored row and creates nothing; another key on a converted lead → 409.

`GET .../convert-it` (same callers): the prefill (name/email/phone from the lead, fee from the latest counseling `fee_quoted`, the
recommended course), the open IT batches (recommended course first, seats left), and the checklist preview.

Onboarding checklist: `GET /it/enrollments/{id}/onboarding` (student own, linked IT counselor, IT Admin) and
`PATCH /it/enrollments/{id}/onboarding/{item_id}` `{done}` (linked IT counselor, IT Admin). Shown on the lead detail after conversion.

## 3. Builder's calls (`NEEDS_CONFIRMATION`)

- **C1 (Q-09)** a small IT-only template table `it_onboarding_template_items` (label, position, active), seeded with five neutral items
  (set password and sign in; accept the enrolment agreement; upload ID proof; upload qualification certificate; attend batch
  orientation), and a per-enrolment `it_onboarding_items` copy (label, position, done_at, done_by). No admin editor yet (follow-up);
  ccrm-018/019 is application-scoped and not reused.
- **C2 (Q-10)** consent is **not** skipped: the enrolment starts `pending_consent` (STU-009-AC02). The lead moves to
  Application/Enrollment now and to Converted when the student accepts the agreement (existing `sync_conversion`).
- **C3** "link existing" = the same endpoint with `student_id` of an active IT student (the counselor already sees matches through
  link suggestions); no welcome mail then.
- **C4** an email used by an overseas student, staff or anyone else → 409 "This email belongs to another account. Use a different email."
  — no name, role or division revealed.
- **C5** phone-only lead: the dialog asks for an email (sign-in needs one).
- **C6** fee 0 (scholarship): no fee row; the account reads "not billed".
- **C7** installments optional, at most 12, each > 0 and due today or later (IST), summing exactly to the fee.
- **C8** `Idempotency-Key` 1–120 of `[A-Za-z0-9._:-]`, required (422); scoped to the lead.
- **C9** callers: the lead's owner IT counselor (`counselor_scope` + IT) and the IT Admin (own division); super_admin is not included
  (csc-005 C13 precedent). Overseas counselor → 403.
- **C10** a non-convertible stage is 409 (backlog), unlike ccrm-008's 422.

## 4. Acceptance criteria (testable)

1. One request creates student, enrolment, fee rows, checklist, counselor link and the lead link; nothing is re-typed (prefill).
2. The lead stays linked to the student (lead detail shows the student, enrolment milestone and the checklist).
3. Same `Idempotency-Key` retry → 200, no new rows.
4. Any failure (forced error after the enrolment insert) rolls back everything.
5. Full/closed batch → 409; non-convertible lead → 409; overseas counselor → 403; another counselor's lead → 404.
6. Existing IT student match → 409 `student_exists`; then conversion with `student_id` succeeds without a mail.
7. Fee 0 → no fee row; installments → one row each; bad sum → 422.

## 5. Regression risks

ccrm-008/csc-002 tests (create_student signature), tel-018 link/sync tests, `create_enrollment` tests, the lead detail `permissions`
consumers (new key only), itc-012/013/016 fee and profile tests.
