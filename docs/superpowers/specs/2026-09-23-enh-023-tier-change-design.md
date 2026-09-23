# ENH-023 — Partnership Tier Change (Upgrade/Downgrade) Workflow — Design

## 1. Problem (audit result, gap confirmed)

`docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-023 (`DERIVED_BLUEPRINT`). The user's instruction: *"hidden requirements as
well like change of gold to platinum etc."*

A Graphify-oriented investigation (2026-09-23, graph refreshed after `ENH-022`/`ENH-013` merged at `5d20295`) confirmed:

1. The only tier write is `update_school`, `PATCH /overseas-admin/schools/{school_id}` (`apps/api/app/api/admin.py`; the
   backlog's `950-969` line numbers are stale). It sets `tier`/`tier_valid_until` and writes one `school.tier_update`
   `AuditLog` row with metadata `{"tier": <new>}`, which has no old tier and no direction. The row is written whenever a
   tier field is present, even when nothing changed. No one is notified.
2. There is **no UI to change a tier** after creation. `AdminSchoolEditPanel.tsx` has no tier field; only
   `AdminSchoolCreatePanel.tsx` sets one.
3. `ENH-022` (merged, `DEC-SCOPE-027`) gates **every write** (D3) through `require_school_entitlement`
   (`schools.py`) on the school's *current* tier. After a downgrade, work already under way for a lost service can
   therefore no longer be updated, finished or scored.
4. `ENH-022`'s own tests model a downgrade by assigning `school.tier` directly and expect PATCH routes to return `403`
   (`test_enh_022_tier_enforcement.py:103,198,224,318`).
5. Principals and Overseas Admins have **no notifications page**. Only coordinators and parents do.
6. `TimestampMixin.created_at` and `AuditLog.created_at` use `server_default=func.now()`, which is the
   **transaction-start** time in PostgreSQL.

## 2. Goals and non-goals

**Goals.** A tier change is a recorded, notified business event. An upgrade tells the school what it gained. A downgrade
or removal is never silent and never destroys work already under way: that work can be finished, while new work for a
lost service is refused.

**Non-goals.**
- Changing `TIER_ORDER`/`TIER_SERVICES`/`_cumulative_services()`, `_entitlement_denial`, `ENH-022`'s `403` strings,
  its denial audit, or `GET /school/entitlements`.
- Treating `tier_valid_until` expiry as a downgrade, or adding any scheduler (D6).
- A tier-history table or any migration (D4).
- An Overseas Admin notifications page (follow-up, §13).
- Share-locking the school row in the 24 gated routes (§8).
- Gating or un-gating any route not listed in §6.

## 3. Decisions confirmed in-session (2026-09-23) — `DEC-SCOPE-029` (provisional number)

The number is provisional and will be renumbered on merge if another branch lands it first (`DEC-SCOPE-024`/`025`
precedent).

| # | Question | Decision (user, `EXPLICIT_APPROVAL`) |
|---|---|---|
| D1 | Relation to `ENH-022` | Built after `ENH-022` merged, against its real helper. |
| D2 | Downgrade policy | **Grandfather**: work under way for a lost service can be finished; new work for it is refused. |
| D3 | What counts as existing | A record whose `created_at` is before the downgrade that removed the service. No end date. |
| D4 | Transition history | Extend the `school.tier_update` `AuditLog` metadata. No new table, no migration. |
| D5 | Notification | The school's Coordinator(s) and Principal(s) get in-app plus email; the acting admin also gets a copy. |
| D6 | Removal / expiry | `tier → null` is a downgrade (grandfathered and notified). Expiry is not; it stays `ENH-022` D2 (no tier, no notification). |
| D7 | UI | Tier and valid-until fields in `AdminSchoolEditPanel`; a downgrade shows an inline confirmation step listing lost services. |
| D8 | Child writes under old work | **Completion only.** Updates, attendance, scores, sessions and assessments on existing work are allowed; new enrolments, visa cases, bridged applications and portfolio entries are refused. |
| D9 | Unreachable notifications | Add a Principal notifications page. The acting admin gets the in-app row plus email (no admin page in this item). |
| D10 | Grandfather mechanism | **Approach A**: the downgrade time is read from the `school.tier_update` audit rows (§5). |
| D11 | No-op and valid-until-only changes | Still audited (as today), with `direction="unchanged"`; **no notification**. |

## 4. The tier change

### 4.1 `_tier_transition` (new, pure, `schools.py` beside `_cumulative_services`)

```python
def _tier_transition(old: str | None, new: str | None) -> tuple[str, list[str], list[str]]:
    """(direction, gained keys, lost keys). Built only from _cumulative_services, so tier ordering lives in one place.
    An unknown or None tier counts as no services."""
