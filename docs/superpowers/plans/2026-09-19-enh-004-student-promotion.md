# ENH-004 Student Promotion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a School Coordinator promote or hold back one or many students into the active academic year, scoped to their own school, with every transition kept in retrievable history and the parent views reflecting the new grade immediately.

**Architecture:** An append-only ledger table `school_student_grade_history` records each transition; `school_students` stays the source of the *current* grade/year, so every existing reader keeps working. One endpoint `POST /school/students/promotions` (list of items, row-locked, partial-commit) and one read endpoint `GET /school/students/{id}/grade-history` (reuses `_load_readable_student`). New coordinator screen `/school/coordinator/promotion` and a read-only grade-history section.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2 (`app/schemas.py`), async SQLAlchemy, Alembic, PostgreSQL, pytest (strict asyncio); Next.js 15 / React 19 / TypeScript, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-19-enh-004-student-promotion-design.md` (approved 2026-09-19, including the §5.4 API review). Read it before starting; this plan implements it and does not restate every rationale.

## Global Constraints

Copied from the spec. Every task's requirements include this section.

- **Who:** `school_coordinator` only. The school always comes from `_own_school_id(user)`; **never** read a school identifier from the request.
- **Endpoints (exact):** `POST /school/students/promotions` (always `200` with a report unless a request-level error) and `GET /school/students/{student_id}/grade-history`.
- **Table/migration (exact):** table `school_student_grade_history`; Alembic revision `0033_student_grade_history`, `down_revision = "0032_welcome_token_purpose"`; create-table only; `downgrade()` drops only that table; unique constraint name `uq_school_student_grade_history_year` on `(school_student_id, to_academic_year_id)`.
- **Limits:** `items` 1–500; `grade_or_class` at most 60 characters after stripping (the `String(60)` column width); `grade_level` promote stops at 12 (`MAX_GRADE_LEVEL = 12`); `PROMOTION_LOCK_TIMEOUT = "5s"`.
- **Stable reason codes (never rename):** `already_in_active_year`, `grade_level_not_set`, `terminal_grade`, `label_unparseable`. Row statuses: `promoted`, `held_back`, `failed`, `skipped`. History `action` values: `promoted`, `held_back`.
- **Check order:** 401 → non-coordinator 403 (a `Depends` gate, so it precedes body validation) → payload 422 → lock+load → unknown **or** foreign student `403` (one generic message) → no active year `409` → per-row rules.
- **Conventions:** `snake_case` fields, lowercase enum values, plural-noun hyphenated paths, errors as FastAPI `{"detail": ...}`; request-validation 422 uses FastAPI's list-shaped `detail`.
- **Do not modify:** `create_student`, `update_student`, `bulk_upload_students`, `link_parent`, `_student_out`, `_school_dashboard_payload`, `_current_academic_year_id`, `app/seed.py`, the `AcademicYear` endpoints in `admin.py`, `app/api/deps.py`, `app/core/rbac.py`, `SchoolStudentsPanel.tsx`. The only existing behavior that changes is the SCH-008 timeline "profile created" `detail` (Task 6).
- **Non-goals:** section field, graduated/alumni status, admin-role promotion, student login view, parent notifications, promotion events in the timeline, `Idempotency-Key`.
- **Test infrastructure (AGENTS.md):** backend tests share one PostgreSQL database and leave rows behind. Create unique data per test, never mutate a shared row, **never run the full suite** (run only the files named in this plan). E2E specs also mutate shared state; use unique names.
- **The user controls Docker.** Never run `docker compose ...` yourself. When a step needs the stack rebuilt or restarted, or a migration applied to the shared database, ask the user and wait.
- **Quality gates:** `python -m ruff check .` and `python -m mypy app` from `apps/api`; `npm run typecheck`, `npm run lint`, `npm run build` from `apps/web`. Ruff line length is 200.
- **Git:** stay on branch `feature/enh-004-student-grade-promotion`. **Never `git add -A` or `git add .`** (an untracked `graphify-out/` must stay out of every commit); add explicit paths. End every commit message with the trailer `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` (pass it as a second `-m`).
- **Security (spec §14):** the school and the target year are server-decided, never read from the request (request models use `extra="forbid"`); the school filter is part of the row-locking query so another school's rows are never locked or read; unknown and other-school IDs are one indistinguishable `403`, and a denied attempt is audited (`school.student_promotion_denied`, counts only, no IDs or names); no SQL is built from a string (`set_config` with a bound parameter, not an f-string `SET LOCAL`); a grade label may not contain control characters; nothing sensitive is logged or added to the audit metadata; no new rate limiter and no CSRF token are added (see spec §14 for why); `PATCH /auth/me` making `profile.school_id` read-only (Task 3b) needs the user's approval because it changes authentication/profile logic.
- **Frontend rules (binding, from `docs/ux/`):** a data table becomes a stacked card list on mobile, never a horizontally scrolling table as the only option (`RESPONSIVE_RULES.md`, `NFR-RESP-001` confirmed); no layout shift; every input has a real label; visible focus, never suppressed; errors stated in text and tied to their field; a keyboard-reachable confirmation before a high-consequence action; outcome never conveyed by colour alone (`ACCESSIBILITY_RULES.md`). Reuse existing classes and components (`.card`, `.btn`, `.status`, `.field`, `.select`, `.search`, `.table-controls`, `.empty`, `.form-error`/`.form-message`, `.jtl-*`); the single new stylesheet is `SchoolPromotionPanel.module.css` (precedent: `ProgramCatalogue.module.css`). No new npm dependency, no `loading.tsx` (there is no shared `school/layout.tsx`, so it would render without the portal shell), no optimistic update, no `window.confirm`. Avoid apostrophes in JSX text (`react/no-unescaped-entities`).
- **Commands:** backend commands run from `apps/api`; frontend commands from `apps/web`. The examples use PowerShell-safe syntax (no `&&`).

## Confirmations to obtain from the user (during execution)

1. **Task 2, Step 6:** permission to apply migration `0033` to the shared database (`python -m alembic upgrade head` from `apps/api`). It is additive (creates one new table) and touches no existing data.
2. **Task 8, Step 6 and Task 9, Step 5:** ask the user to rebuild and restart the `api` and `web` containers so the e2e run sees the new code, then wait for their go-ahead.
3. **Task 8 side effect (accepted by AGENTS.md's shared-state rule, but confirm before the first run):** the e2e spec must activate a new academic year, which cannot be deleted through the API. Each run creates a far-future, strictly increasing year so it always wins the "latest start_date" tie-break; afterwards, students created by *other* specs get that year. Nothing else reads it.

4. **Task 3b, Step 0 (security):** explicit approval to make `profile.school_id` read-only through `PATCH /auth/me`. It is a change to authentication/profile logic, and the exposure it closes is real: without it, ENH-004's "a coordinator cannot promote at another school" criterion can be bypassed by editing one's own profile.

## Execution log and plan corrections (2026-09-20)

Found while executing this plan test-first. Where the task text below disagrees with this section, **this section is correct**; the affected steps were fixed in the code and tests as noted.

| # | Plan said | Reality | What was done |
|---|---|---|---|
| 1 | Lint/type gates "expect clean" (`ruff check .`, `mypy app`). | Baseline `HEAD` already has 1 ruff finding (B904 in `schools.py`) and about 154 mypy errors in existing code. | Gate is **no new findings versus baseline**, checked per file and per changed line range. |
| 2 | Task 1 tests and Task 3 tests both define `_item`. | The later definition shadows the earlier at run time, so two Task 1 tests failed with `TypeError`. | Task 1's helper is `_raw_item`; Task 3's stays `_item`. |
| 3 | Task 2: after `upgrade 0032`, the history table is absent. | `0001_initial` builds the baseline from the current ORM metadata, so on a fresh database the table **already exists** by 0032 (why every migration here is inspector-guarded; `0033` is a no-op there). | The migration test drops the table after reaching 0032 to emulate a real pre-feature database, then asserts `0033` creates it, enforces the unique constraint, and its downgrade keeps student rows. |
| 4 | (not covered) | Alembic's `env.py` calls `logging.config.fileConfig()`, which disables every existing logger, silencing `app.school` for all later tests. | The migration helper snapshots and restores logger `disabled` flags. |
| 5 | Preflight: the shared Postgres is on `localhost:5432`. | The user's stack was running, but Postgres is not published to the host. | A throwaway `postgres:16-alpine` on `127.0.0.1:5433` (`DATABASE_URL` override), migrated with the repo's Alembic. The user's database and containers were never touched. Migration `0033` reaches the user's real DB only when the `api` container is rebuilt (needs the user's go-ahead). |
| 6 | (not covered) | The user asked for operational logging. | Structured `app.school` events (IDs and counts only, never names, labels or student IDs): `student_promotion_completed`, `_denied` (warning), `_no_active_year`, `_lock_timeout` (warning), `_conflict` (warning). Each has a test. |
| 7 | Task 8's "no active year" empty state and the roster link used a plain `<a href>`. | The repo's lint rule requires `next/link` for internal routes. | `Link` is used. |
| 8 | Task 8 has only a Playwright test. | The stack was not available to run it, so the UI had no real RED/GREEN. | Added Vitest + Testing Library component tests (`SchoolPromotionPanel.test.tsx`, 14; `SchoolGradeHistory.test.tsx`, 6). The Playwright spec is written and compiles but **has not been run**. |
| 9 | (not covered) | Testing Library's `getByLabelText` over jsdom is super-linear (16 s at 120 rows). The component itself is fast (501 rows: render ~0.5 s, select-all ~0.13 s). | The 501-row cap test selects by id and text, with a comment saying why. |
| 10 | `npm ci` implicitly available. | `apps/web/node_modules` did not exist in the worktree. | Ran `npm ci` (locked dependencies only; `node_modules/` is git-ignored). |
| 11 | Task 3b (`PATCH /auth/me`) was a normal task. | It changes authentication logic and needed the user's approval. | Approved and implemented 2026-09-20 (5 tests; a mutation check on its log line). `profile.university_id` has the same weakness and was deliberately left alone. |
| 12 | The columned layout switches on at a **viewport** width of 768px. | The browser run showed it overflowing at 768 and 1024px: the four columns need ~700px, but the portal sidebar leaves the content area far narrower than the viewport. | The stylesheet uses a **container query** on the list (`@container (min-width: 720px)`), so it adapts to the list's own width. Verified at 320/768/1024/1440px. |
| 13 | The e2e spec creates a "strictly increasing" far-future year each run. | Start dates are day-granular, so two runs on one calendar day tie, and the "latest start_date" tie-break picks arbitrarily (both years were `5000-09-20`, both active). | The spec first closes any earlier `e2e4-*` year that is still active, then creates its own. It is repeatable (run twice). |
| 14 | The first-transition history entry reads `Academic year: <new year>`. | The e2e students are created inside an existing active year, so the entry correctly reads `<previous year> to <new year>`. | The spec's expectation was loosened; the component was right. |
| 15 | Task 8 Step 6 / Task 11: rebuild the **user's** `api` and `web` containers to run the e2e. | The e2e permanently activates a far-future academic year and creates schools and students in whatever database it runs against. | Ran an **isolated** compose project (`enh004-e2e`, ports 3100/8100, its own volumes, base compose file only so Caddy's 80/443 could not clash, a git-ignored `.env` with a freshly generated secret). The user's containers and data were not touched. `0033` was applied by the API container's own entrypoint. `0033` reaches the user's real database when they deploy the branch. |
| 16 | The student timeline component knows the five SCH-008 categories. | Independent browser QA (QA-001): the API also emits `test_prep`, `foreign_language` and `global_education`, so any student with those events crashed the whole coordinator and parent student page ("Application error"). **Pre-existing** (reproduced on the original stack without ENH-004) but it hid the new "Grade history" card for those students. | `SchoolStudentTimeline` maps the three categories and falls back to a neutral, humanised badge for any future one. Test-first: 10 tests in `SchoolStudentTimeline.test.tsx`, red on the exact `reading 'color'` crash. |
| 17 | The promotion page relies on the API's 403 for non-coordinators. | QA-002: Parent, Teacher and Principal were shown the coordinator nav and the promotion UI (and their roster); only a submit failed with 403. `/team` already denies these roles up front. | The page fetches the user first and shows "Access unavailable — School Coordinator role required" for any other role, without loading the roster. 5 tests in `SchoolCoordinatorPromotionPage.test.tsx`. Authorization is unchanged: the API remains the enforcement point. |
| 18 | Only the success summary takes focus after a submit. | QA-003: after a failed submit the Confirm button is unmounted, focus is lost, and the error banner (top of the panel) could sit above the viewport. | The banner is focusable and takes focus, which also scrolls it into view (as the summary already does). 3 focus tests, red before the change. QA-008 and QA-009 (Low, app-wide: the guard's raw "fetch failed" text, `aria-current` on the nav) are not ENH-004 and are left for their own item. |
| 19 | The promotion screen trusts any 200, shows the API's own failure wording, stays editable while submitting, and treats a 401 like any error. | QA-004 to QA-007 (all Low): a `200 {}` or proxy page crashed the whole screen; results read `grade_or_class has no grade number…`; the list could be edited mid-request; a 401 left no way back to sign in. | (004) A 200 is accepted only if it has the shape of a report, else the "response could not be read; repeating is safe" banner. (005) Each stable `reason` code is worded for a coordinator (the API's `message` and contract are unchanged; unknown reasons fall back to it). No client-side grade parsing was added: rows the server refuses for a label it cannot parse are explained after the fact and fixed via "New label"; a pre-submit hint would need a dry-run endpoint (not in scope). (006) `busy` disables rows, filters and select-all and sets `aria-busy`. (007) 401 shows "Your session has expired" with a Sign in again link; the selection is kept. 9 new tests, red before. |

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `apps/api/app/models.py` | Modify (after `SchoolParentLink`, ~line 1037) | `SchoolStudentGradeHistory` model |
| `apps/api/alembic/versions/0033_student_grade_history.py` | Create | Create-table migration |
| `apps/api/app/schemas.py` | Modify (imports + append) | `PromotionItem`, `StudentPromotionRequest`, response models, grade-history models |
| `apps/api/app/api/schools.py` | Modify | Pure helpers (`_swap_grade_label`, `_decide_promotion`), the promotion route, the grade-history route, the timeline detail fix |
| `apps/api/tests/test_enh_004_student_promotion.py` | Create (grows over Tasks 1–6) | All backend tests |
| `apps/web/components/SchoolPromotionPanel.tsx` | Create | Promotion container (client): filter, selection, confirm step, submit, focus management |
| `apps/web/components/SchoolPromotionRow.tsx` | Create | One student's row/card (memoised, presentational) |
| `apps/web/components/SchoolPromotionPanel.module.css` | Create | The only new CSS: stacked-card layout on mobile, header row from 768px, sticky action bar |
| `apps/web/app/school/coordinator/promotion/page.tsx` | Create | Server page for the route |
| `apps/web/lib/navigation.ts` | Modify line 37 | Coordinator nav entry |
| `apps/web/components/SchoolGradeHistory.tsx` | Create | Read-only history section + loader |
| `apps/web/components/SchoolStudentDetailPanel.tsx` | Modify | Optional grade-history card |
| `apps/web/app/school/coordinator/students/[id]/page.tsx` | Modify | Pass `showGradeHistory` |
| `apps/web/app/school/parent/children/[id]/page.tsx` | Modify | Grade-history card |
| `apps/web/tests/e2e/enh-004-student-promotion.spec.ts` | Create | Playwright coverage |
| `docs/...` | Modify | Task 10 lists them |

---

## Preflight (no commit)

- [ ] **Step 1: Confirm the branch and a clean tree**

Run: `git branch --show-current; git status --short`
Expected: `feature/enh-004-student-grade-promotion`; only `?? graphify-out/` listed.

- [ ] **Step 2: Confirm the backend test toolchain can reach the shared database**

Run (from `apps/api`): `python -m pytest -q tests/test_enh_001_academic_year.py -k "grade_level_backfill_parser"`
Expected: `8 passed` (a pure test, proves pytest and imports work). Then run
`python -m pytest -q tests/test_enh_001_academic_year.py -k "test_create_student_accepts_a_valid_grade_level"`
Expected: `1 passed` (proves the database is reachable). If this fails with a connection error, **stop and ask the user** to bring the stack up; do not start it yourself.

---

## Task 1: Request/response schemas and the pure promotion rules

**Files:**
- Modify: `apps/api/app/schemas.py` (imports at lines 1-4; append at end of file)
- Modify: `apps/api/app/api/schools.py` (imports; insert after `_validate_grade_level`, currently lines 448-453)
- Create: `apps/api/tests/test_enh_004_student_promotion.py`

**Interfaces:**
- Produces (`app.schemas`): `PromotionItem`, `StudentPromotionRequest`, `PromotionResult`, `PromotionCounts`, `PromotionYear`, `StudentPromotionResponse`.
- Produces (`app.api.schools`): constants `MAX_GRADE_LEVEL`, `GRADE_LABEL_MAX_LENGTH`, `REASON_ALREADY_IN_ACTIVE_YEAR`, `REASON_GRADE_LEVEL_NOT_SET`, `REASON_TERMINAL_GRADE`, `REASON_LABEL_UNPARSEABLE`; `_swap_grade_label(label: str | None, from_level: int, to_level: int) -> tuple[str | None, str | None]` (returns `(new_label, problem_message)`; exactly one of the two is non-`None` unless `label` is `None`, which returns `(None, None)`); `@dataclass(frozen=True) PromotionDecision(status, grade_level, grade_or_class, reason=None, message=None)`; `_decide_promotion(*, action, student_year_id, active_year_id, grade_level, grade_or_class, override) -> PromotionDecision`.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_enh_004_student_promotion.py`:

