# tel-019 — exploratory browser QA (2026-10-07)

**Build:** `feature/tel-019` @ `8717f6a9`, isolated stack `tel019` (web :3099, API :8099). **Browser:** Microsoft Edge 154 (isolated profile,
CDP :9399) driven through Browser Use. **Accounts:** throwaway, created through `POST /admin/users` (telecaller A/B, school / college /
agent BDMs, a BDM manager). The shared dev database also holds API-test fixtures (many pending pool requests), which shaped QA-02.

## Scenarios run

| # | Scenario | Role | Result |
|---|---|---|---|
| 1 | Nav entry "BDM requests", empty list state | telecaller | Pass |
| 2 | Empty submit: every required field named in place, first field focused | telecaller | Pass |
| 3 | BDM list follows the type: corporate → "Any College BDM" + college BDMs; school list separate | telecaller | Pass |
| 4 | Invalid phone, past time, invalid email → field messages, entry kept | telecaller | Pass (see note N1) |
| 5 | Happy path: pool school, named college, pool corporate; success banner with the code | telecaller | Pass |
| 6 | Double-click "Send request" | telecaller | **QA-01** → fixed, re-run: one request |
| 7 | Telecaller opens `/bdm/meeting-requests` and a request detail | telecaller | Pass — "BDM role required" |
| 8 | Layout 390 / 768 / 1280: list and form, no sideways scroll | telecaller | Pass |
| 9 | My Day card: count + next requests linked | school BDM | Pass |
| 10 | Inbox scope: school pool only (no named-college, no corporate) | school BDM | Pass |
| 11 | Detail + accept: type, time, purpose prefilled; organization picker; "Accept and book" → APT booked | school BDM | Pass |
| 12 | Accepted request: no actions left; "Accepted by … APT-…" line | school BDM | Pass |
| 13 | Agent BDM: none of the other modules' requests; school detail → "Meeting request not found" | agent BDM | Pass |
| 14 | Inbox ordering with a busy pool | college BDM | **QA-02** → fixed, re-run: named request first |
| 15 | Decline without a reason → message, focus; with a reason → Declined, actions gone; stale second decline → 409 | college BDM | Pass |
| 16 | Layout 390: detail, inbox, My Day | BDM | Pass |
| 17 | Manager list read-only (no detail links), decline through the API → 403 | BDM manager | Pass |
| 18 | Telecaller sees Accepted (APT code + time), Declined (reason), Pending; status filters; bogus `?status=` ignored | telecaller | Pass |
| 19 | API / web logs: no 5xx, no tracebacks | — | Pass |

## Issues

### QA-01 — Double-click files two requests (Medium) — **FIXED**
- **Role / page:** telecaller, `/telecaller/meeting-requests/new`.
- **Steps:** fill the form; click "Send request" twice in quick succession.
- **Expected:** one request. **Actual:** two identical requests (MRQ-000099, MRQ-000100).
- **Evidence:** both rows on `/telecaller/meeting-requests`; two `201` POSTs. The `busy` state disables the button only after React
  re-renders, so a second click in the same tick sends again.
- **Fix:** an in-flight ref in `MeetingRequestForm` (and the decline form in `MeetingRequestDecide`); vitest "sends once on a double
  submit" / "declines once on a double submit" (RED: 2 POSTs → GREEN: 1).

### QA-02 — A request named for the BDM can sit behind the pool (Low, UX) — **FIXED**
- **Role / page:** college BDM, `/bdm/meeting-requests`.
- **Steps:** with 38 pending college/corporate requests in the pool, open the inbox.
- **Expected:** the request a telecaller addressed to this BDM is easy to find. **Actual:** it is ordered by proposed time only, on page 2.
- **Fix:** within Pending, requests named for the viewer come first (then soonest first) — `inbox_order(user)`; pytest
  `test_requests_named_for_the_bdm_come_first_among_the_pending` (RED → GREEN).

### Notes (no change)
- **N1:** with a bad phone **and** a past time, the phone error shows first and the time error only after the phone is fixed (schema
  validation runs before the time rule) — the same two-step reveal as tel-016's booking form.
- **N2:** refreshing `/telecaller/meeting-requests?filed=MRQ-…` shows the "sent" banner again (the URL carries it), as other flows do.
- **N3:** after accepting, the appointment page does not mention the request; the request and the telecaller's list link the appointment.
