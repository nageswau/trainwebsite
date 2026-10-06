# tel-012 Content Library Implementation Plan

> **For agentic workers:** executed inline (superpowers:executing-plans) by the session that wrote it, per the user's standing
> "autonomous, recommended answers" instruction. Steps use checkbox syntax.

**Goal:** Manager-maintained call scripts, WhatsApp/email message templates and PDF brochures, with signed 7-day public brochure links.

**Architecture:** Three tables (`tel_scripts`, `tel_message_templates`, `tel_assets`) in migration `0079_tel_content`; rules in
`services/telecaller_content.py`; routes in `api/telecaller_content.py` (prefix `/telecaller`, plus a `public_router`); three manager
pages reusing the tel-002 `TelecallerCataloguePage` shell.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic + PostgreSQL; python-jose JWT (`app.core.security`); Next.js App Router + Vitest
+ Playwright.

**Spec:** `docs/superpowers/specs/2026-10-06-tel-012-content-library-design.md`

## Global Constraints

- Inline authorization: `User.role` check first (`require_reader` / `require_manager`), then the write. No `require_*` dependencies.
- 422 bodies are one readable sentence (`services/telecaller._parse` with field labels).
- Routes own the transaction; services never commit. Audit rows carry ids + field names only.
- Lists: `{items,total,limit,offset}` using `api.bdm.LIMIT/OFFSET/SEARCH`.
- Placeholders exactly `{name}`, `{product}`, `{brochure_link}`, `{appointment_time}`.
- Link expiry exactly 7 days; token type `tel_asset`; failure message "This link has expired or is no longer available" (404).
- WhatsApp body ≤ 1000, email body ≤ 5000, subject ≤ 200 single line, name ≤ 160, steps 1–20, step title ≤ 120, notes ≤ 1000.
- Never log a token, a storage key (log a digest) or a file's contents.

## Review Focus

1. `{NAME}` / `{ name }` / `{discount}` in a body → 422 naming the token (pinned in Task 2 unit tests).
2. A value containing `{name}` is not re-expanded by `render` (Task 2).
3. A file called `brochure.pdf` whose bytes are PNG → 422; a file name with quotes/unicode → safe `Content-Disposition` (Task 4).
4. The template's asset deactivated later → preview still 200, brochure link omitted (Task 3).
5. A session access token pasted as a link token → 404; a link token used as a Bearer/cookie → 401 (Task 4).

---

### Task 1: Models, schemas, migration + seeds

**Files:** Modify `apps/api/app/models.py` (after `TelCampaign`), `apps/api/app/schemas.py` (after tel-002 block); Create
`apps/api/alembic/versions/0079_tel_content.py`, `apps/api/app/tel_content_kinds.py`; Test `apps/api/tests/test_tel_012_migration.py`.

**Produces:** `TelScript`, `TelMessageTemplate`, `TelAsset`; `WHATSAPP_KINDS`, `EMAIL_KINDS`, `SEED_TEMPLATES`, `SEED_SCRIPT_STEPS`
in `app/tel_content_kinds.py` (imported by models, migration, tests).

- [ ] Write failing tests: after `alembic upgrade head` the 16 seed templates exist (9 whatsapp / 7 email, product NULL, `active`),
  the Cyber Security script has the 7 §6 steps in order, partial unique index `uq_tel_scripts_active_product` exists, the
  `ck_tel_message_templates_subject` and kind checks reject bad rows (raw INSERT → IntegrityError), re-running the seed statements
  inserts nothing.
- [ ] Run → FAIL (tables missing). Implement models + migration (guarded create, idempotent seeds, refusing downgrade). Run → PASS.
- [ ] Commit `feat(tel-012): content tables, kinds and seeds (0078)`.

### Task 2: Placeholder validation + rendering service

**Files:** Create `apps/api/app/services/telecaller_content.py`; Test `apps/api/tests/test_tel_012_render.py`.

**Produces:** `PLACEHOLDERS: tuple[str,...]`; `check_placeholders(*texts: str | None) -> set[str]` (raises 422 on unknown, returns
used names); `render(text: str, values: dict[str, str]) -> str`; `SAMPLE_VALUES`.

- [ ] Unit tests: known tokens filled; unknown `{discount}`, `{NAME}`, `{ name }` → HTTPException 422 with the exact sentence; `{}` and
  lone braces untouched; single pass (`values["name"] = "{product}"` stays literal); missing value → empty string.
- [ ] FAIL → implement (`re.compile(r"\{([^{}\n]*)\}")`) → PASS → commit.

### Task 3: Scripts + templates API

**Files:** Create `apps/api/app/api/telecaller_content.py`; Modify `apps/api/app/main.py` (register routers),
`apps/api/app/services/telecaller_content.py`; Tests `apps/api/tests/test_tel_012_scripts.py`, `apps/api/tests/test_tel_012_templates.py`.

