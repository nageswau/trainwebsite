# PUB-022 Social Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show an admin-entered rating badge and up to 6 consented, featured testimonials on `/`, `/it` and `/overseas`.

**Architecture:**
- Extend the existing `testimonials` table and add a single-row `site_rating_badge` table (migration 0158).
- Move the testimonial logic into a new `app/services/social_proof.py`.
- Add CMS management routes to `app/api/cms.py` and public reads to `app/api/public.py`.
- Web: a `SocialProofStrip` server component, plus a `TestimonialManager` client component mounted on three dedicated admin pages.

**Tech Stack:** FastAPI, async SQLAlchemy, Alembic, Pydantic v2, pytest (strict asyncio, shared DB); Next.js App Router, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-14-pub-022-social-proof-design.md` (SP1–SP9).

**Execution:** native (the owner said "go ahead and implement"), with one whole-branch review at the end.

## Rulings (spec amendments, recorded in spec §10)

- **R1 — photo formats are JPEG and PNG only.** WebP is dropped.
  - *Why:* the codebase's magic-byte check and EXIF/GPS stripper (`app/services/image_metadata.py`) supports only those two formats. A WebP photo would keep its location metadata.
  - *Cost if wrong:* add a WebP stripper later.
- **R2 — the admin screens are dedicated pages.** They live at `app/admin/testimonials`, `app/it/admin/testimonials` and `app/overseas/admin/testimonials`, not inside the generic `[module]` / `[section]` table pages.
  - *Why:* the generic pages are read-only tables with reference-typed forms, which can't do photo upload, delete-confirm or a consent tick.
- **R3 — status codes follow the existing upload helper:**
  - 413 when a photo is over 2 MB;
  - 415 for a wrong file type;
  - 422 for a broken image.

  The spec's "422 for everything" is replaced by these.

## Global Constraints

- Migration `0158_social_proof`, down_revision `0157_direct_tieups`. Every step is guarded, because 0001 builds from the current models.
- Every public query filters on `published = true`. Photo keys are never returned in any response.
- Division admins (it_admin / overseas_admin) act only inside `user.division`. A row in another division returns 404; creating in another division returns 403.
- The badge endpoints are super_admin only.
- Audit rows for testimonials never contain `person_name`, `headline` or `quote`.
- Tests run on a shared, never-truncated database. They create their own rows and assert on their own ids. Testimonials meant for the strip use `display_order = -1000 - n` so they sort first.
- Lite backend tests only. Docker project `pub` with Windows-form mount paths (memory: worktree-api-test-mount-path).

## Review Focus

1. Unpublishing a testimonial makes its photo URL return 404 straight away (no stale public access). Test: `test_photo_404_after_unpublish`.
2. An it_admin PATCHing an overseas row's id gets 404, not 403 or 200. Test: `test_other_division_is_404`.
3. Re-sending `consent_confirmed: true` when consent is already true must not move `consent_at`. Test: `test_consent_timestamp_is_stable`.
4. A strip with a badge but no testimonials, or testimonials but no badge, still renders the part that exists. Vitest: `badge only` / `cards only`.
5. Deleting a testimonial whose photo file is already missing still succeeds (204). Test: `test_delete_with_missing_photo_file`.

---

### Task 1: Migration 0158 + models + seed

**Files:**
- Create: `apps/api/alembic/versions/0158_social_proof.py`
- Modify: `apps/api/app/models.py` (`Testimonial`; new `SiteRatingBadge`), `apps/api/app/seed.py` (demo testimonials created unpublished)
- Test: `apps/api/tests/test_pub_022_migration.py`

**Interfaces — produces:**
- New `Testimonial` fields: `published`, `featured`, `display_order`, `context`, `consent_confirmed`, `consent_by_user_id`, `consent_at`, `photo_key`, `photo_content_type`.
- `SiteRatingBadge` (id = 1).
- `TESTIMONIAL_CHECKS` and `RATING_BADGE_CHECKS` dicts in models.py, which the migration repeats exactly.

Steps:
- [ ] Write tests:
  - the CHECK constraints reject publishing without consent, rating 0 or 6, and division `school`;
  - the badge rejects id 2 and rating 5.5;
  - the migration's CHECKS dicts equal the models' dicts;
  - the downgrade SQL renders.
- [ ] Implement the model columns.
  - Add `photo_content_type varchar(40)`, so the photo route can serve the right type without sniffing. This is an addition to spec §3.1.
- [ ] Implement the migration. The upgrade:
  - adds the columns, guarded;
  - sets `published = false` on every existing row;
  - checks the division values before adding the CHECKs;
  - creates `site_rating_badge`, guarded;
  - adds the index.
- [ ] Change the seed so it creates the demo testimonials with `published=False`.
- [ ] Run the tests, then commit.

### Task 2: Backend service + CMS + public routes

**Files:**
- Create: `apps/api/app/services/social_proof.py`
- Modify: `apps/api/app/api/cms.py`, `apps/api/app/api/public.py`, `apps/api/app/schemas.py`
- Test: `apps/api/tests/test_pub_022_cms.py`, `apps/api/tests/test_pub_022_public.py`

**Interfaces — produces:**
- Schemas:
  - `TestimonialIn` (create) and `TestimonialUpdate` (patch, no `division`), both `extra="forbid"`;
  - `TestimonialManageOut`;
  - `TestimonialOut`, which gains `context` and `photo_url`;
  - `RatingBadgeIn`, `RatingBadgeOut`, `SocialProofOut`.
- `social_proof.photo_url(t) -> str | None` returns `/api/v1/public/testimonials/{id}/photo`.
- `social_proof.apply_consent(t, consent: bool, user)` follows SP6/SP9:
  - false → true sets who and when;
  - true → false clears them and unpublishes.
- `social_proof.featured(db, division) -> list[Testimonial]` returns at most 6 rows that are published and featured, ordered by display_order, then created_at.
- Routes:
  - CMS: `GET /cms/manage/testimonials`, `POST /cms/testimonials`, `PATCH|DELETE /cms/testimonials/{id}`, `PUT|DELETE /cms/testimonials/{id}/photo`, `GET|PUT /cms/rating-badge`;
  - public: `GET /public/social-proof`, plus the existing `/public/testimonials` routes filtered, `GET /public/testimonials/{id}/photo`, and `/public/home` without `stats`.

Steps:
- [ ] Write the CMS tests:
  - the permission matrix (super_admin both divisions; it_admin own division; other division 404; create in other division 403; student 403; badge as non-super 403);
  - publishing without consent returns 422;
  - unticking consent unpublishes;
  - `test_consent_timestamp_is_stable`;
  - photo upload of PNG and JPEG works; a fake PNG (wrong bytes) returns 415; over 2 MB returns 413;
  - delete removes the photo file (storage read raises);
  - `test_delete_with_missing_photo_file`;
  - the delete audit row's metadata contains no name or quote.
- [ ] Write the public tests:
  - unpublished rows are hidden on list, detail (404), `/public/home` and `/social-proof`;
  - the strip includes only featured rows, in order, at most 6;
  - the division filter works, and an invalid division returns 422;
  - the badge is null until published;
  - `stats` is gone from `/public/home`;
  - photo works while published, and `test_photo_404_after_unpublish`;
  - no response contains `photo_key`.
- [ ] Implement, reusing `agent_documents.read_upload`-style validation through `image_metadata.detect_image_type` and `strip_metadata`, with the limit `MAX_PHOTO_BYTES = 2 * 1024 * 1024`. Storage keys use the form `testimonials/{uuid4().hex}`.
- [ ] Run the lite backend set: pub_001–005, pub_022_*, upc_003/017 public, tel_005 public. Then commit.

### Task 3: Web strip on the three homepages

**Files:**
- Create: `apps/web/components/SocialProofStrip.tsx`, `apps/web/lib/socialProof.ts` (types + a `starsLabel` helper)
- Modify: `apps/web/app/page.tsx`, `apps/web/app/it/page.tsx`, `apps/web/app/overseas/page.tsx`, `apps/web/lib/types.ts` (Testimonial gains `context`, `photo_url`), `apps/web/app/globals.css` (strip styles)
- Test: `apps/web/tests/components/SocialProofStrip.test.tsx`

Steps:
- [ ] Split the component in two:
  - `SocialProofStrip` is an async server component that fetches the data;
  - `SocialProofView` is a pure renderer, so vitest can test it.
- [ ] Write vitest cases: empty → renders nothing; badge only; cards only; initials fallback; aria label "Rated 5 out of 5"; the review link has `rel` and `target`.
- [ ] Implement, place the strip on the three pages, then run tsc, eslint and the vitest file. Commit.

### Task 4: Web admin manager + pages + nav

**Files:**
- Create:
  - `apps/web/components/TestimonialManager.tsx`
  - `apps/web/components/RatingBadgeForm.tsx`
  - `apps/web/lib/testimonials.ts` (URLs, types, `formToTestimonial`)
  - `apps/web/app/admin/testimonials/page.tsx`, `apps/web/app/it/admin/testimonials/page.tsx`, `apps/web/app/overseas/admin/testimonials/page.tsx`
- Modify: `apps/web/lib/navigation.ts` (a "Testimonials" entry in the SUPER_ADMIN, it/admin and overseas/admin navs)
- Test: `apps/web/tests/components/TestimonialManager.test.tsx`, `apps/web/tests/components/RatingBadgeForm.test.tsx`, `apps/web/tests/e2e/pub-022-social-proof.spec.ts`

Steps:
- [ ] Write vitest cases:
  - the Publish checkbox is disabled until consent is ticked;
  - unticking consent clears Publish;
  - delete asks for confirmation before calling DELETE;
  - a 422 detail is shown;
  - the badge form sends a PUT with the numeric rating.
- [ ] Implement:
  - the pages check the role (super_admin for `/admin`; it_admin or super_admin for `/it/admin`; overseas_admin or super_admin for `/overseas/admin`);
  - the badge form appears on `/admin/testimonials` only.
- [ ] Write the Playwright spec. A super admin:
  - creates a testimonial, ticks consent, publishes it and features it;
  - sees it on `/` and `/it`;
  - checks the 375px viewport has no horizontal scroll.

  The spec is not run here (the owner runs it).
- [ ] Run tsc, eslint and vitest (full web suite). Commit.

### Task 5: Docs + QA

**Files:**
- `docs/decisions/PRODUCT_DECISION_REGISTER.md` (DEC-SCOPE-210)
- `docs/architecture/RBAC_MATRIX.md` (§2.135)
- `docs/architecture/API_CONTRACT.md` (§12DX)
- `docs/features/MASTER_FEATURE_CATALOG.md`, `docs/quality/RTM.md` (PUB-022 rows)
- `docs/quality/PUB-022_QA_2026-10-14.md`
- spec §10 rulings

Steps:
- [ ] Recheck origin/main for 0158 / 210 / 12DX / 2.135. Write the docs, then commit.
