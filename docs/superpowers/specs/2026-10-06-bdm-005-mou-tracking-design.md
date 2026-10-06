# bdm-005 — MoU tracking: design

- **Feature ID:** `bdm-005` (`BDM_CRM_BACKLOG.md` §4 bdm-005)
- **Decision:** `DEC-SCOPE-074` (owner, in-session 2026-10-06, `EXPLICIT_APPROVAL`)
- **Evidence:** `EVID-016` (`functionalities/edusphere_markdown/BDM Functionalities.md`, `DERIVED_BLUEPRINT`) §10 lines 339–369,
  Agent §B / School §B / College §B (Agreement, MoU, Contract, Renewal Date); `DEC-SCOPE-055` D19 (Q-10), D28 (Q-19);
  `DEC-SCOPE-065` P11; `DEC-SCOPE-071` (bdm-004). Impact analysis 2026-10-06 (graphify-led).
- **Branch:** `feature/bdm-005`, migration `0076_bdm_mous` (after `0075_telecaller_profiles`).

## 1. Scope

In: one MoU record per organization at a time (history kept), the 9 source statuses, dates, reference, notes, one confidential
document, a status/field history, the D28 pipeline advance, an MoU card on both organization detail pages, `/bdm/mous` and
`/bdm/manager/mous` lists, nav items.

Out: reminders (bdm-012 reads `status`, `status_changed_at` and `valid_until`; Q-10 timings live there); dashboard counts (bdm-023);
the `schools.mou_reference` / `partnership_date` columns (unchanged until bdm-018); the `/local-files` mount (residual risk, §7).

## 2. Approaches considered

- **A (chosen):** new `bdm_mous` + append-only `bdm_mou_events`, flat `app/api/bdm_mous.py` + `app/services/bdm_mous.py` (the
  codebase has no route packages), the document as columns on the MoU row, streamed download. Nothing existing changes shape.
- **B:** MoU columns on `bdm_organizations` with history in `bdm_pipeline_events` — rejected: widens bdm-004's event CHECKs, loses old
  MoUs on renewal, grows every organization response.
- **C:** reuse the student / agent document tables for the file — rejected: wrong domain, couples BDM scope to Agent CRM code.
- **Expiry job:** rejected for now (no BDM beat schedule before bdm-012); expiry is computed on read and cannot drift.

## 3. Decisions (owner answers 2026-10-06)

- **M1** All three BDM types (agent, school, college) track MoUs.
- **M2** Status moves are free among the 8 settable statuses; date rules still apply. `Expired` is never stored or settable: a
  `signed` or `active` MoU whose `valid_until` is before today (Asia/Kolkata) reads `expired`. Rejected re-opens by moving to another
  status.
