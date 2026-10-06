# bdm-005 MoU Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (owner chose in-session execution, 2026-10-06) to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BDMs track one MoU per organization through the 9 source statuses, with dates, a confidential document, history, the D28
pipeline advance, and MoU lists for BDMs and managers.

**Architecture:** Two new tables (`bdm_mous`, `bdm_mou_events`) behind a flat router `app/api/bdm_mous.py` and a function-only service
`app/services/bdm_mous.py`, reusing bdm-002 scope (`caller_scope`, `load_scoped`, `require`), bdm-004's pipeline event writer, and
AGN-009's upload validation. Expired is derived on read. The web adds an MoU card on both organization detail pages and two list pages.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, Pydantic 2, PostgreSQL 16; Next.js App Router, React, Vitest, Playwright.

> **Renumbered 2026-10-06** on merging `main` @ `442ce465`: `DEC-SCOPE-074` → `DEC-SCOPE-076`, `0076_bdm_mous` → `0078_bdm_mous`
> (after `0077_bdm_tasks_followups`). The task text below keeps the drafted numbers.

**Spec:** `docs/superpowers/specs/2026-10-06-bdm-005-mou-tracking-design.md` (decisions M1–M9, `DEC-SCOPE-074`).

## Global Constraints

- No new dependencies. No change to `files.py`, `/local-files`, `storage.py`, `BdmOrganizationOut`, `schools` columns.
- Statuses, exact labels and order: Prospect, Discussion Started, Proposal Sent, Under Negotiation, Draft Shared, Signed, Active,
  Expired, Rejected. `expired` is never stored or accepted as input.
- "Today" is the Asia/Kolkata calendar date.
- Signed stage: agent `agreement_signed`, school `signed`, college `mou_signed`; forward only.
- Upload cap: `settings.max_upload_bytes`; PDF/JPEG/PNG by bytes; 20 uploads per user per rolling hour → 429 `Retry-After`.
- Audit actions `bdm_mou.<created|status_changed|updated|document_uploaded|document_downloaded|renewed>`; logs carry ids, status keys,
  field names only — never notes, reference, file name or storage key.
- One commit per route; lock the organization first, then the current MoU.
- Lite tests only (owner): bdm-005 files plus the bdm-002 / bdm-004 suites and touched web tests. The owner runs the full suites.

Test command (isolated stack `bdm005`, code bind-mounted):

```bash
docker compose -p bdm005 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps \
  -v "$(pwd -W)/apps/api:/app" api-test python -m pytest -q -p no:cacheprovider <files>
```

## Review Focus

1. PATCH that clears `signed_on` on an Active MoU (only the cleared field sent) — must be 422 from the merged-state rule (Task 3).
2. A 6-digit year typed into a date (`20266-01-01`) — plain-words 422, not a parser message (Task 2).
3. PNG bytes uploaded as `contract.pdf` — stored and served as `image/png`, metadata stripped (Task 7).
4. `valid_until` = today in IST while the UTC date is still yesterday — not Expired (Task 4).
5. A file name with quotes / CR LF — never reaches the `Content-Disposition` header (Task 7).

---

### Task 1: Catalogue, models, migration `0076_bdm_mous`

**Files:** Modify `apps/api/app/models.py` (after `BdmPipelineEvent`), `apps/api/app/bdm_stages.py`; Create
`apps/api/alembic/versions/0076_bdm_mous.py`, `apps/api/tests/bdm005_helpers.py`, `apps/api/tests/test_bdm_005_migration.py`,
`apps/api/tests/test_bdm_005_catalogue.py`.

**Produces:** `BDM_MOU_STATUSES` (9 keys, source order), `BDM_MOU_STATUS_LABELS` (key → label), `BDM_MOU_SETTABLE` (8),
`BDM_MOU_EVENT_KINDS`, `BDM_MOU_CHECKS` (dict name → sql), models `BdmMou`, `BdmMouEvent`; `bdm_stages.MOU_SIGNED_STAGE`.