**Consumes:** tel-002 `require_reader`-style check (own `CONTENT_READERS`), `require_manager`, `active_filters`, `apply_changes`,
`audit`, `flush_unique`, `locked_active_product`, `_parse`.

- [ ] Tests (scripts): writers create/patch (201/200, audit action+fields); telecaller/it_admin/counselor writes 403; non-readers
  (it_admin, bdm_manager, it_student) GET 403; telecaller GET hides inactive; second active script on a product → 409, reactivating
  into a taken product → 409; steps 0 or 21 → 422; blank step title → 422; inactive product → 422.
- [ ] Tests (templates): create whatsapp/email; email without subject → 422; whatsapp with subject → 422; subject with `\n` → 422;
  kind of the other channel → 422; unknown placeholder on create and on PATCH → 422; `{brochure_link}` without asset → 422 and on
  PATCH removing the asset while body uses it → 422; inactive asset → 422; duplicate name (case-insensitive, same channel) → 409;
  channel change → 422; WhatsApp body 1001 chars → 422; filters channel/kind/product/active/q; preview fills sample values, uses the
  template's product name, includes a working link when the asset is active and omits it when deactivated; telecaller preview of an
  inactive template → 404.
- [ ] FAIL → implement → PASS → commit `feat(tel-012): scripts and templates API`.

### Task 4: Assets — upload, metadata, signed links, public download

**Files:** Modify `apps/api/app/api/telecaller_content.py`, `apps/api/app/services/telecaller_content.py`; Test
`apps/api/tests/test_tel_012_assets.py`.

**Produces:** `asset_link(asset) -> dict{url, expires_at}`, `asset_from_token(db, token) -> TelAsset | None`, `LINK_TTL = timedelta(days=7)`.

- [ ] Tests: manager uploads PDF (201, row + stored bytes, audit); PNG bytes named `.pdf` → 422; empty → 422; oversize (monkeypatch
  `settings.max_upload_bytes`) → 413; telecaller upload → 403; bad kind → 422; link → GET public URL signed-out returns the bytes with
  `application/pdf`, `no-store`, `nosniff` and an RFC 5987 file name; expired token (freeze by minting with past exp) → 404;
  tampered token → 404; access token → 404; link token as Bearer on `/auth/me` → 401; deactivated asset → link 404 and existing link
  404; reactivated → old link works again until its expiry; DB failure after store → object discarded.
- [ ] FAIL → implement → PASS → commit `feat(tel-012): brochure assets and signed links`.

### Task 5: Web library + navigation

**Files:** Create `apps/web/lib/telecallerContent.ts`; Modify `apps/web/lib/navigation.ts`; Test
`apps/web/tests/lib/telecallerContent.test.ts`, update `apps/web/tests/lib/navigation.telecaller.test.ts`.

- [ ] Tests: kind labels cover all 16 kinds; `unknownPlaceholders(text)` mirrors the server rule; manager nav lists Scripts, Templates,
  Brochures. FAIL → implement → PASS → commit.

### Task 6: Manager screens

**Files:** Create `apps/web/app/telecaller/manager/{scripts,templates,brochures}/page.tsx`, components
`TelecallerScriptsPanel.tsx`, `TelecallerScriptRow.tsx`, `TelecallerScriptSteps.tsx`, `TelecallerTemplatesPanel.tsx`,
`TelecallerTemplateRow.tsx`, `TelecallerBrochuresPanel.tsx`, `TelecallerBrochureRow.tsx`; Tests in `apps/web/tests/components/`.

- [ ] Component tests (Vitest + Testing Library, fetch mocked): each panel shows loading → list / empty / error + Retry; create posts the
  right body and shows feedback; double click posts once; step editor add/remove/move; template channel switch shows/hides subject;
  preview renders text; brochure upload sends FormData and blocks a non-PDF client-side; copy link writes to clipboard.
- [ ] FAIL → implement → PASS; `tsc`, `eslint`, `next build` → commit `feat(tel-012): manager content screens`.

### Task 7: Playwright e2e + docs

**Files:** Create `apps/web/tests/e2e/tel-012-content-library.spec.ts`; Modify `docs/delivery/TELECALLER_CRM_BACKLOG.md` (status),
`docs/decisions/PRODUCT_DECISION_REGISTER.md` (DEC-SCOPE-078).

- [ ] e2e: manager creates a script with steps, a template (unknown placeholder rejected, then saved), uploads a PDF, links it, previews,
  opens the public link signed-out (PDF 200), deactivates the brochure → link 404; telecaller cannot open manager pages.
- [ ] Run against the isolated stack → PASS → commit docs.