- **M3** Writes: the assigned BDM and `super_admin` (bdm-002's `can_edit`). Reads and downloads follow organization scope
  (`caller_scope`: a BDM sees their type, a manager their team, super_admin all). Out of scope = 404; every download is audited.
- **M4** Document: PDF / JPEG / PNG decided by the bytes, `settings.max_upload_bytes`, image metadata stripped; one current file per
  MoU; a replace keeps the old object (its key is kept in the event row, never returned).
- **M5** D28: Signed advances the pipeline to the type's signed stage only when the organization is before it (one `move` event with
  a fixed note, same transaction); at or past it, nothing. A Lost organization refuses every MoU write (409 `organization_lost`);
  archived refuses (409, bdm-002's message).
- **M6** Renewal: a new row; at most one current MoU per organization (partial unique index). A new MoU can be started only when
  there is none, or the current one reads Expired or Rejected; the old row becomes not current and keeps its history.
- **M7** Both `signed` and `active` expire.
- **M8** Upload rate limit: 20 uploads per user per rolling hour → 429 with `Retry-After` (audit-row count, the AGN-009 pattern).
- **M9** An Expired MoU refuses a status change (409 `mou_expired`, "Start a renewal") but accepts date / reference / notes
  corrections and a document; each is recorded with its effective from → to status.

## 4. Catalogue

The status constants live in `app/models.py` (as every BDM catalogue); the stage map in `app/bdm_stages.py`:

| key | label (source, exact) | settable |
|---|---|---|
| `prospect` | Prospect | yes |
| `discussion_started` | Discussion Started | yes |
| `proposal_sent` | Proposal Sent | yes |
| `under_negotiation` | Under Negotiation | yes |
| `draft_shared` | Draft Shared | yes |
| `signed` | Signed | yes |
| `active` | Active | yes |
| `expired` | Expired | no (derived) |
| `rejected` | Rejected | yes |

`MOU_SIGNED_STAGE = {"agent": "agreement_signed", "school": "signed", "college": "mou_signed"}` (all manual stages of `PIPELINES`).

## 5. Data model — migration `0076_bdm_mous` (additive; no existing row read or written)

### 5.1 `bdm_mous` (model `BdmMou`, `TimestampMixin`)

| column | type | notes |
|---|---|---|
| `id` | uuid pk | |
| `organization_id` | uuid fk `bdm_organizations` RESTRICT | |
| `created_by_user_id` | uuid fk `users` RESTRICT | |
| `status` | varchar(20) | CHECK in the 8 settable keys |
| `status_changed_at` | timestamptz default now() | the reminder clock for bdm-012 |
| `proposal_sent_on`, `signed_on`, `valid_from`, `valid_until` | date null | `valid_until` = the renewal date |
| `reference` | varchar(100) null | |
| `notes` | varchar(2000) null | |
| `document_key` | varchar(200) null | server-generated `bdm-mous/<uuid4hex>`; never returned or logged |
| `document_content_type` | varchar(50) null | |
| `document_name` | varchar(255) null | display only |
| `document_uploaded_at` | timestamptz null | |
| `is_current` | boolean default true | |

CHECKs (`BDM_MOU_CHECKS`, repeated in the migration, equality asserted by a test):
- `ck_bdm_mous_status`: `status IN (...8...)`
- `ck_bdm_mous_window`: `valid_from IS NULL OR valid_until IS NULL OR valid_until >= valid_from`
- `ck_bdm_mous_signed_on`: `status NOT IN ('signed', 'active') OR signed_on IS NOT NULL`
- `ck_bdm_mous_active_window`: `status <> 'active' OR (valid_from IS NOT NULL AND valid_until IS NOT NULL)`
- `ck_bdm_mous_document`: `(document_key IS NULL) = (document_content_type IS NULL)`

Indexes: `uq_bdm_mous_current` unique `(organization_id) WHERE is_current`; `ix_bdm_mous_org` `(organization_id, created_at)`;
`ix_bdm_mous_status` `(status, valid_until)`.

### 5.2 `bdm_mou_events` (model `BdmMouEvent`, append-only)

`id`, `mou_id` fk RESTRICT, `actor_user_id` fk RESTRICT, `kind` varchar(10) CHECK in `created, status, updated, document, renewed`,
`from_status` varchar(20) null (effective status before; null on `created`), `to_status` varchar(20) (effective after), `changed`
JSON list of field names, `document_key` varchar(200) null (the replaced object's key, `document` kind only; never returned),
`position` bigint identity, `created_at`. Index `(mou_id, position)`.

### 5.3 Migration rules

The 0073 pattern: every create guarded (0001 builds a fresh DB from the models); offline SQL emits everything; `downgrade()` refuses
while any `bdm_mous` row exists.

## 6. Backend

### 6.1 Schemas (`schemas.py`, BDM section)

Text reuses the bdm-010 helpers: `reference` = `_trimmed(100)` + `_trip_text(_BDM_CONTROL, False, MOU_LABELS)`; `notes` =
`_trimmed(2000)` + multiline control check + `_bdm_newlines`; dates = `_trip_date` (YYYY-MM-DD, plain-words error), nullable.

- `BdmMouCreate` (`extra="forbid"`): `status` (settable `Literal`, default `prospect`), the four dates, `reference`, `notes`.
- `BdmMouUpdate` (`extra="forbid"`): every field optional; `status` requires `from_status` (9 keys) → 422 otherwise. Omitted = unchanged,
  `null` = clear.
- `BdmMouOut`, `BdmMouRow`, `BdmMouEnvelope {mou}`, `BdmOrgMouOut {current, can_start}`, `BdmMouPage`, `BdmMouEventOut`,
  `BdmMouEventPage`.

`BdmMouRow`: `id`, `organization {id, code, name, bdm_type}`, `assigned_bdm {id, full_name}`, `status`, `status_label`,
`status_changed_at`, `signed_on`, `valid_until`, `reference`, `has_document`, `is_current`.
`BdmMouOut` = row + `proposal_sent_on`, `valid_from`, `notes`, `document {name, content_type, uploaded_at} | null`, `expired_on`
(`valid_until + 1 day` when it reads Expired, else null), `created_by`, `permissions {can_edit, can_upload, can_renew}`,
`pipeline_on_sign {key, label} | null`, `created_at`, `updated_at`.

### 6.2 Service `app/services/bdm_mous.py` (functions only; never commits)

- `effective_status(mou, today)` / `effective_status_sql(today)`; `today()` = Asia/Kolkata date.
- `check_rules(state)` — the M2 date rules on the merged state → 422 naming the field (`signed_on`, `valid_from`, `valid_until`).
- `load_current(db, org, lock)`, `load_scoped_mou(db, user, mou_id)` (join to the organization under `caller_scope`; unknown and
  out-of-scope give the same 404 "MoU not found").
- `writable(user, org, route)` — `org_svc.require(can_edit)` then Lost → 409 `LOST_CONFLICT`.
- `record(db, user, mou, kind, from_status, to_status, changed, document_key=None)` + `audit(...)` (`bdm_mou.<action>`, entity
  `bdm_mou`, metadata: `org_id`, status keys, field names).
- `advance_pipeline(db, user, org)` → calls the new `bdm_pipeline.advance_to(db, user, org, stage, note)` (forward only; returns the
  from stage or None) and writes bdm-004's `stage_changed` audit row with `source: "mou"`.
- Document: `read_upload` reused from `services.agent_documents` (bytes-decided type, size cap, metadata strip); own `store` /
  `discard` under `bdm-mous/`; `upload_wait(db, user)` counts the caller's `bdm_mou.document_uploaded` audit rows in the last hour.
- `mou_out`, `row_out`, `list_page`, `history_page`.

### 6.3 Routes `app/api/bdm_mous.py` (prefix `/bdm`, registered in `main.py`)

| method + path | result |
|---|---|
| `GET /bdm/organizations/{org_id}/mou` | 200 `{current, can_start}` (`current: null` when none) |
| `POST /bdm/organizations/{org_id}/mou` | 201 `{mou}` — first MoU or renewal; 409 `mou_exists` when a current one is not Expired / Rejected |
| `PATCH /bdm/organizations/{org_id}/mou` | 200 `{mou}`; 404 when there is no current MoU |
| `PUT /bdm/organizations/{org_id}/mou/document` | 200 `{mou}` (multipart `file`) |
| `GET /bdm/mous` | 200 page; `organization`, `status` (9 keys), `bdm_type`, `current` (default true), `limit`, `offset` |
| `GET /bdm/mous/{mou_id}/history` | 200 page |
| `GET /bdm/mous/{mou_id}/document` | 200 bytes, `attachment; filename="mou-<org code>.<ext>"`, `nosniff`, `no-store`; 404 no document |

### 6.4 Error order (every write)

1. 401 not signed in; 403 not a BDM role (`caller_scope`); 404 organization out of scope.
2. 422 body shape (schema).
3. Organization row lock; `require(can_edit)`: 403 wrong person, 409 archived; 409 `organization_lost`.
4. Current MoU row lock; create: 409 `mou_exists`; PATCH/upload: 404 "No MoU yet".
5. PATCH: 409 `mou_status_changed` (stale `from_status`, returns `current_status`); 409 `mou_expired` (status change on Expired);
   422 same status; 422 date rules on the merged state.
6. Upload: 413 too large / 415 wrong type / 422 bad image (read before any lock); 429 rate limit (under the lock).

### 6.5 Transactions and races

One commit per route. Lock order: organization (`load_scoped(lock=True)`), then the current MoU `FOR UPDATE` — the same first lock as
bdm-004 moves, so an MoU write and a stage move serialize and cannot deadlock. Two creates serialize on the organization lock; the
partial unique index is the backstop (`IntegrityError` → rollback → 409 `mou_exists`). The D28 advance runs inside the MoU
transaction on the already-locked organization. Upload: bytes validated first, object written, then the row work; any failure before
the commit deletes the new object (`discard`, prefix-checked) and the old object is untouched. Download: scope check, audit row
committed, then bytes; a failed commit serves nothing.

### 6.6 Logs

After commit through `org_svc.log`: `bdm_mou_created|status_changed|updated|document_uploaded|document_downloaded|renewed|throttled`
with ids, status keys, field names; storage failures logged with a key digest. Never notes, reference, file name or key.

## 7. Security

| threat | control |
|---|---|
| Spoofing | `get_current_user` on every route; session cookie `httpOnly`, `SameSite=Lax` |
| IDOR | MoU ids resolve through the organization's `caller_scope`; unknown = out of scope = same 404; org routes act on the current MoU only |
| Elevation | writes via `require(can_edit)`; actor from the session; `extra="forbid"` rejects `created_by`, `is_current`, `document_*` |
| Tampering / injection | SQLAlchemy expressions only; enum / UUID / date typed filters; control characters refused |
| XSS | React escaping; notes via the existing `multiline` helper; no raw HTML |
| Info disclosure | key never returned or logged; download `attachment` + `nosniff` + `no-store`, server-built ASCII file name; never `presign_download` / `/local-files` |
| CSRF | Lax cookie is not sent on cross-site POST/PATCH/PUT; JSON and multipart PUT bodies only; the GET download can only deliver a file to the victim's own browser |
| DoS | size cap; 20 uploads/hour/user (M8) |
| Repudiation | an event row and an audit row in the write's transaction; every download audited before bytes |

**Residual (out of scope):** `/local-files` serves the whole local upload directory without authentication (existing, also for agent
documents). MoU keys are random and never exposed; production uses S3. Follow-up item to be raised separately.

## 8. Frontend

- `lib/bdmMous.ts` — types, `MOU_STATUSES` (9, source order, labels), `SETTABLE_STATUSES`, URLs, `mouDocumentUrl(id)`.
- `lib/bdmMousServer.ts` — `firstMou(orgId)`: never rejects (`null` on failure → the card's error state).
- `BdmOrganizationMou.tsx` (card, after the pipeline card on both detail pages): heading `MoU`; empty ("No MoU yet" + **Start MoU**
  when `can_start`); status text + ordered step list Prospect → Active (`aria-current="step"`, word "Current"), Expired / Rejected as
  labelled outcomes; dates / reference / notes via `DetailList`, `multiline`, `formatDate`; edit toggle; **Start renewal** behind
  `BdmConfirm` when `can_renew`; history and previous MoUs in `<details>` loaded on first open; error with "Try again".
- `BdmMouForm.tsx` — status `<select>` (8), native date inputs, required hints that follow the chosen status, 422 field errors via
  `sendRequest`, focus to the first error, busy "Saving…"; choosing Signed with `pipeline_on_sign` shows a `BdmConfirm`
  ("This also moves the pipeline to …"); 409 messages mapped (§6.4).
- `BdmMouDocument.tsx` — `InternshipCertificate` pattern: multipart `PUT`, `accept=".pdf,.jpg,.jpeg,.png"`, 413/415/422/429 messages,
  `<a href download>` to the streamed route.
- `BdmMouHistory.tsx` — `BdmStageHistory` pattern; an "Expired on … (automatic)" line when `expired_on`.
- `BdmMousPanel.tsx` + pages `app/bdm/mous`, `app/bdm/manager/mous` (+ `loading.tsx`): server-rendered first page, status filter as
  URL links (full page loads, QA4-01), per-filter empty text, table that stacks at 320 px, organization links to its profile.
- Nav: "MoUs" after Pipeline in `BDM_NAV` and `BDM_MANAGER_NAV`.
- Accessibility: visible labels, `aria-describedby` errors, `role="alert"` / `role="status"`, one `h1`, native controls; 320 / 768 /
  1024 / 1440 px.

## 9. Acceptance criteria

1. **AC1** Every person-made status change writes a `bdm_mou_events` row (actor, time, from → to) and an audit row in the same
   transaction; Expired is shown as an automatic line with no actor.
2. **AC2** Signed / Active without `signed_on` → 422; Active without both validity dates → 422; `valid_until < valid_from` → 422; the
   DB CHECKs reject the same rows.
3. **AC3** Signed / Active with `valid_until` before today (IST) reads `expired` in detail, list and filter; equal to today does not;
   `status: "expired"` → 422; a status change on Expired → 409 `mou_expired`.
4. **AC4** The document downloads for the assigned BDM, a same-type BDM, the assigned BDM's manager and super_admin; 404 for another
   type's BDM, another team's manager and unknown ids; 403 other roles; 401 signed out; each download audited; the key never appears
   in a response.
5. **AC5** The status list equals the 9 source labels in source order (backend and web).
6. **AC6** Signed advances the pipeline only when behind (event + audit); at or past, no change.
7. **AC7** One current MoU per organization; renewal only from Expired / Rejected; old row kept.
8. **AC8** Writes only by the assigned BDM and super_admin (403 others); archived 409; Lost 409 `organization_lost`.
9. **AC9** Upload: wrong type 415, too large 413, metadata stripped, the 21st upload in an hour 429 with `Retry-After`; a failed
   commit deletes the new object.

## 10. Tests (written before the code, per task)

Backend `tests/bdm005_helpers.py` + `test_bdm_005_{migration,schemas,catalogue,service,expiry,pipeline,renewal,document,download,
scope,concurrency,list}.py`. Web: `BdmOrganizationMou`, `BdmMouForm`, `BdmMouDocument`, `BdmMouHistory`, `BdmMousPages` tests and a
nav assertion. Playwright `tests/e2e/bdm-005-mou.spec.ts`. Lite reruns: bdm-002 / 004 suites, organization detail web tests.

## 11. Regression risks

1. D28 coupling — reuses `record_event` and the lock order; no event kind or CHECK change; bdm-004 suite rerun.
2. Organization detail gains a parallel fetch that never rejects.
3. Migration / decision numbers may move if another branch merges first (re-chain on rebase, as 0073).
4. Unchanged: `files.py`, `/local-files`, `storage.py`, `BdmOrganizationOut`, `schools` columns.

## 12. Completion gates

Lite backend + web suites, `tsc`, `eslint`, `ruff`, one alembic head, Playwright bdm-005, then browser validation and an independent
Codex review (both pending; this spec does not claim completion).