- [ ] Write tests: labels equal the source list in order; `MOU_SIGNED_STAGE[t]` is a manual stage of `PIPELINES[t]`; migration
  `CHECKS == BDM_MOU_CHECKS` and `STATUSES` frozen copy equals the model's; one alembic head; DB rejects: active without window,
  signed without `signed_on`, `valid_until < valid_from`, `status='expired'`, a second `is_current` row for one organization.
- [ ] Run → fail (ImportError).
- [ ] Implement models + migration (0073 pattern: guarded creates, offline SQL, downgrade refuses while rows exist).
- [ ] Run → pass. Commit `feat(bdm-005): MoU tables, catalogue and migration 0076`.

### Task 2: Schemas

**Files:** Modify `apps/api/app/schemas.py` (after the bdm-004 block); Create `apps/api/tests/test_bdm_005_schemas.py`.

**Produces:** `BdmMouCreate`, `BdmMouUpdate`, `BdmMouOut`, `BdmMouRow`, `BdmMouEnvelope`, `BdmOrgMouOut`, `BdmMouPage`,
`BdmMouEventOut`, `BdmMouEventPage`, `MOU_FIELD_LABELS`.

- [ ] Tests: unknown field → error (`created_by`, `is_current`, `document_key`); `status="expired"` rejected; update with `status` and
  no `from_status` rejected; `from_status="expired"` accepted; `reference` > 100 rejected, control chars rejected; `notes` keeps line
  breaks, `\r\n` → `\n`, > 2000 rejected; dates `2026-13-01` / `20266-01-01` → "Enter a valid … date"; blank text → None.
- [ ] Run → fail. Implement. Run → pass. Commit.

### Task 3: Service core + organization MoU routes (GET / POST / PATCH)

**Files:** Create `apps/api/app/services/bdm_mous.py`, `apps/api/app/api/bdm_mous.py`; Modify `apps/api/app/main.py` (router tuple);
Create `apps/api/tests/test_bdm_005_service.py`, `apps/api/tests/test_bdm_005_scope.py`.

**Consumes:** `org_svc.load_scoped`, `org_svc.require`, `org_svc.permissions`, `org_svc.log`, `bdm_pipeline.LOST_CONFLICT`,
`bdm.person_ref`.
**Produces:** `svc.today()`, `svc.effective_status(mou, today) -> str`, `svc.check_rules(state: dict)`, `svc.mou_out(db, user, org, mou)`,
`svc.load_current(db, org, lock=False)`, `svc.writable(user, org, route)`, `svc.record(...)`, `svc.audit(...)`.

- [ ] Tests (service): create → 201, status `prospect`, one `created` event + audit; PATCH status with `from_status` → event
  `status` (from, to, actor) + audit `status_changed`; PATCH fields only → event `updated` with field names; stale `from_status` →
  409 `mou_status_changed` + `current_status`; same status → 422; Signed without `signed_on` → 422 on `signed_on`; Active without
  window → 422; `valid_until < valid_from` → 422; **clearing `signed_on` on Active → 422** (Review Focus 1); Proposal Sent defaults
  `proposal_sent_on` to today; GET with none → `{current: null, can_start: true}`; second create → 409 `mou_exists`; PATCH with no MoU
  → 404; no audit or log text contains the notes.
- [ ] Tests (scope matrix, bdm-004 `_world`): GET/POST/PATCH for owner (200/201/200), peer (200/403/403), other_type (404s), manager
  (200/403/403, `can_start` false), other_manager (404s), super_admin (all ok), it_admin/student/no_profile (403), signed out (401);
  archived → 409; Lost → 409 `organization_lost`.
- [ ] Run → fail. Implement. Run → pass. Commit.

### Task 4: Derived Expired

**Files:** Modify `services/bdm_mous.py`; Create `tests/test_bdm_005_expiry.py`.

