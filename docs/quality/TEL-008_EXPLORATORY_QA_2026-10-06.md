# tel-008 — Exploratory browser QA — 2026-10-06

**Build under test:** `feature/tel-008` (`DEC-SCOPE-084`, no migration). Pass 1 was run on the first implementation commit. The fixes
were re-verified after the QA fix commit. The script panel (D6) was checked after merging `main` @ `50838192` (tel-012).

**Environment:** an isolated stack, `docker compose -p tel008 -f docker-compose.yml`:
- web `http://localhost:3088`, API `:8088`;
- seeded with `python -m app.seed`.

**Browser:** Browser Use on an isolated Microsoft Edge profile (CDP `:9388`, `--disable-renderer-backgrounding`). The tab had to be
activated before coordinate clicks registered. Screenshots are in the session scratchpad (`qa-list-*.png`, `qa-detail-*.png`) and are
not committed.

**Accounts and data:** QA-only rows written straight to the stack's database, because assigning a lead to a telecaller arrives with
tel-007 and has no HTTP path yet. The password is the seed demo password.
- IT telecaller manager `qa-tlm@edusphere.local`, with IT telecallers A (`qa-tel-a@…`) and B (`qa-tel-b@…`) as reports. IT counselor
  `qa-couns@…`.
- Leads LD-000180 to LD-000184:
  - four belong to A: hot + Cyber Security + contacted; warm with WhatsApp; cold + not interested; **handed over** (counselor set).
  - one belongs to B.
  - Every enquiry message contains `<script>alert(1)</script>`.

## 1. Automated evidence

| Run | Result |
|---|---|
| Backend `test_tel_008_workspace.py` | 27 passed; all 27 fail on `main` (RED) |
| Backend lite set, pre-merge (tel-001/002/003/004, bdm-017, adm-002) | 176 passed |
| Backend after merging `main` (+ all tel-012 suites) | 172 passed |
| vitest (tel-008 components, admin lead panel, nav) | 42 passed |
| Playwright `tel-008-lead-workspace.spec.ts` + tel-004 + tel-012 (+ tel-001, tel-003 pre-merge) | all passed (11, then 7 after the merge) |
| `next build`, `tsc`, eslint, ruff on changed files | clean |

## 2. Coverage

| # | Area | Result |
|---|---|---|
| 1 | Happy path (list → detail → priority → stage → edit) | Pass |
| 2 | Invalid inputs (blank email, phone `abc!`, closing without a reason) | Pass: each field's message is shown and the entry is kept |
| 3 | Empty states (no leads, no match, no activity, no product / no script) | Pass |
| 4 | Server errors (422 shown in place; a failed list offers Retry) | Pass, after QA-02 |
| 5 | Loading states | Pass (`Loading leads…`, `Loading the call script…`) |
| 6 | Cancel / back | Pass: focus returns to "Change stage"; "Back to leads" keeps the filters in the URL |
| 7 | Refresh | Pass: filters, page and saved values survive a reload |
| 8 | Duplicate submission | Pass: a double-click on Save priority wrote one audit row and one activity entry |
| 9 | Unauthorized user | Pass: signed out goes to `/telecaller/sign-in` (telecaller) or `/admin/login` (manager) with `next` |
| 10 | Wrong role / IDOR | Pass: B's lead, a random id and a malformed id show "Lead not found"; API `404`; a handed-over PATCH is `403` |
| 11–13 | Desktop 1280, tablet 768, mobile 375 | Pass: no horizontal scroll on the list or the detail |
| 14 | Navigation | Pass: "My Leads" (telecaller) and "Leads" (manager) |
| 15–16 | Success and error messages | Pass |
| 17 | Broken images | None on these pages |
| 18 | Console errors | Pass: the Playwright journey asserts none except the expected 422 |
| 19 | Failed network calls | Only the deliberate 422s |
| 20 | Unexpected redirects | None |
| — | XSS | Pass: the `<script>` text is rendered as text, and no script element is injected |
| — | Manager scope | Pass: A's and B's leads plus the IT queue, with a Telecaller column; reopen Lost → Follow-up with a reason |

## 3. Findings (all fixed, test-first, re-verified in the browser)

| ID | Severity | Role / page | Steps | Expected | Actual (before the fix) | Fix |
|---|---|---|---|---|---|---|
| QA-01 | Low | Telecaller, My Leads | Open My Leads with a handed-over lead | A cue that the counselor has it | Looked like any editable lead | A muted "With counselor" line under the stage |
| QA-02 | Low | Any, list | Open `?priority=bogus` or `?product_id=xyz` | The bad value is ignored | API 422, "Unable to load leads"; Retry always failed | The client drops a filter value the API would refuse |
| QA-04 | Low | Any, list | Look at the lead names | Look like links | Plain bold text | `LINK_STYLE` (blue, underlined), the codebase convention |
| QA-05 | Low | Manager, detail | Open a handed-over lead | Told the counselor has it | No notice, while the controls stayed | The notice is shown to managers too (without "cannot change") |

QA-03 was not raised as a defect: earlier success notices stay next to their own sections after later actions.

## 4. Not covered here

- Assigning a lead to a telecaller (tel-007) and handover by the telecaller (tel-018). The QA data set these fields directly.
- The full backend suite. It is deferred to the user's regression session.
