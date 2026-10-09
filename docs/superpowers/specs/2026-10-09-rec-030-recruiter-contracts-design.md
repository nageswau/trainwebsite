# rec-030 — Recruiter contracts / MoU (design)

- **Feature:** rec-030 (`docs/delivery/RECRUITER_CRM_BACKLOG.md` §rec-030). **Source:** EVID-018 §22 (lines 888–916: 9 fields and
  7 statuses) and §3 (Existing Agreement, MoU/Contract Status, Payment/Commercial Terms). `DERIVED_BLUEPRINT`, in scope by R1.
- **Dependency:** rec-003 (company master), merged as PR #152.
- **Pattern:** bdm-005 `bdm_mous` (clone; R9 "contracts follow the BDM MoU pattern").
- **Decision:** DEC-SCOPE-156, migration `0139_recruiter_contracts`, API §12BX, RBAC §2.82. Merged to `main` as PR #208 @ `819ce385`
  (2026-10-09).
- **Answers:** the owner said "proceed with recommended answers". CT1–CT10 below are the recommended defaults. They are
  **UNVERIFIED** until the owner confirms them.

## 1. Decisions (CT1–CT10, UNVERIFIED)

| # | Question | Recommended answer |
|---|---|---|
| CT1 | Status order / skips (AC1) | Six statuses are stored: Discussion, Proposal Sent, Negotiation, Contract Sent, Signed, Active. The ladder is drawn in source order. Any stored status can be chosen, so skipping ahead and correcting backwards are both allowed, and every change is recorded in the history. This is the bdm-005 rule. |
| CT2 | Expired (AC2) | Expired is derived and never stored. A Signed or Active contract whose end date is before today (IST) reads Expired. The status of an Expired contract cannot be changed (409 `contract_expired`, "start a renewal"), but its dates can still be corrected. |
| CT3 | "Signed requires a document" (AC3) | Signed and Active both need the **contract document** on file. Without it the request is a 422 on `status`. Active also needs a start date and an end date, so that it can expire. The MoU file is optional. |
| CT4 | Recruitment fee (+ basis, Q-24) | `fee_basis` is `fixed` (an INR amount) or `percent_of_ctc` (0–100), and `fee_value` is Numeric(12,2) ≥ 0. Both are optional, but they are sent together. Currency is INR only, and GST and per-requirement overrides are left to rec-031. |
| CT5 | Agreement type | Free text, up to 100 characters. The source gives no list, so none is invented. |
| CT6 | Payment terms, replacement policy | Free text, up to 2000 characters each, multi-line. |
| CT7 | One current contract; renewal | A company has at most one `is_current` row (partial unique index). "Start renewal" makes a new row; it is offered only when the current contract reads Signed, Active or Expired. The old row is kept and shown under "Previous contracts". |
| CT8 | Overlap (edge case → 409) | The date window of the current contract must not overlap the window of any previous contract that has a start date. A missing end date counts as open-ended. An overlap is a 409 `contract_overlap`. It is checked under the company row lock. |
| CT9 | Roles | Read: the company's scope. That is the assigned recruiter; the manager for their team and unassigned companies; super_admin for all; the assigned BDM read-only (R10). Write: the company's `can_edit`, which is the assigned recruiter or super_admin. An archived company is a 409, and the manager has no edit (rec-003 D6). Commercial terms are never sent to the employer portal. |
| CT10 | The company shows the status | The company detail gets an additive `contract` field (`{status, status_label}` or null) and a "Contract status" row in Details. The company list is unchanged. |

## 2. Data model (migration 0139)

`recruiter_contracts`: id, company_id (FK companies, RESTRICT), created_by_user_id, status (String 20, default `discussion`),
status_changed_at, agreement_type, start_date, end_date, fee_basis, fee_value Numeric(12,2), payment_terms, replacement_policy,
contract_document_{key,content_type,name,uploaded_at}, mou_document_{key,content_type,name,uploaded_at}, is_current, created_at, updated_at.

CHECKs (`RECRUITER_CONTRACT_CHECKS`, which the migration test pins):
- the status is one of the six;
- end ≥ start;
- `fee_basis` and `fee_value` are both null or both set;
- `fee_basis` is one of the two values;
- `fee_value` ≥ 0, and ≤ 100 when the basis is a percentage;
- Signed or Active ⇒ a contract document key;
- Active ⇒ both dates;
- each document has its key and content type together.

Indexes: `uq_recruiter_contracts_current` (company_id WHERE is_current) and `ix_recruiter_contracts_company` (company_id, created_at).

`recruiter_contract_events`: id, contract_id, actor_user_id, kind (created/status/updated/document/renewed), from_status, to_status
(effective), changed JSON (field names only), document_key (the replaced object's key, never returned), position Identity, created_at.
The downgrade refuses while any contract exists.

## 3. API (§12BX)

| Method | Path | Notes |
|---|---|---|
| GET | `/recruiter/companies/{id}/contracts` | `{current, previous[], can_start}`. Out of scope is a 404. |
| POST | `/recruiter/companies/{id}/contracts` | The first contract or a renewal (CT7). 201 `{contract}`. 409 `contract_exists` / `contract_overlap`; 422 for the rules. |
| PATCH | `/recruiter/companies/{id}/contracts` | Partial update. A status change carries `from_status` (stale: 409 `contract_status_changed`). An optional `expected_updated_at` (stale: 409 `contract_changed`). Nothing changed means nothing is recorded. |
| PUT | `/recruiter/companies/{id}/contracts/document?kind=contract\|mou` | Multipart. Uses `agent_documents.read_upload` (PDF/JPEG/PNG checked by content, 20 MB, metadata stripped). Server-generated key. 20 uploads per hour per user (429). |
| GET | `/recruiter/contracts/{contract_id}/history` | Paged, newest first. |
| GET | `/recruiter/contracts/{contract_id}/documents/{kind}` | Read scope only; audited before the bytes are sent; the file name is built from the company code. |

Every write is one transaction:
1. lock the company and check scope;
2. `require(can_edit)`;
3. lock the current contract;
4. apply the rules to the merged state;
5. write the change, a history row and an audit row (`recruiter_contract.*`, ids, status keys and field names only — never terms or file names);
6. one commit;
7. one log line.

## 4. UI

`RecruiterCompanyContract` is a section on the company detail page, placed after Meetings. It shows:
- the status badge and a step ladder in source order (text, never colour alone), plus an Expired note;
- Edit and Start renewal buttons, from the API's `permissions`;
- the details (agreement type, dates, fee, payment terms, replacement policy);
- two document rows (contract and MoU) with download and upload controls;
- the history;
- the previous contracts.

`RecruiterContractForm` handles start and edit. Required markers follow the chosen status; a 422 lands on its field; a coded 409 reloads the
section. A write re-reads the company, which updates the "Contract status" row.
The section has loading, empty ("No contract yet") and error ("Try again") states.

## 5. Tests

- Backend: `test_rec_030_contracts.py` covers AC1–AC3, end before start (422), overlap (409), the roles (BDM read, manager 403, other
  recruiter 404, archived 409), documents and download scope, history, renewal and the company `contract` field.
  `test_rec_030_migration.py` covers the chain, the model and migration parity, and the round trip.
- Web: vitest for the lib helpers and for the section and form; a Playwright spec for Proposal Sent → upload → Signed and for Expired.

## 6. Out of scope

- revenue, invoices and per-requirement fees (rec-031);
- a cross-company contract list and expiry reminders (not in the backlog item);
- currency other than INR.