```python
"""ENH-004 -- Student promotion to the next academic year / grade
(docs/superpowers/specs/2026-09-19-enh-004-student-promotion-design.md, DEC-SCOPE-020)."""

import uuid

import pytest
from pydantic import ValidationError

from app.api.schools import (
    MAX_GRADE_LEVEL,
    REASON_ALREADY_IN_ACTIVE_YEAR,
    REASON_GRADE_LEVEL_NOT_SET,
    REASON_LABEL_UNPARSEABLE,
    REASON_TERMINAL_GRADE,
    _decide_promotion,
    _swap_grade_label,
)
from app.schemas import StudentPromotionRequest

YEAR_OLD = uuid.uuid4()
YEAR_ACTIVE = uuid.uuid4()


# ---------------------------------------------------------------- label swap (pure)


@pytest.mark.parametrize(
    "label,from_level,to_level,expected",
    [
        ("Grade 8-A", 8, 9, "Grade 9-A"),
        ("Class 10", 10, 11, "Class 11"),
        ("grade 5", 5, 6, "grade 6"),
        ("10-A", 10, 11, "11-A"),
        ("Grade 9", 9, 10, "Grade 10"),
        ("Grade 11 (Gold)", 11, 12, "Grade 12 (Gold)"),
    ],
)
def test_swap_grade_label_advances_only_the_grade_number(label, from_level, to_level, expected):
    assert _swap_grade_label(label, from_level, to_level) == (expected, None)


def test_swap_grade_label_leaves_a_missing_label_missing():
    assert _swap_grade_label(None, 8, 9) == (None, None)


@pytest.mark.parametrize("label", ["8A", "Nonsense", "Std IX", ""])
def test_swap_grade_label_refuses_a_label_without_a_grade_number(label):
    new_label, problem = _swap_grade_label(label, 8, 9)
    assert new_label is None
    assert problem and "supply grade_or_class" in problem


def test_swap_grade_label_refuses_a_number_that_disagrees_with_grade_level():
    new_label, problem = _swap_grade_label("Grade 8-A", 9, 10)
    assert new_label is None
    assert problem and "does not match" in problem


def test_swap_grade_label_refuses_a_result_longer_than_60_characters():
    label = "Grade 9 " + "x" * 52  # exactly 60 characters; "9" -> "10" would make it 61
    assert len(label) == 60
    new_label, problem = _swap_grade_label(label, 9, 10)
    assert new_label is None
    assert problem and "60 characters" in problem


# ---------------------------------------------------------------- per-row decision (pure)


def _decide(**overrides):
    args = {"action": "promote", "student_year_id": YEAR_OLD, "active_year_id": YEAR_ACTIVE, "grade_level": 8, "grade_or_class": "Grade 8-A", "override": None}
    args.update(overrides)
    return _decide_promotion(**args)


def test_promote_advances_the_level_and_the_label():
    d = _decide()
    assert (d.status, d.grade_level, d.grade_or_class, d.reason, d.message) == ("promoted", 9, "Grade 9-A", None, None)


def test_promote_uses_the_override_instead_of_the_swap():
    d = _decide(override="Grade 9 (Gold)")
    assert (d.status, d.grade_level, d.grade_or_class) == ("promoted", 9, "Grade 9 (Gold)")


def test_promote_with_no_label_keeps_no_label():
    d = _decide(grade_or_class=None)
    assert (d.status, d.grade_level, d.grade_or_class) == ("promoted", 9, None)


def test_hold_back_keeps_grade_and_label():
    d = _decide(action="hold_back")
    assert (d.status, d.grade_level, d.grade_or_class, d.reason) == ("held_back", 8, "Grade 8-A", None)


@pytest.mark.parametrize("grade_level", [12, None])
def test_hold_back_is_allowed_at_the_top_grade_and_with_no_grade(grade_level):
    d = _decide(action="hold_back", grade_level=grade_level)
    assert (d.status, d.grade_level) == ("held_back", grade_level)


@pytest.mark.parametrize("action", ["promote", "hold_back"])
def test_a_student_already_in_the_active_year_is_skipped_and_unchanged(action):
    d = _decide(action=action, student_year_id=YEAR_ACTIVE)
    assert (d.status, d.reason, d.grade_level, d.grade_or_class) == ("skipped", REASON_ALREADY_IN_ACTIVE_YEAR, 8, "Grade 8-A")
    assert d.message


def test_a_student_with_no_year_is_processable():
    assert _decide(student_year_id=None).status == "promoted"


def test_promote_without_a_grade_level_fails():
    d = _decide(grade_level=None)
    assert (d.status, d.reason, d.grade_level, d.grade_or_class) == ("failed", REASON_GRADE_LEVEL_NOT_SET, None, "Grade 8-A")


def test_promote_from_the_top_grade_fails():
    assert MAX_GRADE_LEVEL == 12
    d = _decide(grade_level=12, grade_or_class="Grade 12")
    assert (d.status, d.reason, d.grade_level, d.grade_or_class) == ("failed", REASON_TERMINAL_GRADE, 12, "Grade 12")


def test_promote_with_an_unswappable_label_fails_unless_overridden():
    failed = _decide(grade_or_class="8A")
    assert (failed.status, failed.reason, failed.grade_level, failed.grade_or_class) == ("failed", REASON_LABEL_UNPARSEABLE, 8, "8A")
    assert failed.message
    fixed = _decide(grade_or_class="8A", override="Grade 9A")
    assert (fixed.status, fixed.grade_level, fixed.grade_or_class) == ("promoted", 9, "Grade 9A")


# ---------------------------------------------------------------- request model (pure)


def _item(**overrides):
    return {"student_id": str(uuid.uuid4()), "action": "promote", **overrides}


def test_request_accepts_valid_items():
    request = StudentPromotionRequest(items=[_item(), _item(action="hold_back")])
    assert [i.action for i in request.items] == ["promote", "hold_back"]


def test_request_strips_the_override_label():
    request = StudentPromotionRequest(items=[_item(grade_or_class="  Grade 9-A  ")])
    assert request.items[0].grade_or_class == "Grade 9-A"


_DUPLICATE = _item()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"items": []},
        {"items": [_item() for _ in range(501)]},
        {"items": [_DUPLICATE, _DUPLICATE]},
        {"items": [_item(student_id="not-a-uuid")]},
        {"items": [_item(action="graduate")]},
        {"items": [_item(action="hold_back", grade_or_class="Grade 9")]},
        {"items": [_item(grade_or_class="   ")]},
        {"items": [_item(grade_or_class="x" * 61)]},
        {"items": [_item(grade_or_class="Grade\x00 9")]},
        {"items": [_item(grade_or_class="Grade\n9")]},
        {"items": [_item()], "school_id": str(uuid.uuid4())},
        {"items": [_item(academic_year_id=str(uuid.uuid4()))]},
    ],
    ids=[
        "missing_items", "empty_items", "over_the_cap", "duplicate_id", "not_a_uuid", "unknown_action", "hold_back_with_label", "blank_label", "label_too_long",
        "nul_in_label", "newline_in_label", "client_supplied_school_id", "client_supplied_year_on_item",
    ],
)
def test_request_rejects_invalid_payloads(payload):
    with pytest.raises(ValidationError):
        StudentPromotionRequest(**payload)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `apps/api`): `python -m pytest -q tests/test_enh_004_student_promotion.py`
Expected: collection error `ImportError: cannot import name 'MAX_GRADE_LEVEL' from 'app.api.schools'` (and `StudentPromotionRequest` from `app.schemas`).

- [ ] **Step 3: Add the schemas**

In `apps/api/app/schemas.py`, replace the first four lines:

```python
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator
```

with:

```python
import unicodedata
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
```

Then append at the very end of the file:

```python


# --- ENH-004: student promotion (docs/superpowers/specs/2026-09-19-enh-004-student-promotion-design.md) ---


class PromotionItem(BaseModel):
    # `extra="forbid"`: a client-supplied `academic_year_id`/`school_id` is a loud 422, never silently ignored
    # (the target year and the school are server-decided; spec §14).
    model_config = {"str_strip_whitespace": True, "extra": "forbid"}
    student_id: UUID
    action: Literal["promote", "hold_back"]
    grade_or_class: str | None = Field(default=None, min_length=1, max_length=60)

    @field_validator("grade_or_class")
    @classmethod
    def _no_control_characters(cls, value: str | None) -> str | None:
        # A NUL byte cannot be stored in PostgreSQL text (it would surface as a 500), and newlines or other
        # control characters have no place in a grade label that is later rendered and exported.
        if value is not None and any(unicodedata.category(ch) == "Cc" for ch in value):
            raise ValueError("grade_or_class must not contain control characters")
        return value


class StudentPromotionRequest(BaseModel):
    model_config = {"extra": "forbid"}
    items: list[PromotionItem] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _reject_duplicates_and_hold_back_labels(self):
        seen: set[UUID] = set()
        for item in self.items:
            if item.student_id in seen:
                raise ValueError(f"student_id {item.student_id} appears more than once")
            seen.add(item.student_id)
            if item.action == "hold_back" and item.grade_or_class is not None:
                raise ValueError("grade_or_class is only allowed with action 'promote'")
        return self


class PromotionResult(BaseModel):
    student_id: UUID
    status: Literal["promoted", "held_back", "failed", "skipped"]
    reason: str | None = None
    message: str | None = None
    grade_level: int | None = None
    grade_or_class: str | None = None


class PromotionCounts(BaseModel):
    promoted: int = 0
    held_back: int = 0
    failed: int = 0
    skipped: int = 0


class PromotionYear(BaseModel):
    id: UUID
    label: str


class StudentPromotionResponse(BaseModel):
    academic_year: PromotionYear
    counts: PromotionCounts
    results: list[PromotionResult]
```

- [ ] **Step 4: Add the pure rules to `schools.py`**

In `apps/api/app/api/schools.py`, add `from dataclasses import dataclass` to the standard-library imports, between `import secrets` and `from datetime import UTC, date, datetime, timedelta`:

```python
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
```

Then insert the following block immediately after the `_validate_grade_level` function (the one ending `return value`, currently line 453) and before `async def _current_academic_year_id`:

```python
# --- ENH-004: student promotion (docs/superpowers/specs/2026-09-19-enh-004-student-promotion-design.md) ---
MAX_GRADE_LEVEL = 12
GRADE_LABEL_MAX_LENGTH = 60  # the school_students.grade_or_class column width
# Same pattern family as migration 0030 and `_grade_level_from_label`.
GRADE_LABEL_PATTERN = re.compile(r"\b(?:grade|class)\s*(\d{1,2})\b|\b(\d{1,2})\b", re.IGNORECASE)
# Stable, machine-readable reasons on a failed/skipped promotion row. Clients may branch on these: never rename one.
REASON_ALREADY_IN_ACTIVE_YEAR = "already_in_active_year"
REASON_GRADE_LEVEL_NOT_SET = "grade_level_not_set"
REASON_TERMINAL_GRADE = "terminal_grade"
REASON_LABEL_UNPARSEABLE = "label_unparseable"


def _swap_grade_label(label: str | None, from_level: int, to_level: int) -> tuple[str | None, str | None]:
    """Advance the grade number inside a free-text label ("Grade 8-A" -> "Grade 9-A"). Returns
    (new_label, problem): a missing label stays missing; a label with no grade number, whose number
    disagrees with `from_level`, or whose result would not fit the column returns (None, message)."""
    if label is None:
        return None, None
    match = GRADE_LABEL_PATTERN.search(label)
    if match is None:
        return None, "grade_or_class has no grade number to advance; supply grade_or_class"
    group = 1 if match.group(1) is not None else 2
    if int(match.group(group)) != from_level:
        return None, "grade_or_class does not match grade_level; supply grade_or_class"
    swapped = label[: match.start(group)] + str(to_level) + label[match.end(group) :]
    if len(swapped) > GRADE_LABEL_MAX_LENGTH:
        return None, f"the advanced grade_or_class would be longer than {GRADE_LABEL_MAX_LENGTH} characters; supply a shorter grade_or_class"
    return swapped, None


@dataclass(frozen=True)
class PromotionDecision:
    status: str  # promoted | held_back | failed | skipped
    grade_level: int | None
    grade_or_class: str | None
    reason: str | None = None
    message: str | None = None


def _decide_promotion(*, action: str, student_year_id: UUID | None, active_year_id: UUID, grade_level: int | None, grade_or_class: str | None, override: str | None) -> PromotionDecision:
    """The whole per-row rule table (spec §5.2), with no database access. `grade_level` and
    `grade_or_class` on the result are the student's state after the request."""

    def _unchanged(status: str, reason: str, message: str) -> PromotionDecision:
        return PromotionDecision(status, grade_level, grade_or_class, reason, message)

    if student_year_id == active_year_id:
        return _unchanged("skipped", REASON_ALREADY_IN_ACTIVE_YEAR, "Student is already in the active academic year.")
    if action == "hold_back":
        return PromotionDecision("held_back", grade_level, grade_or_class)
    if grade_level is None:
        return _unchanged("failed", REASON_GRADE_LEVEL_NOT_SET, "grade_level is not set; set it on the student before promoting.")
    if grade_level >= MAX_GRADE_LEVEL:
        return _unchanged("failed", REASON_TERMINAL_GRADE, f"Grade {MAX_GRADE_LEVEL} is the highest grade; graduation is not supported yet.")
    new_level = grade_level + 1
    if override is not None:
        return PromotionDecision("promoted", new_level, override)
    new_label, problem = _swap_grade_label(grade_or_class, grade_level, new_level)
    if problem is not None:
        return _unchanged("failed", REASON_LABEL_UNPARSEABLE, problem)
    return PromotionDecision("promoted", new_level, new_label)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest -q tests/test_enh_004_student_promotion.py`
Expected: all pass (about 40 tests, no database needed).

- [ ] **Step 6: Lint and type-check the touched files**

Run: `python -m ruff check app/schemas.py app/api/schools.py tests/test_enh_004_student_promotion.py; python -m mypy app`
Expected: `All checks passed!` and `Success: no issues found`.

- [ ] **Step 7: Commit**

```powershell
git add apps/api/app/schemas.py apps/api/app/api/schools.py apps/api/tests/test_enh_004_student_promotion.py
git commit -m "feat(enh-004): add promotion schemas and pure per-row rules" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 2: History model and migration `0033`

**Files:**
- Modify: `apps/api/app/models.py` (insert after the `SchoolParentLink` class, currently ending at line 1036)
- Create: `apps/api/alembic/versions/0033_student_grade_history.py`
- Modify: `apps/api/tests/test_enh_004_student_promotion.py`

**Interfaces:**
- Produces: `app.models.SchoolStudentGradeHistory` with columns `id, school_student_id, action, from_academic_year_id, from_grade_level, from_grade_or_class, to_academic_year_id, to_grade_level, to_grade_or_class, performed_by_user_id, created_at, updated_at`.

- [ ] **Step 1: Write the failing tests**

In `apps/api/tests/test_enh_004_student_promotion.py`, replace the import block at the top (from `import uuid` down to `from app.schemas import StudentPromotionRequest`) with:

```python
import asyncio
import uuid
from contextlib import contextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.api.schools import (
    MAX_GRADE_LEVEL,
    REASON_ALREADY_IN_ACTIVE_YEAR,
    REASON_GRADE_LEVEL_NOT_SET,
    REASON_LABEL_UNPARSEABLE,
    REASON_TERMINAL_GRADE,
    _decide_promotion,
    _swap_grade_label,
)
from app.core.config import settings
from app.models import SchoolStudentGradeHistory
from app.schemas import StudentPromotionRequest
```

Append at the end of the file:

```python


# ---------------------------------------------------------------- model + migration

API_ROOT = Path(__file__).resolve().parents[1]
HISTORY_TABLE_COUNT_SQL = "SELECT count(*) FROM information_schema.tables WHERE table_name = 'school_student_grade_history'"


def test_grade_history_model_shape():
    table = SchoolStudentGradeHistory.__table__
    assert table.name == "school_student_grade_history"
    for name in ("school_student_id", "action", "to_academic_year_id", "performed_by_user_id"):
        assert table.columns[name].nullable is False, name
    for name in ("from_academic_year_id", "from_grade_level", "from_grade_or_class", "to_grade_level", "to_grade_or_class"):
        assert table.columns[name].nullable is True, name
    assert table.columns["from_grade_or_class"].type.length == 60
    assert "uq_school_student_grade_history_year" in {c.name for c in table.constraints}


def _sql(url: str, statement: str, params: dict | None = None, *, autocommit: bool = False) -> list:
    """Run one statement on its own throwaway engine. A plain (sync) helper on purpose: alembic's
    env.py calls asyncio.run() itself, so the migration test cannot run inside an event loop."""

    async def _inner():
        engine = create_async_engine(url, isolation_level="AUTOCOMMIT") if autocommit else create_async_engine(url)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(sa.text(statement), params or {})
                rows = result.fetchall() if result.returns_rows else []
                await conn.commit()
                return rows
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


@contextmanager
def _isolated_migration_database():
    """A uniquely named, throwaway database (never the shared one -- ENH-001's review found a real
    downgrade destroying live rows). Yields (alembic Config, isolated URL); always drops it."""
    original_url = settings.database_url
    name = f"enh004_migration_isolated_{uuid.uuid4().hex[:8]}"
    isolated_url = make_url(original_url).set(database=name).render_as_string(hide_password=False)
    _sql(original_url, f'CREATE DATABASE "{name}"', autocommit=True)
    settings.database_url = isolated_url
    try:
        cfg = Config(str(API_ROOT / "alembic.ini"))
        cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
        yield cfg, isolated_url
    finally:
        settings.database_url = original_url
        try:
            _sql(original_url, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)
        except Exception:
            pass  # best-effort: a leftover uniquely named throwaway database is a contained cost


def test_migration_0033_creates_and_drops_only_the_history_table_and_keeps_student_rows():
    creator_id, school_id, student_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    unique = uuid.uuid4().hex[:8]
    with _isolated_migration_database() as (cfg, url):
        command.upgrade(cfg, "0032_welcome_token_purpose")
        assert _sql(url, HISTORY_TABLE_COUNT_SQL)[0][0] == 0
        # Raw SQL against the pre-0033 schema (same column list ENH-001's migration test uses; `users` is unchanged since 0028).
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, phone, active, email_verified, locale, profile, student_code) "
            "VALUES (:id, :email, 'x', 'Cycle Admin', 'overseas_admin', 'overseas', NULL, true, true, 'en-GB', '{}', NULL)",
            {"id": creator_id, "email": f"enh004-cycle-{unique}@example.local"},
        )
        _sql(url, "INSERT INTO schools (id, name, created_by_user_id) VALUES (:id, 'ENH-004 Cycle School', :creator)", {"id": school_id, "creator": creator_id})
        _sql(
            url,
            "INSERT INTO school_students (id, school_id, student_code, full_name, grade_or_class, grade_level, created_by_user_id) VALUES (:id, :school, :code, 'Cycle Student', 'Grade 8', 8, :creator)",
            {"id": student_id, "school": school_id, "code": f"E{unique[:7]}".upper(), "creator": creator_id},
        )

        command.upgrade(cfg, "0033_student_grade_history")
        assert _sql(url, HISTORY_TABLE_COUNT_SQL)[0][0] == 1
        year_id = _sql(url, "SELECT id FROM academic_years ORDER BY start_date DESC LIMIT 1")[0][0]
        insert = "INSERT INTO school_student_grade_history (id, school_student_id, action, to_academic_year_id, performed_by_user_id) VALUES (:id, :student, 'held_back', :year, :creator)"
        _sql(url, insert, {"id": uuid.uuid4(), "student": student_id, "year": year_id, "creator": creator_id})
        with pytest.raises(IntegrityError, match="uq_school_student_grade_history_year"):
            _sql(url, insert, {"id": uuid.uuid4(), "student": student_id, "year": year_id, "creator": creator_id})

        command.downgrade(cfg, "0032_welcome_token_purpose")
        assert _sql(url, HISTORY_TABLE_COUNT_SQL)[0][0] == 0
        assert _sql(url, "SELECT full_name, grade_level FROM school_students WHERE id = :id", {"id": student_id}) == [("Cycle Student", 8)]


@pytest.mark.asyncio
async def test_the_shared_database_has_the_history_table(db_session):
    # Fails until the user has applied migration 0033 to the shared database (Task 2, Step 6).
    result = await db_session.execute(text(HISTORY_TABLE_COUNT_SQL))
    assert result.scalar() == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest -q tests/test_enh_004_student_promotion.py -k "grade_history_model or migration_0033 or shared_database"`
