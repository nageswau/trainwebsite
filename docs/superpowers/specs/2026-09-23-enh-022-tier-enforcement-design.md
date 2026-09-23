# ENH-022 — Tier-Gated Feature Access Enforcement — Design

## 1. Problem (audit result, gap confirmed)

`docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-022 (`DERIVED_BLUEPRINT`), citing `School CRM.md §26` and the
brochure's "School Partnership Model" page: a partnership tier defines what a school is *entitled to use*,
not merely informed about. The user's instruction: *"consider the entitlement and there access levels
strictly."*

A Graphify-oriented investigation (2026-09-23) confirmed the backlog's **Existing behavior** section:

1. `TIER_ORDER`, `TIER_SERVICES` and `_cumulative_services()` (`apps/api/app/api/schools.py:798-839`,
   the backlog's `635-724` line numbers are stale) are referenced **only** by
   `GET /school/entitlements` (`schools.py:841`), a read-only report. No write endpoint checks
   `School.tier`.
2. `School.tier_valid_until` (`models.py:941`) is written by `create_school`/`update_school_tier`
   (`admin.py`) and echoed back, never compared to a date.
3. A route-level `Depends(require_tier(key))`, as the backlog suggested, cannot work for most gated
   routes: counselor/psychometric/academic/admin routes only learn the school after loading a student,
   record or batch, and several derive the service key from the request body (`activity_type`,
   `test_type`, `module_type`).

## 2. Goals and non-goals

**Goals.** Every write endpoint whose action corresponds to a `TIER_SERVICES` key is rejected with `403`
for a school whose valid, cumulative tier does not include that key.

**Non-goals.**
- Changing `GET /school/entitlements` in any way (acceptance criterion).
- Changing `TIER_ORDER`/`TIER_SERVICES`/`_cumulative_services()` content or semantics.
- Tier-change (upgrade/downgrade) handling — `ENH-023`.
- A "dedicated counselor" concept or gating staff assignment — deferred to a new backlog item (§3 D6).
- Proactive tier-aware UI (hiding/disabling actions) — §3 D8.
- Gating reads.
- Any schema change or migration.

## 3. Decisions confirmed in-session (2026-09-23) — `DEC-SCOPE-027` (provisional number)

The number is provisional: if another branch lands `DEC-SCOPE-027` first, it is renumbered on merge, per
the `DEC-SCOPE-024`/`025` precedent in `PRODUCT_DECISION_REGISTER.md`.

| # | Question | Decision (user, `EXPLICIT_APPROVAL`) |
|---|---|---|
| D1 | Strictness | **Hard `403`.** No soft-warn mode. |
| D2 | Expired `tier_valid_until` | Treated as **no tier**. The valid-until date itself is still valid (inclusive). `NULL` = no expiry. |
| D3 | Which operations | **All writes** (create, update, delete, attendance, scores) on tier-gated records. Reads stay open. |
| D4 | Admin/overseas actors | **Gated too** — entitlement belongs to the school, regardless of who acts. |
| D5 | Career-counselor records | All three `record_type`s (`guidance_session`, `counselling_note`, `recommendation`) = `individual_counselling` (Silver+). |
| D6 | Dedicated counselor | Platinum schools may have a dedicated counselor; other schools use shared counselors. No model for "dedicated" exists — **deferred to its own backlog item**; staff assignment stays ungated in ENH-022. |
| D7 | Free-text activity (no `activity_type`) | Requires **any valid tier** (a tier-less or expired school cannot create one). |
| D8 | Frontend | **Server `403` + existing error display only.** No proactive hiding. |
| D9 | Bridged overseas scope | Gate **creating a bridged application** (`application_support`) and **creating/updating a VisaCase on a bridged application** (`visa_support`). Other overseas-workflow writes stay ungated. |
| D10 | Expiry calendar | **India date** (`Asia/Kolkata`). |

## 4. Approach

**Chosen: one async helper in `schools.py`, called inside each gated handler** once the school and
service key are known, before the first `db.add`.

- Sits beside the `TIER_*` constants it reuses; no new module.
- Follows the existing import pattern: `school_skills.py`, `portfolio.py`, `school_transfers.py` import
  helpers from `app.api.schools`; `admin.py` already lazily imports from it inside handlers. `workflows.py`
  uses the same lazy-import form.
- No new dependency: `zoneinfo.ZoneInfo("Asia/Kolkata")` is already used in `communications.py`.

**Rejected.**
- *Route dependency `Depends(require_tier(key))`* — only works where the school is on the user's own
  profile (coordinator routes); would need a second mechanism for everything else.
- *Middleware / path→key map* — cannot see body-derived keys and hides the check from the handler reader.

## 5. The helper

```python
# apps/api/app/api/schools.py, beside TIER_ORDER / TIER_SERVICES / _cumulative_services (unchanged)

