# tel-012 — Script, message-template and brochure library (design)

NO-ASSUMPTION MODE. Backlog: `docs/delivery/TELECALLER_CRM_BACKLOG.md` §4 tel-012. Source: `EVID-019` §6, §11, §12. Authority: T9
(`DEC-SCOPE-073`), owner answers C1–C4 of 2026-10-06 (`EXPLICIT_APPROVAL`, recorded as **`DEC-SCOPE-078`**, provisional — re-check
`main` before merge). Branch `feature/tel-012` from `origin/main` @ `442ce465`. Migration **`0079_tel_content`** after
`0078_enquiry_lead_record`.

## 1. Owner answers

| # | Question | Answer |
|---|---|---|
| C1 (Q-15) | Signed-out brochure links | A signed, asset-scoped token valid **7 days**, served by a public streaming endpoint. Deactivating the asset kills every link at once. No file is ever public by URL. |
| C2 | Lead-dependent parts | Build the library + a manager/telecaller **preview** now. `GET /telecaller/leads/{id}/render` and the lead-detail script panel move to **tel-008 / tel-013** (they need tel-003's lead product and tel-008's ownership; both already depend on tel-012). |
| C3 | Script shape | A script has a **required product**, a name and **ordered steps** (title + optional talking points). **At most one active script per product** (its standard script). Seed: the Cyber Security 7-step example. |
| C4 | Seed wording | One **generic** template (no product) per kind — 9 WhatsApp + 7 email — with short neutral English text. Managers edit or deactivate them. |

Recorded defaults (not asked, following T9 and tel-002 P1): writers = `telecaller_manager`, `super_admin`; readers = those two plus
`telecaller`; telecallers see active rows only. Nothing is deleted — deactivation hides a row from pickers; later message history keeps
the name (tel-013).

## 2. Approaches considered

1. **Three tables, one service module, one router (chosen).** Mirrors tel-002 (`telecaller_catalogue`): small focused tables, inline
   role checks, `_parse` 422 sentences, audit with field names only.
2. One generic `tel_content` table with a type column — rejected: scripts (steps), templates (channel/subject) and assets (file) share
   almost no columns; check constraints would become conditional soup.
3. Reuse ENH-014 notification templates — rejected: they live in code, not manager-editable, and target users not leads.

## 3. Data (migration `0079_tel_content`)

`tel_assets` — id, `name` varchar(160), `kind` ∈ {`brochure`, `fee`}, `product_id` → tel_products NULL, `storage_key` varchar(255)
UNIQUE (server-generated `tel-assets/<uuid4hex>`), `file_name` varchar(255) (display only), `size_bytes` int, `active` bool,
`uploaded_by_user_id` → users, timestamps. Always a PDF, so no content-type column.

`tel_message_templates` — id, `channel` ∈ {`whatsapp`, `email`}, `kind` varchar(40) (checked per channel), `name` varchar(160),
`product_id` → tel_products NULL, `asset_id` → tel_assets NULL, `subject` varchar(200) NULL, `body` text, `active`, timestamps.
Checks: kind belongs to channel; `(channel = 'email') = (subject IS NOT NULL)`. Unique `(channel, lower(name))`.

Kinds — WhatsApp (§11): `welcome`, `course_details`, `brochure`, `fee_details`, `counselling_appointment`, `reminder`, `follow_up`,
`overseas_destination`, `document_request`. Email (§12): `course_brochure`, `fee_proposal`, `counselling_confirmation`,
`overseas_information`, `university_information`, `follow_up`, `appointment_confirmation`.

`tel_scripts` — id, `product_id` → tel_products NOT NULL, `name` varchar(160), `steps` JSONB (list of `{title, notes}`), `active`,
timestamps. Partial unique index `uq_tel_scripts_active_product (product_id) WHERE active` enforces C3 even under a race.

