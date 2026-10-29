# nehn-035 — University logo upload and richer university cards (design)

- **Feature:** `nehn-035` (backlog `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` §nehn-035; action 16; §17 L486-492, §26 L798-800).
- **Decision:** `DEC-SCOPE-331`. **API:** §12IC. **RBAC:** §2.234. **Migration:** none (reuses `universities.logo_url`).
- **Dependency:** `nehn-003` (merged, PR #345) — its `university_logo` upload policy and its `public/` storage prefix.

## Existing behaviour (discovery)

- `University.logo_url` (String 500) exists; `UniversityLogo.tsx` falls back to a monogram tile; 21 bundled logos under `/universities/logos/`.
- `UniversityForm.tsx` takes a typed URL only; `LogoUrl` (`schemas.py`) accepts `/universities/logos/<slug>.<ext>` or any `https://` URL.
- `upload_policy.POLICIES["university_logo"]` = PNG, WebP, JPEG, 1 MB. SVG is not in the list (415), and its bytes sniff as text anyway.
- Public catalogue cards: logo, city, name, overview, eligibility, "University profile". No country, program count, Apply, or country filter
  (the API's `?country=<slug>` filter exists since nehn-034, the catalogue's controls do not).
- A logged-out visitor opening a protected route is sent to `/<division>/login?next=<path+query>` and returned there (middleware + LoginForm).

## Decisions (open questions took the builder's defaults; NEEDS_CONFIRMATION by the client)

| ID | Decision |
|---|---|
| L1 | **Upload route** `PUT /api/v1/partnership/universities/{id}/logo` (multipart `file`). Same rule as editing the university (`can_edit`: super_admin, overseas_admin, the university's managers, their head) — row lock, scope check, audit `university.logo`, one commit. Bound to a saved university, so no orphan uploads and resource scope is the existing one; the add form says "upload after saving". |
| L2 | **File rules:** the nehn-003 `university_logo` policy (PNG / JPEG / WebP, ≤ 1 MB, declared type must match the magic bytes). **SVG is refused (415), not sanitised** — no XSS surface. Width and height must each be 32–2048 px (422), read from the header without decoding pixels. PNG/JPEG metadata is stripped (existing `image_metadata`). |
| L3 | **Storage:** key `public/university-logos/<32 hex>.<png|jpg|webp>` through `StorageService` (S3 or local). Logos are public by design. `logo_url` becomes `/api/v1/public/university-logos/<name>`, served by a public route that works in both storage modes, with `nosniff` and a long immutable cache (names are never reused). |
| L4 | **Replace / clear:** when an upload or the form's `PATCH` lets an uploaded logo go (matched by the URL shape), its object is deleted after the commit, unless another university still points at it (the form accepts a copied URL; QA-02). If the upload's commit fails, the new object is deleted. A bundled or `https://` logo is never touched. |
| L5 | `LogoUrl` also accepts the uploaded shape, so the form's PATCH can re-send it. Everything else about the validator is unchanged. |
| L6 | **Public list payload** (`GET /public/universities`) gains additive `programs_count` (active overseas courses), `country_name`, `country_slug`, `country_iso2`. Two queries, no N+1. Other routes keep the defaults (`0` / `null`). |
| L7 | **Card:** logo, country flag + country name + city, name, overview, eligibility, "N programs" badge, "View details" and "Apply". Apply is **hidden when the university has 0 programs** (backlog edge case). Apply → `/overseas/student/applications?university=<slug>`; logged out, the middleware sends the visitor to the overseas login and back. |
| L8 | **Country filter** in the catalogue controls (client-side, like City). |
| L9 | `OverseasApplyPanel` reads `?university=<slug>` and preselects that university and its country. An unknown/unpublished slug preselects nothing. |
| L10 | **Copyright (§26 L800):** a form hint asks for a logo the organisation may use. Formal client guidance remains NEEDS_CONFIRMATION (CI-04). |

## Security

- AuthN: upload needs a session (401); AuthZ: `can_edit` + scope (403 for wrong role/team, 404 unknown id, 409 inactive). The public read takes
  no session but only names matching `^[0-9a-f]{32}\.(png|jpg|webp)$` under the fixed prefix (no traversal; 404 otherwise).
- Content type of the served file comes from the server-chosen extension, never the client's; `X-Content-Type-Options: nosniff`.
- No SVG, no HTML: nothing that can execute in our origin is ever stored. Logs carry ids, sizes and types only.

## Tests

- Backend `tests/test_nehn_035_university_logos.py`: upload happy path + public read; SVG with `<script>` 415; 10 MB 413; renamed text 415;
  too small / too large dimensions 422; wrong role 403; out-of-team manager 403; unknown id 404; no session 401; replace deletes the old
  object; validator accepts the uploaded shape and still rejects others; public route 404s bad names; list payload counts only active
  courses and carries the country. Unit tests for `image_size`.
- Frontend (vitest): catalogue card fields, Apply hidden at 0 programs, country filter; form upload (preview, error, field updated);
  apply panel preselect.
- E2E (Playwright): admin uploads a PNG on the edit page → the card and detail page show it; logged-out Apply → login → apply form preselected.
