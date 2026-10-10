# upc-030 University 360 view — implementation plan

Spec: `docs/superpowers/specs/2026-10-10-upc-030-university-360-view-design.md` (UV1–UV12, AC1–AC8).

## Phase 3 review notes (applied to this plan)

**API:**
- One GET for the view plus one GET to download a file. Errors follow the master's style: 401, 403 for role or division, 404 for scope
  (no existence leak).
- Read-only, so there is no transaction except the download's audit commit.
- Pydantic `response_model` is not used: the exact-keys contract is enforced by the serializer and the snapshot tests, the same way
  the documents and courses routes do it.

**Security:**
- Allow-lists per slice, never strip-from-full.
- `strip_commission` stays on courses as a second line of defence.
- A recursive no-`commission` test.
- Rep scope comes from the server-owned `profile.university_id`.
- The download's file name is built by the server.
- The website is linked only when it is http(s).
- The page receives no PII beyond the slice.
- No new rate limits: plain authenticated reads, as on the master.

**Frontend:**
- A server component, data-only (memory: no function props to client components).
- `<section aria-labelledby>` cards in the existing `action-card` grid; the empty states are text.
- Tables sit in `table-wrap` for mobile.
- The search form is a GET form, so it needs no JavaScript.

## Tasks

1. **RED/GREEN API core:** `tests/test_upc_030_view.py`
   - snapshots per slice (AC1), no commission (AC2), counselor slice contents (AC3), unpublished/inactive 404 (AC4), rep scope (AC5),
     role/division 403 + 401 (AC6).
   - `app/services/university_view.py` (slice builders) + `app/api/university_view.py`, registered in `app/main.py`.
2. **RED/GREEN download (AC7):** the route reuses `university_documents.load/file_bytes/audit/download_name`.
3. **Frontend lib + component:**
   - `lib/universityView.ts`: types, `universityViewUrl`, `viewDocumentFileUrl`, `safeWebsite`.
   - `components/UniversityView.tsx`.
   - vitest `tests/components/UniversityView.test.tsx` covers the sections per slice, the empty states and a non-http website rendered
     as text.
4. **Pages:**
   - counselor list + detail.
   - `/bdm/universities/[id]`.
   - `/overseas/university/profile`.
   - nav items (counselor "universities", university "university-profile" → static `profile` route).
   - BDM org row link.
   - Update the nav tests.
5. **Docs:** DEC-SCOPE-162, API §12CD, RBAC §2.88, backlog status, SCREEN_CATALOG rows.
6. **Playwright** `e2e/upc-030-university-view.spec.ts`: a counselor searches, opens a university and sees the IELTS requirement; a
   rep opens their profile; a BDM opens it from the org link.
