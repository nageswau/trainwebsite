# nehn-032 — Certificate digital signatures (Founder + Coordinator) and designation

**Status:** builder's design, defaults `NEEDS_CONFIRMATION` (DEC-SCOPE-301). **Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md`
`nehn-032` (§11 L249-260, §26 L791-794, actions 11/12; `UNVERIFIED` backlog). Dependencies nehn-003 (`DEC-SCOPE-279`), nehn-030
(`DEC-SCOPE-293`), nehn-031 (`DEC-SCOPE-297`) are merged. The client's signature PNGs (CI-03) are content uploaded through this feature,
not a code dependency.

## Intent

Every newly issued IT certificate carries the Founder's and the Coordinator's signature images, names and designations, placed by the
system. Signature images are sensitive: they never leave the server except inside a rendered certificate or to the people who manage them.
A later change of signature must not change what an already-issued certificate says it was signed with.

## Goals / non-goals / anti-goals

- **Goals:** signatory versions per slot; admin upload with a PNG check; renderer draws both slots; certificates snapshot the versions
  used; issuing is refused while a slot is empty; an admin preview of the layout.
- **Non-goals:** reissue/revocation of old certificates (DEC-SCOPE-297 W9), the client's final visual design (§26 L794 — a later
  change), non-Latin-1 fonts on the certificate (student names already use the standard fonts), per-coordinator signatures.
- **Anti-goals:** a student (or anyone without the grant) able to fetch a signature image; an old PDF re-rendered with a new signature;
  an issued certificate with an empty or placeholder signature.

## Builder's defaults (S1–S9, `NEEDS_CONFIRMATION`)

- **S1 Slots.** Two fixed slots, `founder` and `coordinator`. The coordinator slot is a configured person, not the issuing coordinator
  (the backlog's open question; one signature per slot keeps the upload screen to two cards).
- **S2 Versions.** `certificate_signatories` rows: `id, role, display_name (≤120), designation (≤120), image_key, active_from, active_to,
  created_by_id`. Uploading a new signature for a slot closes the active row (`active_to = now()`) and inserts a new one. A partial unique
  index (`role` where `active_to IS NULL`) allows one active row per slot; the active row is locked while it is replaced, and a lost race is a 409.
- **S3 Edits.** `PATCH` changes the active row's name and designation in place (the PDFs already issued are fixed files and carry the
  snapshot), never its image; a new image is always a new version.
- **S4 Upload check.** The existing nehn-003 `signature` policy (PNG only, ≤ 1 MB, content type and magic bytes) plus a decode check:
  the image must open as a PNG, 50–2000 px wide and 20–1000 px high, and have an alpha channel (a transparent background). Anything else is
  415/413/422 with a plain message.
- **S5 Privacy.** Images are stored at `signatures/<uuid>.png` through `StorageService` (private, no public URL). Only grant holders can
  read them, through `GET /admin/certificate-signatories/{id}/image` (streamed, `Cache-Control: no-store`). They are never presigned.
- **S6 Grant.** A new `certificates.manage` action. super_admin holds it implicitly; no other role gets it by default (backlog:
  "only super_admin (or the `certificates.manage` grant)"). It can be granted on the permission matrix (nehn-006).
- **S7 Issue.** `_issue_certificate` loads both active rows; if either is missing it refuses with 409 "Certificate signatures are not
  configured…" (per item in bulk issue). The rendered PDF draws them and `certificates.signatory_snapshot` stores
  `[{id, role, display_name, designation}]`. Existing certificates keep `NULL`.
- **S8 Layout.** Slots sit between the program title and the authenticity rule (rule moves from y=195 to y=185): founder left,
  coordinator right, each centred in half the content width. Image box 170×50 pt, scaled to fit with its aspect ratio, bottom-aligned on a
  signature line; name (bold, shrinks to fit, min 7 pt) and designation (slate, shrinks to fit) under the line. Decoded images are cached
  per worker by key (keys are immutable).
- **S9 Preview.** `GET /admin/certificates/preview` (grant holders) returns an inline PDF with sample data, a deliberately long name and
  program, and the current signatories; nothing is stored or audited. 409 when a slot is empty.

## API

- `GET /admin/certificate-signatories` → `{items: [...]}` every version, active first per slot (≤ 100), with `active: bool`.
- `POST /admin/certificate-signatories` (multipart: `role`, `display_name`, `designation`, `file`) → 201 new active version; audited
  `certificate_signatory.upload`.
- `PATCH /admin/certificate-signatories/{id}` (`display_name?`, `designation?`) → 200; 409 when the row is not active; audited.
- `GET /admin/certificate-signatories/{id}/image` → `image/png`.
- `GET /admin/certificates/preview` → `application/pdf`.

All refuse 403 without `certificates.manage`.

## Web

The admin portal's Certificates section gains a "Certificate signatures" card, shown when the signed-in role holds `certificates.manage`:
one block per slot with the current image (from the image route), name and designation, an edit form for name/designation, a replace form
(name, designation, PNG) and a "Preview certificate" link that opens the preview PDF in a new tab. Loading, empty ("No signature
uploaded — certificates cannot be issued"), and error states; messages in `role=status`/`role=alert`.

## Data

Migration `0208_certificate_signatories`: the table (guarded create, 0204's idiom), the partial unique index, and
`certificates.signatory_snapshot JSON NULL`. No existing row changes. The downgrade drops the column and the table (stored images remain).
The demo seed (`app.seed`) adds a generated transparent PNG for both slots when a slot is empty, so local and CI issuing keeps working.

## Risks

Existing issuance tests and e2e need signatories (the seed provides them); the PDF layout (visual check in QA); a stale per-worker cache
is impossible because keys never change.