Expected: collection error `ImportError: cannot import name 'SchoolStudentGradeHistory' from 'app.models'`.

- [ ] **Step 3: Add the model**

In `apps/api/app/models.py`, insert immediately after the `SchoolParentLink` class (after its `linked_by_user_id` line) and before `class SchoolActivity`:

```python
class SchoolStudentGradeHistory(Base, TimestampMixin):
    """ENH-004 append-only ledger of a student's grade/academic-year transitions
    (docs/superpowers/specs/2026-09-19-enh-004-student-promotion-design.md §5.1). Each row is
    self-contained -- it records the state the student left (`from_*`) and the state they entered
    (`to_*`) -- so no backfill of existing students is needed and `school_students` stays the
    source of the *current* grade/year. `UNIQUE (school_student_id, to_academic_year_id)` is the
    database backstop against promoting the same student twice into the same year."""

    __tablename__ = "school_student_grade_history"
    __table_args__ = (UniqueConstraint("school_student_id", "to_academic_year_id", name="uq_school_student_grade_history_year"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    action: Mapped[str] = mapped_column(String(20))  # promoted | held_back
    from_academic_year_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("academic_years.id"), nullable=True)
    from_grade_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    from_grade_or_class: Mapped[str | None] = mapped_column(String(60), nullable=True)
    to_academic_year_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("academic_years.id"))
    to_grade_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_grade_or_class: Mapped[str | None] = mapped_column(String(60), nullable=True)
    performed_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


```

- [ ] **Step 4: Add the migration**

Create `apps/api/alembic/versions/0033_student_grade_history.py`:

```python
"""ENH-004 -- school_student_grade_history (append-only promotion/hold-back ledger).

Revision ID: 0033_student_grade_history
Revises: 0032_welcome_token_purpose

docs/superpowers/specs/2026-09-19-enh-004-student-promotion-design.md §5.1. Create-table only:
no existing table is altered and no existing row is read or written (each history row carries its
own "from" state, so there is nothing to backfill). `downgrade()` drops only this table.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0033_student_grade_history"
down_revision = "0032_welcome_token_purpose"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "school_student_grade_history" in inspector.get_table_names():
        return
    op.create_table(
        "school_student_grade_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("school_student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("school_students.id"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("from_academic_year_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("academic_years.id"), nullable=True),
        sa.Column("from_grade_level", sa.Integer(), nullable=True),
        sa.Column("from_grade_or_class", sa.String(60), nullable=True),
        sa.Column("to_academic_year_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("academic_years.id"), nullable=False),
        sa.Column("to_grade_level", sa.Integer(), nullable=True),
        sa.Column("to_grade_or_class", sa.String(60), nullable=True),
        sa.Column("performed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("school_student_id", "to_academic_year_id", name="uq_school_student_grade_history_year"),
    )
    op.create_index("ix_school_student_grade_history_school_student_id", "school_student_grade_history", ["school_student_id"])


def downgrade() -> None:
    op.drop_index("ix_school_student_grade_history_school_student_id", table_name="school_student_grade_history")
    op.drop_table("school_student_grade_history")
```

- [ ] **Step 5: Run the model and isolated-migration tests to verify they pass**

Run: `python -m pytest -q tests/test_enh_004_student_promotion.py -k "grade_history_model or migration_0033"`
Expected: `2 passed`. (The migration test builds and drops its own throwaway database, so it does not need Step 6.)

- [ ] **Step 6: Ask the user, then apply the migration to the shared database**

Ask the user: "Migration `0033_student_grade_history` only creates one new table. May I run `python -m alembic upgrade head` from `apps/api` against the shared database?" Wait for a yes, then run it.
Run (from `apps/api`): `python -m alembic upgrade head`
Expected: `Running upgrade 0032_welcome_token_purpose -> 0033_student_grade_history`.
Then run: `python -m pytest -q tests/test_enh_004_student_promotion.py -k shared_database`
Expected: `1 passed`.

- [ ] **Step 7: Lint and type-check**

Run: `python -m ruff check app tests/test_enh_004_student_promotion.py; python -m mypy app`
Expected: both clean (`alembic/versions` is excluded from ruff; `tests` from mypy).

- [ ] **Step 8: Commit**

```powershell
git add apps/api/app/models.py apps/api/alembic/versions/0033_student_grade_history.py apps/api/tests/test_enh_004_student_promotion.py
git commit -m "feat(enh-004): add school_student_grade_history model and migration 0033" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3: The promotion endpoint

**Files:**
- Modify: `apps/api/app/api/schools.py` (imports; add the constant, the dependency and the route after `link_parent`, i.e. immediately before `@router.get("/activities")`)
- Modify: `apps/api/tests/test_enh_004_student_promotion.py`

**Interfaces:**
- Consumes: Task 1 (`_decide_promotion`, `PromotionDecision`, `StudentPromotionRequest`, `StudentPromotionResponse`), Task 2 (`SchoolStudentGradeHistory`), existing `_own_school_id`, `_require_coordinator`, `_current_academic_year_id`, `get_current_user`, `get_db`.
- Produces: `PROMOTION_LOCK_TIMEOUT = "5s"` (module constant, read at call time so tests can monkeypatch it); `_require_coordinator_user` dependency; route `POST /school/students/promotions`.
- Produces (test helpers used by Tasks 4-6): fixture `future_years` (async factory `await future_years(start=date(9999, 4, 1)) -> AcademicYear`), `_school(db_session, students=...) -> dict`, `_login(client, email)`, `_promote(client, items)`, `_item(student, action="promote", **extra)`, constants `URL`, `PASSWORD`.

- [ ] **Step 1: Write the failing tests**

In `apps/api/tests/test_enh_004_student_promotion.py`, replace the import block at the top (from `import asyncio` through `from app.schemas import StudentPromotionRequest`) with:

```python
import asyncio
import uuid
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import delete, func, or_, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.api.schools import (
    MAX_GRADE_LEVEL,
    REASON_ALREADY_IN_ACTIVE_YEAR,
    REASON_GRADE_LEVEL_NOT_SET,
    REASON_LABEL_UNPARSEABLE,
    REASON_TERMINAL_GRADE,
    _decide_promotion,
    _swap_grade_label,
)
from app.core.config import settings
from app.core.identifiers import unique_student_code
from app.core.security import hash_password
from app.models import (
    AcademicYear,
    AuditLog,
    School,
    SchoolParentLink,
    SchoolStudent,
    SchoolStudentGradeHistory,
    User,
    UserRoleAssignment,
)
from app.schemas import StudentPromotionRequest
```

Append at the end of the file:

```python


# ---------------------------------------------------------------- endpoint helpers

PASSWORD = "Sup3r-Secret-Pass!"
URL = "/api/v1/school/students/promotions"


@pytest_asyncio.fixture
async def future_years(db_session):
    """Factory for ACTIVE academic years dated far in the future, so they win
    `_current_academic_year_id`'s latest-start_date tie-break without ever touching a real year
    (the same technique as test_enh_001's active-year test). Everything the tests attach to them is
    removed afterwards so repeated runs against the shared database stay idempotent."""
    created: list[uuid.UUID] = []

    async def _make(start: date = date(9999, 4, 1)) -> AcademicYear:
        year = AcademicYear(label=f"enh004-{uuid.uuid4().hex[:8]}", start_date=start, end_date=date(9999, 12, 30), status="active")
        db_session.add(year)
        await db_session.commit()
        created.append(year.id)
        return year

    yield _make

    if created:
        await db_session.rollback()
        await db_session.execute(delete(SchoolStudentGradeHistory).where(or_(SchoolStudentGradeHistory.to_academic_year_id.in_(created), SchoolStudentGradeHistory.from_academic_year_id.in_(created))))
        await db_session.execute(update(SchoolStudent).where(SchoolStudent.academic_year_id.in_(created)).values(academic_year_id=None))
        await db_session.execute(delete(AcademicYear).where(AcademicYear.id.in_(created)))
        await db_session.commit()


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200, response.text


async def _user(db_session, *, role: str, full_name: str, school_id=None, assigned_by=None) -> User:
    profile = {"school_id": str(school_id)} if school_id else {}
    u = User(email=f"enh004-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name=full_name, role=role, division="overseas", active=True, profile=profile)
    db_session.add(u)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=u.id, division="overseas", role=role, is_active=True, assigned_by_user_id=(assigned_by or u).id, approval_status="approved"))
    return u


async def _school(db_session, students=(("Grade 8-A", 8), ("Grade 8-B", 8))) -> dict:
    """A fresh school with a coordinator, teacher, principal, a parent linked to the first student,
    and one student per (label, grade_level) pair. Students start with academic_year_id NULL, so
    they are processable once an active year exists. The teacher is assigned to the first student only."""
    admin = await _user(db_session, role="overseas_admin", full_name="Overseas Admin")
    school = School(name=f"ENH-004 Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
    db_session.add(school)
    await db_session.flush()
    coordinator = await _user(db_session, role="school_coordinator", full_name="Coordinator", school_id=school.id, assigned_by=admin)
    teacher = await _user(db_session, role="school_teacher", full_name="Ms Teacher", school_id=school.id, assigned_by=coordinator)
    principal = await _user(db_session, role="school_principal", full_name="Principal", school_id=school.id, assigned_by=coordinator)
    rows = []
    for index, (label, level) in enumerate(students):
        rows.append(
            SchoolStudent(
                school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name=f"Child {index}",
                grade_or_class=label, grade_level=level, created_by_user_id=coordinator.id, assigned_teacher_user_id=teacher.id if index == 0 else None,
            )
        )
    db_session.add_all(rows)
    await db_session.flush()
    parent = await _user(db_session, role="school_parent", full_name="Parent of Child 0", school_id=school.id, assigned_by=coordinator)
    db_session.add(SchoolParentLink(parent_user_id=parent.id, school_student_id=rows[0].id, linked_by_user_id=coordinator.id))
    await db_session.commit()
    return {"admin": admin, "school": school, "coordinator": coordinator, "teacher": teacher, "principal": principal, "parent": parent, "students": rows}


def _item(student, action: str = "promote", **extra) -> dict:
    return {"student_id": str(student.id), "action": action, **extra}


async def _promote(client, items: list[dict]):
    return await client.post(URL, json={"items": items})


async def _history(db_session, student) -> list[SchoolStudentGradeHistory]:
    return list((await db_session.scalars(select(SchoolStudentGradeHistory).where(SchoolStudentGradeHistory.school_student_id == student.id))).all())


# ---------------------------------------------------------------- endpoint: happy paths


@pytest.mark.asyncio
async def test_promote_single_student_advances_grade_label_year_and_records_history(client, db_session, future_years):
    year = await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(student)])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["academic_year"] == {"id": str(year.id), "label": year.label}
    assert body["counts"] == {"promoted": 1, "held_back": 0, "failed": 0, "skipped": 0}
    assert body["results"] == [{"student_id": str(student.id), "status": "promoted", "reason": None, "message": None, "grade_level": 9, "grade_or_class": "Grade 9-A"}]
    await db_session.refresh(student)
    assert (student.grade_level, student.grade_or_class, student.academic_year_id) == (9, "Grade 9-A", year.id)
    rows = await _history(db_session, student)
    assert len(rows) == 1
    row = rows[0]
    assert (row.action, row.from_academic_year_id, row.from_grade_level, row.from_grade_or_class) == ("promoted", None, 8, "Grade 8-A")
    assert (row.to_academic_year_id, row.to_grade_level, row.to_grade_or_class, row.performed_by_user_id) == (year.id, 9, "Grade 9-A", ctx["coordinator"].id)


@pytest.mark.asyncio
async def test_bulk_promote_records_one_history_row_per_student(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session, students=(("Grade 8-A", 8), ("Grade 8-B", 8), ("Class 10", 10)))
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(s) for s in ctx["students"]])

    assert response.status_code == 200, response.text
    assert response.json()["counts"] == {"promoted": 3, "held_back": 0, "failed": 0, "skipped": 0}
    for student, expected in zip(ctx["students"], [(9, "Grade 9-A"), (9, "Grade 9-B"), (11, "Class 11")], strict=True):
        await db_session.refresh(student)
        assert (student.grade_level, student.grade_or_class) == expected
    total = await db_session.scalar(select(func.count()).select_from(SchoolStudentGradeHistory).where(SchoolStudentGradeHistory.school_student_id.in_([s.id for s in ctx["students"]])))
    assert total == 3


@pytest.mark.asyncio
async def test_hold_back_moves_the_year_but_keeps_grade_and_records_history(client, db_session, future_years):
    year = await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(student, "hold_back")])

    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["status"] == "held_back"
    await db_session.refresh(student)
    assert (student.grade_level, student.grade_or_class, student.academic_year_id) == (8, "Grade 8-A", year.id)
    row = (await _history(db_session, student))[0]
    assert (row.action, row.from_grade_level, row.to_grade_level, row.from_grade_or_class, row.to_grade_or_class, row.to_academic_year_id) == ("held_back", 8, 8, "Grade 8-A", "Grade 8-A", year.id)


@pytest.mark.asyncio
async def test_an_override_label_wins_over_the_swap(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(student, grade_or_class="Grade 9 (Gold)")])

    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["grade_or_class"] == "Grade 9 (Gold)"
    await db_session.refresh(student)
    assert (student.grade_level, student.grade_or_class) == (9, "Grade 9 (Gold)")


@pytest.mark.asyncio
async def test_an_audit_row_is_written_only_when_something_changed(client, db_session, future_years):
    year = await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    await _promote(client, [_item(student)])
    await _promote(client, [_item(student)])  # already in the active year -> skipped, nothing written

    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.student_promotion", AuditLog.entity_id == str(year.id)))).all()
    assert len(rows) == 1
    assert rows[0].user_id == ctx["coordinator"].id
    assert rows[0].metadata_json == {"academic_year_id": str(year.id), "promoted": 1, "held_back": 0, "failed": 0, "skipped": 0}


@pytest.mark.asyncio
async def test_the_parent_view_shows_the_new_grade_immediately(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)
    assert (await _promote(client, [_item(student)])).status_code == 200

    await _login(client, ctx["parent"].email)
    listing = await client.get("/api/v1/school/students")
    assert listing.status_code == 200, listing.text
    assert [(s["grade_level"], s["grade_or_class"]) for s in listing.json()] == [(9, "Grade 9-A")]
    detail = await client.get(f"/api/v1/school/students/{student.id}")
    assert (detail.json()["grade_level"], detail.json()["grade_or_class"]) == (9, "Grade 9-A")


@pytest.mark.asyncio
async def test_the_dashboard_grade_counts_follow_the_promotion(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session)
    await _login(client, ctx["coordinator"].email)

    def _counts(response):
        return {k["key"]: k["value"] for k in response.json()["school_crm_kpis"]}

    before = _counts(await client.get("/api/v1/school/dashboard"))
    assert (before["grade_8"], before["grade_9"]) == (2, 0)
    await _promote(client, [_item(ctx["students"][0])])
    after = _counts(await client.get("/api/v1/school/dashboard"))
    assert (after["grade_8"], after["grade_9"]) == (1, 1)


# ---------------------------------------------------------------- endpoint: authorization and validation


@pytest.mark.asyncio
async def test_a_coordinator_cannot_promote_students_at_another_school(client, db_session, future_years):
    await future_years()
    school_a = await _school(db_session)
    school_b = await _school(db_session)
    foreign = school_a["students"][0]
    await _login(client, school_b["coordinator"].email)

    response = await _promote(client, [_item(foreign)])

    assert response.status_code == 403
    await db_session.refresh(foreign)
    assert (foreign.grade_level, foreign.grade_or_class, foreign.academic_year_id) == (8, "Grade 8-A", None)
    assert await _history(db_session, foreign) == []


@pytest.mark.asyncio
async def test_one_foreign_student_in_a_mixed_list_rejects_the_whole_request(client, db_session, future_years):
    await future_years()
    school_a = await _school(db_session)
    school_b = await _school(db_session)
    own, foreign = school_b["students"][0], school_a["students"][0]
    await _login(client, school_b["coordinator"].email)

    response = await _promote(client, [_item(own), _item(foreign)])

    assert response.status_code == 403
    await db_session.refresh(own)
    assert (own.grade_level, own.academic_year_id) == (8, None)
    assert await _history(db_session, own) == []


@pytest.mark.asyncio
async def test_an_unknown_student_id_is_indistinguishable_from_a_foreign_one(client, db_session, future_years):
    await future_years()
    school_a = await _school(db_session)
    school_b = await _school(db_session)
    await _login(client, school_b["coordinator"].email)

    foreign = await _promote(client, [_item(school_a["students"][0])])
    unknown = await client.post(URL, json={"items": [{"student_id": str(uuid.uuid4()), "action": "promote"}]})

    assert foreign.status_code == unknown.status_code == 403
    assert foreign.json() == unknown.json()


@pytest.mark.asyncio
async def test_a_rejected_request_never_locks_or_waits_on_another_schools_rows(client, db_session, future_years, monkeypatch):
    """Security (spec §14): the school filter is part of the locking query. If the request first locked every
    listed row and only then checked ownership, naming school A's IDs would make school B's coordinator wait
    on (and briefly hold) school A's rows -- a lock-griefing lever. Here school A's row is locked by someone
    else; B's request must be refused at once (403), not time out on the lock (409)."""
    await future_years()
    school_a = await _school(db_session)
    school_b = await _school(db_session)
    foreign = school_a["students"][0]
    await _login(client, school_b["coordinator"].email)
    monkeypatch.setattr("app.api.schools.PROMOTION_LOCK_TIMEOUT", "200ms")
    await db_session.execute(select(SchoolStudent).where(SchoolStudent.id == foreign.id).with_for_update())
    try:
        response = await _promote(client, [_item(foreign)])
    finally:
        await db_session.rollback()

    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_a_cross_school_attempt_is_audited_as_denied_with_counts_only(client, db_session, future_years):
    await future_years()
    school_a = await _school(db_session)
    school_b = await _school(db_session)
    own, foreign = school_b["students"][0], school_a["students"][0]
    await _login(client, school_b["coordinator"].email)

    response = await _promote(client, [_item(own), _item(foreign)])

    assert response.status_code == 403
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.student_promotion_denied", AuditLog.entity_id == str(school_b["school"].id)))).all()
    assert len(rows) == 1
    assert (rows[0].user_id, rows[0].entity_type, rows[0].outcome) == (school_b["coordinator"].id, "school", "denied")
    assert rows[0].metadata_json == {"requested": 2, "not_in_school": 1}  # counts only: no student IDs or names
    await db_session.refresh(own)
    assert own.grade_level == 8 and await _history(db_session, own) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("role_key", ["principal", "teacher", "parent", "admin"])
