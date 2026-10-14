# PUB-022 — Homepage social proof (rating badge + testimonials) — Design

- **Feature ID:** PUB-022 (next free after PUB-021)
- **Decision:** DEC-SCOPE-210 (planned; recheck main before building)
- **Migration:** 0158_social_proof (after 0157_direct_tieups)
- **API contract:** §12DX (planned) · **RBAC:** §2.135 (planned)
- **Branch / worktree:** `feature/pub-022` in `../pub-022`, from main @2e96cac8
- **Origin:** item 1 of the 360digrii.com review (2026-10-14). Their homepage shows a
  Google rating (4.8) and reviews; EduSphere's homepage shows neither.
- **Evidence class:** EXPLICIT_APPROVAL. The owner answered SP1–SP9 in this
  session (2026-10-14) and approved the design in chat.

## 1. Goal

`/`, `/it` and `/overseas` show real, consented social proof:
- one organisation-wide rating badge;
- up to 6 featured testimonials.

All of it is entered by staff. Nothing appears until it is published, and nothing
fabricated is ever public.

## 2. Owner decisions

| # | Decision |
|---|---|
| SP1 | Staff enter testimonials and the rating by hand. No Google or other external review API. |
| SP2 | super_admin manages all testimonials. it_admin and overseas_admin manage only their own division's testimonials (the existing CMS `require_editor` rule). |
| SP3 | No stat numbers in this feature. Remove the hard-coded `stats` (1250 / 830 / 75 / 96) from `GET /public/home`. Verified numbers belong to a later item (#11). |
| SP4 | The demo testimonials (Rahul K, Sneha P) become unpublished. The migration unpublishes every existing row, and the seed keeps creating them unpublished. `/it/success-stories` then lists only published rows. |
| SP5 | One organisation-wide rating badge: source name, rating (0.0–5.0, one decimal place), review count, optional link, as-of date, published flag. Only super_admin edits it. |
| SP6 | A testimonial cannot be published unless consent is recorded. The consent record stores the user who confirmed it and when. A photo is optional. |
| SP7 | The strip appears on `/` (both divisions), on `/it` (IT only) and on `/overseas` (overseas only). |
| SP8 | A testimonial appears in the strip when it is both **featured** and published. Strips are ordered by `display_order` and show at most 6. Published testimonials that are not featured still appear on the success-stories pages. |
| SP9 | When a person withdraws consent, an editor can **delete the testimonial permanently**. Deleting removes the row and the photo file. The audit log keeps only the id, who deleted it and when; it never keeps the name or quote. Unticking consent also unpublishes the testimonial. |

## 3. Data (migration 0158_social_proof)

### 3.1 `testimonials` — new columns

| Column | Type | Rule |
|---|---|---|
| `published` | bool, not null, server default false | The migration sets every existing row to false |
| `featured` | bool, not null, default false | |
| `display_order` | int, not null, default 0 | Lower values appear first |
| `context` | varchar(160), nullable | e.g. "Python Full-Stack · Placed at X" or "MSc Data Science · Univ. of Reading" |
| `consent_confirmed` | bool, not null, default false | |
| `consent_by_user_id` | uuid FK users.id, nullable | Set by the server; clients cannot send it |
| `consent_at` | timestamptz, nullable | Set by the server |
| `photo_key` | varchar(300), nullable | A storage key, never a URL |

CHECK constraints:
- `ck_testimonials_publish_needs_consent`: `NOT published OR consent_confirmed`
- `ck_testimonials_rating_range`: `rating BETWEEN 1 AND 5`
- `ck_testimonials_division`: `division IN ('it','overseas')`. The upgrade first verifies that no existing row breaks this rule. If one does, it raises and names the row.

Index: `(division, published, featured, display_order)`.

### 3.2 New table `site_rating_badge` (single row)

| Column | Type | Rule |
|---|---|---|
| `id` | int PK | CHECK `id = 1` (only one row may exist) |
| `source_name` | varchar(60), not null | e.g. "Google" |
| `rating` | numeric(2,1), not null | CHECK 0.0–5.0 |
| `review_count` | int, not null | CHECK ≥ 0 |
| `review_url` | varchar(500), nullable | Must start with `https://` (enforced by the schema) |
| `as_of` | date, not null | |
| `published` | bool, not null, default false | |
| `updated_by_user_id` | uuid FK users.id, nullable | |
| timestamps | | |

Downgrade: drop the table and the new columns, then restore the old behaviour where every row is visible.

## 4. API

### 4.1 Public (no login)

- **`GET /api/v1/public/social-proof?division=it|overseas|all`** (default `all`) returns:
  ```json
  {"badge": {"source_name","rating","review_count","review_url","as_of"} | null,
   "testimonials": [{"id","division","person_name","headline","quote","rating","context","photo_url"|null}]}
  ```
  - `badge` is null unless the badge is published.
  - `testimonials` contains only rows that are published and featured, ordered by `display_order`, then `created_at`, limited to 6.
  - With `all`, rows from both divisions share the same ordering.
  - `photo_url` is `/api/v1/public/testimonials/{id}/photo` when a photo exists.
  - An invalid division value returns 422.
- **`GET /public/testimonials`** and **`GET /public/testimonials/{id}`** return only published rows. An unpublished id returns 404. `TestimonialOut` gains `context` and `photo_url`.
- **`GET /public/testimonials/{id}/photo`** streams the image bytes with the stored content type and `Cache-Control: public, max-age=300`. It returns 404 when the testimonial is unpublished, has no photo, or does not exist.
- **`GET /public/home`**: the `stats` key is removed (SP3), and `testimonials` is filtered to published rows.

### 4.2 CMS (logged in)

- `GET /cms/manage/testimonials?division=` lists every row with all fields. Division admins are limited to their own division.
- `POST /cms/testimonials` creates a testimonial. Body fields: division, person_name, headline, quote, rating, context, featured, display_order, consent_confirmed, published. Pydantic `extra="forbid"`.
- `PATCH /cms/testimonials/{id}` edits a testimonial; `division` cannot be changed.
- `DELETE /cms/testimonials/{id}` deletes the row and its photo (SP9). Returns 204.
- `PUT /cms/testimonials/{id}/photo` uploads a photo as multipart form data:
  - only JPEG, PNG or WebP, checked against the file's magic bytes as well as the declared content type;
  - at most 2 MB;
  - any previous photo is replaced and its file deleted.
- `DELETE /cms/testimonials/{id}/photo` removes the photo.
- `GET /cms/rating-badge` returns the badge or null (super_admin only).
- `PUT /cms/rating-badge` creates or updates the badge (super_admin only).

Rules:
- Publishing without consent returns 422 `"Record consent before publishing"`. The database CHECK enforces the same rule.
- When `consent_confirmed` changes from true to false, the server also sets `published` to false.
- When `consent_confirmed` changes from false to true, the server sets `consent_by_user_id` and `consent_at`.
- Editors cannot be outside their division:
  - creating a testimonial for another division returns 403;
  - any other action on another division's testimonial returns 404, so its existence is not revealed.
- Any role other than super_admin, it_admin or overseas_admin gets 403.
- Audit actions:
  - `cms.testimonial.create`, `.update` (records the changed field names, not their values), `.delete` (id only), `.photo`
  - `cms.rating_badge.update`

## 5. Web

- **`components/SocialProofStrip.tsx`**:
  - a server component that receives `division: "it" | "overseas" | "all"`;
  - it fetches `/public/social-proof` and renders nothing when there is no badge and no testimonials, or when the fetch fails;
  - the badge shows the star rating, then "4.8 on Google · 1,234 reviews · as of 1 Oct 2026", with an optional "Read reviews" link (`rel="noopener"`, opens in a new tab);
  - each card shows the photo (`next/image`, unoptimised, alt "Photo of {name}") or the person's initials, then the quote, name, context and stars;
  - stars have an accessible label ("Rated 5 out of 5");
  - layout: a responsive grid that becomes one column at 375px.
- **Placement:**
  - `app/page.tsx`: under the two service cards, with `division="all"`.
  - `app/it/page.tsx` and `app/overseas/page.tsx`: before the last section, with their own division.
- **`/it/success-stories`** keeps its current page and now gets only published rows from the API.
- **Admin screen `components/TestimonialManager.tsx`:**
  - a table listing division, name, headline, published, featured, order and consent;
  - a create/edit form;
  - a consent checkbox with the text "I confirm this person agreed to public use of their name, words and photo";
  - photo upload and remove;
  - a delete button with a confirmation step.

  It is mounted at:
  - `/admin/testimonials` (super_admin, both divisions, including the **Rating badge** form);
  - `/it/admin/testimonials` and `/overseas/admin/testimonials` (division admins, no badge form).

  Navigation entries are added for each of these.

## 6. Security & privacy

- Unpublished testimonials, photos and the badge never reach anyone who is not logged in. Every public query filters on `published`.
- Photo keys and storage URLs are never exposed. Public photos are served only through the streaming route.
- Uploads are validated by magic bytes and size. A stored filename never comes from the client.
- Delete is a hard delete, and the audit log holds no personal data (SP9).
- Consent fields are set only by the server.

## 7. Tests

Backend — `tests/test_pub_022_*.py`:
- The migration unpublishes existing rows. The CHECK constraints reject publishing without consent and a rating outside 1–5. The badge table allows only one row.
- Permission matrix:
  - super_admin can act on both divisions;
  - it_admin on overseas content gets 403 or 404, and the same in reverse;
  - other roles get 403;
  - nobody except super_admin can use the badge endpoints.
- Consent:
  - publishing without consent returns 422;
  - unticking consent unpublishes;
  - `consent_by_user_id` and `consent_at` are set by the server.
- Public filtering: `/public/social-proof`, `/public/testimonials`, the detail route and `/public/home` hide unpublished rows. The strip's featured filter, ordering and 6-row limit work. `stats` is gone from `/public/home`.
- Photos:
  - uploading a type that isn't allowed, or a file over 2 MB, returns 422;
  - a fake extension is rejected by the magic-byte check;
  - an unpublished testimonial's photo returns 404;
  - delete removes the photo file.
- Audit: the delete row contains no name or quote.
- Update the existing upc/public tests that read `stats` or show unpublished testimonials.

Web:
- vitest: strip (empty, badge only, cards, initials fallback, aria labels); TestimonialManager (consent gating in the form, delete confirmation).
- tsc and eslint pass.
- Playwright `tests/e2e/pub-022-social-proof.spec.ts`: an admin publishes a testimonial, it appears on `/` and `/it`, and the layout holds at 375px.

## 8. Docs

- DEC-SCOPE-210 (SP1–SP9) in `docs/decisions/PRODUCT_DECISION_REGISTER.md`
- RBAC §2.135 and API §12DX
- A PUB-022 row in `docs/features/MASTER_FEATURE_CATALOG.md` and `docs/quality/RTM.md`
- QA note `docs/quality/PUB-022_QA_<date>.md`

## 9. Out of scope

- Google or other live review APIs.
- Stat counters (item #11).
- Hiring-partner logo wall (#2).
- An overseas success-stories page (#3).
- Video testimonials.
- Students submitting their own testimonials.

## 10. Implementation rulings (2026-10-14)

- **R1 — photo formats are JPEG and PNG only.** WebP is dropped. The existing magic-byte check and EXIF/GPS stripper (`app/services/image_metadata.py`) supports only those two formats, and a WebP photo would keep its location metadata.
- **R2 — the admin screens are dedicated pages:** `/admin/testimonials` (with the badge form), `/it/admin/testimonials` and `/overseas/admin/testimonials`. The generic `[module]`/`[section]` table pages can't do upload, delete-confirm or a consent tick.
- **R3 — photo errors follow the existing upload helper:**
  - 413 when a photo is over 2 MB;
  - 415 for a wrong type;
  - 422 for an empty or unreadable file.

  This replaces "422 for everything" in §4.2.
- **R4 — PUB-022 is recorded in DEC-SCOPE-210, RBAC §2.135 and API §12DX,** not in the approval-gated `MASTER_FEATURE_CATALOG.md` / `RTM.md` (the dtu-001 / mgmt precedent). §8 is amended accordingly.
- **Additions:**
  - **`photo_content_type`** (varchar 40) on `testimonials`, so the photo route serves the stored type.
  - **`consent_by_user_id` / `updated_by_user_id`** use `ON DELETE SET NULL`.
  - **Text limits:** `quote` ≤ 2000 characters. Name, headline, quote and context reject control and bidirectional-override characters (the shared `clean_free_text` rule).
  - **`display_order`** is limited to ±100000.
  - **Unchanged consent:** re-sending `consent_confirmed: true` leaves `consent_at` unchanged.
  - **The `/it/success-stories` e2e** (pub-001) now accepts the empty state, because seeded stories are unpublished (SP4).
