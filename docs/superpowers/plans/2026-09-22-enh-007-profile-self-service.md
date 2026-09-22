# ENH-007 — Profile Self-Service Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every School-domain role (`school_coordinator`, `school_principal`, `school_teacher`,
`school_parent`, `academic_team`, `career_counselor`, `psychometric_team`) a working self-service page to
view/edit their own `full_name` and `phone`, reusing the existing `PATCH /api/v1/auth/me` endpoint.

**Architecture:** One shared route (`/account/profile`) linked from the shared `PortalShell` sidebar,
following the exact pattern already shipped for `/account/password` (ENH-006). Backend gets one small,
additive Pydantic validator fix; no new route, table, migration, or RBAC change.

**Tech Stack:** FastAPI + Pydantic v2 + SQLAlchemy (async) on the backend; Next.js App Router + React
(server component page, client form component) on the frontend; pytest + httpx for backend tests, vitest +
`@testing-library/react` for component tests, Playwright for e2e.

**Spec:** `docs/superpowers/specs/2026-09-22-enh-007-profile-self-service-design.md`

## Global Constraints

- Stay inside ENH-007 scope: `full_name`/`phone` only, 7 School-domain roles, no new route/table/migration/RBAC.
- Reuse existing code: model `account/profile/page.tsx` on `account/password/page.tsx`, `ProfileForm.tsx`
  on `ChangePasswordForm.tsx`, verbatim where the pattern applies — do not paraphrase.