async def test_only_a_school_coordinator_may_promote(client, db_session, future_years, role_key):
    await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx[role_key].email)

    response = await _promote(client, [_item(student)])

    assert response.status_code == 403
    await db_session.refresh(student)
    assert (student.grade_level, student.academic_year_id) == (8, None)


@pytest.mark.asyncio
async def test_an_unauthenticated_request_is_401(client, db_session):
    ctx = await _school(db_session)
    response = await _promote(client, [_item(ctx["students"][0])])
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_a_non_coordinator_with_a_malformed_body_gets_403_not_422(client, db_session):
    ctx = await _school(db_session)
    await _login(client, ctx["parent"].email)
    response = await client.post(URL, json={"items": "nope"})
    assert response.status_code == 403


INVALID_PAYLOADS = {
    "missing_items": lambda sid: {},
    "empty_items": lambda sid: {"items": []},
    "over_the_cap": lambda sid: {"items": [{"student_id": str(uuid.uuid4()), "action": "promote"} for _ in range(501)]},
    "duplicate_id": lambda sid: {"items": [{"student_id": sid, "action": "promote"}] * 2},
    "not_a_uuid": lambda sid: {"items": [{"student_id": "not-a-uuid", "action": "promote"}]},
    "unknown_action": lambda sid: {"items": [{"student_id": sid, "action": "graduate"}]},
    "hold_back_with_label": lambda sid: {"items": [{"student_id": sid, "action": "hold_back", "grade_or_class": "Grade 9"}]},
    "blank_label": lambda sid: {"items": [{"student_id": sid, "action": "promote", "grade_or_class": "   "}]},
    "label_too_long": lambda sid: {"items": [{"student_id": sid, "action": "promote", "grade_or_class": "x" * 61}]},
    # Security (spec §14): a NUL byte would otherwise reach PostgreSQL and surface as a 500; a client-supplied
    # school or year is refused loudly, not ignored.
    "nul_in_label": lambda sid: {"items": [{"student_id": sid, "action": "promote", "grade_or_class": "Grade\u0000 9"}]},
    "newline_in_label": lambda sid: {"items": [{"student_id": sid, "action": "promote", "grade_or_class": "Grade\n9"}]},
    "client_supplied_school_id": lambda sid: {"items": [{"student_id": sid, "action": "promote"}], "school_id": str(uuid.uuid4())},
    "client_supplied_year_on_item": lambda sid: {"items": [{"student_id": sid, "action": "promote", "academic_year_id": str(uuid.uuid4())}]},
}


@pytest.mark.asyncio
@pytest.mark.parametrize("case", sorted(INVALID_PAYLOADS))
async def test_invalid_payloads_are_422_and_write_nothing(client, db_session, future_years, case):
    await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    response = await client.post(URL, json=INVALID_PAYLOADS[case](str(student.id)))

    assert response.status_code == 422, response.text
    assert isinstance(response.json()["detail"], list)
    await db_session.refresh(student)
    assert (student.grade_level, student.academic_year_id) == (8, None)


@pytest.mark.asyncio
async def test_no_active_academic_year_is_409(client, db_session, monkeypatch):
    async def _no_active_year(db):
        return None

    monkeypatch.setattr("app.api.schools._current_academic_year_id", _no_active_year)
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(student)])

    assert response.status_code == 409
    assert "active academic year" in response.json()["detail"]
    await db_session.refresh(student)
    assert student.grade_level == 8


# ---------------------------------------------------------------- endpoint: per-row outcomes


@pytest.mark.asyncio
async def test_a_top_grade_student_fails_alone_and_the_rest_commit(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session, students=(("Grade 12", 12), ("Grade 8-A", 8)))
    top, other = ctx["students"]
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(top), _item(other)])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"] == {"promoted": 1, "held_back": 0, "failed": 1, "skipped": 0}
    assert (body["results"][0]["status"], body["results"][0]["reason"]) == ("failed", "terminal_grade")
    assert body["results"][0]["message"]
    await db_session.refresh(top)
    await db_session.refresh(other)
    assert (top.grade_level, top.academic_year_id) == (12, None)
    assert await _history(db_session, top) == []
    assert (other.grade_level, other.grade_or_class) == (9, "Grade 9-A")


@pytest.mark.asyncio
async def test_a_student_without_a_grade_level_fails_with_grade_level_not_set(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session, students=(("Grade 8", None),))
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(ctx["students"][0])])

    assert response.status_code == 200, response.text
    assert (response.json()["results"][0]["status"], response.json()["results"][0]["reason"]) == ("failed", "grade_level_not_set")


@pytest.mark.asyncio
async def test_an_unswappable_label_fails_then_succeeds_with_an_override(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session, students=(("8A", 8),))
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    first = await _promote(client, [_item(student)])
    assert (first.json()["results"][0]["status"], first.json()["results"][0]["reason"]) == ("failed", "label_unparseable")
    await db_session.refresh(student)
    assert (student.grade_level, student.grade_or_class) == (8, "8A")

    second = await _promote(client, [_item(student, grade_or_class="Grade 9A")])
    assert second.json()["results"][0]["status"] == "promoted"
    await db_session.refresh(student)
    assert (student.grade_level, student.grade_or_class) == (9, "Grade 9A")


@pytest.mark.asyncio
async def test_a_label_that_disagrees_with_grade_level_fails(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session, students=(("Grade 8-A", 9),))
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(ctx["students"][0])])

    assert (response.json()["results"][0]["status"], response.json()["results"][0]["reason"]) == ("failed", "label_unparseable")
    assert "does not match" in response.json()["results"][0]["message"]


@pytest.mark.asyncio
async def test_a_swapped_label_over_60_characters_fails_only_its_own_row(client, db_session, future_years):
    await future_years()
    long_label = "Grade 9 " + "x" * 52  # 60 characters; "9" -> "10" would make it 61
    ctx = await _school(db_session, students=((long_label, 9), ("Grade 8-A", 8)))
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(s) for s in ctx["students"]])

    assert response.status_code == 200, response.text
    results = response.json()["results"]
    assert (results[0]["status"], results[0]["reason"]) == ("failed", "label_unparseable")
    assert "60 characters" in results[0]["message"]
    assert results[1]["status"] == "promoted"


