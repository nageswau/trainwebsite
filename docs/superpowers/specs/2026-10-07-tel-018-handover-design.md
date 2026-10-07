# tel-018 — Handover to counselor, return, student link, computed conversion (design)

- **Backlog item:** `docs/delivery/TELECALLER_CRM_BACKLOG.md` → tel-018 (§10, §13; T4, T5, T19, T20, T29; Q-18 part 2, Q-22).
- **Dependencies (all merged):** tel-004 (PR #81), tel-008 (PR #85), tel-016 (PR #103), tel-017 (PR #73), bdm-017 (`7de5d44f`).
- **Decision:** `DEC-SCOPE-101` (tel-010 096, bdm-014 097, tel-019 098, bdm-015 099, tel-013 100 merged first; re-numbered twice). API contract §12V, RBAC §2.28 (bdm-015 took §12T / §2.26, tel-013 §12U / §2.27). **No migration.**
- **Branch:** `feature/tel-018` from `origin/main` @ `0261cfc3`.

## 1. Owner answers (2026-10-07, `EXPLICIT_APPROVAL`)

| # | Question | Answer |
|---|---|---|
| HO1 | Q-22: who may unlink | The division admin at any time (the bdm-017 route) and the assigned counselor while the lead is not Converted. The telecaller manager may not. |
| HO2 | Unlink after conversion | Only an admin. The lead goes back to Follow-up and no longer counts as converted. |
| HO3 | T5 evidence / Q-18 part 2 | An IT `Enrollment` with status `active` (not `pending_consent`), or an `OverseasApplication` with status `enrolled`, of the linked student. An enrolment that predates the lead or the link counts. Conversion credit (Q-18 part 1) is deferred to tel-024; the stage history keeps who and when. |
| HO4 | Handover / return | Handover from any open stage before Application/Enrollment (closed → 409) by the owning telecaller or their manager; a manager may re-hand to another counselor. Handover cancels open follow-ups ("Handed over to counselor") and leaves the stage. Return needs a reason and is allowed only before the link (linked → 409); it moves the lead to Follow-up and cancels the counselor's open appointment. The alerts (counselor alerted, "Lead Returned") are tel-020's (its backlog entry lists them). |

## 2. What exists and is reused

- `telecaller_leads.read_only` / `require_writable`: once `owner_id` is set a telecaller gets 403 on every lead write (tel-008 D1). **AC1 needs no new write gate**; tel-018 only adds the action that sets `owner_id`.
- `lead_stages.EVENTS` already has `student_linked`, `student_unlinked` and `converted`; the admin link already applies `student_linked` (tel-004 PL4).
- bdm-017: `converted_user_id` / `converted_at` / `converted_by_user_id` with `ck_enquiries_conversion` and `uq_enquiries_converted_user`; `bdm_leads.locked_student` / `check_student_free` / `audit_conversion`.
- tel-016: `lead_appointments.lock_counselor` (active counselor of the division, 422 otherwise) and the `appointment-options` endpoint (the counselor picker).
- tel-011 / tel-016: `lead_pipeline._cancel_open_follow_ups` / `_cancel_open_appointments` (made public with a reason argument).

`converted_at` keeps its bdm-017 meaning (the time the link was made; the check constraint ties it to the link). **The moment of conversion is the `converted` stage-history row** (and `stage_changed_at`), so nothing new is stored.

## 3. Backend

### 3.1 Pipeline (`lead_stages.py`, `lead_pipeline.py`)

- New event `returned`: from every open stage up to Counselling Completed → `follow_up`. `follow_up` is in the from-set on purpose: a return is always written to the stage history (Follow-up → Follow-up), so its reason and its actor are in the activity list.
- `student_unlinked` also leaves `converted` (HO2; only the admin route reaches it from there).
- `apply_event(..., reason=None)`: an optional reason (the return's). Backward compatible.
- `cancel_open_follow_ups(db, lead, reason)` and `cancel_open_appointments(db, lead, actor, reason, audit_reason)`: the two tel-011/tel-016 helpers, public, with the reason as an argument (closing keeps "Lead closed").

### 3.2 `services/lead_handover.py` (new)

| Function | Rules |
|---|---|
| `handover(db, user, kind, lead, counselor_id)` | Telecaller: `require_writable` (403 when already handed over). Closed → 409. At or past Application/Enrollment → 409. `lock_counselor` (422). Same counselor → 409. Sets `owner_id`; cancels open follow-ups; audit `lead.handover {counselor_id, from_counselor_id}`. |
| `counselor_scope(user)` | `counselor` only (403 otherwise): `owner_id == user.id AND division == user.division`. Out of scope → 404. |
| `return_lead(db, user, lead, reason)` | Linked → 409. `returned` event with the reason; `owner_id = NULL`; cancels the open appointment; audit `lead.return`. |
| `link_student(db, user, lead, student)` | Shared by the admin and the counselor routes (AC5). Linked → 409; student free → 409; `student_linked`; the three columns; audit `lead.convert`; then `sync_conversion`. |
| `unlink_student(db, user, lead, *, admin)` | Not linked → 409. Converted and not admin → 409. `student_unlinked`; audit `lead.unconvert`; clears the columns. |
| `converted_evidence(student_id)` | `EXISTS` an active `Enrollment` OR an `enrolled` `OverseasApplication` (HO3). |
| `sync_conversion(db, lead)` | At Application/Enrollment + evidence → `converted` (system actor). |
| `observe_conversion(db, lead_id)` | On a detail read: one indexed query; only a lead that turns converted is locked, moved and committed. |
| `sweep_conversions(db)` | Beat job, every 15 minutes, a bounded batch (500), `SKIP LOCKED`. |
| `milestones(db, lead)` | Read-only (T4): the linked student, their IT enrolments (batch, status, date) or overseas applications (university, status, reference) and visa cases. |
| `suggestions(db, lead, q)` | Active `<division>_student` accounts of the lead's division. No `q`: accounts whose email or mobile equals the lead's (the suggested match). With `q` (≥ 3 characters): a literal substring of name, email or mobile. At most 10. Each says whether it is already linked to another lead. |

`bdm_leads.locked_student` takes the lookup condition, so the admin finds by email (unchanged) and the counselor by id; the 422 message is shared.

### 3.3 API (§12V)

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/telecaller/leads/{id}/handover` `{counselor_id}` | the lead's telecaller, their manager, super_admin (tel-004 scope) | 200 → the telecaller lead detail |
| GET | `/counselor/leads` | counselor | `{items,total,limit,offset}`, newest first |
| GET | `/counselor/leads/{id}` | counselor | the lead row + message + `milestones` + `permissions {return, link, unlink}` |
| GET | `/counselor/leads/{id}/timeline` | counselor | tel-008's timeline |
| POST | `/counselor/leads/{id}/return` `{reason}` | counselor | 200 → the counselor detail; the lead leaves their scope |
| GET | `/counselor/leads/{id}/link-suggestions?q=` | counselor | `{items}` |
| POST | `/counselor/leads/{id}/student-link` `{student_id}` | counselor | 200 → detail; 409 / 422 as the admin link |
| DELETE | `/counselor/leads/{id}/student-link` | counselor | 409 when converted |
| POST/DELETE | `/admin/leads/{id}/conversion` | admins | unchanged contract; now the shared rules + conversion check |
| GET | `/telecaller/leads/{id}` | unchanged scope | adds `milestones` (additive) |

Bodies are `extra="forbid"`. The reason reuses `BdmApptReason` (trimmed, 1–500).

### 3.4 Worker

`tel018-conversion-sweep` every 900 s → `sweep_conversions` through `_run_with_fresh_pool`.

## 4. Frontend

- **Telecaller / manager lead detail (`LeadDetailPanel`):** `LeadHandoverForm` ("Assign to counselor"; a manager sees "Change counselor" on a handed-over lead), the counselor picker from `appointment-options`. `LeadMilestones` (linked student, Converted badge, read-only enrolment/application/visa milestones).
- **Counselor:** the Leads section shows `CounselorLeadsPanel` (paged table, Lead ID links to the detail) for both divisions. New page `/{it|overseas}/counselor/leads/[id]` → `CounselorLeadDetail`: lead details (read only), `ReturnLeadForm` (reason required, confirm), `LinkStudentPanel` (suggested matches first, search, confirm before linking, unlink with confirm), `LeadMilestones`, activity.
- Loading / empty / error states in each panel; buttons disabled while busy; `role="status"` / `role="alert"` notices; labels on every control.

## 5. Phase 3 reviews

- **API:** new verbs are actions on a lead (POST), the link is a sub-resource (POST/DELETE). Scope misses are 404, role misses 403, rule conflicts 409, invalid input 422 — the existing tel-* semantics. Existing contracts unchanged except the additive `milestones`.
- **Transactions / races:** every write locks the lead (`locked_lead` / `locked_for_admin`) first; the counselor row is locked for the handover; the student row `FOR SHARE`; `uq_enquiries_converted_user` is the backstop (IntegrityError → 409). The sweep uses `SKIP LOCKED` so it never waits on a user's write.
- **Security:** IDOR — the counselor routes filter by `owner_id` + division from the session; the handover target is validated by division and role; a student link only to an active student of the lead's division; suggestions only in the counselor's division (they already see that division's students). Free text (reason) is stored in the stage history only, never in logs or audit metadata. React escapes output. Cookies + the existing CSRF/same-site posture are unchanged.
- **Frontend:** reuses `sendJson`, `getPage`, `BdmConfirm`, the action-card layout and the notice pattern of `LeadDetailPanel`.

## 6. Tests

- `test_tel_018_handover.py`: handover happy path, 403 after, closed 409, past-link 409, other-division counselor 422, manager re-hand, same counselor 409, follow-ups cancelled, outsider 404.
- `test_tel_018_return.py`: return → Follow-up + history reason + owner cleared + telecaller can write again; linked 409; reason required 422; appointment cancelled; another counselor 404; non-counselor 403.
- `test_tel_018_link.py`: counselor link → Application/Enrollment; taken 409; other division 422; active enrolment → converted (on link, on read, by the sweep); `pending_consent` doesn't count; overseas `enrolled`; counselor unlink → Follow-up; converted unlink: counselor 409, admin → Follow-up; suggestions; milestones.
- bdm-017 / tel-004 / tel-008 / tel-011 / tel-016 / tel-017 suites re-run (regression).
- Web: vitest for the new components; Playwright `tel-018-handover.spec.ts` (handover → counselor link → return path).
