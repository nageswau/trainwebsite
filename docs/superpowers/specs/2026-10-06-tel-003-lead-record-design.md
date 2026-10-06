# tel-003 — Lead record: `enquiries` extension, Lead ID, admin list alignment (design)

Backlog: `docs/delivery/TELECALLER_CRM_BACKLOG.md` tel-003 (EVID-019 §2, Appendix A L22–L90; `DEC-SCOPE-073` T6, T25, T29).
Dependencies: tel-001 (PR #68), tel-002 (PR #69) and bdm-017 (`0074`) are all merged on `main` @ `784738e7`. Branch `feature/tel-003`.
Decision: `DEC-SCOPE-077`. Migration: `0078_enquiry_lead_record` (after bdm-008's `0077_bdm_tasks_followups`). Drafted as
`DEC-SCOPE-075` / `0077`; re-chained on merging `main` @ `675762d3` (bdm-008 took 075 and 0077, tel-017 took 076 and API contract §12E).

## 1. Owner answers (2026-10-06, `EXPLICIT_APPROVAL`) and recorded defaults

| # | Question | Answer |
|---|---|---|
| L1 (Q-01) | Lead ID format | **`LD-000001`, one global sequence**, assigned by the database default on every insert path; existing rows are backfilled oldest-first (`created_at`, `id`) |
| L2 | Legacy `source` values outside the §2 list | **Lower-case and trim first; anything still unknown becomes `other`**, and the original text is copied into `metadata_json.legacy_source`. The public API then answers 422 for a source outside the list |
| L3 (Q-04, default) | Mobile normalisation | Reuse `app/notifications/phone.normalise_phone` (ENH-014): `+` and 8–15 digits are kept as typed; an Indian 10-digit mobile (optionally prefixed `0`/`91`) becomes `+91…`; anything else → `NULL` |
| L4 (Q-03, deferred) | Nullable `email` | **Not changed in tel-003.** Every current intake path requires an email; the phone-only manual lead arrives with tel-005, which owns the change |
| L5 (default) | Status editor on the admin list | **Unchanged in tel-003** (the same 5 options, the same `PATCH`). The backlog states "valid transitions (via tel-004)"; tel-004 owns the stage engine and replaces the editor |
| L6 (default) | Q-02 / Q-21 | Deferred to tel-004 (status mapping) and tel-005/013/014 (consent, retention). Not decided here |

## 2. Acceptance criteria (backlog AC1–AC5, made testable)

1. **AC1** Every existing and new enquiry has a unique Lead ID matching `^LD-\d{6,}$`. The backfill numbers existing rows oldest-first,
   and the sequence continues after the highest backfilled number. Website, BDM, seed and direct-model inserts all get one. 20
   concurrent creates get 20 distinct codes.
2. **AC2** `POST /public/enquiries` still answers 201 with `id`, `status` and `crm_sync_status`, plus `lead_code`. A `source` outside the
   13 §2 values → 422. The CRM webhook payload gains `lead_code` (additive).
3. **AC3** `GET /admin/leads` returns `{items,total,limit,offset}` (limit 1–100, default 50; offset ≥ 0) and filters by `status`
   (stage), `product_id`, `campaign_id`, `telecaller_user_id`, `source`, `bdm_organization_id` and `q` (Lead ID, name, email, phone,
   subject; a literal case-insensitive substring). Every filter is ANDed with the existing division scope. Rows add the new fields.
   The admin panel pages, filters and searches through the API, with the state kept in the URL.
4. **AC4** bdm-017's attribution and link columns, their CHECKs and indexes, and the conversion routes are untouched (same tests pass).
5. **AC5** Downgrade refuses while new data exists (any non-default value in a column a downgrade would drop: `whatsapp_number`,
   `city`, `state`, `qualification`, `passing_year`, `institution`, `product_id`, `campaign_id`, `telecaller_user_id`, or a
   `priority` other than `warm`). Otherwise it restores `source` from `metadata_json.legacy_source` and drops the columns.
- **Edge:** a legacy row with an invalid phone keeps `phone_normalized = NULL`. A `phone` edit re-derives `phone_normalized` (model
  validator), so it never goes stale.

## 3. Data model (migration `0078_enquiry_lead_record`)

New columns on `enquiries`:

| Column | Type | Rule |
|---|---|---|
| `lead_code` | `varchar(20)` NOT NULL, unique `uq_enquiries_lead_code` | server default `'LD-' \|\| translate(format('%6s', nextval('enquiry_lead_code_seq')), ' ', '0')`: zero-padded to 6, and it **never truncates** past 999999 (unlike `lpad`); one `nextval`, so it is atomic |
| `phone_normalized` | `varchar(20)` NULL | set by `@validates("phone")` on the model (every path); migration backfills with a frozen copy of the rule |
| `whatsapp_number` | `varchar(40)` NULL | |
| `city`, `state` | `varchar(120)` NULL | |
| `qualification` | `varchar(120)` NULL | |
| `passing_year` | `integer` NULL | CHECK `ck_enquiries_passing_year`: NULL or 1950–2100 |
| `institution` | `varchar(200)` NULL | College/University |
| `product_id` | FK `tel_products.id` NULL | |
| `campaign_id` | FK `tel_campaigns.id` NULL | |
| `telecaller_user_id` | FK `users.id` ON DELETE RESTRICT NULL | set by tel-007 |
| `priority` | `varchar(10)` NOT NULL default `'warm'` | CHECK `ck_enquiries_priority` in hot/warm/cold (tel-008 edits it) |
| `stage_changed_at` | `timestamptz` NOT NULL default `now()` | backfilled to `created_at`; tel-004 maintains it |

- CHECK `ck_enquiries_source`: `source IN TEL_SOURCES` (13 values). The model reads `app/tel_sources.py`; the migration keeps a frozen copy.
- Indexes: `ix_enquiries_telecaller_status (telecaller_user_id, status)`, `ix_enquiries_phone_normalized`, `ix_enquiries_email_lower
  (lower(email))`, `ix_enquiries_campaign`, `ix_enquiries_product`.
- `Sequence("enquiry_lead_code_seq", metadata=Base.metadata)`, so 0001's `create_all` builds it before the table on a fresh database.
  The migration creates it `IF NOT EXISTS`. Upgrade is guarded (0074's idiom: skip if `lead_code` exists).
- Upgrade order: sequence → nullable columns → source normalisation (L2) → `lead_code` backfill via `row_number()` then `setval` →
  phone backfill (batched Python, ids only) → `stage_changed_at = created_at` → NOT NULL + defaults → CHECKs → indexes.
- `owner_id` keeps its meaning (assigned counselor). bdm-017's columns are untouched. The model gets `eager_defaults` so the
  server-generated `lead_code` / `stage_changed_at` come back in `RETURNING` (no lazy load on an async session).

## 4. API

- `schemas.EnquiryIn.source: TelSource = "website"` → 422 outside the list. `public.create_enquiry` returns `lead_code` too.
- `admin.leads` (inline auth unchanged: `ensure_admin` + division scope) → `{items,total,limit,offset}` with `LIMIT`/`OFFSET`/`SEARCH`
  from `api/bdm.py`, `like_pattern` + `_matching` for `q`, newest first (`created_at desc, id desc`). The 500-row cap is gone.
- `services/bdm_leads.admin_rows/admin_out` add outer joins to `TelProduct`, `TelCampaign`, the telecaller and the counselor (`owner_id`)
  and the keys `lead_code`, `priority`, `whatsapp_number`, `city`, `state`, `qualification`, `passing_year`, `institution`, `created_at`,
  `stage_changed_at`, `product {id,name}`, `campaign {id,name}`, `telecaller {id,full_name}`, `counselor {id,full_name}` (each object null
  when absent). All existing keys are unchanged, so the conversion routes' single-row answer gains the same keys.
- `worker.sync_enquiry_to_crm_task` payload adds `lead_code`.
- `PATCH /admin/leads/{id}` is unchanged (L5).

## 5. Frontend

- `AdminLeadManagementPanel.tsx`: fetch the page from the API with `q`, `status`, `source`, `product_id`, `campaign_id`,
  `telecaller_user_id`, `bdm_organization_id` and `offset` read from the URL (tel-002 QA-04 idiom: refresh keeps the place, Back works).
  Filters: Stage, Source (the 13 labels; "Website" replaces the old "Website (no organization)" option), Product (the tel-002
  `TelecallerProductOptions` picker), Campaign, Telecaller (`/admin/users?role=telecaller`), Organization (the organizations on the
  current page plus the selected one). The search becomes a submit-on-Enter search form. A pager appears when `total > 50`.
- Columns: Name (the sticky row header, kept first so it stays in view — QA17-03), Lead ID, Interest (product name, else subject),
  Source · Campaign, Telecaller, Priority, Organization, CRM sync, Status, Student, Action. The filter bar is its own component
  (`AdminLeadFilters.tsx`; frontend review: keeps the panel focused). Loading / error + Retry / empty / no-match states. The table scrolls horizontally inside `table-scroll`.
- `app/admin/[module]/page.tsx` leads table reads `.items` and shows `lead_code` as the reference.
- `lib/telecallerCatalogue.ts`: `activeCampaigns()`, built on the same paged reader as `activeProducts()`.

## 6. Security review

- AuthN/AuthZ unchanged: the same `ensure_admin` dependency and the same division `WHERE`. Every new filter only narrows (IDOR: a
  `product_id`/`telecaller_user_id` from another division matches no rows in scope). The telecaller filter list comes from the same
  division-scoped `/admin/users`.
- `q` is a bound `ILIKE` with escaped wildcards (`like_pattern`), so no SQL injection or wildcard abuse. React escapes every value, so no XSS.
- PII: new PII columns on a shared table. No new logs. The migration logs nothing per row. Audit is unchanged (no new write route).
- Public endpoint: a stricter `source` only. No new public field is accepted.

## 7. Alternatives considered

- Lead code assigned in Python (bdm-002 idiom): every `Enquiry(...)` creator (public, BDM, seed, 5 test files, future tel-005/006)
  would have to remember it. **Rejected** for the DB default.
- A SQL function for the code: needs a DDL hook for fresh databases. `translate(format('%6s', …))` is a plain expression.
- Keep the list unpaginated with a higher cap: it contradicts AC3 and T25.

## 8. Regression risk

High. The list shape is a breaking change, so every consumer is updated in this item: `AdminLeadManagementPanel`, the admin module
table, `test_adm_002`, `test_bdm_017_conversion`, the `pub-002` / `adm-002` / `bdm-017` e2e specs. Untouched readers that the lite set
re-runs: counselor My Leads (`test_cns_001`), RPT-001 (`test_rpt_001`), the dashboard, the BDM organization lead list
(`test_bdm_017_leads`), and the CRM sync (`test_pub_002_enquiry_crm`).