- [ ] Tests (monkeypatch `svc.today`): Active with `valid_until` yesterday → `status == "expired"`, `expired_on` = valid_until + 1;
  Signed with past `valid_until` → expired; `valid_until == today` → still active (**IST vs UTC**, Review Focus 4: patch `today` only,
  and a unit test of `today()` using a fixed UTC instant 2026-10-05T20:00Z → 2026-10-06); status change on Expired → 409
  `mou_expired`; PATCH `valid_until` to the future on Expired → 200, event `updated` from `expired` to `active`.
- [ ] Run → fail. Implement. Run → pass. Commit.

### Task 5: D28 pipeline advance

**Files:** Modify `apps/api/app/services/bdm_pipeline.py` (add `advance_to`), `services/bdm_mous.py`; Create
`tests/test_bdm_005_pipeline.py`.

**Produces:** `bdm_pipeline.advance_to(db, user, org, stage: str, note: str) -> str | None` (forward only, records a `move` event,
returns the previous stage or None).

- [ ] Tests (each type): org at prospect → MoU to Signed → stage = signed stage, one pipeline `move` event with note
  "Advanced by MoU signed", audit `bdm_organization.stage_changed` with `source: "mou"`; org already past (college at
  `college_activated`) → unchanged, no pipeline event; created directly as Signed → advances; `pipeline_on_sign` reflects behind /
  not behind; Active after Signed → no second advance.
- [ ] Run → fail. Implement. Run → pass. Commit.

### Task 6: Renewal and concurrency

**Files:** Modify `services/bdm_mous.py`, `api/bdm_mous.py`; Create `tests/test_bdm_005_renewal.py`, `tests/test_bdm_005_concurrency.py`.

- [ ] Tests: POST when current is Expired → new current Prospect row, old row `is_current=false` + `renewed` event; POST when
  current is Rejected → same; POST when current is Active → 409 `mou_exists`; `can_renew` / `can_start` flags; two concurrent
  creates (two sessions, `asyncio.gather`) → exactly one 201 and one 409, one current row; status change racing a stage move → both
  succeed in some order, no deadlock.
- [ ] Run → fail. Implement. Run → pass. Commit.

### Task 7: Document upload, download, rate limit

**Files:** Modify `services/bdm_mous.py`, `api/bdm_mous.py`, `services/agent_orgs.py` (`retry_after` gains `window` kw, default
unchanged); Create `tests/test_bdm_005_document.py`, `tests/test_bdm_005_download.py`.

**Consumes:** `agent_documents.read_upload`, `storage.write_bytes/read_bytes/delete`, `agent_orgs.retry_after`.

- [ ] Tests: upload PDF → 200, `document {name, content_type, uploaded_at}`, no key anywhere in JSON; **PNG bytes named
  contract.pdf → `image/png`** (Review Focus 3); text bytes → 415; > cap → 413; replace → old object still in storage, event
  `document` holds old key, response never shows it; storage write failure → 500, no row change; commit failure → new object deleted;
  21st upload within an hour → 429 with `Retry-After`; peer/manager → 403; download by owner, peer, manager, super_admin → 200 bytes
  equal to the stored ones, `attachment; filename="mou-<code>.pdf"`, `nosniff`, `no-store`; **file name `a"\r\n.pdf` never in the
  header** (Review Focus 5); other_type / other_manager / unknown → 404 identical; it_admin → 403; signed out → 401; no document →
  404; every download writes `bdm_mou.document_downloaded`.
- [ ] Run → fail. Implement. Run → pass. Commit.

### Task 8: List and history endpoints

**Files:** Modify `services/bdm_mous.py`, `api/bdm_mous.py`; Create `tests/test_bdm_005_list.py`.

- [ ] Tests: `GET /bdm/mous` scoped (BDM sees type, manager team, super_admin all); `status=expired` returns the derived rows only;
  `status=active` excludes expired; `status=bogus` → 422; `organization=<id>&current=false` lists previous MoUs; pagination
  `limit/offset/total`; history page ordered by `position`, actor ref, labels; history of an out-of-scope MoU → 404.