@pytest.mark.asyncio
async def test_repeating_a_request_never_promotes_twice(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    first = await _promote(client, [_item(student)])
    second = await _promote(client, [_item(student)])

    assert first.json()["results"][0]["status"] == "promoted"
    assert (second.json()["results"][0]["status"], second.json()["results"][0]["reason"]) == ("skipped", "already_in_active_year")
    assert (second.json()["results"][0]["grade_level"], second.json()["results"][0]["grade_or_class"]) == (9, "Grade 9-A")
    await db_session.refresh(student)
    assert student.grade_level == 9
    assert len(await _history(db_session, student)) == 1


@pytest.mark.asyncio
async def test_a_student_created_in_the_active_year_is_skipped(client, db_session, future_years):
    year = await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    student.academic_year_id = year.id
    await db_session.commit()
    await _login(client, ctx["coordinator"].email)

    response = await _promote(client, [_item(student)])

    assert (response.json()["results"][0]["status"], response.json()["results"][0]["reason"]) == ("skipped", "already_in_active_year")
    assert await _history(db_session, student) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest -q tests/test_enh_004_student_promotion.py -k "not shared_database and not migration_0033" -x -q`
Expected: the first endpoint test fails with `assert 405 == 200` (the route does not exist yet; `POST /students/promotions` matches the path of the existing `GET /students/{student_id}` route, so Starlette answers 405 Method Not Allowed; a `404` is also acceptable evidence).

- [ ] **Step 3: Implement the route**

In `apps/api/app/api/schools.py`:

(a) Change the SQLAlchemy imports so they read:

```python
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
```

(b) In the `from app.models import (...)` list, add `SchoolStudentGradeHistory,` immediately after `SchoolStudent,`.

(c) Immediately after the `from app.models import (...)` block and before `from app.services.integrations import send_notification`, add:

```python
from app.schemas import StudentPromotionRequest, StudentPromotionResponse
```

(d) Insert this block immediately after the `link_parent` function (which ends with `return {"id": link.id, "parent_user_id": parent.id, "school_student_id": student.id}`) and before `@router.get("/activities")`:

```python
# Bounded wait for the row locks a promotion takes (ENH-004 spec §5.2). A module constant, read at
# call time so a test can shorten it; it is interpolated into SET LOCAL below and is never request input.
PROMOTION_LOCK_TIMEOUT = "5s"


async def _require_coordinator_user(user: User = Depends(get_current_user)) -> User:
    """Dependency form of `_require_coordinator`. FastAPI resolves dependencies before it validates
    the request body, so a non-coordinator gets 403 before any 422 (spec §5.2 check order)."""
    _require_coordinator(user)
    return user


@router.post("/students/promotions", response_model=StudentPromotionResponse)
async def promote_students(payload: StudentPromotionRequest, user: User = Depends(_require_coordinator_user), db: AsyncSession = Depends(get_db)):
    """ENH-004 -- promote (grade + 1) or hold back (same grade) students into the ACTIVE academic
    year, one transaction per request. The school always comes from the caller's own profile. Every
    listed student is row-locked in id order; an unknown or other-school ID rejects the whole request
    with one generic 403 (nothing written). Business-rule failures are per-row results in a 200 body
    and never block the valid rows. A student already in the active year is skipped, which is what
    makes a retry or a concurrent duplicate safe (backed by UNIQUE (student, target year))."""
    school_id = _own_school_id(user)
    student_ids = [item.student_id for item in payload.items]
    # `set_config(..., true)` is SET LOCAL with a bound parameter, so no SQL is built from a string.
    await db.execute(text("SELECT set_config('lock_timeout', :timeout, true)"), {"timeout": PROMOTION_LOCK_TIMEOUT})
    # The school filter is part of the locking query itself, so another school's rows are never locked (or even
    # read) by this request. `school_id` never changes after creation (DATA_MODEL.md §6.11), so there is no
    # check/use gap. An unknown ID and another school's ID are the same absence here, which is what makes them
    # indistinguishable to the caller.
    locked = (await db.scalars(select(SchoolStudent).where(SchoolStudent.id.in_(student_ids), SchoolStudent.school_id == school_id).order_by(SchoolStudent.id).with_for_update())).all()
    students = {s.id: s for s in locked}
    if len(students) != len(student_ids):
        # A security-relevant event (probing, or a stale/misdirected client): record it, then refuse. Nothing else has
        # been written yet, and the audit row carries counts only (no student IDs or names).
        db.add(AuditLog(user_id=user.id, action="school.student_promotion_denied", entity_type="school", entity_id=str(school_id), outcome="denied", metadata_json={"requested": len(student_ids), "not_in_school": len(student_ids) - len(students)}))
        await db.commit()
        raise HTTPException(403, "One or more students are not at your institution")
    active_year_id = await _current_academic_year_id(db)
    active_year = await db.get(AcademicYear, active_year_id) if active_year_id else None
    if active_year is None:
        raise HTTPException(409, "No active academic year. Ask an Overseas Admin to activate one.")

    counts = {"promoted": 0, "held_back": 0, "failed": 0, "skipped": 0}
    results: list[dict] = []
    history: list[SchoolStudentGradeHistory] = []
    for item in payload.items:
        student = students[item.student_id]
        decision = _decide_promotion(
            action=item.action, student_year_id=student.academic_year_id, active_year_id=active_year.id,
            grade_level=student.grade_level, grade_or_class=student.grade_or_class, override=item.grade_or_class,
        )
        if decision.status in ("promoted", "held_back"):
            history.append(
                SchoolStudentGradeHistory(
                    school_student_id=student.id, action=decision.status,
                    from_academic_year_id=student.academic_year_id, from_grade_level=student.grade_level, from_grade_or_class=student.grade_or_class,
                    to_academic_year_id=active_year.id, to_grade_level=decision.grade_level, to_grade_or_class=decision.grade_or_class,
                    performed_by_user_id=user.id,
                )
            )
            student.academic_year_id = active_year.id
            student.grade_level = decision.grade_level
            student.grade_or_class = decision.grade_or_class
        counts[decision.status] += 1
        results.append({"student_id": student.id, "status": decision.status, "reason": decision.reason, "message": decision.message, "grade_level": decision.grade_level, "grade_or_class": decision.grade_or_class})

    if history:
        db.add_all(history)
        db.add(AuditLog(user_id=user.id, action="school.student_promotion", entity_type="academic_year", entity_id=str(active_year.id), metadata_json={"academic_year_id": str(active_year.id), **counts}))
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(409, "A concurrent promotion was detected; reload and retry") from exc
    return {"academic_year": {"id": active_year.id, "label": active_year.label}, "counts": counts, "results": results}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest -q tests/test_enh_004_student_promotion.py -k "not shared_database and not migration_0033"`
Expected: all pass (unit tests plus about 35 endpoint tests).
If `test_the_dashboard_grade_counts_follow_the_promotion` fails on `KeyError: 'school_crm_kpis'`, read `test_enh_001_academic_year.py:593-596` (it uses the same key) and fix the test's key, not the endpoint.

- [ ] **Step 5: Lint and type-check**

Run: `python -m ruff check app tests/test_enh_004_student_promotion.py --fix; python -m ruff check .; python -m mypy app`
Expected: clean. (`--fix` only re-sorts the test imports if needed.)

- [ ] **Step 6: Confirm existing behavior is untouched**

Run: `python -m pytest -q tests/test_enh_001_academic_year.py tests/test_sch_002_bulk_roster_upload.py tests/test_sch_roster_parent_invite.py`
Expected: all pass, same counts as before this task.

- [ ] **Step 7: Commit**

```powershell
git add apps/api/app/api/schools.py apps/api/tests/test_enh_004_student_promotion.py
git commit -m "feat(enh-004): add POST /school/students/promotions" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3b: Close the tenant-escalation path in `PATCH /auth/me` (**needs the user's approval first**)

**Why this is in ENH-004:** every school authorization check (`_own_school_id`, `_require_coordinator`) trusts `user.profile["school_id"]`, and `PATCH /auth/me` (`auth.py:143`) merges an **unrestricted** client-supplied `profile` dict into `user.profile`. Any coordinator can therefore send `{"profile": {"school_id": "<another school's id>"}}` and then read, edit and **promote** that school's students. ENH-004's first security acceptance criterion ("a coordinator cannot promote students at a school outside their own institution (403)") is not true while this holds, whatever the promotion endpoint does. See spec §14, finding S1.

**This task changes authentication/profile logic, which the security review lists as "ask first".** Step 0 is the gate.

**Files:**
- Modify: `apps/api/app/api/auth.py` (the `update_me` function, currently lines 143-155)
- Modify: `apps/api/tests/test_enh_004_student_promotion.py`

**Interfaces:**
- Consumes: Task 3's test helpers (`_school`, `_user`, `_login`, `_promote`, `_item`, `future_years`, `PASSWORD`).
- Produces: `SERVER_OWNED_PROFILE_KEYS = ("school_id",)` in `auth.py`; `PATCH /auth/me` answers `403` (detail `"school_id cannot be changed here"`) when the body's `profile.school_id` differs from the user's current value, applies no other change from that request, and writes an `AuditLog` row `profile.update_denied` (`outcome="denied"`, metadata `{"field": "school_id"}`). Echoing the *unchanged* value back is accepted (the web "Update profile" form sends the whole profile, `WorkflowPanel.tsx:254`).

**Deliberately not changed:** other profile keys, notably `university_id` (the same bypass class for university reps, `workflows.py:158,1824`, `inbound.py:138`, `portal.py:929`) — that belongs to UNI-001 and is reported to the user as a separate finding, not silently widened here. The admin route `PATCH /admin/users/{id}` (which legitimately sets `profile`) is untouched.

- [ ] **Step 0: Get approval**

Tell the user, in plain words: "Any logged-in user can currently change their own `profile.school_id` via `PATCH /auth/me`, which defeats every school scope check including ENH-004's. The fix makes `school_id` read-only through that route (an unchanged echo is still accepted) and audits attempts. It changes profile-update logic. May I make it in this branch?" Wait for a yes. If the user declines or wants it done separately, skip this task, keep the rest of the plan, and record the exposure in the final report and in `DEC-SCOPE-020`'s `NEEDS_CONFIRMATION` list.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/test_enh_004_student_promotion.py`:

```python


# ---------------------------------------------------------------- tenant escalation via PATCH /auth/me (spec §14, S1)


async def _patch_profile(client, body: dict):
    return await client.patch("/api/v1/auth/me", json=body)


@pytest.mark.asyncio
async def test_a_coordinator_cannot_re_point_their_own_school_via_profile_update(client, db_session, future_years):
    await future_years()
    school_a = await _school(db_session)
    school_b = await _school(db_session)
    victim = school_b["students"][0]
    await _login(client, school_a["coordinator"].email)

    response = await _patch_profile(client, {"profile": {"school_id": str(school_b["school"].id)}})

    assert response.status_code == 403, response.text
    await db_session.refresh(school_a["coordinator"])
    assert school_a["coordinator"].profile["school_id"] == str(school_a["school"].id)
    # The boundary this protects still holds: nothing of school B is reachable.
    assert (await _promote(client, [_item(victim)])).status_code == 403
    listing = await client.get("/api/v1/school/students")
    assert {s["id"] for s in listing.json()} == {str(s.id) for s in school_a["students"]}
    denied = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "profile.update_denied", AuditLog.user_id == school_a["coordinator"].id))).all()
    assert len(denied) == 1
    assert (denied[0].outcome, denied[0].metadata_json) == ("denied", {"field": "school_id"})


@pytest.mark.asyncio
async def test_a_refused_profile_update_applies_no_partial_change(client, db_session):
    school_a = await _school(db_session)
    school_b = await _school(db_session)
    await _login(client, school_a["coordinator"].email)

    response = await _patch_profile(client, {"full_name": "Renamed Coordinator", "profile": {"school_id": str(school_b["school"].id)}})

    assert response.status_code == 403, response.text
    await db_session.refresh(school_a["coordinator"])
    assert school_a["coordinator"].full_name == "Coordinator"


@pytest.mark.asyncio
async def test_a_user_with_no_school_cannot_acquire_one_via_profile_update(client, db_session):
    school = await _school(db_session)
    outsider = await _user(db_session, role="overseas_student", full_name="Outsider")
    await db_session.commit()
    await _login(client, outsider.email)

    response = await _patch_profile(client, {"profile": {"school_id": str(school["school"].id)}})

    assert response.status_code == 403, response.text
    await db_session.refresh(outsider)
    assert "school_id" not in (outsider.profile or {})


@pytest.mark.asyncio
async def test_a_profile_update_that_echoes_the_unchanged_school_id_still_works(client, db_session):
    ctx = await _school(db_session)
    await _login(client, ctx["coordinator"].email)

    response = await _patch_profile(client, {"profile": {"school_id": str(ctx["school"].id), "education": "B.Ed"}})

    assert response.status_code == 200, response.text
    profile = response.json()["profile"]
    assert profile["school_id"] == str(ctx["school"].id)
    assert profile["education"] == "B.Ed"
```

- [ ] **Step 2: Run the tests to verify the exploit is real**

Run (from `apps/api`): `python -m pytest -q tests/test_enh_004_student_promotion.py -k "profile_update"`
Expected: `test_a_coordinator_cannot_re_point_their_own_school_via_profile_update`, `test_a_refused_profile_update_applies_no_partial_change` and `test_a_user_with_no_school_cannot_acquire_one_via_profile_update` FAIL with `assert 200 == 403` (the bypass succeeds today); the echo test passes. **Report the three failures to the user as confirmation of the finding before continuing.**

- [ ] **Step 3: Implement the fix**

In `apps/api/app/api/auth.py`, replace:

```python
@router.patch("/me", response_model=UserOut)
async def update_me(payload: ProfileUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    changes = payload.model_dump(exclude_unset=True)
    if "full_name" in changes:
```

with:

```python
# Profile keys that carry an authorization scope. A user may echo their own current value back (the web
# "Update profile" form sends the whole profile) but may never change it: only an admin route sets these.
SERVER_OWNED_PROFILE_KEYS = ("school_id",)


@router.patch("/me", response_model=UserOut)
async def update_me(payload: ProfileUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    changes = payload.model_dump(exclude_unset=True)
    # Checked before anything is mutated: the audit commit below would otherwise also persist an
    # already-assigned full_name/phone from a request that is being refused.
    incoming = changes.get("profile") or {}
    current = user.profile or {}
    for key in SERVER_OWNED_PROFILE_KEYS:
        if key in incoming and incoming[key] != current.get(key):
            db.add(AuditLog(user_id=user.id, action="profile.update_denied", entity_type="user", entity_id=str(user.id), outcome="denied", metadata_json={"field": key}))
            await db.commit()
            raise HTTPException(403, f"{key} cannot be changed here")
    if "full_name" in changes:
```

- [ ] **Step 4: Run the tests, and the existing profile tests**

Run: `python -m pytest -q tests/test_enh_004_student_promotion.py -k "profile_update"; python -m pytest -q tests/test_stu_011_profile_documents.py tests/test_role_assignments.py`
Expected: all pass (the existing tests PATCH `profile.skills`, which is untouched).

- [ ] **Step 5: Document, lint, commit**

Run (Grep tool): search `docs/architecture/API_CONTRACT.md` for `PATCH /auth/me`. If a row exists, append this sentence to it: `**Addendum, 2026-09-19 (ENH-004 security review):** \`profile.school_id\` is server-owned: a request that changes it is 403 (\`school_id cannot be changed here\`) and audited as \`profile.update_denied\`; echoing the unchanged value is accepted.` If no row exists, add nothing (do not invent a contract entry).
Run: `python -m ruff check .; python -m mypy app`
Expected: clean.

```powershell
git add apps/api/app/api/auth.py apps/api/tests/test_enh_004_student_promotion.py docs/architecture/API_CONTRACT.md
git commit -m "fix(auth): make profile.school_id read-only via PATCH /auth/me" -m "Any user could re-point their own school scope, defeating every school authorization check including ENH-004's. An unchanged echo is still accepted; attempts are audited as profile.update_denied." -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 4: Concurrency and bounded lock wait

**Files:**
- Modify: `apps/api/app/api/schools.py` (the `locked = ...` statement in `promote_students`)
- Modify: `apps/api/tests/test_enh_004_student_promotion.py`

**Interfaces:**
- Consumes: Task 3's route, `PROMOTION_LOCK_TIMEOUT`, and the test helpers.
- Produces: `409` with detail `"Another promotion is in progress; retry"` when the row locks cannot be taken within `PROMOTION_LOCK_TIMEOUT`.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/test_enh_004_student_promotion.py`:

```python


# ---------------------------------------------------------------- concurrency


@pytest.mark.asyncio
async def test_two_concurrent_identical_requests_promote_each_student_once(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)

    first, second = await asyncio.gather(_promote(client, [_item(student)]), _promote(client, [_item(student)]))

    assert first.status_code == second.status_code == 200, (first.text, second.text)
    assert sorted(r.json()["results"][0]["status"] for r in (first, second)) == ["promoted", "skipped"]
    await db_session.refresh(student)
    assert student.grade_level == 9
    assert len(await _history(db_session, student)) == 1


@pytest.mark.asyncio
async def test_a_request_that_cannot_get_the_row_locks_in_time_returns_409(client, db_session, future_years, monkeypatch):
    await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)
    monkeypatch.setattr("app.api.schools.PROMOTION_LOCK_TIMEOUT", "200ms")
    # Hold the row lock in the test's own session, exactly as a slower concurrent promotion would.
    await db_session.execute(select(SchoolStudent).where(SchoolStudent.id == student.id).with_for_update())
    try:
        response = await _promote(client, [_item(student)])
    finally:
        await db_session.rollback()

    assert response.status_code == 409
    assert "in progress" in response.json()["detail"]
    await db_session.refresh(student)
    assert student.grade_level == 8
```

- [ ] **Step 2: Run the tests to verify the lock test fails**

Run: `python -m pytest -q tests/test_enh_004_student_promotion.py -k "concurrent or row_locks"`
Expected: the concurrent test passes already (Task 3's `FOR UPDATE` serializes); `test_a_request_that_cannot_get_the_row_locks_in_time_returns_409` FAILS with a raised `sqlalchemy.exc.DBAPIError` / `LockNotAvailableError` (the lock timeout fires but is not mapped yet).

- [ ] **Step 3: Map the lock timeout to 409**

In `apps/api/app/api/schools.py`, add `DBAPIError` to the exception import:

```python
from sqlalchemy.exc import DBAPIError, IntegrityError
```

In `promote_students`, replace this line:

```python
    locked = (await db.scalars(select(SchoolStudent).where(SchoolStudent.id.in_(student_ids), SchoolStudent.school_id == school_id).order_by(SchoolStudent.id).with_for_update())).all()
```

with:

```python
    try:
        locked = (await db.scalars(select(SchoolStudent).where(SchoolStudent.id.in_(student_ids), SchoolStudent.school_id == school_id).order_by(SchoolStudent.id).with_for_update())).all()
    except DBAPIError as exc:
        await db.rollback()
        if getattr(exc.orig, "sqlstate", None) == "55P03":  # lock_not_available: the wait exceeded PROMOTION_LOCK_TIMEOUT
            raise HTTPException(409, "Another promotion is in progress; retry") from exc
        raise
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest -q tests/test_enh_004_student_promotion.py -k "concurrent or row_locks"`
Expected: `2 passed`.
If the lock test still errors, print `exc.orig.__dict__` in a scratch run to find the attribute that carries `55P03` (`sqlstate` or `pgcode`) and use that; do not weaken the assertion.

- [ ] **Step 5: Mutation check — prove the lock test is meaningful**

Temporarily delete `.with_for_update()` from the `locked = ...` query, then run:
`python -m pytest -q tests/test_enh_004_student_promotion.py -k "concurrent or row_locks"`
Expected: **both FAIL** (the concurrent pair can both read the old year, so one gets the unique-constraint `409`; the lock-timeout test no longer blocks). Restore `.with_for_update()` and re-run: `2 passed`. Confirm with `git diff apps/api/app/api/schools.py` that the restored line matches Step 3.

- [ ] **Step 6: Lint, type-check, commit**

Run: `python -m ruff check .; python -m mypy app`
Expected: clean.

```powershell
git add apps/api/app/api/schools.py apps/api/tests/test_enh_004_student_promotion.py
git commit -m "feat(enh-004): bound the promotion lock wait and cover concurrent requests" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: The grade-history read endpoint

**Files:**
- Modify: `apps/api/app/schemas.py` (append)
- Modify: `apps/api/app/api/schools.py` (imports; add the route immediately after `student_timeline`, before `@router.post("/students", status_code=201)`)
- Modify: `apps/api/tests/test_enh_004_student_promotion.py`

**Interfaces:**
- Consumes: `_load_readable_student` (existing), `SchoolStudentGradeHistory`, test helpers.
- Produces: `GET /school/students/{student_id}/grade-history` returning `{"student": {"id", "full_name"}, "history": [{"id", "action", "from": {"academic_year_id", "academic_year_label", "grade_level", "grade_or_class"}, "to": {...same...}, "created_at"}]}`, newest first. No performer field.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/tests/test_enh_004_student_promotion.py`:

```python


# ---------------------------------------------------------------- grade-history read endpoint


def _history_url(student) -> str:
    return f"/api/v1/school/students/{student.id}/grade-history"


@pytest.mark.asyncio
async def test_grade_history_lists_transitions_newest_first_with_year_labels(client, db_session, future_years):
    year_one = await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)
    first = await _promote(client, [_item(student)])
    assert first.json()["academic_year"]["id"] == str(year_one.id)
    # A later-dated year is created and becomes "the" active year: the rollover to the next year.
    year_two = await future_years(date(9999, 5, 1))
    second = await _promote(client, [_item(student)])
    assert second.json()["academic_year"]["id"] == str(year_two.id)
    assert second.json()["results"][0]["status"] == "promoted"

    response = await client.get(_history_url(student))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["student"] == {"id": str(student.id), "full_name": "Child 0"}
    history = body["history"]
    assert [(h["action"], h["from"]["grade_level"], h["to"]["grade_level"]) for h in history] == [("promoted", 9, 10), ("promoted", 8, 9)]
    assert (history[0]["from"]["academic_year_label"], history[0]["to"]["academic_year_label"]) == (year_one.label, year_two.label)
    assert (history[1]["from"]["academic_year_id"], history[1]["from"]["academic_year_label"]) == (None, None)
    assert history[1]["to"]["academic_year_label"] == year_one.label
    assert (history[0]["to"]["grade_or_class"], history[1]["from"]["grade_or_class"]) == ("Grade 10-A", "Grade 8-A")
    assert "performed_by_user_id" not in history[0] and "performed_by" not in history[0]


@pytest.mark.asyncio
async def test_a_never_promoted_student_has_an_empty_history(client, db_session):
    ctx = await _school(db_session)
    await _login(client, ctx["coordinator"].email)
    response = await client.get(_history_url(ctx["students"][1]))
    assert response.status_code == 200, response.text
    assert response.json()["history"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role_key,student_index,expected",
    [
        ("coordinator", 0, 200), ("coordinator", 1, 200),
        ("principal", 1, 200),
        ("teacher", 0, 200), ("teacher", 1, 403),  # the teacher is assigned to students[0] only
        ("parent", 0, 200), ("parent", 1, 403),  # the parent is linked to students[0] only
    ],
)
async def test_grade_history_follows_the_existing_student_read_scope(client, db_session, role_key, student_index, expected):
    ctx = await _school(db_session)
    await _login(client, ctx[role_key].email)
    response = await client.get(_history_url(ctx["students"][student_index]))
    assert response.status_code == expected, response.text


@pytest.mark.asyncio
async def test_grade_history_of_another_school_is_403_and_unknown_is_404(client, db_session):
    school_a = await _school(db_session)
    school_b = await _school(db_session)
    await _login(client, school_b["coordinator"].email)
    assert (await client.get(_history_url(school_a["students"][0]))).status_code == 403
    assert (await client.get(f"/api/v1/school/students/{uuid.uuid4()}/grade-history")).status_code == 404


@pytest.mark.asyncio
async def test_grade_history_requires_a_session(client, db_session):
    ctx = await _school(db_session)
    assert (await client.get(_history_url(ctx["students"][0]))).status_code == 401
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest -q tests/test_enh_004_student_promotion.py -k "grade_history"`
Expected: FAIL — responses are `404`/`405` for the missing route (e.g. `assert 404 == 200`).

- [ ] **Step 3: Add the response models**

Append to `apps/api/app/schemas.py`:

```python


class GradeHistoryState(BaseModel):
    academic_year_id: UUID | None = None
    academic_year_label: str | None = None
    grade_level: int | None = None
    grade_or_class: str | None = None


class GradeHistoryEntry(BaseModel):
    model_config = {"populate_by_name": True}
    id: UUID
    action: Literal["promoted", "held_back"]
    from_: GradeHistoryState = Field(alias="from")
    to: GradeHistoryState
    created_at: datetime


class GradeHistoryStudent(BaseModel):
    id: UUID
    full_name: str


class GradeHistoryResponse(BaseModel):
    student: GradeHistoryStudent
    history: list[GradeHistoryEntry]
```

- [ ] **Step 4: Add the route**

In `apps/api/app/api/schools.py`:

(a) Update the schemas import added in Task 3 to:

```python
from app.schemas import GradeHistoryResponse, StudentPromotionRequest, StudentPromotionResponse
```

(b) Add the ORM import next to the other SQLAlchemy imports:

```python
from sqlalchemy.orm import aliased
```

(c) Insert after the `student_timeline` function (its last line is `return {"student": {"id": student.id, "full_name": student.full_name}, "events": events}`) and before `@router.post("/students", status_code=201)`:

```python
@router.get("/students/{student_id}/grade-history", response_model=GradeHistoryResponse)
async def student_grade_history(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ENH-004 -- one student's grade/academic-year transitions, newest first. The same own-scope
    loader as the overview and timeline (own institution; assigned-only for a Teacher; own-child-only
    for a Parent). Bounded by one row per academic year per student, so it is not paginated. The
    performer is stored but deliberately not returned, so a Parent never receives a staff user ID."""
    student = await _load_readable_student(db, user, student_id)
    from_year = aliased(AcademicYear)
    to_year = aliased(AcademicYear)
    rows = (
        await db.execute(
            select(SchoolStudentGradeHistory, from_year, to_year)
            .outerjoin(from_year, from_year.id == SchoolStudentGradeHistory.from_academic_year_id)
            .join(to_year, to_year.id == SchoolStudentGradeHistory.to_academic_year_id)
            .where(SchoolStudentGradeHistory.school_student_id == student.id)
            .order_by(SchoolStudentGradeHistory.created_at.desc(), SchoolStudentGradeHistory.id.desc())
        )
    ).all()
    return {
        "student": {"id": student.id, "full_name": student.full_name},
        "history": [
            {
                "id": h.id, "action": h.action, "created_at": h.created_at,
                "from": {"academic_year_id": h.from_academic_year_id, "academic_year_label": from_y.label if from_y else None, "grade_level": h.from_grade_level, "grade_or_class": h.from_grade_or_class},
                "to": {"academic_year_id": h.to_academic_year_id, "academic_year_label": to_y.label, "grade_level": h.to_grade_level, "grade_or_class": h.to_grade_or_class},
            }
            for h, from_y, to_y in rows
        ],
    }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest -q tests/test_enh_004_student_promotion.py -k "grade_history"`
Expected: all pass (about 12).

- [ ] **Step 6: Lint, type-check, commit**

Run: `python -m ruff check .; python -m mypy app`
Expected: clean.

```powershell
git add apps/api/app/schemas.py apps/api/app/api/schools.py apps/api/tests/test_enh_004_student_promotion.py
git commit -m "feat(enh-004): add GET /school/students/{id}/grade-history" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 6: Keep the timeline's "profile created" detail truthful

**Files:**
- Modify: `apps/api/app/api/schools.py` (`student_timeline`, the `events` initializer)
- Modify: `apps/api/tests/test_enh_004_student_promotion.py`

**Interfaces:**
- Consumes: `SchoolStudentGradeHistory`, existing `student_timeline`.
- Produces: unchanged response shape; the `profile_created` event's `detail` uses the earliest history row's `from_grade_or_class` when the student has history, otherwise `student.grade_or_class` exactly as today.

- [ ] **Step 1: Write the failing test**

Append to `apps/api/tests/test_enh_004_student_promotion.py`:

```python


# ---------------------------------------------------------------- SCH-008 timeline stays truthful


@pytest.mark.asyncio
async def test_the_timeline_profile_event_keeps_the_pre_promotion_label(client, db_session, future_years):
    await future_years()
    ctx = await _school(db_session)
    student = ctx["students"][0]
    await _login(client, ctx["coordinator"].email)
    assert (await _promote(client, [_item(student)])).status_code == 200

    await _login(client, ctx["parent"].email)
    response = await client.get(f"/api/v1/school/students/{student.id}/timeline")

    assert response.status_code == 200, response.text
    events = response.json()["events"]
    assert (events[0]["type"], events[0]["detail"]) == ("profile_created", "Added to Grade 8-A")
    assert len(events) == 1  # promotion adds no timeline events (spec non-goal)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest -q tests/test_enh_004_student_promotion.py -k "timeline_profile_event"`
Expected: FAIL — `assert 'Added to Grade 9-A' == 'Added to Grade 8-A'`.

- [ ] **Step 3: Implement the fix**

In `apps/api/app/api/schools.py`, in `student_timeline`, replace:

```python
    events: list[dict] = [{
        "date": student.created_at, "category": "profile", "type": "profile_created",
        "title": "Student profile created", "detail": f"Added to {student.grade_or_class}" if student.grade_or_class else None,
    }]
```

with:

```python
    # ENH-004: once a student has been promoted, `grade_or_class` is no longer where they were added.
    # The earliest history row's `from_grade_or_class` is; with no history the current label is still right.
    first_move = await db.scalar(
        select(SchoolStudentGradeHistory).where(SchoolStudentGradeHistory.school_student_id == student.id).order_by(SchoolStudentGradeHistory.created_at.asc(), SchoolStudentGradeHistory.id.asc()).limit(1)
    )
    added_to = first_move.from_grade_or_class if first_move else student.grade_or_class
    events: list[dict] = [{
        "date": student.created_at, "category": "profile", "type": "profile_created",
        "title": "Student profile created", "detail": f"Added to {added_to}" if added_to else None,
    }]
```

- [ ] **Step 4: Run the new test and the existing timeline suite**

Run: `python -m pytest -q tests/test_enh_004_student_promotion.py -k "timeline_profile_event"; python -m pytest -q tests/test_sch_008_student_timeline.py`
Expected: `1 passed`, then every existing SCH-008 test passes (in particular `test_a_new_students_timeline_has_only_the_profile_created_event`, which asserts `"Added to Grade 8"` for a never-promoted student).

- [ ] **Step 5: Lint, type-check, commit**

Run: `python -m ruff check .; python -m mypy app`
Expected: clean.

```powershell
git add apps/api/app/api/schools.py apps/api/tests/test_enh_004_student_promotion.py
git commit -m "fix(enh-004): timeline profile event reports the pre-promotion label" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 7: Backend regression gate

**Files:** none modified unless a check fails.

- [ ] **Step 1: Run the ENH-004 file and the affected suites (targeted, not the full suite)**

Run (from `apps/api`):
`python -m pytest -q tests/test_enh_004_student_promotion.py tests/test_enh_001_academic_year.py tests/test_sch_001_school_portal_access.py tests/test_sch_002_bulk_roster_upload.py tests/test_sch_007_parent_portal.py tests/test_sch_008_student_timeline.py tests/test_sch_reports.py tests/test_sch_roster_parent_invite.py`
Expected: all pass. Compare against the pre-branch baseline if anything fails: run the same files on `main` before deciding a failure is caused by this work (AGENTS.md notes known shared-database flakiness; re-run a single failing file alone first).

- [ ] **Step 2: Full backend quality gates**

Run: `python -m ruff check .; python -m mypy app`
Expected: `All checks passed!`, `Success: no issues found`.

- [ ] **Step 3: Confirm nothing outside the plan changed**

Run: `git diff --stat main -- apps/api`
Expected: only `models.py`, `schemas.py`, `api/schools.py`, `alembic/versions/0033_student_grade_history.py`, `tests/test_enh_004_student_promotion.py`. If any other file appears, revert it.

(No commit: nothing changed.)

---

## Task 8: The promotion screen

Design constraints for this task come from `docs/ux/RESPONSIVE_RULES.md` (confirmed requirement `NFR-RESP-001`: a data table becomes a stacked card list on mobile, never a horizontally scrolling table as the only option; no layout shift; the primary action stays reachable) and `docs/ux/ACCESSIBILITY_RULES.md` (keyboard operable, visible focus, real labels, errors identified in text and tied to the field, a keyboard-reachable confirmation for a high-consequence action). Spec §7.1 records the resulting decisions.

**Files:**
- Create: `apps/web/components/SchoolPromotionRow.tsx` (presentational: one student)
- Create: `apps/web/components/SchoolPromotionPanel.tsx` (container: state, filter, confirm step, submit)
- Create: `apps/web/components/SchoolPromotionPanel.module.css` (the only new CSS; precedent: `ProgramCatalogue.module.css`)
- Create: `apps/web/app/school/coordinator/promotion/page.tsx`
- Modify: `apps/web/lib/navigation.ts:37`
- Create: `apps/web/tests/e2e/enh-004-student-promotion.spec.ts`

**Reuse, not rebuilt:** `PortalShell`, `.card`, `.btn` (+`.ghost`), `.status` (+`.error`/`.pending`), `.field`, `.select`, `.search`, `.table-controls`, `.empty`, `.form-error`/`.form-message` (as `SchoolStudentsPanel` uses them), the inline two-step confirm pattern from `AdminUserManagementPanel`/`AdminProgramManagementPanel` (no `window.confirm`), and the "Showing X of Y" `aria-live` pattern from `DataTable`. `DataTable` itself is not reusable here: it renders plain values only and cannot host per-row controls.

**Deliberately not done:** no `loading.tsx` (no route in the app has one, and there is no shared `school/layout.tsx`, so it would render without the portal shell); no optimistic update (promotion is server-authoritative and rows can fail, so the UI shows the server's per-row result the moment it returns, then reconciles with `router.refresh()`); no new dependency (no axe-core).

**Interfaces:**
- Consumes: Task 3's `POST /api/v1/school/students/promotions` (request `{items:[{student_id, action, grade_or_class?}]}`; response `{academic_year:{id,label}, counts, results:[{student_id,status,reason,message,grade_level,grade_or_class}]}`), existing `GET /api/v1/school/students` and `GET /api/v1/school/academic-years/active` (returns `null` when none).
- Produces: route `/school/coordinator/promotion`. Accessible names the e2e relies on: filter `#promotion-filter` (label "Grade level"); select-all checkbox (label "Select all shown"); per-student checkbox whose label text contains the student's full name; per-row selects/inputs labelled "Action" and "New label (optional)"; buttons "Review changes (N)", "Confirm promotion", "Cancel"; confirm text `Promote N and hold back M into <year label>?`; result text `Done for <year label>: N promoted, N held back, N not changed, N skipped.`; a locked row shows `Already in <year label>`.

- [ ] **Step 1: Write the failing e2e spec**

Create `apps/web/tests/e2e/enh-004-student-promotion.spec.ts`:

```ts
import { test, expect, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-004 -- student promotion. Requires the stack running via `docker compose up` with
// `python -m app.seed` applied (seeds overseasadmin@edusphere.local/Demo@123). Builds two throwaway
// schools; the second exists only to prove a coordinator cannot promote another school's student.
//
// Shared-state note: promotion needs an ACTIVE academic year the students are not already in, and a
// year cannot be deleted through the API. So each run creates a far-future, strictly increasing year
// (it always wins the "latest start_date" tie-break) and activates it AFTER the roster exists.
// The only lasting effect is that students later created by other specs get that year.

const ADMIN_EMAIL = "overseasadmin@edusphere.local";
const ADMIN_PASSWORD = "Demo@123";
const PARENT_PASSWORD = "Sup3r-Secret-Pass!";

async function signIn(page: Page, email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(landing);
}

async function createSchool(page: Page, unique: number, tag: string) {
  const coordinatorEmail = `enh004-e2e-${tag}-${unique}@example.local`;
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E ENH-004 School ${tag} ${unique}`);
  await page.fill("#school-coordinator-name", `E2E ENH-004 Coordinator ${tag}`);
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();
  return coordinatorEmail;
}

async function createStudent(page: Page, data: Record<string, unknown>) {
  const response = await page.request.post("/api/v1/school/students", { data });
  expect(response.status()).toBe(201);
  return response.json();
}

const studentRow = (page: Page, name: string) => page.getByRole("listitem").filter({ hasText: name });

test("coordinator promotes and holds back students; the parent sees the new grade; another school is refused (ENH-004)", async ({ page }) => {
  test.setTimeout(90_000);
  const unique = Date.now();
  const parentEmail = `enh004-e2e-parent-${unique}@example.local`;

  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD, "**/overseas/admin/dashboard");
  const coordinatorA = await createSchool(page, unique, "a");
  const coordinatorB = await createSchool(page, unique, "b");

  // School A's roster is created while the previous academic year is still the active one.
  await signIn(page, coordinatorA, E2E_PASSWORD, "**/school/coordinator/dashboard");
  const alpha = await createStudent(page, { full_name: "E2E Promo Alpha", grade_or_class: "Grade 8-A", grade_level: 8, parent_name: "E2E Promo Parent", parent_email: parentEmail });
  await createStudent(page, { full_name: "E2E Promo Beta", grade_or_class: "Grade 8-B", grade_level: 8 });
  await createStudent(page, { full_name: "E2E Promo Twelve", grade_or_class: "Grade 12", grade_level: 12 });
  const parentToken = alpha.development_invite_token;
  expect(parentToken).toBeTruthy();

  // A new academic year becomes active (start date far in the future and strictly increasing per run).
  await signIn(page, ADMIN_EMAIL, ADMIN_PASSWORD, "**/overseas/admin/dashboard");
  const startMs = Date.UTC(5000, 0, 1) + (Date.now() - Date.UTC(2026, 0, 1));
  const yearLabel = `e2e4-${unique}`;
  const created = await page.request.post("/api/v1/overseas-admin/academic-years", {
    data: { label: yearLabel, start_date: new Date(startMs).toISOString().slice(0, 10), end_date: new Date(startMs + 300 * 86_400_000).toISOString().slice(0, 10) },
  });
  expect(created.status()).toBe(201);
  const activated = await page.request.patch(`/api/v1/overseas-admin/academic-years/${(await created.json()).id}`, { data: { status: "active" } });
  expect(activated.ok()).toBeTruthy();

  // Another school's coordinator cannot touch school A's student (AC-04).
  await signIn(page, coordinatorB, E2E_PASSWORD, "**/school/coordinator/dashboard");
  const foreign = await page.request.post("/api/v1/school/students/promotions", { data: { items: [{ student_id: alpha.id, action: "promote" }] } });
  expect(foreign.status()).toBe(403);

  // School A's coordinator promotes Alpha, holds Beta back, and tries the Grade 12 student.
  await signIn(page, coordinatorA, E2E_PASSWORD, "**/school/coordinator/dashboard");
  await page.goto("/school/coordinator/promotion");
  await expect(page.getByText(yearLabel).first()).toBeVisible();
  await page.getByRole("checkbox", { name: /E2E Promo Alpha/ }).check();
  await page.getByRole("checkbox", { name: /E2E Promo Beta/ }).check();
  await studentRow(page, "E2E Promo Beta").getByLabel("Action").selectOption("hold_back");
  await page.getByRole("checkbox", { name: /E2E Promo Twelve/ }).check();
  // The Grade 12 student is flagged before anything is submitted (advisory; the server decides).
  await expect(studentRow(page, "E2E Promo Twelve")).toContainText("Grade 12 is the highest grade");

  // High-consequence action: an explicit confirmation step, not a one-click apply.
  await page.getByRole("button", { name: /Review changes \(3\)/ }).click();
  await expect(page.getByText(`Promote 2 and hold back 1 into ${yearLabel}?`)).toBeVisible();
  await page.getByRole("button", { name: "Confirm promotion" }).click();
  await expect(page.getByText(`Done for ${yearLabel}: 1 promoted, 1 held back, 1 not changed, 0 skipped.`)).toBeVisible();

  // The server's per-row outcome is shown at once, before any reload.
  await expect(studentRow(page, "E2E Promo Alpha")).toContainText("Grade 9-A");
  await expect(studentRow(page, "E2E Promo Alpha")).toContainText("Promoted");
  await expect(studentRow(page, "E2E Promo Beta")).toContainText("Held back");
  await expect(studentRow(page, "E2E Promo Twelve")).toContainText("Not changed");

  // ...and it survives a full reload: processed students are locked, the failed one is not.
  await page.reload();
  await expect(studentRow(page, "E2E Promo Alpha")).toContainText(`Already in ${yearLabel}`);
  await expect(studentRow(page, "E2E Promo Beta")).toContainText(`Already in ${yearLabel}`);
  await expect(studentRow(page, "E2E Promo Twelve")).not.toContainText("Already in");
  await page.selectOption("#promotion-filter", "12");
  await expect(page.getByRole("listitem").filter({ hasText: "E2E Promo" })).toHaveCount(1);

  // Keyboard: Space toggles the checkbox; Enter opens the confirm step and moves focus to it; Escape backs out and returns focus.
  const twelveBox = page.getByRole("checkbox", { name: /E2E Promo Twelve/ });
  await twelveBox.focus();
  await page.keyboard.press("Space");
  await expect(twelveBox).toBeChecked();
  const review = page.getByRole("button", { name: /Review changes \(1\)/ });
  await review.press("Enter");
  await expect(page.getByRole("button", { name: "Confirm promotion" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(review).toBeFocused();

  // Responsive (RESPONSIVE_RULES): no horizontal scroll at 320 / 768 / 1024 / 1440, and the primary action stays reachable.
  for (const width of [320, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 800 });
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), { message: `horizontal overflow at ${width}px` }).toBe(true);
    await expect(review).toBeInViewport();
  }
  await page.setViewportSize({ width: 1280, height: 720 });

  // The Parent (invited earlier, accepting now) sees the promoted grade on the dashboard.
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${parentToken}/accept`);
  await page.fill("#invite-password", PARENT_PASSWORD);
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/parent/dashboard");
  await expect(page.getByRole("heading", { name: "E2E Promo Alpha" })).toBeVisible();
  await expect(page.getByText("Grade 9-A").first()).toBeVisible();
});
```

- [ ] **Step 2: Confirm the spec compiles**

Run (from `apps/web`): `npx tsc --noEmit`
Expected: passes. The spec fails at runtime until Steps 3-6 exist; the first real run is Step 8 (it needs the stack, which the user controls).

- [ ] **Step 3: Create the scoped stylesheet**

Create `apps/web/components/SchoolPromotionPanel.module.css` (uses only existing CSS variables; no new colors; no animation):

```css
.list { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.header { display: none; }
.row { display: grid; gap: 12px; padding: 14px; border: 1px solid var(--line); border-radius: 12px; background: #fff; }
.who { display: flex; gap: 12px; align-items: flex-start; }
.who input { width: 22px; height: 22px; margin-top: 2px; flex: none; }
.who label { display: grid; gap: 2px; cursor: pointer; }
.control { display: grid; gap: 7px; }
.outcome { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 13px; }
.hint { color: var(--muted); font-size: 13px; }
.bar { position: sticky; bottom: 0; display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; margin-top: 16px; padding: 12px 14px; background: #fff; border-top: 1px solid var(--line); }
.barText { margin: 0; font-weight: 700; }
.barActions { display: flex; gap: 10px; flex-wrap: wrap; }
.summary:focus { outline: 2px solid var(--blue); outline-offset: 2px; }

@media (max-width: 640px) {
  .row select, .row input[type="text"] { min-height: 44px; width: 100%; }
  .bar .btn, .barActions { width: 100%; }
  .bar .btn { min-height: 44px; }
  .barActions .btn { flex: 1; min-height: 44px; }
}

/* Labels are visible on small screens (the card stack has no column headers) and move to a header row from 768px up. */
@media (min-width: 768px) {
  .header, .row { grid-template-columns: minmax(220px, 2fr) 150px minmax(180px, 1.5fr) minmax(150px, 1fr); align-items: center; }
  .header { display: grid; padding: 0 14px; font-size: 12px; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
  .row { border: 0; border-bottom: 1px solid var(--line); border-radius: 0; }
  .controlLabel { position: absolute; width: 1px; height: 1px; margin: -1px; padding: 0; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }
  .outcomeWide { grid-column: 2 / -1; }
}
```

- [ ] **Step 4: Create the row component**

Create `apps/web/components/SchoolPromotionRow.tsx`:

```tsx
import { memo } from "react";
import styles from "./SchoolPromotionPanel.module.css";

export type PromotionStudent = { id: string; student_code: string; full_name: string; grade_or_class: string | null; grade_level: number | null; academic_year_id: string | null };
export type PromotionAction = "promote" | "hold_back";
export type PromotionRowResult = { student_id: string; status: "promoted" | "held_back" | "failed" | "skipped"; reason: string | null; message: string | null; grade_level: number | null; grade_or_class: string | null };

type Props = {
  student: PromotionStudent;
  activeYearLabel: string;
  inActiveYear: boolean;
  selected: boolean;
  action: PromotionAction;
  override: string;
  result: PromotionRowResult | null;
  onSelect: (id: string, on: boolean) => void;
  onAction: (id: string, action: PromotionAction) => void;
  onOverride: (id: string, value: string) => void;
};

// Advisory only: the server decides (spec §5.2). It just spares the coordinator a predictable failed row.
function promoteHint(level: number | null) {
  if (level === null) return "Grade level is not set. Set it on the roster before promoting.";
  if (level >= 12) return "Grade 12 is the highest grade and cannot be promoted. Choose Hold back.";
  return null;
}

// One student. Memoised with primitive props and stable callbacks so ticking one box does not re-render
// the whole roster. Labels are real <label>s (visible on mobile, moved to a header row from 768px up).
function SchoolPromotionRow({ student, activeYearLabel, inActiveYear, selected, action, override, result, onSelect, onAction, onOverride }: Props) {
  const id = student.id;
  const settled = result && (result.status === "promoted" || result.status === "held_back") ? result : null;
  const locked = inActiveYear || settled !== null;
  const gradeText = settled ? settled.grade_or_class : student.grade_or_class;
  const level = settled ? settled.grade_level : student.grade_level;
  const hint = locked || action !== "promote" ? null : promoteHint(student.grade_level);
  const failure = result && (result.status === "failed" || result.status === "skipped") ? result : null;
  const describedBy = failure ? `promo-msg-${id}` : hint ? `promo-hint-${id}` : undefined;

  return (
    <li className={styles.row}>
      <div className={styles.who}>
        <input id={`promo-select-${id}`} type="checkbox" checked={selected && !locked} disabled={locked} onChange={(e) => onSelect(id, e.target.checked)} />
        <label htmlFor={`promo-select-${id}`}>
          <strong>{student.full_name}</strong>
          <span className="muted">{student.student_code} · {gradeText || "Grade not set"}{level !== null ? ` (level ${level})` : ""}</span>
        </label>
      </div>
      {locked ? (
        <div className={`${styles.outcome} ${styles.outcomeWide}`}>
          {settled ? <span className="status">{settled.status === "promoted" ? "Promoted" : "Held back"}</span> : null}
          <span>{settled ? `Now in ${activeYearLabel}` : `Already in ${activeYearLabel}`}</span>
        </div>
      ) : (
        <>
          <div className={`field ${styles.control}`}>
            <label className={styles.controlLabel} htmlFor={`promo-action-${id}`}>Action</label>
            <select id={`promo-action-${id}`} className="select" value={action} aria-describedby={describedBy} onChange={(e) => onAction(id, e.target.value as PromotionAction)}>
              <option value="promote">Promote</option>
              <option value="hold_back">Hold back</option>
            </select>
          </div>
          <div className={`field ${styles.control}`}>
            <label className={styles.controlLabel} htmlFor={`promo-label-${id}`}>New label (optional)</label>
            <input id={`promo-label-${id}`} type="text" className="search" placeholder="automatic" maxLength={60} value={override} disabled={action !== "promote"} aria-describedby={describedBy} onChange={(e) => onOverride(id, e.target.value)} />
          </div>
          <div className={styles.outcome}>
            {failure ? (
              <>
                <span className={failure.status === "failed" ? "status error" : "status pending"}>{failure.status === "failed" ? "Not changed" : "Skipped"}</span>
                <span id={`promo-msg-${id}`}>{failure.message}</span>
              </>
            ) : hint ? (
              <span id={`promo-hint-${id}`} className={styles.hint}>{hint}</span>
            ) : null}
          </div>
        </>
      )}
    </li>
  );
}

export default memo(SchoolPromotionRow);
```

- [ ] **Step 5: Create the panel**

Create `apps/web/components/SchoolPromotionPanel.tsx`:

```tsx
"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, useTransition, type KeyboardEvent } from "react";
import SchoolPromotionRow, { type PromotionAction, type PromotionRowResult, type PromotionStudent } from "@/components/SchoolPromotionRow";
import styles from "./SchoolPromotionPanel.module.css";

type ActiveYear = { id: string; label: string } | null;
type Report = { academic_year: { id: string; label: string }; counts: { promoted: number; held_back: number; failed: number; skipped: number }; results: PromotionRowResult[] };

const MAX_ITEMS = 500; // the API's per-request cap (spec §5.2)
const FILTER_ALL = "all";
const FILTER_UNSET = "unset";

// Same two shapes SchoolStudentsPanel handles: a string `detail` (403/409) or FastAPI's list (422).
function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Something went wrong.";
}

// ENH-004: the Coordinator's rollover screen. Choose students, review, confirm. Each selected student is
// promoted (grade + 1) or held back (same grade) into the ACTIVE academic year. Students already in that
// year are locked, so a second submit can never promote twice. Failed rows stay selected, with their
// reason beside the field, so the label can be corrected and retried.
export default function SchoolPromotionPanel({ students, activeYear }: { students: PromotionStudent[]; activeYear: ActiveYear }) {
  const router = useRouter();
  const [refreshing, startRefresh] = useTransition();
  const [filter, setFilter] = useState(FILTER_ALL);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [actions, setActions] = useState<Record<string, PromotionAction>>({});
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, PromotionRowResult>>({});
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const reviewRef = useRef<HTMLButtonElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);
  const summaryRef = useRef<HTMLDivElement>(null);
  const restoreFocus = useRef(false);

  // Focus management: the confirm button takes focus when it appears, Cancel/Escape returns it to
  // "Review changes", and after a result the (now unmounted) confirm button's focus moves to the summary.
  useEffect(() => {
    if (confirming) confirmRef.current?.focus();
    else if (restoreFocus.current) {
      restoreFocus.current = false;
      reviewRef.current?.focus();
    }
  }, [confirming]);
  useEffect(() => {
    if (summary) summaryRef.current?.focus();
  }, [summary]);

  const onSelect = useCallback((id: string, on: boolean) => {
    setSelected((prev) => ({ ...prev, [id]: on }));
    setConfirming(false);
  }, []);
  const onAction = useCallback((id: string, action: PromotionAction) => setActions((prev) => ({ ...prev, [id]: action })), []);
  const onOverride = useCallback((id: string, value: string) => setOverrides((prev) => ({ ...prev, [id]: value })), []);

  if (activeYear === null) {
    return (
      <div className="portal-content">
        <div className="card">
          <h2>Promote students</h2>
          <div className="empty" role="status">
            <h3>No active academic year</h3>
            <p>Promotion becomes available once an Overseas Admin activates the new academic year.</p>
          </div>
        </div>
      </div>
    );
  }

  const inActiveYear = (s: PromotionStudent) => s.academic_year_id === activeYear.id;
  const isSettled = (s: PromotionStudent) => results[s.id]?.status === "promoted" || results[s.id]?.status === "held_back";
  const isLocked = (s: PromotionStudent) => inActiveYear(s) || isSettled(s);
  const levels = Array.from(new Set(students.map((s) => s.grade_level).filter((l): l is number => l !== null))).sort((a, b) => a - b);
  const visible = students.filter((s) => filter === FILTER_ALL || (filter === FILTER_UNSET ? s.grade_level === null : String(s.grade_level) === filter));
  const selectable = visible.filter((s) => !isLocked(s));
  const chosen = students.filter((s) => selected[s.id] && !isLocked(s));
  const holdCount = chosen.filter((s) => actions[s.id] === "hold_back").length;
  const promoteCount = chosen.length - holdCount;
  const tooMany = chosen.length > MAX_ITEMS;
  const allShownSelected = selectable.length > 0 && selectable.every((s) => selected[s.id]);

  function changeFilter(value: string) {
    setFilter(value);
    setSelected({});
    setConfirming(false);
  }

  function toggleAllShown(on: boolean) {
    setSelected((prev) => {
      const next = { ...prev };
      for (const s of selectable) next[s.id] = on;
      return next;
    });
    setConfirming(false);
  }

  function cancelConfirm() {
    restoreFocus.current = true;
    setConfirming(false);
  }

  function onBarKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape" && confirming && !busy) cancelConfirm();
  }

  async function submit() {
    setBusy(true);
    setError(null);
    setSummary(null);
    const items = chosen.map((s) => {
      const action = actions[s.id] ?? "promote";
      const override = (overrides[s.id] || "").trim();
      return { student_id: s.id, action, ...(action === "promote" && override ? { grade_or_class: override } : {}) };
    });
    let response: Response;
    try {
      response = await fetch("/api/v1/school/students/promotions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ items }) });
    } catch {
      setBusy(false);
      setConfirming(false);
      setError("The request did not complete. Your selection is kept. Refresh to check the current state, then try again; repeating it is safe.");
      return;
    }
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    setConfirming(false);
    if (!response.ok) {
      setError(detailMessage(data.detail));
      return;
    }
    const report = data as Report;
    const c = report.counts;
    setResults((prev) => ({ ...prev, ...Object.fromEntries(report.results.map((r) => [r.student_id, r])) }));
    setSelected(Object.fromEntries(report.results.filter((r) => r.status === "failed").map((r) => [r.student_id, true])));
    setSummary(`Done for ${report.academic_year.label}: ${c.promoted} promoted, ${c.held_back} held back, ${c.failed} not changed, ${c.skipped} skipped.`);
    startRefresh(() => router.refresh());
  }

  return (
    <div className="portal-content">
      <div className="card">
        <h2>Promote students</h2>
        <p>Move students into <span className="status">{activeYear.label}</span>, the active academic year. <strong>Promote</strong> advances the grade by one; <strong>Hold back</strong> keeps the grade and records the new year.</p>

        {error && <div className="form-error" role="alert">{error}</div>}
        {summary && <div ref={summaryRef} tabIndex={-1} className={`form-message ${styles.summary}`} role="status">{summary}</div>}

        {students.length === 0 ? (
          <div className="empty">
            <h3>No students on the roster yet</h3>
            <p>Add students first, then come back to promote them.</p>
            <a className="btn secondary small" href="/school/coordinator/students">Go to the student roster</a>
          </div>
        ) : (
          <>
            <div className="table-controls" aria-label="Promotion filters">
              <div>
                <label htmlFor="promotion-filter">Grade level</label>
                <select id="promotion-filter" className="select" value={filter} onChange={(e) => changeFilter(e.target.value)}>
                  <option value={FILTER_ALL}>All grades</option>
                  {levels.map((l) => <option key={l} value={String(l)}>Grade {l}</option>)}
                  <option value={FILTER_UNSET}>Grade level not set</option>
                </select>
              </div>
              <div>
                <label htmlFor="promotion-select-all">Select all shown</label>
                <input id="promotion-select-all" type="checkbox" checked={allShownSelected} disabled={selectable.length === 0} onChange={(e) => toggleAllShown(e.target.checked)} />
              </div>
            </div>
            <p className="muted" aria-live="polite">Showing {visible.length} of {students.length} students</p>

            {visible.length === 0 ? (
              <div className="empty">
                <h3>No students match this filter</h3>
                <button type="button" className="btn secondary small" onClick={() => changeFilter(FILTER_ALL)}>Show all grades</button>
              </div>
            ) : (
              <ul className={styles.list} role="list" aria-busy={refreshing}>
                <li className={styles.header} aria-hidden="true"><span>Student</span><span>Action</span><span>New label (optional)</span><span>Status</span></li>
                {visible.map((s) => (
                  <SchoolPromotionRow
                    key={s.id} student={s} activeYearLabel={activeYear.label} inActiveYear={inActiveYear(s)}
                    selected={!!selected[s.id]} action={actions[s.id] ?? "promote"} override={overrides[s.id] ?? ""} result={results[s.id] ?? null}
                    onSelect={onSelect} onAction={onAction} onOverride={onOverride}
                  />
                ))}
              </ul>
            )}

            <div className={styles.bar} onKeyDown={onBarKeyDown}>
              {confirming ? (
                <>
                  <p id="promotion-confirm-text" className={styles.barText}>Promote {promoteCount} and hold back {holdCount} into {activeYear.label}? This changes the current grade of each selected student.</p>
                  <div className={styles.barActions}>
                    <button ref={confirmRef} type="button" className="btn" onClick={submit} disabled={busy} aria-describedby="promotion-confirm-text">{busy ? "Promoting…" : "Confirm promotion"}</button>
                    <button type="button" className="btn ghost" onClick={cancelConfirm} disabled={busy}>Cancel</button>
                  </div>
                </>
              ) : (
                <>
                  <p id="promotion-selected-count" className={styles.barText}>{chosen.length} selected{tooMany ? `. Select at most ${MAX_ITEMS} at a time.` : ""}</p>
                  <button ref={reviewRef} type="button" className="btn" disabled={chosen.length === 0 || tooMany} aria-describedby="promotion-selected-count" onClick={() => setConfirming(true)}>Review changes ({chosen.length})</button>
                </>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Create the page and add the nav entry**

Create `apps/web/app/school/coordinator/promotion/page.tsx`:

```tsx
import PortalShell from "@/components/PortalShell";
import SchoolPromotionPanel from "@/components/SchoolPromotionPanel";
import type { PromotionStudent } from "@/components/SchoolPromotionRow";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

type ActiveYear = { id: string; label: string } | null;

// ENH-004: academic-year rollover -- promote or hold back students, own institution only.
export default async function SchoolCoordinatorPromotionPage() {
  let user: User;
  let students: PromotionStudent[];
  let activeYear: ActiveYear;
  try {
    [user, students, activeYear] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<PromotionStudent[]>("/api/v1/school/students"),
      serverApi<ActiveYear>("/api/v1/school/academic-years/active"),
    ]);
  } catch (e) {
    return (
      <div className="section">
        <div className="container card">
          <h1>Access unavailable</h1>
          <p>{e instanceof Error ? e.message : "Unable to load this workspace"}</p>
          <a className="btn" href="/overseas/login">Return to login</a>
        </div>
      </div>
    );
  }
  return (
    <PortalShell nav={SCHOOL_NAV.coordinator} roleLabel="School Coordinator" userName={user.full_name}>
      <SchoolPromotionPanel students={students} activeYear={activeYear} />
    </PortalShell>
  );
}
```

In `apps/web/lib/navigation.ts` line 37, change the coordinator array from
`["dashboard", "students", "activities", "team", "reports", "entitlements"]` to
`["dashboard", "students", "promotion", "activities", "team", "reports", "entitlements"]`
(the label "Promotion" and href `/school/coordinator/promotion` are derived by the existing `.map`).

- [ ] **Step 7: Static checks**

Run (from `apps/web`): `npm run typecheck; npm run lint`
Expected: both clean. If lint flags `react/no-unescaped-entities`, replace the apostrophe with a rewording; do not disable the rule.

- [ ] **Step 8: Run the e2e spec (needs the user)**

Ask the user to rebuild and restart the `api` and `web` containers so they contain Tasks 1-8 (the API needs migration `0033` applied — done in Task 2 — and the new routes), and to confirm the shared-state note in the spec header. Wait for their go-ahead.
Run (from `apps/web`): `npx playwright test tests/e2e/enh-004-student-promotion.spec.ts --workers=1`
Expected: `1 passed`. If a step fails, open only that failure's trace; re-run alone with `--workers=1` once before classifying it as a regression.
If only the **320 px overflow** assertion fails, first load `/school/coordinator/students` at 320 px: horizontal overflow there too means the portal shell, not this screen, is responsible. Report it to the user as a pre-existing finding; do not paper over it in this component and do not weaken the assertion.

- [ ] **Step 9: Manual pass (ask the user to do this, or do it with them)**

Load `/school/coordinator/promotion` with a roster of 20+ students. Check: Tab reaches every control in a logical order with a visible focus ring; at 320 px each student is a stacked card with visible "Action" and "New label (optional)" labels and no horizontal scroll; at 1024 px+ the header row replaces the per-row labels; with the browser's reduced-motion setting on, nothing animates; a screen reader reads the checkbox as the student's name and code and announces the result summary. Record anything that fails as a bug, not a note.

- [ ] **Step 10: Commit**

```powershell
git add apps/web/components/SchoolPromotionRow.tsx apps/web/components/SchoolPromotionPanel.tsx apps/web/components/SchoolPromotionPanel.module.css apps/web/app/school/coordinator/promotion/page.tsx apps/web/lib/navigation.ts apps/web/tests/e2e/enh-004-student-promotion.spec.ts
git commit -m "feat(enh-004): add the coordinator promotion screen" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 9: Grade history on the parent and coordinator pages

