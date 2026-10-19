# csc-003 — Counselor resends the link and fixes details on a pending walk-in account (design)

`DEC-SCOPE-228`, API `12EN`, RBAC `2.150`, no migration. Backlog: `docs/delivery/COUNSELOR_WALKIN_BACKLOG.md` §3 `csc-003`; owner answer
W6 ("resend link + fix name/phone/email while pending; deactivation and reassignment stay with Overseas Admin"). Builds on csc-002.

## Intent

A walk-in student says the email never came, or the counselor mistyped the address. The counselor resends the set-password link, or
corrects the name, phone or email, without an admin — but only while the account has never been activated.

## Rules (both routes)

- Only an Overseas `counselor` (csc-002 `require_overseas_counselor`).
- Only a student **linked to the caller** (`overseas_student_counselors`). Anyone else's student, an unknown id, or a non-student → `404
  "Student not found"` (no disclosure).
- Only while **pending**: ENH-003 `provisioning_statuses` has the student (`pending_setup` or `link_expired`). A student who has set a
  password → `409 "This student has already set a password"`. An account an admin deactivated → `409 "This account is deactivated"`.
- Lock order: the counselor's own row (the mail budget), then the student row `FOR UPDATE`, then tokens — as csc-002 create and the
  ENH-003 Re-send.
- **Mail budget (C2, extended):** a resend and an email change each send mail, so they count toward the counselor's 20 per rolling 24 h
  with creations and refused duplicates (AGN-002 counts staff resets with creations the same way) → `429` + `Retry-After`. A name/phone
  edit sends nothing and is not counted.
- The raw token is never returned (AGN-001/002 S3).

### `POST /counselor/students/{id}/welcome-links` → 201

The ENH-003 per-account cooldown applies (`resend_wait_seconds`: the first resend after creation is always allowed, another within 60 s
of the newest link → `429` + `Retry-After`). Supersedes the open link, issues a new one, audits `counselor.student_resend`, commits, then
emails it. Response `{"student": {…, "setup": "pending_setup"}, "email_status", "expires_at"}`.

### `PATCH /counselor/students/{id}` → 200

Body (`CounselorStudentUpdate`, `extra="forbid"`): `full_name?`, `email?`, `phone?` — omitted = unchanged; `phone` null or blank clears
it; same validation as create. Email compared lower-case:

- unchanged → name/phone only, no mail;
- changed to an address another account has → `409 "Email already exists"` (audited `counselor.student_create_rejected`-style as
  `counselor.student_update_rejected`, counted);
- changed → every open welcome link is revoked and a new one is issued to the new address and emailed after the commit; response adds
  `email_status` and `expires_at`.

Audit `counselor.student_update` lists the changed field **names** only (never values). Response `{"student": …}` (+ delivery when
emailed). An empty body is a no-op 200.

## Frontend

Each pending row in *Walk-in students* gets **Edit** and **Resend link**; an active row gets none. Edit opens an inline form (name,
email, phone) with the note "Changing the email sends a new link to the new address; the old link stops working." — Save / Cancel /
Escape, focus returned to Edit, entry kept on failure. Resend link posts directly (it never touches a password) with a busy state.
Results go to the panel's announced notice; errors (409/429/network) to the row's status region. New `CounselorWalkInStudentRow`
(AgentStaffRow's pattern, trimmed to these two actions).

## Builder's calls (owner: proceed with recommended answers)

- C5 — resends and email changes share the C2 mail budget; name/phone edits do not.
- C6 — Resend link needs no confirmation (it cannot affect a password); the per-account 60 s cooldown prevents bursts.
- C7 — a pending account an admin deactivated is refused (409), as the admin Re-send refuses it.

## Not changed

`services/provisioning.py`, the admin routes, the agent flows, csc-002 create/list behaviour (only its budget counts two more actions).

## Tests

`test_csc_003_walk_in_resend_edit.py`: resend 201 + new link works + old link dead; cooldown 429; active 409; deactivated 409; other
counselor's / unknown / non-student 404; IT counselor and other roles 403; anonymous 401. Edit name/phone (no mail, audit names only);
email change (old link dead, new address mailed, new link works, `email_verified` false); email to an existing address 409 counted;
case-only change is not a change; active 409; validation 422 (extra field, blank name, bad email, long phone); empty body no-op; budget:
resends and email changes count, name edits do not. Component tests for the row; e2e: create → edit email → link arrives at the new
address (via admin Re-send helper pattern) / resend → cooldown message.