def _today_ist() -> date: ...            # datetime.now(ZoneInfo("Asia/Kolkata")).date(); patchable in tests

def _minimum_tier(service_key: str) -> str: ...   # first TIER_ORDER entry whose TIER_SERVICES lists the key;
                                                  # ValueError for an unknown key

def _entitlement_denial(tier: str | None, valid_until: date | None, service_key: str | None, today: date) -> str | None:
    """Pure: the 403 message, or None if allowed. service_key=None means 'any valid tier'."""

async def require_school_entitlement(db: AsyncSession, school_id: UUID, service_key: str | None) -> None:
    """ENH-022 / DEC-SCOPE-027: raise HTTPException(403, message) unless allowed."""
```

**Evaluation order inside `_entitlement_denial`.**
1. `service_key` not `None` and not in any tier → `ValueError` (programming error: a mis-wired key must
   fail loudly in tests, never become a silent permanent `403`).
2. `tier` is `None` or not in `TIER_ORDER` → *no tier* message.
3. `valid_until` is not `None` and `valid_until < today` → *expired* message.
4. `service_key` not `None` and not in `{k for k, _ in _cumulative_services(tier)}` → *not included*
   message.
5. Otherwise `None`.

`require_school_entitlement` loads the school with `db.get(School, school_id)` (identity-map cached if the
session already holds it). A missing school yields the *no tier* message — unreachable in practice because
every call site has already scope-checked the school, but never a `500`.

### 5.1 Stable `403` `detail` strings

| Case | `detail` |
|---|---|
| No tier / unknown tier | `This school has no active partnership tier.` |
| Expired | `This school's partnership expired on {DD Mon YYYY}.` (e.g. `30 Jun 2026`, `%d %b %Y`) |
| Not included | `This school's {Tier} partnership does not include {label} (requires {MinTier} or higher).` |

`{Tier}`/`{MinTier}` are capitalised tier names (`Bronze`…`Platinum`); `{label}` is the `TIER_SERVICES`
label, so the wording matches the entitlements page. For a `service_key=None` check only the first two
messages can occur.

## 6. API contract

- **Error shape:** FastAPI `{"detail": "<string>"}`, as every implemented route (`API_CONTRACT.md` §0.3's
  `error_code` shape is implemented nowhere; not introduced here).
- **Status:** `403` (authenticated, not entitled). `402` rejected (reserved, unused); `404` rejected
  (misrepresents existence).
- **Check order per handler:** role check → scope check (existing `403`/`404`, unchanged) → validation of
  the *key-deciding field only* (`422`) → **tier (`403`)** → remaining validation (`422`) → write.
  Consequences: an out-of-scope caller sees exactly today's response and never learns another school's
  tier; a request that can never succeed is told so before being asked to fix other fields.
- **PATCH/PUT/DELETE derive the key from the stored record** (record `test_type`, batch `module_type`,
  activity `activity_type`, application `school_student_id`) — never from the body.
- **Backward compatibility:** the only change is a new `403` on existing write routes. Request bodies,
  success responses and existing error strings are unchanged. Documented as an `API_CONTRACT.md` addendum.
- **Idempotency:** a tier `403` is deterministic and writes nothing — retry-safe. No `Idempotency-Key`
  (§0.2, not financial).

## 7. Gated endpoints