**Files:**
- Create: `apps/web/components/SchoolGradeHistory.tsx`
- Modify: `apps/web/components/SchoolStudentDetailPanel.tsx`
- Modify: `apps/web/app/school/coordinator/students/[id]/page.tsx`
- Modify: `apps/web/app/school/parent/children/[id]/page.tsx`
- Modify: `apps/web/tests/e2e/enh-004-student-promotion.spec.ts` (append assertions to the existing test)

**Reuse, not rebuilt:** the existing `.jtl-*` timeline rail classes and the timeline component's colour-plus-text badge convention. History is a short, ordered list of dated events, which is exactly what the rail already presents, and it stacks on mobile with no new CSS (a four-column table would need horizontal scroll at 320 px). `SchoolStudentTimeline` itself is not modified.

**Interfaces:**
- Consumes: Task 5's `GET /api/v1/school/students/{id}/grade-history`; existing `formatDate` (`SchoolChildOverview.tsx:30`).
- Produces: `loadGradeHistory(studentId)`, types `GradeHistoryEntry` / `StudentGradeHistory`, default component `SchoolGradeHistory({ history })`; `SchoolStudentDetailPanel` gains optional prop `showGradeHistory?: boolean` (default `false`, so the principal and teacher pages are unchanged). Visible copy the e2e relies on: `Moved from <grade> to <grade>`, `Kept in <grade>`, badge `Promoted`/`Held back`, empty state `No promotions recorded yet.`

