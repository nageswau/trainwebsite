# itc-018 — Student portal fee summary and course details (design)

**Backlog:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` itc-018. **Decision:** `DEC-SCOPE-353`. **Dependencies:** itc-013 (merged,
DEC-SCOPE-346); itc-019 (My faculty card) and itc-020 (Timetable) are merged and already render on the student portal.
Owner instruction for this session: proceed with recommended answers. Every call below marked *(Claude's call)* is
`NEEDS_CONFIRMATION`.

## Intent

The IT student should see, without asking accounts: what the course costs, what they have paid, what is left and when the next
amount is due, with receipts; and the course and batch facts (dates, mode, where the class happens).

## What already exists (not rebuilt)

- `/it/student/fees`: `FeeAccountSummary` (itc-013) shows per enrolment course fee, discount, tax, total payable, paid, credits,
  balance, state — from `fee_accounts.balance_for`, the same definition accounts staff read (AC1 holds by construction).
- `FeePaymentPanel`: Pay Now, receipt download, EMI timeline (unchanged).
- `/it/student/course`: My faculty card (itc-019), course table with program, batch, trainer, schedule, progress, status.

## Gaps closed by itc-018

1. **Next due** on each fee account card. `fee_accounts.accounts()` gains `next_due: {amount, due_date} | null` — the oldest owed
   bill (pending/overdue, amount > 0), ordered like `record_payment` (due date ascending, nulls last, then age). One extra grouped
   read for the whole list (fixed query count). `balance_for` is untouched (its one-query pin stays). Additive for the staff
   readers of `accounts()` too. *(Claude's call: F1 — no "overdue" flag; the existing payment table already shows status.)*
2. **Course and batch details** in the `course` section rows: `start_date`, `end_date` and `mode` are the enrolment's effective
   values (itc-012 override, else the batch's), plus `room_or_link`. Columns "Starts", "Ends", "Mode", "Room or link" are added; no
   existing column is removed (additive payload).
3. **Room or link** *(Claude's call: F2)* is derived from the batch's weekly timetable slots (itc-020): offline slot rooms, distinct,
   comma-joined; an online slot adds "Online — join link in your Timetable"; no slots → "Not scheduled yet". **The raw meeting URL is
   never put in this payload**: the timetable hides links from a student whose `live_classes` access is locked, and repeating the
   URL here would bypass that lock. The Timetable page stays the one place a link is shown.
4. **AC2 — another student's receipt returns 404.** `GET /payments/{id}/receipt` returned 403 "Payment belongs to another user"
   for a caller who neither owns the payment nor administers its division. It now returns the same 404 "Payment not found" as a
   missing payment (no disclosure that the id exists). Admin access is unchanged. *(This changes a status code; the AC requires it.)*

## Non-goals

No new table, endpoint, dependency or migration. The dashboard "Pending fee" tile is unchanged (F3: out of scope, regression risk
on `test_stu_*`). Razorpay, EMI, discounts and record-payment are unchanged.

## Edge cases

- No fee (scholarship / never billed): state `not_billed`, card says no fee billed, `next_due` null.
- Fully paid: `next_due` null; card shows "Nothing due".
- A zero-amount owed row (100 % discount) is not a next due.
- Owed bill without a due date: `next_due.due_date` null → "Next due INR X (no due date set)".

## Acceptance criteria (testable)

1. The fee card balance equals `fee_accounts.balance_for` (the accounts figure) — existing itc-013 test plus an itc-018 check.
2. Another student's payment receipt → 404; own paid receipt → 200; missing → 404.
3. A partial payment (₹45,000 fee, ₹20,000 paid, the rest due 10-Dec) → balance 25,000, `next_due` {25000, 2026-12-10}; the card
   shows "Next due INR 25,000.00 · 10 Dec 2026".
4. Course rows carry effective dates/mode (an override wins) and a room-or-link label without any URL.
5. Unbilled enrolment → `next_due` null, card shows "No fee has been billed".

## Security

Own data only: `/it/student/fee-accounts` already filters by `user.id` and 403s non-students; course rows filter
`Enrollment.student_id == user.id`. No URL leak (above). Receipt IDOR closed to 404.