| Endpoint (file) | Service key | Key / school source |
|---|---|---|
| `POST /school/activities` (`schools.py`) | `activity_type` → key (`campus_visit` → `monthly_campus_visits`; other three map 1:1); absent → any valid tier | body, after `activity_type` validation; school from `_own_school_id` |
| `POST /school/activities/{id}/attendance` (`schools.py`) | same mapping on the stored activity's `activity_type` | stored activity |
| `POST /school/career-counselor/records` (`schools.py`) | `individual_counselling` | school from `_student_in_portfolio` |
| `POST`, `PATCH /school/psychometric-team/records[/{id}]` (`schools.py`) | `psychometric_test` | student / record's student |
| `POST`, `PATCH /school/academic-team/test-prep-records[/{id}]` (`schools.py`) | `ielts_coaching` / `sat_coaching` | body `test_type` (POST, after its validation); stored `test_type` (PATCH) |
| `POST`, `PATCH /school/academic-team/language-records[/{id}]` (`schools.py`) | `foreign_language_classes` | student / record's student |
| Skills: `POST skill-batches`, `PATCH skill-batches/{id}`, `POST skill-batches/{id}/enrollments`, `PATCH skill-enrollments/{id}`, `POST skill-batches/{id}/sessions`, `PUT skill-sessions/{id}/attendance`, `POST skill-batches/{id}/assessments`, `PUT skill-assessments/{id}/scores` (`school_skills.py`) | `USAGE_KEYS[module_type]` (`soft_skills` → `soft_skills`, `digital_skills` → `web_designing`) | body `school_id`/`module_type` on create (after the existing portfolio check); stored batch otherwise — checked **after** `_batch_in_portfolio(lock=…)` so lock order is unchanged |
| Portfolio: `POST …/portfolio/entries`, `PATCH …/entries/{id}`, `DELETE …/entries/{id}`, `PATCH …/personal-statement` (`portfolio.py`) | `digital_portfolio_creation` | student's school, after `_require_portfolio_write` |
| `POST /overseas-admin/school-students/{id}/applications` (`admin.py`) | `application_support` | the `SchoolStudent`'s school, after the student lookup |
| `POST /workflows/overseas/visa`, `PATCH /workflows/overseas/visa/{id}` (`workflows.py`) | `visa_support` **only when** `application.school_student_id` is set | application → `SchoolStudent` → school; ordinary overseas applications unaffected |

**Not gated:** student/roster, bulk upload, promotions, transfers, parent links, team/invites, academic
results (not a `TIER_SERVICES` key), staff assignment (D6), every `GET`, and `GET /school/entitlements`.

## 8. Transactions, concurrency, data

- **Transactions:** the check is a read in the request's existing session, placed before any
  `db.add`/`flush`. A `403` leaves nothing written, no audit row, no notification. No new commit points.
- **Race with a concurrent tier change:** the school row is read without a lock; a gated action racing
  an `update_school_tier` commit observes one committed value or the other. Accepted for v1 per the
  backlog; `ENH-023` may add `FOR SHARE` if downgrade handling needs strict ordering.
- **Database:** one primary-key read per gated request; no index, no migration, no data change.
- **Pre-deploy data risk:** any existing school with `tier IS NULL` or `tier_valid_until < today` loses
  write access to every gated service on deploy. Release step: run a read-only query listing such schools
  and confirm with the business before release. Seed data (Platinum, valid one year) is unaffected.

## 9. Frontend

No new screens, calls or tier logic (D8). Each affected panel's existing error area must render the
server's string `detail`: `SchoolActivitiesPanel`, `SchoolCareerRecordsPanel`,
`SchoolPsychometricRecordsPanel`, `SchoolTestPrepLanguagePanel`, the skills components
(`SchoolSkillBatchForm`, `SchoolSkillEnrolments`, `SchoolSkillAttendance`, `SchoolSkillScores`,
`SchoolSkillBatchHeader`), `PortfolioPanel`/`PortfolioEntryForm`, `AdminSchoolApplicationsPanel`, and the
visa-case callers of `/workflows/overseas/visa` (`CounselorVisaPanel`, `VisaChecklistPanel`,
`WorkflowPanel`). A panel that replaces a `403` string with a generic message is fixed minimally using
`detailMessage()` from `apps/web/lib/apiErrors.ts`; loading/empty states are untouched. A `403` writes
nothing, so the form keeps the user's input.

## 10. Error states and edge cases

| Case | Behavior |
|---|---|
| `tier = NULL` (allowed by `create_school`) | Every gated write → *no tier* `403`, including free-text activities (D7). |
| `tier` holds an unexpected string | Treated as no tier (matches `_cumulative_services` returning `[]`). |
| `tier_valid_until = today (IST)` | Allowed. |
| `tier_valid_until = yesterday (IST)` | *Expired* `403` for every gated write. |
| UTC just before / after 18:30 on the valid-until date | Allowed / expired (IST midnight boundary). |
| Platinum school, Bronze service | Allowed (cumulative). |
| PATCH body tries to change the key-deciding field | Key still comes from the stored record. |
| Visa case on a non-bridged application | Unchanged behavior. |
| Expired school calls `GET /school/entitlements` | **Unchanged** — still lists services; logged as a follow-up (§13). |

