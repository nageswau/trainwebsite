# ccrm-024 — Offer conditions — design

Date 2026-10-25. Backlog: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` § `ccrm-024` (source §9 "conditions to satisfy, owner, due date and
completion evidence"; §11 offer condition due). Depends on ccrm-023 (merged, PR #307). Decision `DEC-SCOPE-260`. Migration
`0182_offer_conditions` (after ccrm-004's `0181_lead_meetings`). API §12FM. RBAC §2.174. Re-chained 2026-10-25 after ccrm-004 (PR #322)
took 0181 / DEC-SCOPE-259 / 12FL / 2.173.

## 1. Owner answers (2026-10-25, clarifying prompt)

| ID | Answer |
| --- | --- |
| C1 | Keep the offer's free-text conditions. Whenever an offer is recorded with conditions text (counselor route or agency PUT), one open condition row (owner student) is created from it — the same as the migration. |
| C2 | An evidence document is **required** to mark a condition Met. |
| C3 | Conditions belong to their offer. When a new offer supersedes it they stay with the old offer as read-only history. |
| C4 | All conditions met or waived → prompt only: "All conditions satisfied" with a button opening Record offer prefilled as Unconditional. Nothing changes automatically. |

Defaults (not asked, recorded here): C5 waived/failed need a note; C6 owner `agent` only on an agency application (422 otherwise);
C7 the writers are ccrm-023's (counselor on own applications, Overseas Admin); the student and the agency read through
`GET …/offers`; C8 condition writes move no stage, so they are allowed on hold and refused on withdrawn / terminal outcome / archived
agency record (`_writable(moves_stage=False)`); C9 the agency PATCH that only moves the active offer's deadline re-records the same
university offer, so its conditions move to the new row (no seed); C10 no delete — a wrong condition is waived with a note; any
status may be changed again (a correction), each change kept in history; C11 evidence is a "Condition evidence" document uploaded to
the application (the offer-letter upload rules).

## 2. Existing behaviour (verified on `6941d5dc`)

One free-text `application_offers.conditions` (≤2000), mirrored to `overseas_applications.offer_conditions`. Written by the counselor
route (`POST …/offers`) and the agency PUT/PATCH through `services/application_offers.record`. The counselor panel shows it as
"Conditions: …". ccrm-030 (reminders) is not built.

## 3. Design

### 3.1 Data — `application_offer_conditions` (new)

| Column | Type | Rule |
| --- | --- | --- |
| id | uuid PK | |
| offer_id | FK application_offers ON DELETE CASCADE, not null | indexed |
| description | text not null | ≤1000 on the route; a seeded row carries the offer text (≤2000) |
| owner | varchar(20) | CHECK student / counselor / agent |
| due_date | date null | feeds ccrm-030 |
| status | varchar(20) default `open` | CHECK open / met / waived / failed |
| evidence_document_id | FK student_documents ON DELETE SET NULL, null | required for met (route rule, C2) |
| note | text null | required for waived / failed (route rule, C5) |
| created_by_id, updated_by_id | FK users null | NULL on migrated rows |
| status_changed_at | timestamptz null | |
| created_at, updated_at | TimestampMixin | |

Migration `0182`: create the table (guarded — 0001 builds from models), then insert one `open` / `student` row per offer whose
`conditions` text is non-blank (every offer status, so history stays faithful). Downgrade drops the table.

### 3.2 Service `services/offer_conditions.py` (no commits)

- `seed(db, user, offer)` — C1: one open student row from the offer's text (called by `application_offers.record`).
- `move(db, previous, offer)` — C9: re-point the previous offer's conditions at the new row.
- `add(user, offer, values)`, `update(user, condition, values)` — set fields, `updated_by`, `status_changed_at` when the status moves.
- `check(app, values, evidence)` — C2/C5/C6 rules → `HTTPException(422)`.
- `views(db, offer_ids)` → `{offer_id: [view]}` with the evidence `{id, name}` (never `file_url`); `summary(rows)` →
  `{total, satisfied, open, failed, all_satisfied}` (`all_satisfied` = total > 0 and every row met/waived).

`application_offers.record(..., carry_conditions=False)` seeds after inserting the new row; the agency PATCH deadline path passes
`carry_conditions=True` (moves instead of seeding). `views()` adds `condition_items` and `conditions_summary` to each offer.

### 3.3 API

| Route | Roles | Behaviour |
| --- | --- | --- |
| `GET …/applications/{id}/offers` | unchanged | each offer gains `condition_items` + `conditions_summary`; the payload gains `agency` (bool) and `evidence_documents` (writers only, like `offer_letters`). |
| `POST …/applications/{id}/condition-evidence` (multipart) | counselor (own), overseas_admin | ccrm-023 `_upload` with type "Condition evidence". `201 {"document"}`. |
| `POST …/offers/{offer_id}/conditions` | counselor (own), overseas_admin | `OfferConditionCreate {description, owner, due_date?}` (extra 422). Offer of another application → 404; not active → 409. Creates an open row. `201 {"condition", "conditions_summary"}`. |
| `PATCH …/offers/{offer_id}/conditions/{condition_id}` | counselor (own), overseas_admin | `OfferConditionUpdate` (partial: description, owner, due_date, status, evidence_document_id, note). Condition of another offer → 404; offer not active → 409; C2/C5/C6/C11 → 422. Unchanged → `200 changed:false`. |

Each write: one `ApplicationStatusHistory` row (stage and sub-status unchanged, note "Offer condition added: …" / "Offer condition
updated: … — Met"), audit `overseas.application.offer_condition` (`{offer_id, condition_id, action, status}`), the student notified,
the agency told (CC5, `agent_notifications.offer_changed`), a structured log line.

### 3.4 Web

- `lib/applicationOffers.ts`: condition types, labels, URLs, `conditionsProgress()`.
- `components/OfferConditions.tsx`: inside each offer card. Lists conditions (status badge, owner, due date, evidence, note) and the
  "n of m satisfied" line. On the current offer: "Add condition" and per-row "Update" forms (status, evidence pick-or-upload, note,
  description, owner, due date). C4: all satisfied → "All conditions satisfied" + "Record unconditional offer".
- `ApplicationOffersPanel.tsx`: renders it; `RecordOfferForm` takes an initial type.

### 3.5 Non-goals

Reminders on due dates (ccrm-030), student/agency condition UI (nehn-033 / agency), deleting conditions, automatic sub-status changes.

## 4. Acceptance criteria

1. The counselor adds a condition (description, owner, due date) to the current offer; it is open; history, audit, student + agency told.
2. Met without evidence → 422; with this application's "Condition evidence" → met; another application's document → 422.
3. Waived/failed without a note → 422.
4. Owner agent on a direct application → 422; allowed on an agency application.
5. A superseded / closed offer's conditions are read-only → 409; a condition of another offer → 404.
6. Recording an offer with conditions text seeds one open student row (counselor route and agency PUT); a new offer leaves the old
   offer's conditions on the old offer (C3); the agency deadline-only PATCH moves them (C9).
7. `conditions_summary.all_satisfied` is true only when every condition is met or waived; the panel then offers "Record unconditional
   offer" prefilled (C4).
8. Scope: another counselor 403; student and agent read conditions through GET and cannot write (403); evidence list writers only;
   no `file_url` anywhere.
9. On hold allows condition writes; a terminal outcome refuses them (409).
10. Migration: existing offer text becomes one open student row; round trip.

## 5. Risks

`record()` is shared with the agency PUT/PATCH (AGN-010 tests); the offer view grows two keys (ccrm-023/025 tests compare fields, not
whole dicts); ccrm-004's 0181 migration test uses the walk idiom, so 0182 chaining after it needs no test change.
