# ENH-010 Account Activation/Deactivation — Verification & Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove, with real test runs, that ENH-010's already-shipped `SCH-003` implementation satisfies all four acceptance criteria; close two honest test gaps (AC2 login-after-deactivation, mass-assignment/role-escalation immunity) found during the design audit and the `security-and-hardening` review; fix one real, small frontend bug found during live browser QA (`ENH010-QA-01`, rapid double-click sends duplicate `PATCH` requests); then reconcile the stale backlog/RTM documentation and draft the missing `DEC-SCOPE-023` decision entry for user approval.

**Architecture:** Three small, independent additions to already-shipped code, no new endpoints or models. Tasks 1–2 are backend *characterization* tests (the behavior already exists and is expected to pass immediately) appended to the existing `apps/api/tests/test_sch_team_account_activation.py`, each proven non-vacuous with a temporary mutation check (this repo's own established pattern from ENH-006 Task 3) rather than a literal RED phase, since there is no implementation gap to drive. Task 3 is a genuine RED→GREEN frontend fix: a `useRef`-based per-row re-entrancy guard in `SchoolTeamPanel.tsx`, mirroring the `submitting` ref pattern already used in `ChangePasswordForm.tsx`, with a new, narrowly-scoped test file (no existing component-test file exists for this component). Task 4 runs the full regression surface for real and reconciles documentation — no further code changes.

**Tech Stack:** FastAPI + async SQLAlchemy + pytest (existing, Task 1–2), Next.js/React + vitest + Testing Library (existing, Task 3). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-22-enh-010-account-activation-design.md`. Read it first — §3 (`DEC-SCOPE-023` draft), §6 (AC→test mapping), §7–8 (findings) are authoritative. This plan additionally covers `ENH010-QA-01` (found during the browser QA pass that followed the spec, not in the spec itself) and drops the two frontend a11y items the spec's design-review round originally flagged (`refocus`, `role="alert"`) — both were found to already match `AdminUserManagementPanel.tsx`'s own established convention for this exact component shape (per-row table toggle), so "fixing" them would make `SchoolTeamPanel.tsx` *inconsistent* with its true sibling, not consistent with it. Do not reintroduce them without re-litigating that finding.

## Global Constraints

- No new dependency, no migration, no new table, no new endpoint.
- Do **not** change `update_team_account`'s existing behavior, only add tests and (Task 3 only) the re-entrancy guard. Do not touch `_require_coordinator`, `INVITABLE_ROLES`, `get_current_user`, `login`, `_assignment_is_usable`, or any RBAC code.
- Do **not** add `refocus()` calls or change the `role="status"`/`role="alert"` split in `SchoolTeamPanel.tsx` — both were investigated and found to already match this component's true sibling (`AdminUserManagementPanel.tsx`), not to deviate from it (spec note above).
- Every test that creates a user does so via the existing `_create_school_with_roles` fixture (backend) — never touch a seeded demo account.
- Audit metadata stays IDs/booleans only — no name/email in `AuditLog.metadata_json` (unaffected by this plan, but do not add any while touching this file).
- Never alter product behaviour merely to make a test pass; a failing mutation check that *doesn't* fail is a signal to fix the test, not to weaken it.
- Commit messages end with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`, per this session's attribution convention.

## Execution prerequisites (read before Task 1)

- **Docker stack is already up and seeded** in this worktree (`.claude/worktrees/enh-010`), ports `3000`/`8000`, `.env` copied from `.env.example` (gitignored, placeholder values only). Do not tear it down mid-plan.
- **Backend test loop** (mirrors ENH-006's `BACKEND_TEST`):
  ```powershell
  docker compose cp apps/api/app/. api:/app/app/
  docker compose cp apps/api/tests/. api:/app/tests/
  docker compose exec api python -m pytest -q tests/test_sch_team_account_activation.py
  ```
  Call this **`BACKEND_TEST`** below.
- **Frontend unit loop:** `cd apps/web; npx vitest run <file>` (no Docker, no rebuild needed for a vitest-only change). Call this **`WEB_UNIT`**.
- **Frontend E2E loop** (Task 3 only, if you choose to re-verify at that level): needs `docker compose build web; docker compose up -d --force-recreate web` first (the running `web` image doesn't hot-reload from a host edit), then `cd apps/web; npx playwright test tests/e2e/sch-team-management.spec.ts --workers=1`. Not required by this plan's tasks (unit coverage is sufficient for the guard), but available if you want extra confidence.
- **Commits:** create them as each task finishes; no separate approval gate mid-plan (already approved).

## File structure

| File | Action | Responsibility |
|---|---|---|
| `apps/api/tests/test_sch_team_account_activation.py` | Modify | Task 1 + Task 2 tests (append) |
| `apps/web/tests/components/SchoolTeamPanel.test.tsx` | Create | Task 3's one test |
| `apps/web/components/SchoolTeamPanel.tsx` | Modify | Task 3's re-entrancy guard |
| `docs/decisions/PRODUCT_DECISION_REGISTER.md` | Modify | Task 4: add `DEC-SCOPE-023` |
| `docs/delivery/ENHANCEMENT_BACKLOG.md` | Modify | Task 4: supersede the stale ENH-010 "not confirmed" line |
| `docs/quality/RTM.md` | Modify | Task 4: supersede the stale row `B2` line |
| `docs/product/PRD_OPEN_ITEMS.md` | Modify (conditionally) | Task 4: close the item if ENH-010/B2 appears there |

`apps/api/app/api/schools.py` is touched only transiently during Task 2's mutation check (Step 3) and is always restored byte-for-byte before that task's commit — it is not part of the committed diff anywhere in this plan.

---

### Task 1: AC2 characterization test — deactivated user cannot authenticate

**Files:**
- Modify: `apps/api/tests/test_sch_team_account_activation.py` (append)

**Interfaces:**
- Consumes: `_create_school_with_roles`, `_login`, `PASSWORD` (all already defined in this file).
- Produces: nothing new consumed by later tasks (Task 2 is independent, also appends to this file).

- [ ] **Step 1: Confirm a green baseline**

Run `BACKEND_TEST`. Expected: PASS, 7/7 (the existing suite). Record the count. If anything already fails, stop and report — do not attribute it to this plan later.

- [ ] **Step 2: Write the test**

This is a *characterization* test of already-correct existing behavior (`login()` at `auth.py:95` and `get_current_user` at `deps.py:24-25` both already filter `User.active.is_(True)`) — it is expected to **pass immediately**, not fail. Step 3 proves it is not vacuous via a mutation check, per this repo's own established pattern for exactly this situation (`docs/superpowers/plans/2026-09-21-enh-006-change-password.md` Task 3).

Append to `apps/api/tests/test_sch_team_account_activation.py`, directly after `test_coordinator_deactivates_and_reactivates_a_teacher`:

```python
@pytest.mark.asyncio
async def test_deactivated_teacher_cannot_log_in_and_reactivation_restores_access(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)
    teacher = ctx["school_teacher"]

    deactivated = await client.patch(f"/api/v1/school/team/accounts/{teacher.id}", json={"active": False})
    assert deactivated.status_code == 200

    blocked = await client.post("/api/v1/auth/login", json={"email": teacher.email, "password": PASSWORD, "division": "overseas"})
    assert blocked.status_code == 401

    reactivated = await client.patch(f"/api/v1/school/team/accounts/{teacher.id}", json={"active": True})
    assert reactivated.status_code == 200

    restored = await client.post("/api/v1/auth/login", json={"email": teacher.email, "password": PASSWORD, "division": "overseas"})
    assert restored.status_code == 200
```

- [ ] **Step 3: Run to confirm it passes, then prove it's not vacuous (mutation check)**

Run `BACKEND_TEST`. Expected: PASS, 8/8.

Then temporarily comment out the `User.active.is_(True)` clause in `login()`'s query (`apps/api/app/api/auth.py:95` — change `select(User).where(User.email == payload.email.lower(), User.active.is_(True))` to drop the `, User.active.is_(True))` part, closing the `where(...)` after `payload.email.lower()`), copy the file into the container, run only the new test:
```powershell
docker compose cp apps/api/app/. api:/app/app/
docker compose exec api python -m pytest -q tests/test_sch_team_account_activation.py -k test_deactivated_teacher_cannot_log_in
```
Expected: FAIL (the `blocked.status_code == 401` assertion fails — login now succeeds for a deactivated user). Then **restore the line exactly** (`git diff apps/api/app/api/auth.py` must show no change), copy again, rerun the same `-k` filter, expect PASS. Record the mutation result in the final report.

- [ ] **Step 4: Lint and commit**

```bash
cd apps/api
python -m ruff check tests/test_sch_team_account_activation.py 2>&1 || echo "ruff not available, skip"
cd ..
git add apps/api/tests/test_sch_team_account_activation.py
git commit -m "test(enh-010): prove a deactivated user cannot log in, mutation-checked

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Mass-assignment / role-escalation immunity test

**Files:**
- Modify: `apps/api/tests/test_sch_team_account_activation.py` (append)

**Interfaces:**
- Consumes: same fixtures as Task 1. Independent of Task 1 — order between the two doesn't matter.

- [ ] **Step 1: Write the test**

Also a characterization test — `update_team_account` (`schools.py:197`) already reads only `payload["active"]`, so this is expected to pass immediately. Append, after Task 1's test:

```python
@pytest.mark.asyncio
async def test_toggle_ignores_extra_fields_and_changes_only_active(client, db_session):
    ctx = await _create_school_with_roles(db_session)
    await _login(client, ctx["school_coordinator"].email)
    teacher = ctx["school_teacher"]
    original = (teacher.role, teacher.division, teacher.email, teacher.full_name, teacher.password_hash)

    response = await client.patch(
        f"/api/v1/school/team/accounts/{teacher.id}",
        json={
            "active": False,
            "role": "super_admin",
            "division": "global",
            "email": "attacker@example.local",
            "full_name": "Hacked",
            "password_hash": "x",
        },
    )
    assert response.status_code == 200

    await db_session.refresh(teacher)
    assert (teacher.role, teacher.division, teacher.email, teacher.full_name, teacher.password_hash) == original
    assert teacher.active is False
```

- [ ] **Step 2: Run to confirm it passes**

Run `BACKEND_TEST`. Expected: PASS, 9/9.

- [ ] **Step 3: Mutation check**

Temporarily replace the single line `target.active = payload["active"]` in `apps/api/app/api/schools.py` (`update_team_account`, around line 197) with:

```python
    for key, value in payload.items():
        setattr(target, key, value)
```

Copy the file into the container, run only the new test:
```powershell
docker compose cp apps/api/app/. api:/app/app/
docker compose exec api python -m pytest -q tests/test_sch_team_account_activation.py -k test_toggle_ignores_extra_fields
```
Expected: FAIL (the tuple-equality assertion fails — `teacher.role` is now `"super_admin"`). Then **restore the original single line exactly** (`git diff apps/api/app/api/schools.py` must show no change), copy again, rerun the same `-k` filter, expect PASS. Record the mutation result.

- [ ] **Step 4: Run the whole file once more, then lint and commit**

Run `BACKEND_TEST`. Expected: PASS, 9/9.

```bash
cd apps/api
python -m ruff check tests/test_sch_team_account_activation.py 2>&1 || echo "ruff not available, skip"
cd ..
git add apps/api/tests/test_sch_team_account_activation.py
git commit -m "test(enh-010): prove extra payload fields cannot escalate role or mutate other columns, mutation-checked

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Frontend re-entrancy guard (`ENH010-QA-01`)

**Files:**
- Create: `apps/web/tests/components/SchoolTeamPanel.test.tsx`
- Modify: `apps/web/components/SchoolTeamPanel.tsx`

**Interfaces:**
- Consumes: nothing from Tasks 1–2 (independent, different stack).
- Produces: nothing consumed by Task 4 (Task 4 only re-runs suites and touches docs).

This is a genuine bug — found live during browser QA, not by reading code: three rapid clicks on the same row's "Deactivate" button fire three separate `PATCH` requests, because `busyId`'s re-render hasn't committed yet when the 2nd/3rd click lands in the same tick, so `disabled={busyId === a.id}` doesn't protect against it. `ChangePasswordForm.tsx` already solves the equivalent problem for its single button with a `submitting = useRef(false)` guard checked synchronously at the top of `submit()`. This task ports that idea to a per-row `Set` (multiple rows can be in flight at once, unlike the single-form case).

- [ ] **Step 1: Write the failing test**

No test file exists yet for this component (component-level unit tests were explicitly out of scope for the earlier verification-only round; this one new test is narrowly for the QA-01 bug only — do not expand this file into full component coverage).

Create `apps/web/tests/components/SchoolTeamPanel.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolTeamPanel from "@/components/SchoolTeamPanel";

const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const ACCOUNT = { id: "11111111-1111-1111-1111-111111111111", name: "Test Teacher", email: "teacher@example.local", role: "school_teacher", active: true };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SchoolTeamPanel (ENH010-QA-01)", () => {
  it("ignores repeat clicks on the same row while the first toggle is still pending", async () => {
    let release!: (response: Response) => void;
    const mock = vi.fn().mockReturnValue(new Promise<Response>((resolve) => { release = resolve; }));
    vi.stubGlobal("fetch", mock);

    render(<SchoolTeamPanel accounts={[ACCOUNT]} pendingInvites={[]} />);
    const button = screen.getByRole("button", { name: "Deactivate" });
    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);

    expect(mock).toHaveBeenCalledTimes(1);
    release(new Response(JSON.stringify({ id: ACCOUNT.id, active: false }), { status: 200 }));
    await screen.findByText(/deactivated\./);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `WEB_UNIT apps/web/tests/components/SchoolTeamPanel.test.tsx` (i.e. `cd apps/web; npx vitest run tests/components/SchoolTeamPanel.test.tsx`).
Expected: FAIL — `expect(mock).toHaveBeenCalledTimes(1)` reports 3 calls. Confirm it fails for that reason, not an import/render error.

- [ ] **Step 3: Implement the minimal guard**

In `apps/web/components/SchoolTeamPanel.tsx`:

Change the import line (currently `import { FormEvent, useState } from "react";`) to:

```tsx
import { FormEvent, useRef, useState } from "react";
```

Add, directly after the existing `useState` declarations (after the `rowMessage` line):

```tsx
  // ENH010-QA-01: busyId alone doesn't guard against a 2nd/3rd click landing before the
  // first click's setBusyId re-render commits (all in the same tick) -- mirrors
  // ChangePasswordForm's `submitting` ref, but per-row since multiple accounts can toggle independently.
  const inFlight = useRef<Set<string>>(new Set());
```

Change `toggleActive` from:

```tsx
  async function toggleActive(account: Account) {
    setBusyId(account.id);
    setRowMessage(null);
```

to:

```tsx
  async function toggleActive(account: Account) {
    if (inFlight.current.has(account.id)) return;
    inFlight.current.add(account.id);
    setBusyId(account.id);
    setRowMessage(null);
```

And change the existing line `setBusyId(null);` inside `toggleActive` (the one right after `const data = await response.json().catch(() => ({}));`) to:

```tsx
    inFlight.current.delete(account.id);
    setBusyId(null);
```

No other lines in this function change. `router.refresh()` at the end is untouched.

- [ ] **Step 4: Run to verify it passes**

Run: `WEB_UNIT apps/web/tests/components/SchoolTeamPanel.test.tsx`.
Expected: PASS.

- [ ] **Step 5: Refactor check**

Re-read the diff (`git diff apps/web/components/SchoolTeamPanel.tsx`). Confirm: only the import line, the one new `useRef` line, and the two lines inside `toggleActive` changed — no other behavior touched (the invite form's `submit()` is unaffected; it wasn't part of QA-01). If satisfied, no further refactor needed — this is already the minimal change.

- [ ] **Step 6: Run the full frontend unit suite once more, then lint and commit**

Run: `cd apps/web; npx vitest run` (whole suite — confirm nothing else broke), then `npx eslint components/SchoolTeamPanel.tsx tests/components/SchoolTeamPanel.test.tsx` if configured.

```bash
git add apps/web/components/SchoolTeamPanel.tsx apps/web/tests/components/SchoolTeamPanel.test.tsx
git commit -m "fix(enh-010): guard SchoolTeamPanel's toggle against rapid repeat clicks (ENH010-QA-01)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Full regression pass and documentation reconciliation

**Files:**
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md`, `docs/delivery/ENHANCEMENT_BACKLOG.md`, `docs/quality/RTM.md`
- Modify (conditionally): `docs/product/PRD_OPEN_ITEMS.md`

**Interfaces:** consumes nothing new; this task only runs suites and edits docs, no application code.

- [ ] **Step 1: Full adjacent-regression backend run**

```powershell
docker compose cp apps/api/app/. api:/app/app/
docker compose cp apps/api/tests/. api:/app/tests/
docker compose exec api python -m pytest -q tests/test_sch_team_account_activation.py tests/test_role_assignments.py tests/test_sec_001_audit_trail.py tests/test_sch_001_school_portal_access.py
```
Expected: PASS, unchanged counts except `test_sch_team_account_activation.py` now at 9 (was 7). Record the actual counts as this round's release evidence (do not summarize — paste the real pass/fail line).

- [ ] **Step 2: E2E**

```powershell
docker compose build web
docker compose up -d --force-recreate web
cd apps/web
npx playwright test tests/e2e/sch-team-management.spec.ts --workers=1
```
Expected: PASS, 2/2.

- [ ] **Step 3: Add `DEC-SCOPE-023` to the register**

In `docs/decisions/PRODUCT_DECISION_REGISTER.md`, insert a new entry after the last one (`DEC-SCOPE-022`, ends around line 2172 — insert directly after its closing `---` if present, or after its last line before the next `###` heading):

```markdown
### DEC-SCOPE-023 — School Master (`School CRM.md` Part B §2) = `school_coordinator`; account activate/deactivate confirmed in scope (`ENH-010`)

**Status:** PENDING_CONFIRMATION — drafted 2026-09-22, not yet approved by the user.

**Question:** Is `School CRM.md` Part B §2's "School Master" role the same actor as the
already-confirmed `school_coordinator` role (`DEC-SCOPE-011`), and is "Activate/deactivate
users" confirmed in scope for that role, scoped to their own institution?

**Evidence:** `School CRM.md` (`EVID-014`, `DERIVED_BLUEPRINT`, unattributed) Part B §2,
verbatim: *"School Master can: … Activate/deactivate users."* Per `CLAUDE.md`, this document's
own claim is not `EXPLICIT_APPROVAL` by itself.

**Current state:** `apps/api/app/api/schools.py`'s `update_team_account` (added in the initial
School-domain commit) already implements this and its own docstring asserts it was resolved
"per direct user confirmation" — but no matching entry exists anywhere in this register.
`DEC-SCOPE-011` confirms Coordinator "write access" broadly ("add/manage students… monitor
services") but never names account activation specifically. This entry does not assume which:
an undocumented earlier confirmation, or an inference never actually put to the user.

**Proposed resolution (drafted, not self-approved):** adopt "School Master" (§2) as the same
actor as `school_coordinator` (§33, `DEC-SCOPE-011`) — consistent with `DEC-SCOPE-011` already
treating that role as having broad write access over the school's accounts and data — and
confirm "Activate/deactivate users" as in-scope write access, scoped to the coordinator's own
institution, excluding the coordinator's own account and any peer Coordinator account. This
matches exactly what the shipped code (tested by `test_sch_team_account_activation.py`) already
does.

**Verified 2026-09-22:** the implementation satisfies all four ENH-010 acceptance criteria, by
both a real automated test run (9/9 in `test_sch_team_account_activation.py`, including two new
mutation-checked characterization tests) and a live browser QA pass (all four ACs individually
observed, not read from code) — see `docs/superpowers/specs/2026-09-22-enh-010-account-
activation-design.md` §6 and the ENH010-QA findings for the evidence.

**Not resolved by this entry:** whether the two frontend a11y items considered during design
(`refocus`, differentiated `role="alert"`) should ever be applied — investigated and found to
already match this component's true sibling's convention, not to deviate from it; left open,
not part of this decision either way.
```

- [ ] **Step 4: Reconcile `ENHANCEMENT_BACKLOG.md`**

In `docs/delivery/ENHANCEMENT_BACKLOG.md`, find the ENH-010 entry (`## ENH-010 — Account
Activation / Deactivation (School Master Capability)`). Locate its **Existing behavior.**
paragraph (currently starts "Not confirmed as a coordinator-facing capability…"). Leave that
paragraph's text untouched (never delete evidence-history per this project's own convention) and
append immediately after it:

```markdown
**Resolution, 2026-09-22 (SUPERSEDES the "not confirmed" reading above):** audit found the
capability already shipped under the `SCH-003` addendum (`apps/api/app/api/schools.py`
`update_team_account`, `PATCH /api/v1/school/team/accounts/{user_id}`), predating this backlog
entry. All four acceptance criteria verified — 9/9 automated tests
(`apps/api/tests/test_sch_team_account_activation.py`, including two new mutation-checked
characterization tests for AC2 and mass-assignment immunity) plus a live browser QA pass. One
real bug found and fixed during QA: `ENH010-QA-01`, a rapid-click re-entrancy gap in
`SchoolTeamPanel.tsx`. Decision `DEC-SCOPE-023` (drafted, `PENDING_CONFIRMATION`) records the
`School CRM.md` Part B §2 → `school_coordinator` mapping this relies on. See
`docs/superpowers/specs/2026-09-22-enh-010-account-activation-design.md`.
```

Also update the row in the scan table (around line 113): change
`| ENH-010 | Account activation / deactivation (School Master capability) | Small | Medium | Possibly (TBD) | — |`
to
`| ENH-010 | Account activation / deactivation (School Master capability) | Small | Medium | Yes (verified) | — |`.

- [ ] **Step 5: Reconcile `RTM.md`**

In `docs/quality/RTM.md`, find row `B2` (`| B2 | School Master Login capabilities | ⚠️ Partial |
Most covered by SCH-002/SCH-003; "Activate/deactivate users" not confirmed — see ENH-010 |`).
Change the status cell from `⚠️ Partial` to `✅ Built` and the note cell to:
`Fully covered by SCH-002/SCH-003; "Activate/deactivate users" verified 2026-09-22 (ENH-010, DEC-SCOPE-023 drafted) — see the ENH-010 backlog entry.`

- [ ] **Step 6: Check `PRD_OPEN_ITEMS.md`**

```bash
grep -n "ENH-010\|School Master\|Activate/deactivate" docs/product/PRD_OPEN_ITEMS.md
```
If ENH-010 or this capability appears as an open item, close it with a one-line note pointing to this plan and `DEC-SCOPE-023`, using the same "supersede in place" style as Steps 4–5 (append, don't delete). If nothing matches, do nothing — do not invent an entry that isn't there.

- [ ] **Step 7: Commit the documentation**

```bash
git add docs/decisions/PRODUCT_DECISION_REGISTER.md docs/delivery/ENHANCEMENT_BACKLOG.md docs/quality/RTM.md docs/product/PRD_OPEN_ITEMS.md
git commit -m "docs(enh-010): reconcile backlog/RTM with the verified SCH-003 implementation; draft DEC-SCOPE-023

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

- [ ] **Step 8: Final report**

Do not claim ENH-010 complete. Report: the real test counts from Steps 1–2, the two mutation-check results (Tasks 1–2), confirmation Task 3's test suite is green, and that `DEC-SCOPE-023` is drafted but `PENDING_CONFIRMATION` — awaiting the user's explicit approval before it can read `CONFIRMED_CURRENT`. Independent Codex review is still outstanding per the user's own instruction and is not part of this plan.