```

`direction` is `upgrade` when `gained` is non-empty, `downgrade` when `lost` is non-empty, else `unchanged`. The tiers
are cumulative, so a change is never both. Key order follows `TIER_SERVICES`.

| old → new | direction | gained | lost |
|---|---|---|---|
| `None → bronze` | upgrade | Bronze's 5 | — |
| `gold → platinum` | upgrade | Platinum's 7 | — |
| `platinum → gold` | downgrade | — | Platinum's 7 |
| `silver → None` | downgrade | — | Bronze's 5 + Silver's 2 |
| `gold → gold`, `None → None` | unchanged | — | — |

### 4.2 `PATCH /overseas-admin/schools/{school_id}` (`update_school`, `admin.py`)

1. The role check is unchanged. The school is loaded with `select(School).where(School.id == school_id).with_for_update()`
   instead of `db.get`, so concurrent tier changes queue (§8). An unknown school still gets `404`.
2. Tier validation is unchanged (same `422` message).
3. When `tier` or `tier_valid_until` is in the body, exactly one `school.tier_update` row is written (as today), with
   `created_at=func.clock_timestamp()` and metadata:

   ```json
   {"tier": "<new>", "from_tier": "<old|null>", "to_tier": "<new|null>", "direction": "upgrade|downgrade|unchanged",
    "gained": ["<key>", ...], "lost": ["<key>", ...],
    "tier_valid_until": "<ISO date|null>", "previous_tier_valid_until": "<ISO date|null>"}
   ```

   The `"tier"` key is kept for existing readers. When only `tier_valid_until` is sent, `from_tier == to_tier` and
   `direction == "unchanged"`.
4. The profile-field path and its `school.profile_update` row are unchanged.
5. One `await db.commit()`, as today. Notifications (§4.4) are sent only after it, and only when
   `direction != "unchanged"`.
6. Response: the existing `SchoolOut` body **plus** one additive field:

   ```json
   "tier_change": {"direction": "...", "from_tier": "...", "to_tier": "...",
                   "gained": [{"key": "...", "label": "..."}], "lost": [{"key": "...", "label": "..."}]}
   ```

   `tier_change` is `null` when the body carried neither `tier` nor `tier_valid_until`. Labels come from
   `SERVICE_LABELS`.

### 4.3 `GET /overseas-admin/schools/{school_id}/tier-change-preview?tier=<tier>` (new, read-only)

- Same role check as the PATCH (`403`). Unknown school → `404`. `tier` is optional and empty/absent means removal.
  Any other value outside `TIER_ORDER` → `422` with the PATCH's message.
- Returns the §4.2 `tier_change` object computed from the school's current tier. It writes nothing and takes no lock.

### 4.4 Notifications

- **Recipients:** active users with `role in {"school_coordinator", "school_principal"}` and
  `profile["school_id"] == str(school.id)` (the query form already used in `admin.py`), plus the acting admin.
- **Channel:** reuse `schools._notify_parent(db, user, school_name=…, title=…, body=…, action_url=…)`. It writes the
  in-app `Notification`, attempts the SMTP email with the webhook fallback, and records a `NotificationDelivery`. It
  takes any `User`; a short comment at the call site notes this.
- **After commit, failure-isolated:** every recipient is tried in its own `try` / `commit` / `rollback`, following
  `school_skills._notify_after_commit`. A failure logs `logger.warning("tier_change_notification_failed", …)` with
  IDs only and never fails or undoes the tier change.
- **Content** (labels from `SERVICE_LABELS`; tier names capitalised; removal shown as "no partnership tier"):

| Case | Title | Body | `action_url` |
|---|---|---|---|
| Upgrade (school) | `Your partnership is now {To}` | `{School} has moved from {From} to {To}. Newly available: {labels}.` | `/school/coordinator/entitlements` or `/school/principal/entitlements` |
| Downgrade / removal (school) | `Your partnership changed from {From} to {To}` | `These services are no longer available for new work: {labels}. Work already started for them can still be completed.` | as above |
| Admin copy | `Tier change recorded: {School}, {From} → {To}` | The same list as the school received | `None` |

## 5. Grandfathering in the enforcement check

`require_school_entitlement` gains one keyword-only argument:

```python
async def require_school_entitlement(db, user, school_id, service_key, *, grandfathered_since: datetime | None = None) -> None:
```

With the argument omitted, behaviour is byte-for-byte `ENH-022`'s. With it, a would-be denial is overturned **only if**
all of these hold:

1. The denial reason is `not_included` or `no_tier`. An `expired` denial is never overturned (D6).
2. `school.tier_valid_until` is `None` or not before `_today_ist()`. This covers a removal on an already-expired school.
3. Some `AuditLog` row with `action == "school.tier_update"`, `entity_id == str(school_id)` and
   `created_at > grandfathered_since` has metadata where:
   - `service_key` is in `lost`, when `service_key` is not `None`;
   - `to_tier` is `None` and `direction == "downgrade"`, when `service_key` is `None` (a free-text activity, `ENH-022`
     D7).

   Rows written before this item have no `lost`/`direction` keys and never match.

The lookup runs only on the would-be-denial path. It filters on the indexed `action` column and on `entity_id` in SQL,
then inspects the metadata in Python, so no JSON operators and no migration are needed. On a grandfathered allow it
logs `logger.info("tier_grandfathered", extra={"extra_fields": {actor_id, role, school_id, service_key}})`, returns,
and writes **no** denial row. On a real denial the `ENH-022` path (denial audit, commit, `logger.warning`, `403`) is
unchanged. A database error in the lookup propagates, so the check fails closed.

**Consequence (deliberate):** a tier change made directly in the database (seed data, tests) leaves no transition row
and so grandfathers nothing. `ENH-022`'s tests keep passing unchanged (AC-13).

**Operational constraint:** `school.tier_update` rows are now read by business logic and must not be pruned.

## 6. Routes

`grandfathered_since` is passed only by the routes that finish existing work (D8). `_require_module_entitlement`
(`school_skills.py`) and `_require_bridged_visa_entitlement` (`workflows.py`) gain the same optional keyword and pass
it through.

| Route (file) | `grandfathered_since` = `created_at` of |
|---|---|
| `POST /school/activities/{id}/attendance` (`schools.py`) | the activity |
| `PATCH /school/psychometric-team/records/{id}` (`schools.py`) | the record |
| `PATCH /school/academic-team/test-prep-records/{id}` (`schools.py`) | the record |
| `PATCH /school/academic-team/language-records/{id}` (`schools.py`) | the record |
| `PATCH skill-batches/{id}`, `POST skill-batches/{id}/sessions`, `POST skill-batches/{id}/assessments` (`school_skills.py`) | the batch |
| `PUT skill-sessions/{id}/attendance`, `PUT skill-assessments/{id}/scores` (`school_skills.py`) | the session's / assessment's batch |
| `PATCH skill-enrollments/{id}` (`school_skills.py`) | the enrolment |
| `PATCH`, `DELETE …/portfolio/entries/{id}` (`portfolio.py`) | the entry |
| `PATCH …/portfolio/personal-statement` (`portfolio.py`) | the existing `PortfolioProfile` row; `None` if there is none yet |
| `PATCH /workflows/overseas/visa/{id}` (`workflows.py`) | the visa case |

**Unchanged (fully gated on the current tier):** `POST /school/activities`, career-counselor record create,
psychometric / test-prep / language record create, skill-batch create, `POST skill-batches/{id}/enrollments`, portfolio
entry create, bridged-application create (`admin.py`), visa-case create, and `PATCH …/career-goal` (a student
attribute, not a commitment).

Every anchor value is read from a row the route has already loaded and scope-checked, so the check order from
`ENH-022` §6 (role → scope → key-deciding validation → tier → remaining validation → write) and the skills lock order
are unchanged.

## 7. Frontend

### 7.1 `AdminSchoolEditPanel.tsx`

- `School` type gains `tier`, `tier_valid_until`. Two new fields: **Partnership tier** (`select`: Not set / Bronze /
  Silver / Gold / Platinum) and **Valid until** (`date`), prefilled from the looked-up school.
- Both join the existing diff-then-send logic. An untouched tier or date is not sent, so a profile-only save sends
  exactly what it sends today and writes no tier audit row.
- **Save flow:**
  1. If the tier is unchanged, the save is today's save.
  2. If the tier changed, the panel calls the preview endpoint first, with the button reading `Checking tier change…`.
     - **Upgrade:** it PATCHes straight away.
     - **Downgrade/removal:** it PATCHes nothing yet and renders a confirmation block inside the form, directly under
       the submit button: *"Downgrading {school} from {From} to {To}. These services will no longer be available for
       new work: {labels}. Work already started can still be completed. The school will be notified."* The block has
       **Confirm downgrade** (sends the same single PATCH, profile edits included) and **Cancel** (hides the block,
       keeps all input).
  3. The success message is built from the PATCH response's `tier_change`, never from the preview. It reads
     `School updated. Now {To}; newly available: …` for an upgrade and `School updated. Now {To}.` for a downgrade.
     A concurrent change by another admin is therefore reported truthfully.
- **Error states:**
  - A preview failure (network or `4xx`) shows the error and saves nothing; input is kept.
  - Save failures keep the existing messages.
  - Error-tone messages render with `role="alert"`; success keeps `role="status"`/`aria-live="polite"`.
  - `busy` resets on every path; all buttons are disabled while busy; a stale confirmation block is cleared on a new
    lookup.
  - Only existing classes are used; no CSS change.

### 7.2 `/school/principal/notifications` (new page)

- A copy of the coordinator notifications page with the `school_principal` role check (`accessDenied` otherwise),
  `SchoolNotificationList`, the same `GET /api/v1/workflows/notifications` feed (keyed on the signed-in user) and
  `accessUnavailable` for failures.
- Empty text: `No notifications yet. You will be told here when your school's partnership changes.`
- `SCHOOL_NAV.principal` gains `notifications`. There is no loading file, matching the existing notifications pages.
- The coordinator page's empty text gains `… or your school's partnership changes.`

**Unchanged:** both entitlements pages, `AdminSchoolCreatePanel`, CSS.

## 8. Transactions, concurrency, data

- **Tier change:** the school row lock, the attribute changes, the audit row and any profile audit row share one
  transaction and one commit. Notifications run afterwards, each in its own commit.
- **Concurrent tier changes:** `FOR UPDATE` serialises them. The second reads the first's committed tier, so its
  `from_tier` is correct (AC-10).
- **Tier change vs. a gated write** (READ COMMITTED; gated writes read the school without a lock, per `ENH-022` §8):
  - A write that reads the school after the downgrade commits sees the new tier: new work is refused, existing work is
    grandfathered.
  - A write whose transaction started earlier and read the old tier keeps a `created_at` (its transaction start)
    earlier than the downgrade row's `clock_timestamp()`, which is taken after the lock. That record is therefore
    grandfathered.
  - **Residual window (accepted, documented):** a create whose transaction starts in the microseconds between the
    audit row's insert and the downgrade's commit, and still reads the old tier, gets a `created_at` later than the
    downgrade row. Later updates to that one record are then refused. Closing this needs a share lock in all 24 gated
    routes, which is out of scope and listed as a follow-up.
- **Database:** no migration, no backfill; existing rows are untouched. Old `school.tier_update` rows remain valid and
  simply never grandfather anything.

## 9. Error states and edge cases

| Case | Behavior |
|---|---|
| PATCH: unknown tier / unknown school / wrong role | Unchanged `422` / `404` / `403` |
| Preview: wrong role / unknown school / unknown tier | `403` / `404` / `422`; writes nothing |
| Same tier re-sent; only `tier_valid_until` sent | Audit row with `direction="unchanged"`; `tier_change` returned; no notification |
| Profile-only PATCH | `tier_change: null`; no tier audit row |
| School with no coordinator/principal account | Only the admin copy is sent; the change still succeeds |
| Notification send fails | Change stays committed; warning logged; `NotificationDelivery` records the failure |
| Downgrade then re-upgrade | Two audit rows, both kept (history is never collapsed) |
| Lost, regained, lost again | A record created before the latest loss is grandfathered |
| Downgraded school later expires | Grandfathered writes are refused (`expired`) |
| Grandfather lookup errors | Propagates (`500`); never allows |
| Personal statement never saved before the downgrade | No `PortfolioProfile` row, so no anchor: refused (new work) |

## 10. Acceptance criteria (local IDs)

- **AC-1** Upgrade through the PATCH writes one `school.tier_update` row with `from_tier`, `to_tier`,
  `direction="upgrade"` and `gained`. Each active Coordinator and Principal of the school and the acting admin get one
  in-app `Notification` plus one email `NotificationDelivery`, listing the gained labels.
- **AC-2** Downgrade and removal: as AC-1, with `direction="downgrade"`, `lost`, and the completion sentence.
- **AC-3** A same-tier or valid-until-only PATCH writes the audit row with `direction="unchanged"` and no notification.
- **AC-4** The PATCH response adds `tier_change` and every pre-existing field is unchanged. A profile-only PATCH returns
  `tier_change: null` and writes no tier audit row.
- **AC-5** The preview returns the correct `tier_change`, enforces `403`/`404`/`422`, and writes nothing.
- **AC-6** Every §6 grandfathered route succeeds on a record created before a PATCH downgrade that lost its service,
  and writes no `school.tier_access_denied` row.
- **AC-7** A record created after the downgrade, and any record under a direct-database tier change, still gets
  `ENH-022`'s `403`. At least one create route per module is still refused after a downgrade.
- **AC-8** An expired school is refused even on a grandfathered record.
- **AC-9** A downgrade followed by a re-upgrade leaves two distinct audit rows.
- **AC-10** Two concurrent PATCHes serialise; the second's `from_tier` equals the first's `to_tier`.
- **AC-11** A failing notification send never fails or rolls back the tier change.
- **AC-12** Panel: an upgrade saves without confirmation; a downgrade shows the lost labels and saves only on
  **Confirm**; **Cancel** keeps input; preview and save failures render `role="alert"`; no button is left disabled.
- **AC-13** `test_enh_022_tier_enforcement.py` passes without edits.
- **AC-14** The Principal notifications page lists the principal's notifications, shows the empty text, and refuses
  other roles.

## 11. Regression risks

1. `test_sch_003_school_onboarding.py` (3 tests near `:427-489`) assert tier metadata equals exactly `{"tier": …}`.
   These assertions change to the §4.2 shape. This is the D4 contract change, recorded in `API_CONTRACT.md`, not
   product behaviour bent to pass a test.
2. `AdminSchoolEditPanel.test.tsx` asserts the exact PATCH body. An untouched tier/date must stay absent.
3. `sch-003-school-onboarding.spec.ts` and `sch-011-entitlements.spec.ts` drive these forms.
4. The admin audit viewer and export show the richer metadata (additive), to be checked visually.
5. A `grandfathered_since` wrongly added to a create route would let new work through. AC-7 covers each module.
6. `ENH-022`'s suite must stay green unchanged (AC-13).

## 12. Test plan (written before code)

1. *Unit* (`tests/test_enh_023_tier_change.py`): the §4.1 `_tier_transition` truth table. The grandfather decision:
   lost after the anchor / before it; legacy rows without `lost`; expired; removal with `service_key=None`;
   `grandfathered_since=None` equals `ENH-022` behaviour.
2. *Integration* (same file): AC-1 to AC-11. One test per §6 grandfathered route (downgrade via the PATCH, then the
   write succeeds), plus one create route per module refused. AC-10 uses two sessions, following
   `test_enh_011_concurrency.py`. AC-11 patches the mailer to raise.
3. *Existing-test updates:* the §11.1 assertions only.
4. *Frontend* (Vitest + Testing Library): `AdminSchoolEditPanel.test.tsx` extended for AC-12, and a new
   `SchoolPrincipalNotificationsPage.test.tsx` for AC-14.
5. *E2E* (`enh-023-tier-change.spec.ts`): the admin downgrades a Platinum school to Gold through the confirmation step,
   then its coordinator and principal each see the notification.
6. *Runs:* every new and affected suite runs for real per task (`ENH-022`, `SCH-003`, `SCH-011`, the panel, and the
   skills/portfolio/visa suites touched by §6). Full backend/E2E regression follows the every-3-to-4-features cadence;
   the plan records whether ENH-023 is that point.

## 13. Documentation deliverables and follow-ups

- `PRODUCT_DECISION_REGISTER.md`: `DEC-SCOPE-029` (D1–D11).
- `API_CONTRACT.md` §12A: the PATCH's `tier_change` and new audit metadata, the preview endpoint, and the
  `ENH-022` helper's grandfather rule.
- `RBAC_MATRIX.md`: the grandfather rule on the §6 actions.
- `RTM.md`, `ENHANCEMENT_BACKLOG.md` (ENH-023 status), `SCREEN_CATALOG.md`/`screen_catalog.json`,
  `ROLE_NAVIGATION.md` (principal notifications).
- Follow-ups: (a) an Overseas Admin notifications page; (b) closing the §8 residual race with a share lock;
  (c) notifying schools ahead of `tier_valid_until` expiry.

## 14. Security review

| Area | Finding | Consequence |
|---|---|---|
| Authorization | PATCH and preview keep the Overseas Admin/Super Admin check; the preview reveals only one school's tier to the same roles that can already read and edit it. | No new exposure. |
| Grandfather bypass | The anchor is always a server-loaded, scope-checked row's `created_at`, never request input; create routes never pass it. | A client cannot claim to be finishing existing work. |
| Tier oracle | Scope checks still precede the tier check (`ENH-022` §6); grandfathering runs inside the same position. | Unchanged. |
| Fail-closed | Lookup errors propagate; expired is never grandfathered; unknown metadata never matches. | No path allows on error. |
| Notification content | Titles and bodies are built from server constants and the school name; `_notify_parent`'s email escapes them (`mailer.py`). React renders the in-app text. | No XSS. |
| Sensitive logs | Log fields are IDs, role, service key and direction only. | No PII. |
| Audit integrity | Transition rows become business inputs; they are append-only via the ORM and never updated. | Retention constraint noted (§5). |