Creation is guarded (0001 builds a fresh DB from the models — 0076's idiom). Seeds always run and insert only what is missing:
16 templates by `(channel, lower(name))`; the Cyber Security script only when the IT product "Cyber Security" exists and has no script.
`downgrade()` refuses while manager data exists (any asset, or any template/script row that is not an untouched seed).

## 4. Placeholders and rendering (`services/telecaller_content.py`)

Allowed: `{name}`, `{product}`, `{brochure_link}`, `{appointment_time}`. On save every `{…}` token in subject and body is checked;
an unknown one → **422** "Unknown placeholder {x}. Use {name}, {product}, {brochure_link} or {appointment_time}" (AC3).
`{brochure_link}` additionally needs the template to have a brochure (`asset_id`) — checked on the merged row → 422.
A linked asset must be active when it is set or changed (FOR SHARE lock, the `locked_active_product` idiom).

`render(text, values)` is a single-pass `re.sub`: a value containing `{name}` is never expanded again. Output is **plain text**;
escaping belongs to the sink — tel-013 URL-encodes for wa.me, tel-014 HTML-escapes the whole rendered body (the ENH-005 mailer
precedent). Escaping values here would double-escape there.

Preview: `GET /telecaller/templates/{id}/preview` renders with sample values (`Priya Sharma`, the template's product or
`Cyber Security`, `Mon 14 Sept 2026, 10:30 AM`) and, when the template has an active asset, a real signed brochure link.
Read-only: it writes nothing except minting a token (no DB row).

## 5. Signed brochure links (C1)

Token = JWT HS256 with `settings.secret_key`, claims `{sub: asset_id, type: "tel_asset", exp: now + 7 days}`. `deps.get_current_user`
already rejects any token whose type is not `access`, so a link token is never a session; the public route accepts only
`type == "tel_asset"`, so a session token is never a link.

- `POST /telecaller/assets/{id}/link` (readers) → `{url, expires_at}`, `url = {FRONTEND_URL}/api/v1/public/telecaller-assets/{token}`.
  Inactive or missing asset → 404.
- `GET /public/telecaller-assets/{token}` (no auth) → 200 `application/pdf`, `Content-Disposition: inline; filename*=UTF-8''…`,
  `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`. Bad signature, wrong type, expired, missing or **inactive** asset →
  404 "This link has expired or is no longer available" (one answer, so nothing is learned about which). AC4.
- The token is never logged. No rate limit: the endpoint only verifies an HMAC (no guessable space) and streams one file.
- Accepted risk (agent-documents precedent): with local storage the object also sits under the `/local-files` static mount, but its key
  is 128 random bits and is never returned by any API.

## 6. API (`api/telecaller_content.py`, prefix `/telecaller`; public route on a second router)

Lists return `{items,total,limit,offset}` with `LIMIT/OFFSET/SEARCH` from `api/bdm`; `q` matches name; telecallers get active rows only
(`active_filters`).

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/scripts?product_id&active&q` | readers | ordered active first, product name, name |
| POST | `/scripts` | writers | `{product_id, name, steps}`; product active; 409 if the product already has an active script |
| PATCH | `/scripts/{id}` | writers | name, steps, product_id, active; reactivating/moving into a product with an active script → 409 |
| GET | `/templates?channel&kind&product_id&active&q` | readers | ordered channel, kind order, name |
| POST | `/templates` | writers | `{channel, kind, name, product_id?, asset_id?, subject?, body}` |
| PATCH | `/templates/{id}` | writers | channel fixed (422); kind re-checked against channel |
| GET | `/templates/{id}/preview` | readers | §4 |
| GET | `/assets?kind&product_id&active&q` | readers | newest first |
| POST | `/assets` | writers | multipart `file`, `name`, `kind`, `product_id?` |
| PATCH | `/assets/{id}` | writers | name, kind, product_id, active (metadata only; no file replace) |
| POST | `/assets/{id}/link` | readers | §5 |
| GET | `/public/telecaller-assets/{token}` | anyone | §5 |

Validation: names trimmed 1–160, no control characters; steps 1–20, title 1–120, notes ≤ 1000; subject 1–200 single line (CR/LF/
control → 422 — header-injection guard for tel-014); WhatsApp body ≤ 1000, email body ≤ 5000, tabs/newlines allowed, other control
characters refused. Upload: empty → 422; > `max_upload_bytes` → 413; bytes not starting `%PDF-` → **422** "Upload a PDF file"
(backlog negative scenario); the client name/content type are never trusted. The object is written before the row; if the DB write
fails the object is deleted (`discard`). Every write is audited (`telecaller.script_*`, `telecaller.template_*`,
`telecaller.asset_*`) with ids and field names only.

## 7. Frontend

`TELECALLER_MANAGER_NAV` gains Scripts, Templates, Brochures. Pages `/telecaller/manager/{scripts,templates,brochures}` reuse the
`TelecallerCataloguePage` shell (manager + super_admin). Each panel follows `TelecallerProductsPanel`: create form with feedback focus,
double-submit guard, list with loading / error + Retry / empty / pager, filter in the URL, rows with inline edit (Esc), deactivate
with inline confirm, reactivate. Specifics: the script form edits an ordered step list (add, remove, move up/down); the template row
offers Preview (rendered subject/body + brochure link); the brochure form uploads a PDF (client pre-check of type/size, server
decides) and each brochure row offers "Copy link" (7-day link). Shared code in `lib/telecallerContent.ts`.

## 8. Acceptance criteria (testable)

1. AC1 Seeded: 9 WhatsApp + 7 email generic templates and the Cyber Security 7-step script exist after migration.
2. AC2 Rendering fills `{name}`, `{product}`, `{brochure_link}`, `{appointment_time}` (unit + preview endpoint); single pass.
3. AC3 Unknown placeholder → 422 on create and update; `{brochure_link}` without a brochure → 422.
4. AC4 An asset link works signed-out until expiry, fails after expiry, after deactivation, and for a tampered/session token.
5. AC5 Non-PDF upload → 422; oversize → 413.
6. AC6 Writers only: telecaller and other roles get 403 on writes; non-readers 403 on reads; telecaller never sees inactive rows.
7. AC7 One active script per product → 409; deactivated rows disappear from telecaller lists but keep their names.
8. AC8 Manager screens: create, edit, deactivate/reactivate, preview, upload and copy link work with keyboard; responsive at 375/768/1280.

## 9. Out of scope (moved by C2)

Lead render route, lead-detail script panel, message sending/logging (tel-013/014), consent (Q-21).