- [ ] Run → fail. Implement. Run → pass. Rerun the bdm-002 + bdm-004 suites. Commit.

### Task 9: Web library, server fetch, navigation

**Files:** Create `apps/web/lib/bdmMous.ts`, `apps/web/lib/bdmMousServer.ts`; Modify `apps/web/lib/navigation.ts`;
Tests `apps/web/tests/components/BdmMouLib.test.ts` (or in the card test), nav assertion in `BdmPages.test.tsx`.

**Produces:** types `Mou`, `MouRow`, `MouStatus`, `OrgMou`, `MouEvent`; `MOU_STATUSES` (key/label, 9), `SETTABLE_MOU_STATUSES` (8),
`orgMouUrl(orgId)`, `MOUS_URL`, `mouDocumentUrl(id)`, `mouHistoryUrl(id)`; `firstMou(orgId): Promise<OrgMou | null>`.

- [ ] Tests: labels equal the source list; nav has "MoUs" after Pipeline for both roles. Run → fail. Implement. Pass. Commit.

### Task 10: MoU card and form on the organization detail

**Files:** Create `apps/web/components/BdmOrganizationMou.tsx`, `apps/web/components/BdmMouForm.tsx`; Modify
`apps/web/components/BdmOrganizationDetail.tsx`, `apps/web/app/bdm/organizations/[id]/page.tsx`,
`apps/web/app/bdm/manager/organizations/[id]/page.tsx`; Tests `BdmOrganizationMou.test.tsx`, `BdmMouForm.test.tsx`.

- [ ] Tests: empty + `can_start` → Start MoU; empty read-only → text only; failed initial load → alert + Try again refetches;
  current shown with status text, `aria-current="step"`, dates; edit form shows required hint for Signed date when Signed chosen,
  window when Active; 422 field error rendered under the field and focused; choosing Signed with `pipeline_on_sign` asks to confirm
  with the stage label; 409 `mou_status_changed` shows the message and reloads; Start renewal behind confirm when `can_renew`.
- [ ] Run → fail. Implement. Pass. Commit.

### Task 11: Document control and history

**Files:** Create `apps/web/components/BdmMouDocument.tsx`, `apps/web/components/BdmMouHistory.tsx`; Tests
`BdmMouDocument.test.tsx`, `BdmMouHistory.test.tsx`.

- [ ] Tests: upload sends multipart PUT to `orgMouUrl/document`, success notice, 413/415/429 messages; download is a link with
  `download` to `mouDocumentUrl`; no upload control without `can_upload`; history loads on open, shows actor and labels, "Show more",
  error + retry, the automatic Expired line.
- [ ] Run → fail. Implement. Pass. Commit.

### Task 12: List pages

**Files:** Create `apps/web/components/BdmMousPanel.tsx`, `apps/web/app/bdm/mous/page.tsx`, `apps/web/app/bdm/mous/loading.tsx`,
`apps/web/app/bdm/manager/mous/page.tsx`, `apps/web/app/bdm/manager/mous/loading.tsx`; Test `BdmMousPages.test.tsx`.

- [ ] Tests: rows link to the right detail path per role; status filter links are plain `<a>` with `?status=`; current filter marked;
  empty text per filter; page error via `accessUnavailable`.
- [ ] Run → fail. Implement. Pass. Run tsc + eslint + web BDM tests. Commit.

### Task 13: Playwright, docs

**Files:** Create `apps/web/tests/e2e/bdm-005-mou.spec.ts`; Modify `docs/delivery/BDM_CRM_BACKLOG.md` (status line),
`docs/decisions/PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-074`), `docs/architecture/API_CONTRACT.md` (bdm-005 routes).

- [ ] E2E: BDM creates an org, starts an MoU, Proposal Sent → Under Negotiation → Signed (confirm) with a PDF → pipeline shows the
  signed stage → Active with a window; download link present; 320 px pass; keyboard-only edit.
- [ ] Run the bdm-005 spec. Update docs. Commit. Status stays "implementation complete — browser validation and Codex review pending".