- No new dependencies, no new shared abstraction (no new `lib/formErrors.ts` — keep the local `message()`
  helper duplicated in `ProfileForm.tsx` exactly as `ChangePasswordForm.tsx` already does it; this
  codebase's own convention, not an oversight).
- Preserve API compatibility: `PATCH /auth/me`'s route code (`apps/api/app/api/auth.py`) is not modified,
  only `schemas.py`'s `ProfileUpdate` gets one additive validator.
- Preserve database data: no migration, no schema change; every write in this feature already existed.
- Authorization: unchanged, self-only via `get_current_user` — verified in the spec's §4a/§10a reviews,
  no new check needed anywhere in this plan.
- Transactions/concurrency: unchanged — `update_me()`'s single-commit, no-lock, flat-overwrite behavior is
  correct for `full_name`/`phone` (spec §4a) and this plan introduces no new write path.
- Operational logging: no new logging needed. The new validator raises a standard Pydantic validation
  error (surfaced as the existing generic `422` path), exactly like the neighboring
  `new_password_is_not_blank` validator, which also adds none.
- Every test file creates its own throwaway user (never a seeded/shared account), per this repo's
  established pytest convention (`test_enh_006_change_password.py`'s header comment).

**Environment note (added mid-execution, ledger `Task 1: Ruling`):** this worktree's docker compose stack
runs on non-default ports — `API_PORT=8020`, `WEB_PORT=3020` (the defaults, 8000/3000, were already held
by another worktree's stack on this shared machine) — and without the `docker-compose.override.yml`
`caddy` service (its ports 80/443 are hardcoded, no env override, and were also already held elsewhere;
not needed to run tests). Every backend pytest command in this plan runs as
`docker compose exec api python -m pytest ...` from the worktree root, never `cd apps/api && python -m
pytest` on the host — `db_session`'s `DATABASE_URL` hostname (`postgres`) only resolves inside the compose
network. Frontend vitest commands are unaffected (`cd apps/web && npx vitest run ...` on the host — no
server needed, jsdom only). Playwright (Task 7) needs `E2E_BASE_URL=http://localhost:3020` set in its
environment, since the config's default is `http://localhost:3000`.

---

### Task 1: Backend — fix explicit-null `full_name` crash

**Files:**
- Create: `apps/api/tests/test_enh_007_profile_self_service.py`
- Modify: `apps/api/app/schemas.py:70-73` (`ProfileUpdate`)

**Interfaces:**
- Consumes: `app.core.security.hash_password`, `app.models.User` (existing).
- Produces: `ProfileUpdate.full_name_is_not_null` validator — later tasks don't call this directly, but
  Task 2's tests rely on it not firing for valid/omitted input.

- [ ] **Step 1: Write the failing test**

```python
"""ENH-007 -- Profile self-service, cross-role completion audit.
Spec: docs/superpowers/specs/2026-09-22-enh-007-profile-self-service-design.md

PATCH /auth/me already exists and is reused unmodified except for one validator fix (schemas.py).
Every test creates its own user, per this repo's convention.
"""

import uuid

import pytest

from app.core.security import hash_password
from app.models import User

PASSWORD = "Sup3r-Secret-Pass!"
URL = "/api/v1/auth/me"


async def _make_user(db_session, *, role="school_coordinator", division="overseas") -> User:
    user = User(
        email=f"enh007-{uuid.uuid4().hex[:10]}@example.local",
        password_hash=hash_password(PASSWORD),
        full_name="ENH-007 User",
        role=role,
        division=division,
        active=True,
        email_verified=True,
        profile={"school_id": "11111111-1111-1111-1111-111111111111"},
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _sign_in(client, user, password=PASSWORD):
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": password, "division": user.division})
    assert response.status_code == 200, response.text


async def _signed_in_user(client, db_session, **kwargs) -> User:
    user = await _make_user(db_session, **kwargs)
    await _sign_in(client, user)
    return user


@pytest.mark.asyncio
async def test_explicit_null_full_name_is_rejected_not_a_crash(client, db_session):
    user = await _signed_in_user(client, db_session)
    response = await client.patch(URL, json={"full_name": None})
    assert response.status_code == 422, response.text
    await db_session.refresh(user)
    assert user.full_name == "ENH-007 User"  # unchanged
```

- [ ] **Step 2: Run test to verify it fails for the expected reason**

Run: `docker compose exec api python -m pytest tests/test_enh_007_profile_self_service.py::test_explicit_null_full_name_is_rejected_not_a_crash -v`

Expected: **FAILS**, but not as a clean assertion mismatch — the test's own `client` fixture
(`apps/api/tests/conftest.py`) uses `httpx.ASGITransport` with its default `raise_app_exceptions=True`, so
an unhandled exception inside the route propagates up into the test itself. Expected failure:
`AttributeError: 'NoneType' object has no attribute 'strip'`, raised from `auth.py:191`
(`user.full_name = changes["full_name"].strip()`). This confirms the bug described in spec §4a: explicit
`{"full_name": null}` passes Pydantic validation (`str | None` accepts `None`; `min_length` only
constrains strings) and then crashes the handler.

- [ ] **Step 3: Write minimal implementation**

Edit `apps/api/app/schemas.py`. Current (lines 70-73):

```python
class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    profile: dict | None = None
```

New:

```python
class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=40)
    profile: dict | None = None

    @field_validator("full_name")
    @classmethod
    def full_name_is_not_null(cls, value: str | None) -> str:
        # ENH-007: `str | None` lets an explicit `null` satisfy validation (`min_length` only
        # constrains strings) and reach auth.py's `changes["full_name"].strip()`, which raises an
        # unhandled 500 on None. Pydantic v2 does not validate unset defaults, so this only fires
        # when the key is actually present -- omitting `full_name` is unaffected (still means
        # "don't change it").
        if value is None:
            raise PydanticCustomError("null_full_name", "full_name cannot be null")
        return value
```

`field_validator` and `PydanticCustomError` are already imported at the top of `schemas.py` (lines 7-8) —
no new import needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose exec api python -m pytest tests/test_enh_007_profile_self_service.py::test_explicit_null_full_name_is_rejected_not_a_crash -v`

Expected: PASS — `422`, `user.full_name` unchanged.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/schemas.py apps/api/tests/test_enh_007_profile_self_service.py
git commit -m "fix(enh-007): reject explicit null full_name in PATCH /auth/me

Closes a pre-existing unhandled 500: str | None let an explicit null past
min_length validation, then auth.py's .strip() crashed on it. Mirrors the
existing new_password_is_not_blank validator pattern."
```

---

### Task 2: Backend — characterize the existing full_name/phone update path

No implementation change in this task — the audit found `PATCH /auth/me`'s general `full_name`/`phone`
path has zero test coverage even though the code is already correct (spec §5). These tests close that gap
and prove it, including the authorization boundary this feature must never cross (§4/§7 AC-06/AC-07).

**Files:**
- Modify: `apps/api/tests/test_enh_007_profile_self_service.py` (add to the file from Task 1)

**Interfaces:**
- Consumes: `_make_user`, `_sign_in`, `_signed_in_user` from Task 1 (same file).

- [ ] **Step 1: Write the tests**

Append to `apps/api/tests/test_enh_007_profile_self_service.py`:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    ["school_coordinator", "school_principal", "school_teacher", "school_parent", "academic_team", "career_counselor", "psychometric_team"],
)
async def test_full_name_and_phone_update_succeeds_for_every_school_domain_role(client, db_session, role):
    user = await _signed_in_user(client, db_session, role=role)
    response = await client.patch(URL, json={"full_name": "  Updated Name  ", "phone": "+91 90000 00000"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["full_name"] == "Updated Name"  # server-trimmed (auth.py:191)
    assert body["phone"] == "+91 90000 00000"
    await db_session.refresh(user)
    assert user.full_name == "Updated Name"
    assert user.phone == "+91 90000 00000"


@pytest.mark.asyncio
async def test_omitting_phone_leaves_it_unchanged(client, db_session):
    user = await _make_user(db_session)
    user.phone = "+91 11111 11111"
    await db_session.commit()
    await _sign_in(client, user)
    response = await client.patch(URL, json={"full_name": "New Name"})
    assert response.status_code == 200, response.text
    await db_session.refresh(user)
    assert user.phone == "+91 11111 11111"  # untouched


@pytest.mark.asyncio
async def test_unauthenticated_request_is_401(client):
    response = await client.patch(URL, json={"full_name": "New Name"})
    assert response.status_code == 401, response.text


@pytest.mark.asyncio
async def test_a_full_name_and_phone_only_request_never_touches_the_profile_json(client, db_session):
    user = await _make_user(db_session)
    original_profile = dict(user.profile)
    await _sign_in(client, user)
    response = await client.patch(URL, json={"full_name": "New Name", "phone": "+91 22222 22222"})
    assert response.status_code == 200, response.text
    await db_session.refresh(user)
    # school_id (server-owned) and every other profile key are byte-identical -- the request never
    # included a `profile` key, so `update_me()`'s exclude_unset check means user.profile is untouched.
    assert user.profile == original_profile


@pytest.mark.asyncio
async def test_full_name_under_two_characters_is_rejected_and_nothing_is_saved(client, db_session):
    user = await _signed_in_user(client, db_session)
    response = await client.patch(URL, json={"full_name": "A"})
    assert response.status_code == 422, response.text
    await db_session.refresh(user)
    assert user.full_name == "ENH-007 User"  # unchanged -- AC-04


@pytest.mark.asyncio
async def test_omitting_full_name_entirely_leaves_it_unchanged(client, db_session):
    user = await _signed_in_user(client, db_session)
    response = await client.patch(URL, json={"phone": "+91 33333 33333"})
    assert response.status_code == 200, response.text
    await db_session.refresh(user)
    assert user.full_name == "ENH-007 User"  # unchanged -- AC-10's "omit to skip" contract
    assert user.phone == "+91 33333 33333"
```

- [ ] **Step 2: Run tests to verify they pass immediately**

Run: `docker compose exec api python -m pytest tests/test_enh_007_profile_self_service.py -v`

Expected: **PASS**, all of them, on the first run — this is characterization, not TDD-driven
implementation. `update_me()`'s `full_name`/`phone` path and its `profile`-untouched behavior are already
correct (spec §4/§4a); these tests document and lock that in, closing the coverage gap the original audit
found. Per this project's constitution: do not alter product behavior to make a test pass here — if any of
these fail, stop and investigate rather than "fixing" the route.

- [ ] **Step 3: Run the targeted backend regression scope from spec §8**

Run: `docker compose exec api python -m pytest tests/test_enh_004_student_promotion.py tests/test_role_assignments.py tests/test_stu_011_profile_documents.py -v`

Expected: PASS — confirms the Task 1 validator addition didn't regress the `school_id`/`university_id`
denial path (`test_enh_004_student_promotion.py`'s `test_a_coordinator_cannot_re_point_their_own_school_via_profile_update`
and its `university_rep` counterpart) or any other existing `/auth/me` consumer (AC-09).

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/test_enh_007_profile_self_service.py
git commit -m "test(enh-007): cover PATCH /auth/me's full_name/phone path

Closes a pre-existing coverage gap (only the school_id/university_id
denial path had tests). No production code change -- this path was
already correct."
```

---

### Task 3: Frontend — `ProfileForm` happy path

**Files:**
- Create: `apps/web/tests/components/ProfileForm.test.tsx`
- Create: `apps/web/components/ProfileForm.tsx`

**Interfaces:**
- Produces: `export default function ProfileForm({ fullName, phone }: { fullName: string; phone: string | null })`
  — a client component. Task 5 (the page) renders it as
  `<ProfileForm fullName={user.full_name} phone={user.phone ?? null} />`.

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProfileForm from "@/components/ProfileForm";

afterEach(cleanup);

beforeEach(() => {
  global.fetch = vi.fn();
});

describe("ProfileForm (ENH-007)", () => {
  it("renders the current full name and phone as initial values", () => {
    render(<ProfileForm fullName="Asha Rao" phone="+91 90000 00000" />);
    expect(screen.getByLabelText("Full name")).toHaveValue("Asha Rao");
    expect(screen.getByLabelText("Phone")).toHaveValue("+91 90000 00000");
  });

  it("renders a blank phone input when phone is null", () => {
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    expect(screen.getByLabelText("Phone")).toHaveValue("");
  });

  it("PATCHes /api/v1/auth/me with exactly full_name and phone, never profile", async () => {
    vi.mocked(global.fetch).mockResolvedValue(
      new Response(JSON.stringify({ full_name: "New Name", phone: "+91 11111 11111" }), { status: 200 }),
    );
    render(<ProfileForm fullName="Asha Rao" phone="+91 90000 00000" />);
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "New Name" } });
    fireEvent.change(screen.getByLabelText("Phone"), { target: { value: "+91 11111 11111" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    const [url, init] = vi.mocked(global.fetch).mock.calls[0];
    expect(url).toBe("/api/v1/auth/me");
    expect(init?.method).toBe("PATCH");
    const body = JSON.parse(init?.body as string);
    expect(body).toEqual({ full_name: "New Name", phone: "+91 11111 11111" });
    expect(Object.keys(body)).not.toContain("profile");
  });

  it("shows a success message and syncs fields from the response's canonical values after save", async () => {
    vi.mocked(global.fetch).mockResolvedValue(
      new Response(JSON.stringify({ full_name: "Trimmed Name", phone: "+91 11111 11111" }), { status: 200 }),
    );
    render(<ProfileForm fullName="Asha Rao" phone="+91 90000 00000" />);
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "  Trimmed Name  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("Your profile was updated.");
    // Server-trimmed value, not the raw " Trimmed Name " the user typed -- the frontend review
    // finding this closes (spec §6): auth.py:191 strips server-side, and this form must not drift
    // from that canonical value until the next reload.
    expect(screen.getByLabelText("Full name")).toHaveValue("Trimmed Name");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/web && npx vitest run tests/components/ProfileForm.test.tsx`

Expected: FAIL — `Cannot find module '@/components/ProfileForm'` (the component doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `apps/web/components/ProfileForm.tsx`:

```tsx
"use client";

import { CSSProperties, FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";

function message(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  }
  return "Unable to update your profile. Try again in a moment.";
}

// Announced to assistive tech but not shown: the button label already says "Saving…" on screen.
const VISUALLY_HIDDEN: CSSProperties = { position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)", whiteSpace: "nowrap" };

// Where a signed-out visitor returns to after signing in.
const NEXT = encodeURIComponent("/account/profile");

export default function ProfileForm({ fullName, phone }: { fullName: string; phone: string | null }) {
  const [error, setError] = useState("");
  const [errorField, setErrorField] = useState<"full_name" | null>(null);
  const [notice, setNotice] = useState("");
  const [signedOut, setSignedOut] = useState(false);
  const [busy, setBusy] = useState(false);
  // Canonical values, updated only after a successful save (from the server's response) -- never
  // from onChange, so typing doesn't remount the inputs mid-edit. Keys the inputs below so React
  // re-mounts them with the new defaultValue exactly once, right after a save.
  const [saved, setSaved] = useState({ fullName, phone: phone ?? "" });
  const submitting = useRef(false);
  const [focusRequest, setFocusRequest] = useState<{ id: string } | null>(null);

  useEffect(() => {
    if (focusRequest) document.getElementById(focusRequest.id)?.focus();
  }, [focusRequest]);

  function finish(focusId = "profile-submit") {
    submitting.current = false;
    setBusy(false);
    setFocusRequest({ id: focusId });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true;
    const form = event.currentTarget;
    setBusy(true);
    setError("");
    setErrorField(null);
    setNotice("");
    setSignedOut(false);
    const data = new FormData(form);
    const phoneValue = String(data.get("phone") || "").trim();
    let response: Response;
    try {
      response = await fetch("/api/v1/auth/me", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: data.get("full_name"), phone: phoneValue || null }),
      });
    } catch {
      // Safe to retry (spec §4): this PATCH has no rate limiter or one-shot side effect, unlike
      // change-password, so there's no "unknown outcome" caveat needed here.
      setError("Network error. Try again.");
      finish();
      return;
    }
    const body = await response.json().catch(() => ({}));
    if (response.ok) {
      setSaved({ fullName: body.full_name, phone: body.phone ?? "" });
      setNotice("Your profile was updated.");
      finish();
      return;
    }
    if (response.status === 401) {
      setSignedOut(true);
      finish();
      return;
    }
    setError(message(body.detail));
    if (response.status === 422) {
      setErrorField("full_name");
      finish("profile-full-name");
      return;
    }
    finish();
  }

  return (
    <form className="form" onSubmit={submit} aria-label="Your profile" aria-busy={busy}>
      <div className="field">
        <label htmlFor="profile-full-name">Full name</label>
        <input
          id="profile-full-name"
          key={saved.fullName}
          name="full_name"
          type="text"
          minLength={2}
          maxLength={160}
          defaultValue={saved.fullName}
          aria-invalid={errorField === "full_name" ? true : undefined}
          aria-describedby={errorField === "full_name" ? "profile-error" : undefined}
          required
        />
      </div>
      <div className="field">
        <label htmlFor="profile-phone">Phone</label>
        <input id="profile-phone" key={saved.phone} name="phone" type="text" maxLength={40} defaultValue={saved.phone} />
      </div>
      {error && (
        <div id="profile-error" className="form-error" role="alert" aria-live="assertive">
          <p style={{ margin: 0 }}>{error}</p>
        </div>
      )}
      {signedOut && (
        <div className="form-error" role="alert" aria-live="assertive">
          <p style={{ margin: 0 }}>Your session has expired. Sign in again to update your profile.</p>
          <p style={{ margin: "6px 0 0" }}>
            <Link href={`/it/login?next=${NEXT}`} style={{ color: "var(--blue)", fontWeight: 800 }}>IT Training sign in</Link>{" "}
            <Link href={`/overseas/login?next=${NEXT}`} style={{ color: "var(--blue)", fontWeight: 800 }}>Overseas Education sign in</Link>
          </p>
        </div>
      )}
      {busy ? (
        <div role="status" aria-live="polite" style={VISUALLY_HIDDEN}>
          Saving your profile…
        </div>
      ) : (
        notice && (
          <div className="form-message" role="status" aria-live="polite">
            {notice}
          </div>
        )
      )}
      <button id="profile-submit" className="btn" aria-disabled={busy}>
        {busy ? "Saving…" : "Save changes"}
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && npx vitest run tests/components/ProfileForm.test.tsx`

Expected: PASS, all four tests.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/ProfileForm.tsx apps/web/tests/components/ProfileForm.test.tsx
git commit -m "feat(enh-007): add ProfileForm happy path

Modeled on ChangePasswordForm.tsx's structure. Sends only full_name/phone
to PATCH /auth/me, never profile. Syncs from the server's canonical
(trimmed) values after a successful save."
```

---

### Task 4: Frontend — `ProfileForm` error states

**Files:**
- Modify: `apps/web/tests/components/ProfileForm.test.tsx` (add to Task 3's file)
- Modify: `apps/web/components/ProfileForm.tsx` (add to Task 3's file)

**Interfaces:**
- Consumes/extends the component from Task 3 — no signature change.

- [ ] **Step 1: Write the failing tests**

Append to `apps/web/tests/components/ProfileForm.test.tsx`:

```tsx
  it("shows a signed-out banner with both division sign-in links on 401", async () => {
    vi.mocked(global.fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "Not authenticated" }), { status: 401 }));
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText(/session has expired/);
    expect(screen.getByRole("link", { name: "IT Training sign in" })).toHaveAttribute("href", "/it/login?next=%2Faccount%2Fprofile");
    expect(screen.getByRole("link", { name: "Overseas Education sign in" })).toHaveAttribute("href", "/overseas/login?next=%2Faccount%2Fprofile");
  });

  it("shows an inline field error and focuses full name on 422", async () => {
    vi.mocked(global.fetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: [{ msg: "String should have at least 2 characters" }] }), { status: 422 }),
    );
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "A" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("String should have at least 2 characters");
    expect(screen.getByLabelText("Full name")).toHaveAttribute("aria-invalid", "true");
    await waitFor(() => expect(screen.getByLabelText("Full name")).toHaveFocus());
  });

  it("shows a network-error banner and never claims success", async () => {
    vi.mocked(global.fetch).mockRejectedValue(new TypeError("fetch failed"));
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("Network error. Try again.");
    expect(screen.queryByText("Your profile was updated.")).not.toBeInTheDocument();
  });

  it("ignores a second submit while one is pending", async () => {
    let resolveFirst: (value: Response) => void = () => {};
    vi.mocked(global.fetch).mockReturnValue(new Promise((resolve) => { resolveFirst = resolve; }));
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    const button = screen.getByRole("button", { name: /Save changes|Saving/ });
    fireEvent.click(button);
    fireEvent.click(button);
    resolveFirst(new Response(JSON.stringify({ full_name: "Asha Rao", phone: null }), { status: 200 }));
    await waitFor(() => expect(global.fetch).toHaveBeenCalledTimes(1));
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/web && npx vitest run tests/components/ProfileForm.test.tsx`

Expected: FAIL — these four behaviors (401 banner, 422 inline error + focus, network-error banner,
double-submit guard) are all already implemented in Task 3's `ProfileForm.tsx` (it mirrors
`ChangePasswordForm.tsx`'s pattern in full). Run this step for real: if any of these four fail, it is a
genuine gap in Task 3's implementation, not an expected RED — investigate and fix `ProfileForm.tsx` rather
than treating this as normal TDD red.

- [ ] **Step 3: Fix any gap found, or confirm no code change is needed**

If Step 2 showed failures, fix `apps/web/components/ProfileForm.tsx` to match. If Step 2 already passed
(the behavior was already correctly implemented in Task 3), state that explicitly and skip to Step 4 — do
not invent a change.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && npx vitest run tests/components/ProfileForm.test.tsx`

Expected: PASS, all eight tests (four from Task 3, four from this task).

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/ProfileForm.tsx apps/web/tests/components/ProfileForm.test.tsx
git commit -m "test(enh-007): cover ProfileForm's error and double-submit states"
```

---

### Task 5: Frontend — `/account/profile` page

**Files:**
- Create: `apps/web/tests/components/AccountProfilePage.test.tsx`
- Create: `apps/web/app/account/profile/page.tsx`

**Interfaces:**
- Consumes: `ProfileForm` from Task 3/4, `serverApi`/`ApiError` from `@/lib/api`, `ROLE_DASHBOARD_PATH`
  from `@/lib/navigation`, `User` from `@/lib/types`, `PublicShell` from `@/components/PublicShell`.
- Produces: `export default async function AccountProfilePage()`, `export const metadata`.

- [ ] **Step 1: Write the failing test**

Model exactly on `apps/web/tests/components/AccountPasswordPage.test.tsx`'s pattern (async server
component tested via the `elements`/`text` tree helpers, not DOM rendering):

```tsx
import { beforeEach, describe, expect, it, vi } from "vitest";

import ProfileForm from "@/components/ProfileForm";
import PublicShell from "@/components/PublicShell";
import { ApiError, serverApi } from "@/lib/api";
import AccountProfilePage, { metadata } from "@/app/account/profile/page";
import { elements, text } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));
vi.mock("@/components/PublicShell", () => ({ default: function PublicShell() { return null; } }));

const user = (overrides: Record<string, unknown> = {}) => ({ id: "u1", email: "coordinator@example.local", full_name: "Fatima Coordinator", role: "school_coordinator", division: "overseas", phone: "+91 90000 00000", profile: {}, ...overrides });

async function render() {
  return elements(await AccountProfilePage());
}

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});

describe("/account/profile page (ENH-007)", () => {
  it("shows the form for a signed-in School-domain user with their current name and phone", async () => {
    vi.mocked(serverApi).mockResolvedValue(user());
    const tree = await render();
    const form = tree.find((el) => el.type === ProfileForm)!;
    expect(form.props.fullName).toBe("Fatima Coordinator");
    expect(form.props.phone).toBe("+91 90000 00000");
    expect(tree.find((el) => el.type === PublicShell)!.props.division).toBe("overseas");
    expect(text(tree.find((el) => el.type === "h1")!)).toBe("Your profile");
    expect(serverApi).toHaveBeenCalledWith("/api/v1/auth/me");
  });

  it("passes null, not undefined, when phone is unset", async () => {
    vi.mocked(serverApi).mockResolvedValue(user({ phone: undefined }));
    const tree = await render();
    expect(tree.find((el) => el.type === ProfileForm)!.props.phone).toBeNull();
  });

  it("links back to the role's own dashboard", async () => {
    vi.mocked(serverApi).mockResolvedValue(user());
    const back = (await render()).find((el) => el.props.href && text(el).includes("Back to dashboard"))!;
    expect(back.props.href).toBe("/school/coordinator/dashboard");
  });

  it("asks a signed-out visitor to sign in and returns them to this page afterwards", async () => {
    vi.mocked(serverApi).mockRejectedValue(new ApiError("Not authenticated", 401));
    const tree = await render();
    expect(text(tree.find((el) => el.type === "h1")!)).toBe("Sign in required");
    const links = tree.filter((el) => el.type === "a").map((el) => el.props.href);
    expect(links).toEqual(["/it/login?next=%2Faccount%2Fprofile", "/overseas/login?next=%2Faccount%2Fprofile"]);
    expect(tree.some((el) => el.type === ProfileForm)).toBe(false);
  });

  it.each([
    ["the API answers 500", () => new ApiError("500 Internal Server Error", 500)],
    ["the API cannot be reached at all", () => new TypeError("fetch failed")],
  ])("says the service is unavailable, not \"sign in\", when %s", async (_label, failure) => {
    vi.mocked(serverApi).mockRejectedValue(failure());
    const tree = await render();
    expect(text(tree.find((el) => el.type === "h1")!)).toBe("Temporarily unavailable");
    expect(tree.some((el) => el.type === ProfileForm)).toBe(false);
  });

  it("has a page title of its own", () => {
    expect(metadata.title).toBe("Your profile");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/web && npx vitest run tests/components/AccountProfilePage.test.tsx`

Expected: FAIL — `Cannot find module '@/app/account/profile/page'` (the page doesn't exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `apps/web/app/account/profile/page.tsx`, modeled directly on the current
`apps/web/app/account/password/page.tsx`:

```tsx
import type { Metadata } from "next";
import Link from "next/link";
import ProfileForm from "@/components/ProfileForm";
import PublicShell from "@/components/PublicShell";
import { ApiError, serverApi } from "@/lib/api";
import { ROLE_DASHBOARD_PATH } from "@/lib/navigation";
import type { User } from "@/lib/types";

// Belongs to no one role's portal nav (PORTAL_NAV/SCHOOL_NAV), so it is one shared route, same
// reasoning as /account/password (ENH-006). Renders inside PublicShell (site header, footer) and
// links back to the role's dashboard, so it is never a dead end. Gates itself: /account/* is
// outside middleware.ts's matcher, and the API re-checks the session on every request regardless.
const NEXT = encodeURIComponent("/account/profile");

export const metadata: Metadata = { title: "Your profile" };

export default async function AccountProfilePage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (error) {
    // Only an explicit 401 means "signed out". An outage, a 5xx or a network failure must not be
    // reported as that -- following "sign in" would lead to a login that fails too.
    if (!(error instanceof ApiError && error.status === 401)) {
      return (
        <PublicShell>
          <div className="section">
            <div className="container card">
              <h1>Temporarily unavailable</h1>
              <p className="muted">We can&apos;t reach EduSphere right now. Your profile has not been changed. Try again in a moment.</p>
              <a className="btn" href="/account/profile">Try again</a>
            </div>
          </div>
        </PublicShell>
      );
    }
    return (
      <PublicShell>
        <div className="section">
          <div className="container card">
            <h1>Sign in required</h1>
            <p className="muted">You need to be signed in to view your profile.</p>
            <div className="actions">
              <a className="btn" href={`/it/login?next=${NEXT}`}>IT Training sign in</a>
              <a className="btn secondary" href={`/overseas/login?next=${NEXT}`}>Overseas Education sign in</a>
            </div>
          </div>
        </div>
      </PublicShell>
    );
  }
  const division = user.division === "it" || user.division === "overseas" ? user.division : undefined;
  return (
    <PublicShell division={division}>
      <div className="section compact">
        <div className="container" style={{ maxWidth: 560 }}>
          <Link href={ROLE_DASHBOARD_PATH[user.role] || "/"} className="muted" style={{ display: "inline-block", padding: "6px 0" }}>← Back to dashboard</Link>
          <h1 style={{ fontSize: 34, marginTop: 14 }}>Your profile</h1>
          <p className="muted">Signed in as {user.full_name} ({user.email}).</p>
          <div className="action-card">
            <ProfileForm fullName={user.full_name} phone={user.phone ?? null} />
          </div>
        </div>
      </div>
    </PublicShell>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/web && npx vitest run tests/components/AccountProfilePage.test.tsx`

Expected: PASS, all six tests.

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/account/profile/page.tsx apps/web/tests/components/AccountProfilePage.test.tsx
git commit -m "feat(enh-007): add /account/profile page

Modeled on account/password/page.tsx: same 401-vs-outage handling,
back-to-dashboard link, division-aware PublicShell."
```

---

### Task 6: Frontend — `PortalShell` entry point (widest blast radius, done last)

This is the one change in this plan that touches every portal role, not just School-domain ones — done
last, on top of an already-tested `ProfileForm`/page, and covered by the existing `PortalShell.test.tsx`'s
own established pattern.

**Files:**
- Modify: `apps/web/tests/components/PortalShell.test.tsx`
- Modify: `apps/web/components/PortalShell.tsx:13`

**Interfaces:**
- No new exports — `PortalShell`'s props are unchanged.

- [ ] **Step 1: Write the failing tests**

Extend the existing `describe` block in `apps/web/tests/components/PortalShell.test.tsx` (add these `it`s
inside it, alongside the existing three):

```tsx
  it("offers My profile in the desktop sidebar footer, right after Change password", () => {
    const { container } = renderShell();
    const footer = container.querySelector(".sidebar-footer") as HTMLElement;
    const links = within(footer).getAllByRole("link").map((link) => link.textContent);
    expect(links).toEqual(["Change password", "My profile"]);
    expect(within(footer).getByRole("link", { name: "My profile" })).toHaveAttribute("href", "/account/profile");
  });

  // Mirrors the QA-004 lesson this file already tests for "Change password": a shared link must stay
  // front-loaded in the mobile menu, not appended after the role's own (much longer) nav array.
  it("keeps My profile front-loaded in the mobile menu too, not buried after the role's items", () => {
    const { container } = renderShell();
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const mobile = container.querySelector("#portal-mobile-nav-panel") as HTMLElement;
    expect(within(mobile).getAllByRole("link").map((link) => link.textContent)).toEqual(["Change password", "My profile", "Dashboard", "My courses"]);
  });
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/web && npx vitest run tests/components/PortalShell.test.tsx`

Expected: FAIL — "My profile" doesn't exist yet in either the desktop footer or the mobile array.

- [ ] **Step 3: Write minimal implementation**

Edit `apps/web/components/PortalShell.tsx` (single-line file; two exact substring replacements on line 13).

Current:
```
<div className="sidebar-footer" style={{display:"grid",gap:10,justifyItems:"start"}}><Link className="btn ghost small" style={{color:"white",borderColor:"#45668e"}} href="/account/password">Change password</Link><button className="btn ghost small" style={{color:"white",borderColor:"#45668e"}} onClick={logout}>Sign out</button></div>
```

New:
```
<div className="sidebar-footer" style={{display:"grid",gap:10,justifyItems:"start"}}><Link className="btn ghost small" style={{color:"white",borderColor:"#45668e"}} href="/account/password">Change password</Link><Link className="btn ghost small" style={{color:"white",borderColor:"#45668e"}} href="/account/profile">My profile</Link><button className="btn ghost small" style={{color:"white",borderColor:"#45668e"}} onClick={logout}>Sign out</button></div>
```

Current:
```
<MobileNavToggle nav={[{href:"/account/password",label:"Change password"},...nav]} buttonClassName="portal-mobile-menu" panelClassName="portal-mobile-nav-panel" panelId="portal-mobile-nav-panel"/>
```

New:
```
<MobileNavToggle nav={[{href:"/account/password",label:"Change password"},{href:"/account/profile",label:"My profile"},...nav]} buttonClassName="portal-mobile-menu" panelClassName="portal-mobile-nav-panel" panelId="portal-mobile-nav-panel"/>
```

Nothing else in the file changes — `.portal-nav` and each role's own `nav` array are untouched.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/web && npx vitest run tests/components/PortalShell.test.tsx`

Expected: PASS, all five tests (three pre-existing + two new).

- [ ] **Step 5: Run the full frontend regression set named in spec §8**

Run: `cd apps/web && npx vitest run tests/components/AccountPasswordPage.test.tsx tests/components/ProfileForm.test.tsx tests/components/AccountProfilePage.test.tsx tests/components/PortalShell.test.tsx`

Expected: PASS — confirms the shared-component edit didn't regress the sibling `/account/password` page
or its own `PortalShell` entry point.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/PortalShell.tsx apps/web/tests/components/PortalShell.test.tsx
git commit -m "feat(enh-007): add My profile entry point to PortalShell

Front-loaded in both the desktop sidebar footer and the mobile menu
(same relative order as Change password), so it isn't buried the way
QA-004 (ENH-006) found Change password buried before that fix."
```

---

### Task 7: Playwright — end-to-end profile self-service

Uses the pre-seeded `school.coordinator@edusphere.local` / `Demo@123` account (`apps/api/app/seed.py:622`,
`PASSWORD = "Demo@123"` at `seed.py:13`) rather than building a School from scratch through the UI — this
feature's code path is identical for all 7 roles (no role branching), so one seeded role is representative
evidence, and reusing the seed avoids an unnecessary, expensive onboarding flow just to reach this page.

**Files:**
- Create: `apps/web/tests/e2e/enh-007-profile-self-service.spec.ts`

**Interfaces:**
- None — exercises the running stack through the browser only.

- [ ] **Step 1: Write the spec**

```typescript
import { test, expect } from "@playwright/test";

// ENH-007 -- Profile Self-Service. Requires the stack running via `docker compose up` with
// `python -m app.seed` already applied (seeds school.coordinator@edusphere.local / Demo@123,
// apps/api/app/seed.py:622). All 7 School-domain roles share the identical
// shell/route/component with no role-conditional logic (spec §8), so this one seeded role is
// sufficient evidence -- not one spec per role.

test("a School-domain user can find, view, and edit their profile from the portal", async ({ page }) => {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "school.coordinator@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  await page.click("a:has-text('My profile')");
  await page.waitForURL("**/account/profile");
  await expect(page.locator("h1")).toHaveText("Your profile");

  const unique = Date.now();
  const newName = `E2E Updated Name ${unique}`;
  await page.fill("#profile-full-name", newName);
  await page.fill("#profile-phone", "+91 90000 00000");
  await page.click("button:has-text('Save changes')");
  await expect(page.getByText("Your profile was updated.")).toBeVisible();

  await page.reload();
  await expect(page.locator("#profile-full-name")).toHaveValue(newName);
  await expect(page.locator("#profile-phone")).toHaveValue("+91 90000 00000");
});

test("a full name under 2 characters is rejected with a field-level error and nothing is saved", async ({ page }) => {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "school.coordinator@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");

  await page.goto("/account/profile");
  const before = await page.locator("#profile-full-name").inputValue();
  await page.fill("#profile-full-name", "A");
  await page.click("button:has-text('Save changes')");
  await expect(page.locator("#profile-full-name")).toHaveAttribute("aria-invalid", "true");

  await page.reload();
  await expect(page.locator("#profile-full-name")).toHaveValue(before);
});

test("a signed-out visit to /account/profile prompts sign-in and returns after login", async ({ page }) => {
  await page.goto("/account/profile");
  await expect(page.locator("h1")).toHaveText("Sign in required");
  await page.click("a:has-text('Overseas Education sign in')");
  await page.fill("#login-email", "school.coordinator@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/account/profile");
  await expect(page.locator("h1")).toHaveText("Your profile");
});
```

- [ ] **Step 2: Run it against the running stack**

Run: `cd apps/web && npx playwright test tests/e2e/enh-007-profile-self-service.spec.ts`

Expected: PASS, all three tests, against the already-running `docker compose` stack (per this repo's
convention — the user starts/stops the stack; do not start it yourself). If the stack isn't up, report
that rather than attempting to start it.

- [ ] **Step 3: Run the targeted regression scope from spec §8**

Run: `cd apps/web && npx playwright test tests/e2e/stu-011-profile-documents.spec.ts tests/e2e/auth-001-login.spec.ts`

Expected: PASS — confirms the `PortalShell` mobile-menu change (Task 6) didn't regress specs that assert
on it.

- [ ] **Step 4: Commit**

```bash
git add apps/web/tests/e2e/enh-007-profile-self-service.spec.ts
git commit -m "test(enh-007): add Playwright coverage for profile self-service

One seeded School-domain role is representative -- the feature has no
role-conditional logic to vary per role."
```

---

## After all tasks: what is still required before this can be called done

Per the user's explicit instruction, implementation completing all 7 tasks above is **not** completion.
Still outstanding after this plan's tasks are green:

1. **Browser validation** — an actual browser pass (not just Playwright's automated assertions) across
   the 7 School-domain roles' portal entry points, mobile menu at a real narrow viewport, and the
   401/422/network-error states, the way ENH-006's own spec §13 recorded its browser-QA findings.
2. **Independent Codex review** — a second, independent review of the diff before this is merged.
3. **Documentation** — the spec §10 updates (`RTM.md`, `ENHANCEMENT_BACKLOG.md`) should be current before
   merge; this fix wave already did them (final whole-branch review, 2026-09-22), but note it here so a
   future plan doesn't drop this the way this one did.

Do not report ENH-007 as complete until all three of these have actually run and their results are recorded.