- [ ] **Step 1: Write the failing e2e assertions**

In `apps/web/tests/e2e/enh-004-student-promotion.spec.ts`, replace the trailing lines of the test:

```ts
  await expect(page.getByRole("heading", { name: "E2E Promo Alpha" })).toBeVisible();
  await expect(page.getByText("Grade 9-A").first()).toBeVisible();
});
```

with:

```ts
  await expect(page.getByRole("heading", { name: "E2E Promo Alpha" })).toBeVisible();
  await expect(page.getByText("Grade 9-A").first()).toBeVisible();

  // The child page keeps the prior grade: a "Promoted" entry from Grade 8-A to Grade 9-A in the new year (AC-02).
  await page.click('a:has-text("View full profile & progress")');
  await page.waitForURL(`**/school/parent/children/${alpha.id}`);
  await expect(page.getByRole("heading", { name: "Grade history" })).toBeVisible();
  await expect(page.getByText("Moved from Grade 8-A to Grade 9-A")).toBeVisible();
  await expect(page.getByText(`Academic year: ${yearLabel}`)).toBeVisible();

  // The coordinator's student page shows the held-back outcome, and the empty state for an unpromoted student.
  await signIn(page, coordinatorA, E2E_PASSWORD, "**/school/coordinator/dashboard");
  const students = await (await page.request.get("/api/v1/school/students")).json();
  const beta = students.find((s: { full_name: string }) => s.full_name === "E2E Promo Beta");
  const twelve = students.find((s: { full_name: string }) => s.full_name === "E2E Promo Twelve");
  await page.goto(`/school/coordinator/students/${beta.id}`);
  await expect(page.getByRole("heading", { name: "Grade history" })).toBeVisible();
  await expect(page.getByText("Kept in Grade 8-B")).toBeVisible();
  await page.goto(`/school/coordinator/students/${twelve.id}`);
  await expect(page.getByText("No promotions recorded yet.")).toBeVisible();
});
```

- [ ] **Step 2: Confirm it compiles**

Run (from `apps/web`): `npx tsc --noEmit`
Expected: passes. (The new assertions fail at runtime until Steps 3-4; the run is Step 5.)

- [ ] **Step 3: Create the component**

Create `apps/web/components/SchoolGradeHistory.tsx`:

```tsx
import { formatDate } from "@/components/SchoolChildOverview";
import { serverApi } from "@/lib/api";

// ENH-004 -- a student's grade/academic-year transitions, read from GET /school/students/{id}/grade-history.
// That endpoint reuses the same own-scope loader as the overview and timeline, so this renders correctly
// for whichever role is looking (a Parent gets their own child's history only). It deliberately reuses the
// Journey Timeline's `.jtl-*` rail: a short, dated list that stacks on mobile without horizontal scroll.
// Outcome is stated in text (badge + sentence), never by colour alone.

type State = { academic_year_id: string | null; academic_year_label: string | null; grade_level: number | null; grade_or_class: string | null };
export type GradeHistoryEntry = { id: string; action: "promoted" | "held_back"; from: State; to: State; created_at: string };
export type StudentGradeHistory = { student: { id: string; full_name: string }; history: GradeHistoryEntry[] };

export async function loadGradeHistory(studentId: string): Promise<StudentGradeHistory> {
  return serverApi<StudentGradeHistory>(`/api/v1/school/students/${studentId}/grade-history`);
}

const OUTCOME: Record<GradeHistoryEntry["action"], { label: string; color: string }> = {
  promoted: { label: "Promoted", color: "#15803d" },
  held_back: { label: "Held back", color: "#b45309" },
};

function gradeText(state: State) {
  return state.grade_or_class || (state.grade_level !== null ? `Grade ${state.grade_level}` : "Grade not set");
}

function summarize(entry: GradeHistoryEntry) {
  return entry.action === "held_back" ? `Kept in ${gradeText(entry.to)}` : `Moved from ${gradeText(entry.from)} to ${gradeText(entry.to)}`;
}

export default function SchoolGradeHistory({ history }: { history: GradeHistoryEntry[] }) {
  if (history.length === 0) {
    return <p className="muted">No promotions recorded yet.</p>;
  }
  return (
    <div className="jtl">
      {history.map((h) => {
        const meta = OUTCOME[h.action];
        return (
          <div className="jtl-row" key={h.id}>
            <div className="jtl-rail">
              <span className="jtl-node" style={{ "--jtl-color": meta.color } as React.CSSProperties} />
            </div>
            <div className="jtl-body">
              <span className="jtl-date">{formatDate(h.created_at, true)}</span>
              <span className="jtl-badge" style={{ "--jtl-color": meta.color } as React.CSSProperties}>{meta.label}</span>
              <h4 className="jtl-title">{summarize(h)}</h4>
              <p className="jtl-detail">Academic year: {h.from.academic_year_label ? `${h.from.academic_year_label} to ` : ""}{h.to.academic_year_label}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Wire it into the two pages (loading in parallel)**

Replace the whole of `apps/web/components/SchoolStudentDetailPanel.tsx` with:

```tsx
import SchoolGradeHistory, { loadGradeHistory } from "@/components/SchoolGradeHistory";
import SchoolStudentTimeline, { loadStudentTimeline } from "@/components/SchoolStudentTimeline";
import { formatDate } from "@/components/SchoolChildOverview";

// Shared read-only student header + Journey Timeline, reused across every School role that
// can open one student's page within their own SCH-001 scope: Teacher (assigned), School
// Coordinator and Principal (own institution). Each role keeps its own thin page/route
// (matching this app's existing per-role-route convention -- see SchoolServiceDeliverySummary
// for the same reuse pattern across dashboards) -- only this presentational piece is shared,
// so no role gains another role's write actions by using it.
// ENH-004: `showGradeHistory` (default off, so the Principal and Teacher pages are unchanged)
// adds the read-only grade-history card for the Coordinator. Both reads start together.