## 11. Acceptance criteria (local IDs)

- **AC-1** Every §7 route returns `403` with the §5.1 *not included* string when the school's valid tier
  is below the key's minimum tier, and succeeds at exactly the minimum tier.
- **AC-2** Every §7 route returns the *no tier* `403` for a tier-less school.
- **AC-3** Every §7 route returns the *expired* `403` when `tier_valid_until` is before the IST date; the
  valid-until date itself is allowed; `NULL` never expires.
- **AC-4** On any tier `403`, no row, audit log or notification is written.
- **AC-5** Out-of-scope callers receive exactly the pre-ENH-022 status and `detail`.
- **AC-6** PATCH/PUT/DELETE routes derive the key from the stored record.
- **AC-7** Visa writes on a non-bridged application and all non-§7 routes behave exactly as before.
- **AC-8** `GET /school/entitlements` responses are byte-for-byte unchanged, including for an expired
  school.
- **AC-9** Each affected panel shows the `403` `detail` string as a `role="alert"` beside the form that
  failed, keeps the user's input, and never leaves its submit button stuck after a network failure (§9).
- **AC-10** An unknown service key passed to the helper raises `ValueError`.

## 12. Regression risks and test plan (written before code)

**Risks.** (1) Existing tests/specs create tier-less schools and will start receiving `403`s. (2) A wrong
key mapping blocks an entitled action — mitigated by AC-1's minimum-tier success case per route and
AC-10. (3) `digital_skills` ≠ `web_designing` — reuse `USAGE_KEYS`, never `module_type` directly.
(4) Parent timeline, Student 360 and portfolio view read gated data — reads are not gated (D3).
(5) Tier-less production schools (§8).

**Tests.**
1. *Unit* (`tests/test_enh_022_tier_enforcement.py`): `_entitlement_denial` truth table — tier-less,
   unknown tier, minimum tier passes, one below fails, cumulative, expired/today/NULL, `service_key=None`,
   exact message strings; `_minimum_tier`; unknown key → `ValueError`; IST boundary via patched
   `_today_ist`.
2. *Integration* (same file): per §7 route — minimum tier succeeds; one tier below `403` + exact
   `detail`; tier-less `403`; expired `403`; row and `AuditLog` counts unchanged on `403`; out-of-scope
   caller unchanged. Plus: PATCH key from stored record; free-text activity on any valid tier vs.
   tier-less; visa on non-bridged application unchanged.
3. *Regression pin:* `/school/entitlements` for an expired Gold school returns the same body as before.
4. *Existing-test setup:* fixtures of suites that hit §7 routes (`test_sch_004`, `005`, `007`, `008`,
   `009`, `010`, `test_enh_012`, `enh011_helpers`, bridged-application fixtures in `test_ovs_*`/
   `test_visa_*`) set `tier="platinum"`. No assertion changes. `test_sch_011` untouched.
5. *E2E:* existing specs that create a school through the admin form (`sch-004-005-006`, `sch-007`,
   `sch-008`, `sch-009`, `sch-010`, `enh-002`, `enh-011`, `enh-012`) select **Platinum**; new
   `enh-022-tier-enforcement.spec.ts`: Bronze coordinator's campus-visit activity shows the `403` message,
   a career seminar succeeds.
6. *Frontend component tests:* per §9, one file per changed panel.
7. *Runs:* new + affected suites per task; full backend and E2E suites once at the end (justified: the
   change spans every School service).

## 13. Documentation deliverables

- `PRODUCT_DECISION_REGISTER.md`: `DEC-SCOPE-027` (D1–D10).
- `API_CONTRACT.md`: ENH-022 addendum (routes, `403` strings, check order).
- `RBAC_MATRIX.md`: tier as an additional authorization dimension on the §7 actions.
- `RTM.md` and `ENHANCEMENT_BACKLOG.md`: ENH-022 status; two new follow-up items —
  (a) dedicated-counselor model and enforcement (D6), (b) `/entitlements` reflecting expiry.

## 14. Open items

None blocking. Follow-ups are listed in §13.
