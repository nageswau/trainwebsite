# ccrm-028 — Arrival and orientation tracking (design)

Status: design, 2026-10-25. Backlog item `ccrm-028` (`docs/delivery/COUNSELOR_CRM_BACKLOG.md`, CC6). Source class: owner request on an
`UNVERIFIED` spec (backlog header); only the backlog's quote of §10 is used: "track arrival/orientation confirmation if this is part of
EduSphere's service". Decision `DEC-SCOPE-265`, migration `0187_application_arrival`, API §12FR, RBAC §2.179. Depends on ccrm-027
(enrolment confirmation, `DEC-SCOPE-262`, PR #325), merged.

## 1. Requirement (backlog)

- After enrolment, the counselor records **arrival date, arrival confirmed (by whom), orientation attended, notes**.
- DB: migration (columns or `application_arrivals`). Complexity small, risk low.
- Open question: does arrival trigger anything (e.g. commission eligibility in UPC/mgmt)?

No owner questions were asked in this session (the session brief asks to proceed with recommended answers); the defaults below are
recorded as `NEEDS_CONFIRMATION` in `DEC-SCOPE-265`.

## 2. Existing behaviour (verified on main @ 8979c06f)

- Nothing records arrival or orientation. `non_arrival` (ccrm-027 E6) is an outcome recorded **before** enrolment and refused once
  enrolled.
- ccrm-027's post-offer router (`api/application_offers.py`) already has the writer entry `_writable` (role, `_assigned_application`
  scope, row lock, swapped-counselor re-check, closed/on-hold/archived-agency refusals) and the readers' GET pattern (`READERS` =
  counselor, Overseas Admin, student, agent).
- The counselor card (`CounselorEvaluationPanel`) opens the Enrolment panel from the offer stage on.

## 3. Decisions (defaults, `NEEDS_CONFIRMATION`)

| ID | Question | Default |
| --- | --- | --- |
| A1 | Does arrival trigger anything? | **No.** Record only: no stage, sub-status, outcome or commission change, no UPC/management eligibility. Commission stays on enrolment (AGT-003). |
| A2 | Who records, on which applications | Counselor (own applications, **direct and agency**: CC4) and Overseas Admin (any), through `PUT …/arrival`. The student and the agency read it (`GET`, the enrolment readers). |
| A3 | When | Only once the application is **`enrolled`** (otherwise 422 "Arrival is recorded after enrolment is confirmed"). Closed / archived-agency refuse (409, `_writable`); allowed on hold (moves no stage). |
| A4 | "Arrival confirmed (by whom)" | The system stamps **who** (the signed-in counselor/Admin) and **when** at the moment `arrival_confirmed` turns true; how it was confirmed (phone, university email …) goes in the notes. Turning it off clears the stamp (a correction). |
| A5 | Validation | Arrival date optional while unconfirmed (an expected date); **required** to confirm, and a confirmed arrival cannot be in the future. Orientation attended needs a confirmed arrival. Dates 2000–2100; notes ≤ 2000 chars, cleaned. |
| A6 | Storage and trail | Columns on `overseas_applications` (one arrival per application, like enrolment). A change writes one status-history note ("Arrival updated -- …", the ccrm-025 deposit pattern), an audit row, and tells the agency on agency applications (CC5, `details_changed`). The student is not notified. An unchanged save writes nothing. |

## 4. Design

**DB (`0187_application_arrival`).** `overseas_applications.arrival_date DATE NULL`, `arrival_confirmed_at TIMESTAMPTZ NULL`,
`arrival_confirmed_by_id UUID NULL` (FK `users`, `ON DELETE SET NULL`), `orientation_attended BOOLEAN NOT NULL DEFAULT false`,
`arrival_notes TEXT NULL`. A CHECK `ck_overseas_applications_orientation_arrival`: `NOT orientation_attended OR arrival_confirmed_at IS
NOT NULL`. Additive; columns added only when missing (0001 builds from models: the 0170/0184 idiom).

**Service (`services/application_arrival.py`).** Messages, `view(db, app)` (confirmed-by name, not email), `check(app, payload)`.

**API (`api/application_offers.py`).**
- `GET …/{id}/arrival` — `READERS`: `{arrival}`.
- `PUT …/{id}/arrival` — body `ApplicationArrivalSave {arrival_date, arrival_confirmed, orientation_attended, notes}`
  (`extra: forbid`). `_writable(moves_stage=False)` → 422 unless enrolled → A5 checks → no-op when unchanged → set fields, stamp/clear
  confirmed by/at → history note, agency told, audit (`overseas.application.arrival`, field names only) → commit.

**Web.** `lib/applicationArrival.ts` (types, URL, `showsArrival`); `ApplicationArrivalPanel` (load / error + retry / read view / edit
form: date, "Arrival confirmed" checkbox, "Orientation attended" checkbox disabled until arrival is confirmed, notes; one-shot submit;
Escape cancels; errors in `role="alert"`). Mounted on the counselor card under the Enrolment toggle for enrolled applications.

## 5. Acceptance criteria (tests)

1. The counselor records an expected arrival date on an enrolled application; then confirms arrival → stamped by/at, history note,
   audit; GET returns the counselor's name.
2. Before enrolment → 422; a confirmed arrival with no date or a future date → 422; orientation without a confirmed arrival → 422.
3. Unconfirming clears confirmed by/at and orientation must already be off (else 422); an unchanged save → `changed: false`, no new
   history row.
4. Agency application: the assigned counselor records it and the agency is told; another counselor → 403; Admin may record any.
5. Student and agent read (200) but cannot write (403); a student of another application → 403/404 (the existing scope).
6. Nothing else changes: status, sub-status, outcome and commissions are untouched (A1).
7. Migration: chain after 0184, single head, columns + CHECK round trip.
8. Web: the panel shows load/error states, confirms arrival, disables orientation until arrival is confirmed, shows server errors.

## 6. Regression risks

Low. New nullable/defaulted columns; no existing route changes. The ccrm-027 migration test asserts a single head and its own revision in
the chain — both still hold.
