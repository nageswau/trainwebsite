# ENH-005 — independent code review (Codex): findings and dispositions, 2026-09-21

Each finding was checked against the code, the spec and the existing architecture before anything was changed. Fixes were made only for findings
that were valid and MEDIUM or higher, with the regression test written first and seen to fail.

| # | Reviewer severity | Verdict | Disposition |
|---|---|---|---|
| 1 | HIGH — cap and throttle are raceable | **VALID** | **Fixed** |
| 2 | MEDIUM — cap/throttle refusals are not audited (AC-27) | **PARTIALLY VALID** | **Cap 409 fixed; throttle 429 rejected (by design)** |
| 3 | MEDIUM — pending parent invites orphaned by approval | **PARTIALLY VALID** | **No code change: decided by the owner on 2026-09-21 (keep the admin warning), already mitigated** |
| 4 | LOW — generic table above the admin queue (N3) | **VALID** (low) | Not fixed in the review round (below the threshold); **fixed afterwards at the owner's request** |
| 5 | OPTIONAL — "Request a transfer" hard to find on mobile (N4) | **VALID** (optional) | Not fixed in the review round; **fixed afterwards at the owner's request** |

## 1. Filing cap and hourly throttle are raceable — VALID, fixed

**Checked.** `_filing_guard` counted `AuditLog` rows (throttle) and pending requests (cap), then the endpoint inserted later in the same request. At
Postgres's default READ COMMITTED level two concurrent transactions both count before either commits, so both pass. The only database guard is the
partial unique index (one pending request per *student*); nothing bounds a school or a coordinator. The existing concurrency tests covered approval,
promotion and result verification, not filing. **Confirmed by test before the fix:** ten simultaneous incoming filings against a limit of three all
returned `202`; a burst against a cap of two exceeded it; and a filing did not wait for a lock held on the school row.

**Consistent with the requirement and architecture.** AC-20 and AC-26 state hard limits, and the throttle exists to bound code probing (S3), so a
bypass by parallelism defeats its purpose. The fix uses the codebase's existing tool (row locks, as in approval and promotion) rather than a new
mechanism.

**Fix.** `_filing_guard` first takes the school's row with `FOR NO KEY UPDATE`, so a school's filings (and therefore each coordinator's) run one at a
time until the caller's commit, when the new request row and its audit row are visible to the next count. That lock mode excludes another filing but
not a foreign-key insert that merely references the school; no other code locks a school row, so it cannot join a cycle with approval's request →
student → parents → results order. The duplicate-insert path now uses a savepoint, so losing the race does not release the lock before its `denied`
row is committed (a plain rollback would have opened a small window).

**Tests** (`test_enh_005_concurrency.py`): a forced-interleaving test (a held school lock makes both filings wait, then exactly one of two is
refused at a cap of one), and two burst tests (cap 2 with 8 simultaneous filings gives exactly 2 created; throttle 3 with 10 simultaneous gives exactly 3
accepted and 3 counted audit rows).

## 2. Cap/throttle refusals are not audited — PARTIALLY VALID

- **Cap `409` — valid.** AC-27 says every attempt that passes validation writes exactly one row; a cap refusal is such an attempt and wrote none.
  **Fixed:** it now writes a `denied` row with `reason_token: "cap_reached"` and the school ID (never the code typed) and commits before the `409`.
  Such a row counts toward the hourly throttle, which is consistent with D8 ("valid or not") and safe because it only occurs while the school is at
  its cap.
- **Throttle `429` — invalid, by design.** Spec §8 says "the throttle's `429` is logged, not audited (no feedback loop)". The throttle counts
  `AuditLog` rows, so auditing its own refusals would make a client that keeps retrying extend its own lockout indefinitely. An existing test asserts no
  throttle audit row is written; it now also asserts that blocked attempts add no filing rows. The spec's AC-27 wording was ambiguous against §8 and
  has been corrected to say so.

## 3. Pending parent invites orphaned by approval — PARTIALLY VALID, no code change

**Checked.** The description is accurate (approval clears `pending_parent_email`; `accept_invite` links only students still at the invite's school). It
is not an undiscovered defect: it was found by the browser E2E, recorded as an open decision in `DEC-SCOPE-021` and spec §13, and mitigated on
2026-09-21 by an admin-facing warning (`pending_parent_invite`) at the queue row and the confirm step. Fixing it means carrying an invite across
schools, which needs an exception to the same-school link invariant (S2/AC-29) and a rule for a parent whose invite covers several students. The
project's rule is `NEEDS_CONFIRMATION` for an unresolved scope choice, so it was left for the owner, who decided on 2026-09-21 to keep the admin warning and not carry the invite over. **Decided; no code change.**

## 4 and 5. Admin table above the queue (N3); request form position (N4)

Both are accurate and already recorded as N3/N4 in `ENH-005_BROWSER_QA_2026-09-21.md`; the code references match (`portal.py` builds the generic
200-row table; `WorkflowPanel` mounts the action panel separately; the form renders after the timeline). Neither is MEDIUM or higher, N3 is a layout
choice for the owner, and N4 is optional, so neither was changed in the review round. The owner then asked for both: N3 became a dedicated admin page
(the generic portal payload and its wiring were removed) and N4 moved the disclosure under the student header; see `ENH-005_BROWSER_QA_2026-09-21.md`.

## Verification after the fixes

All 96 ENH-005 backend tests pass (93 before, plus three concurrency tests; two existing filing tests gained assertions). `ruff check` is clean on the
changed files. Not re-run: the full backend suite, the full Playwright suite, and a browser check (the change is backend-only and has no UI).