type Student = { id: string; student_code: string; full_name: string; date_of_birth: string | null; grade_or_class: string | null };

export default async function SchoolStudentDetailPanel({ student, backHref, backLabel, showGradeHistory = false }: { student: Student; backHref: string; backLabel: string; showGradeHistory?: boolean }) {
  const [timeline, gradeHistory] = await Promise.all([
    loadStudentTimeline(student.id).catch(() => null),
    showGradeHistory ? loadGradeHistory(student.id).catch(() => null) : Promise.resolve(null),
  ]);
  return (
    <div className="portal-content">
      <div className="card">
        <h2>{student.full_name} <span className="muted" style={{ fontSize: 14 }}>({student.student_code})</span></h2>
        <p><strong>Grade/Class:</strong> {student.grade_or_class || "-"}</p>
        <p><strong>Date of birth:</strong> {formatDate(student.date_of_birth)}</p>
        <a className="btn secondary" href={backHref}>{backLabel}</a>
      </div>
      {showGradeHistory && (
        <div className="card">
          <h3>Grade history</h3>
          {gradeHistory ? <SchoolGradeHistory history={gradeHistory.history} /> : <p className="muted">Grade history is unavailable right now.</p>}
        </div>
      )}
      <div className="card">
        <h3>Journey timeline</h3>
        {timeline ? <SchoolStudentTimeline events={timeline.events} /> : <p className="muted">Timeline is unavailable right now.</p>}
      </div>
    </div>
  );
}
```

In `apps/web/app/school/coordinator/students/[id]/page.tsx`, change the panel line to:

```tsx
      <SchoolStudentDetailPanel student={student} backHref="/school/coordinator/students" backLabel="Back to students" showGradeHistory />
```

In `apps/web/app/school/parent/children/[id]/page.tsx`:

(a) Add the import below the timeline import:

```tsx
import SchoolGradeHistory, { loadGradeHistory, type StudentGradeHistory } from "@/components/SchoolGradeHistory";
```

(b) Replace the line `const timeline: StudentTimeline | null = await loadStudentTimeline(id).catch(() => null);` with:

```tsx
  const [timeline, gradeHistory]: [StudentTimeline | null, StudentGradeHistory | null] = await Promise.all([
    loadStudentTimeline(id).catch(() => null),
    loadGradeHistory(id).catch(() => null),
  ]);
```

(c) Between the `<SchoolChildOverview overview={overview} />` line and the timeline card, add:

```tsx
        <div className="card">
          <h3>Grade history</h3>
          {gradeHistory ? <SchoolGradeHistory history={gradeHistory.history} /> : <p className="muted">Grade history is unavailable right now.</p>}
        </div>
```

- [ ] **Step 5: Static checks, then the e2e run (needs the user)**

Run (from `apps/web`): `npm run typecheck; npm run lint`
Expected: both clean.
Ask the user to rebuild/restart `web` (the API is unchanged since Task 8), wait for their go-ahead, then run:
`npx playwright test tests/e2e/enh-004-student-promotion.spec.ts --workers=1`
Expected: `1 passed`.

- [ ] **Step 6: Commit**

```powershell
git add apps/web/components/SchoolGradeHistory.tsx apps/web/components/SchoolStudentDetailPanel.tsx "apps/web/app/school/coordinator/students/[id]/page.tsx" "apps/web/app/school/parent/children/[id]/page.tsx" apps/web/tests/e2e/enh-004-student-promotion.spec.ts
git commit -m "feat(enh-004): show grade history to parents and coordinators" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 10: Documentation and decision record

**Files (all Modify; append or insert exactly as described):**
- `docs/decisions/PRODUCT_DECISION_REGISTER.md`
- `docs/architecture/API_CONTRACT.md`
- `docs/architecture/DATA_MODEL.md`
- `docs/ux/SCREEN_CATALOG.md`
- `docs/ux/ROLE_NAVIGATION.md`
- `docs/delivery/ENHANCEMENT_BACKLOG.md`

`RTM.md` is intentionally not touched (its own header says ENH-001/ENH-002 are not tracked there; ENH-003 was, at that spec's explicit direction). `docs/ux/screen_catalog.json` is not touched (it does not contain `SCR-SCH-025` either, so it is already out of step with the Markdown catalogue).

- [ ] **Step 1: Register `DEC-SCOPE-020`**

Append to the end of `docs/decisions/PRODUCT_DECISION_REGISTER.md` (leave one blank line after the previous entry):

```markdown

### DEC-SCOPE-020 — Student promotion to the next academic year / grade (`ENH-004`)

**Question:** `docs/delivery/ENHANCEMENT_BACKLOG.md` ENH-004 (source: the user's instruction to think broadly about user lifecycle, "promoted to upper grade in next year if required") had no Decision ID or Feature ID. How does a School Coordinator advance students at academic-year rollover, and what happens to the prior grade?

**Evidence:** Audit of the code, 2026-09-19 (`UNVERIFIED` until re-run at implementation time): no promotion action existed; `PATCH /school/students/{id}` overwrote `grade_or_class`/`grade_level` in place with no history; every school page renders the free-text `grade_or_class` (only the dashboard KPIs read `grade_level`); `SchoolStudent` has no section field; school students never log in (`DEC-ROLE-004`).

**Resolution:** User confirmed in-session, 2026-09-19 (`EXPLICIT_APPROVAL`), six points:

1. **Bulk selection:** an explicit list of student IDs (the UI filters and ticks); no server-side grade/section selector.
2. **Grade label:** the number inside `grade_or_class` is advanced automatically ("Grade 8-A" → "Grade 9-A"); a label that cannot be advanced fails that row unless the coordinator supplies a replacement.
3. **Top grade:** a Grade 12 promotion is rejected for that row; graduate/alumni handling is out of scope.
4. **Who:** `school_coordinator` only, scoped to their own school; the school is never client-supplied.
5. **Target year and hold-back:** the active academic year, server-resolved; "hold back" is a recorded action (same grade, moved into the new year).
6. **Partial failure:** valid rows commit and failures are reported per row; a student from another school (or an unknown ID) rejects the whole request with `403`.

Design and API review: `docs/superpowers/specs/2026-09-19-enh-004-student-promotion-design.md`.

**Consequences:** new append-only table `school_student_grade_history` (migration `0033`); `POST /school/students/promotions` and `GET /school/students/{id}/grade-history`; the "student dashboard" in the backlog's acceptance criteria maps to the parent view only.

**`NEEDS_CONFIRMATION` (not decided here):** graduate/alumni handling after Grade 12; a real section field; whether admin roles should ever promote; parent notification on promotion; promotion events in the SCH-008 timeline. Security follow-ups found during review and outside this feature: `profile.university_id` can be changed by its owner through `PATCH /auth/me` (the same class as the `school_id` exposure; UNI-001); no school-student erasure path exists; no app-wide rate limiter or CSRF token.
```

- [ ] **Step 2: Document the endpoints**

In `docs/architecture/API_CONTRACT.md`, insert these two rows immediately after the `GET /school/academic-years/active` row (the row that ends `... Response shape (when active exists): `{id, label, start_date, end_date, status}`. |`):

```markdown
| `POST /school/students/promotions` | Authenticated | School Coordinator, own institution only | **ENH-004 / `DEC-SCOPE-020`.** Body `{items: [{student_id, action: "promote"\|"hold_back", grade_or_class?}]}`, 1–500 items; `grade_or_class` (≤60 chars) only with `promote`. Moves each student into the **active** academic year: `promote` adds one to `grade_level` and advances the number inside `grade_or_class` (an unswappable label needs the override); `hold_back` keeps grade and label. Always **200** with `{academic_year, counts, results[{student_id, status: promoted\|held_back\|failed\|skipped, reason, message, grade_level, grade_or_class}]}` (200 even when nothing changed, unlike `bulk-upload`'s 201, because a request can create nothing). Row `reason` codes (stable): `already_in_active_year`, `grade_level_not_set`, `terminal_grade`, `label_unparseable`. Valid rows commit; failed/skipped rows change nothing. **Errors:** 401; 403 if the caller is not a coordinator (checked before body validation) or if any listed student is unknown **or** at another institution (one generic message, nothing written); 409 if there is no active academic year, on a concurrent-promotion conflict, or if row locks cannot be taken within 5 s; 422 (FastAPI list-shaped `detail`) for an empty/oversized/duplicated/malformed list, an unknown action, a label with `hold_back` or containing control characters, or **any unknown body field** (a client-supplied `school_id` or `academic_year_id` is refused, never ignored). A 403 for a student outside the caller's institution is recorded as `school.student_promotion_denied` (`outcome=denied`, counts only). **Retry:** no `Idempotency-Key`; the natural key is (student, target year), enforced by a row lock plus `UNIQUE (school_student_id, to_academic_year_id)`. A repeat reports `skipped: already_in_active_year` instead of replaying `promoted`, so confirm via `results[].grade_level` or `GET …/grade-history`. |
| `GET /school/students/{id}/grade-history` | Authenticated | Coordinator, Principal (own institution) / Teacher (assigned) / Parent (own child(ren)) | **ENH-004.** `{student: {id, full_name}, history: [{id, action: promoted\|held_back, from: {academic_year_id, academic_year_label, grade_level, grade_or_class}, to: {…}, created_at}]}`, newest first; `[]` if never promoted. Same scope loader as `GET /school/students/{id}` (403 outside scope, 404 for an unknown ID). Not paginated (at most one row per academic year per student). The performer is stored but not returned. |
```

- [ ] **Step 3: Document the table**

In `docs/architecture/DATA_MODEL.md`, find the `### 6.12` heading (the section after `### 6.11`, starting at line 428). Immediately **before** that heading insert:

```markdown
**Addendum, 2026-09-19 (`ENH-004` / `DEC-SCOPE-020` — `school_student_grade_history`):** an append-only ledger of grade/academic-year transitions. Columns: `id`; `school_student_id` (FK `school_students`, indexed); `action` (`promoted` \| `held_back`); `from_academic_year_id` (FK `academic_years`, nullable), `from_grade_level` (int, nullable), `from_grade_or_class` (≤60, nullable); `to_academic_year_id` (FK `academic_years`, not null), `to_grade_level`, `to_grade_or_class` (both nullable); `performed_by_user_id` (FK `users`, not null); `created_at`/`updated_at`. `UNIQUE (school_student_id, to_academic_year_id)` (`uq_school_student_grade_history_year`) is the database backstop against promoting a student twice into the same year. Each row records its own "from" state, so no backfill of existing students was needed; `school_students` remains the source of the *current* grade and year. Migration `0033_student_grade_history` is create-table only and its downgrade drops only this table.

```

- [ ] **Step 4: Add the screens**

In `docs/ux/SCREEN_CATALOG.md`, insert these two rows immediately after the `SCR-SCH-026` row of the school table (`| `SCR-SCH-026` | `/school/principal/students/[id]` | Principal | `SCH-008` |`):

```markdown
| `SCR-SCH-027` | `/school/coordinator/promotion` | School Coordinator | `ENH-004` |
| `SCR-SCH-028` | *(embedded in `SCR-SCH-022` and `SCR-SCH-025` — not a standalone route)* Grade history section | Parent, School Coordinator | `ENH-004` |
```

Then append these two detail sections immediately after the `### SCR-SCH-026` section (before the next `###` heading):

```markdown

### `SCR-SCH-027` *(added 2026-09-19, `ENH-004` / `DEC-SCOPE-020`)*
- **Route:** `/school/coordinator/promotion`
- **Role(s):** School Coordinator
- **Purpose:** Academic-year rollover: promote (grade + 1) or hold back the selected students into the active academic year, own institution only.
- **Linked Feature ID(s):** `ENH-004`
- **Entry points:** "Promotion" item in the Coordinator navigation.
- **Required data:** `GET /school/students`, `GET /school/academic-years/active`, `POST /school/students/promotions`.
- **Key actions:** Filter by grade level; select students (or all shown); choose Promote or Hold back per student; optional replacement label; "Review changes (N)" then an explicit "Confirm promotion" (or Cancel / Escape). At most 500 students per request.
- **Empty state:** "No students on the roster yet" with a link to the roster / "No students match this filter" with "Show all grades" / "No active academic year" (nothing to act on until an Overseas Admin activates one).
- **Loading state:** Server-rendered. While submitting, the confirm button is disabled and reads "Promoting…"; the server's per-row outcome is shown as soon as it returns, then the list is refreshed in a transition (`aria-busy`).
- **Error state:** 403/409/422 and network failures render an `alert` message and keep the selection (a repeat is safe). Per-row failures show "Not changed" or "Skipped" plus the reason beside the row's own controls and stay selected for a corrected retry. Known-to-fail rows (Grade 12, no grade level) carry an advisory hint before submit. A student already in the active year is locked ("Already in <year>").
- **Permissions/resource scope:** Coordinator only; the school is server-derived, never client-supplied.
- **Responsive behavior:** Each student is a stacked card on mobile (visible "Action" and "New label" labels); from 768px a header row replaces the per-row labels; the action bar is sticky so the primary action stays reachable; no horizontal scroll at 320/768/1024/1440px (asserted in the e2e).
- **Accessibility requirements:** Real labels on every control; the checkbox is labelled by the student's name, code and grade; a keyboard-reachable confirmation step (focus moves to Confirm; Escape/Cancel returns focus to Review); focus moves to the result summary, which is a status region; the filter's "Showing N of M" is a polite live region; outcomes are stated in text as well as colour.
- **Desktop/tablet/mobile behavior:** One list structure at every width, restyled by breakpoint (cards below 768px, columned rows above).
- **Visual-reference mapping:** None — not inspected. Do not claim parity.
- **Acceptance evidence needed:** `enh-004-student-promotion.spec.ts`, `test_enh_004_student_promotion.py`.

### `SCR-SCH-028` *(added 2026-09-19, `ENH-004`)*
- **Route:** Embedded section, not a standalone route — appears on `SCR-SCH-022` (`/school/parent/children/[id]`) and `SCR-SCH-025` (`/school/coordinator/students/[id]`).
- **Role(s):** Parent (own child), School Coordinator (own institution)
- **Purpose:** Read-only list of a student's promotions and hold-backs (date, outcome, "Moved from X to Y" / "Kept in X", academic year).
- **Linked Feature ID(s):** `ENH-004`
- **Required data:** `GET /school/students/{id}/grade-history`.
- **Empty state:** "No promotions recorded yet."
- **Error state:** "Grade history is unavailable right now." without blocking the rest of the page.
- **Permissions/resource scope:** The same own-scope loader as the overview and timeline.
- **Responsive behavior:** Reuses the Journey Timeline's single-column rail (`SCR-SCH-024`), so no horizontal scroll at any width.
- **Accessibility requirements:** The outcome is a text badge plus a sentence, never colour alone; loaded in parallel with the timeline.
- **Acceptance evidence needed:** `enh-004-student-promotion.spec.ts`.
```

- [ ] **Step 5: Add the navigation line and the backlog status**

In `docs/ux/ROLE_NAVIGATION.md`, insert after the `SCR-SCH-025` line (`- `SCR-SCH-025` — /school/coordinator/students/[id] — One student's Journey Timeline ...`):

```markdown
- `SCR-SCH-027` — /school/coordinator/promotion — Promote or hold back students at academic-year rollover (`ENH-004`, added 2026-09-19).
```

In `docs/delivery/ENHANCEMENT_BACKLOG.md`, in the ENH-004 section, after the line beginning `**Regression risks.** Any existing report, dashboard, or filter keyed off the raw `grade` string.` add:

```markdown

**Status (2026-09-19).** Designed and decided in `docs/superpowers/specs/2026-09-19-enh-004-student-promotion-design.md` (`DEC-SCOPE-020`); implemented on branch `feature/enh-004-student-grade-promotion`. The line references above (`models.py:221,992,1157`, `schools.py:1145`) were stale when this item was drafted; the current definitions are `SchoolStudent` in `models.py` and `bulk_upload_students` in `schools.py`. The endpoint paths differ from the example above: the school is derived from the caller, never a path parameter (`POST /school/students/promotions`).
```

- [ ] **Step 6: Verify no doc still contradicts the implementation**

Run: `git diff --stat main -- docs`
Expected: the spec, this plan, and exactly the six files above.
Run (Grep tool): search the six edited docs for `already_processed`.
Expected: no matches.

- [ ] **Step 7: Commit**

```powershell
git add docs/decisions/PRODUCT_DECISION_REGISTER.md docs/architecture/API_CONTRACT.md docs/architecture/DATA_MODEL.md docs/ux/SCREEN_CATALOG.md docs/ux/ROLE_NAVIGATION.md docs/delivery/ENHANCEMENT_BACKLOG.md
git commit -m "docs(enh-004): register DEC-SCOPE-020 and document the promotion API, table and screens" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 11: Final verification and handoff

**Files:** none modified unless a check fails.

- [ ] **Step 1: Backend gates and targeted suites**

Run (from `apps/api`):
`python -m ruff check .; python -m mypy app; python -m pytest -q tests/test_enh_004_student_promotion.py tests/test_enh_001_academic_year.py tests/test_sch_001_school_portal_access.py tests/test_sch_002_bulk_roster_upload.py tests/test_sch_007_parent_portal.py tests/test_sch_008_student_timeline.py tests/test_sch_reports.py tests/test_sch_roster_parent_invite.py`
Expected: clean, then all pass.

- [ ] **Step 2: Frontend gates**

Run (from `apps/web`): `npm run typecheck; npm run lint; npm run build`
Expected: all succeed. (`npm test` runs vitest; run it too and expect no new failures.)

- [ ] **Step 3: Impacted e2e specs (needs the user)**

Ask the user to confirm the stack is rebuilt with all tasks, then run (from `apps/web`):
`npx playwright test tests/e2e/enh-004-student-promotion.spec.ts tests/e2e/enh-001-academic-year.spec.ts tests/e2e/sch-007-parent-portal.spec.ts tests/e2e/sch-008-student-timeline.spec.ts tests/e2e/sch-002-bulk-roster-upload.spec.ts tests/e2e/sch-roster-parent-invite.spec.ts --workers=1`
Expected: all pass. The full backend and e2e regression suites are **not** run for this feature alone (the user's cadence is every 3-4 features).

- [ ] **Step 4: Acceptance check against the spec**

For each of AC-01 … AC-11 in the spec §10 and each security item S1 and H1-H5 in §14.1, name the passing test that proves it (the test names in Tasks 3-6 and the e2e spec map one-to-one). Report any AC with no passing test as a gap; do not claim completion with a gap.

- [ ] **Step 5: Hand off**

Use the `superpowers:verification-before-completion` skill, then `superpowers:finishing-a-development-branch`. Report: what was verified and the exact outputs; that the full regression was deliberately not run; the e2e shared-state side effect (Task 8 note); and the open `NEEDS_CONFIRMATION` items from `DEC-SCOPE-020`.
