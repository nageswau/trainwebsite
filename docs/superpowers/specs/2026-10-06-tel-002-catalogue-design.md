# tel-002 — Product/interest catalogue + campaign list (design)

- **Feature:** `tel-002` in `docs/delivery/TELECALLER_CRM_BACKLOG.md` §4. Source `EVID-019` §2 (lead sources, "exact campaign/source")
  and §3 (product/interest list). Scope authority `DEC-SCOPE-073` T16, T17, T18 plus the owner answers P1–P4 below (`DEC-SCOPE-074`).
- **Depends on:** tel-001 (merged, PR #68 @ `e73dfa60`, migration `0075`). Branch `feature/tel-002` from `origin/main` @ `e73dfa60`.
- **Migration:** `0076_tel_catalogue` (provisional; re-chain at merge if main moved).

## 1. Owner answers (2026-10-06, `EXPLICIT_APPROVAL`)

| # | Question | Answer |
|---|---|---|
| P1 | Who reads the lists ("others read active items only") | `telecaller`, `telecaller_manager`, `super_admin`, `it_admin`, `overseas_admin`, `counselor` read **active** rows. `telecaller_manager` and `super_admin` also see inactive rows. Every other role → 403 |
| P2 | Which team routes a product (T18) | **Fixed for IT/Overseas:** an IT product's team is `it`, an Overseas product's is `overseas`. Only `other` products have an editable team (`it`, `overseas`, or none = unassigned queue). The optional course link is IT-only and points at an IT `programs` row |
| P3 | Campaign dates | Start **required**, end optional. End before start → 422 |
| P4 | Deactivation | **Independent.** Deactivating a product leaves its campaigns alone. A campaign can be created on, or moved to, an **active** product only; an existing campaign whose product was deactivated stays editable |

## 2. Acceptance criteria (backlog AC1–AC4, made testable)

- **AC1** After `alembic upgrade head` all 18 §3 values exist: 5 `it` (team it), 9 `overseas` (team overseas), 4 `other` — Job Assistance
  and Career Change team `it`; Career Guidance and General Enquiry team none (T18). Re-running the seed never duplicates.
- **AC2** A deactivated product or campaign is absent from the reader lists (pickers) and from `active=true`; its row is unchanged and
  still returned by id-bearing reads for managers (it stays on existing leads — tel-003 adds the FK).
- **AC3** A campaign's `source` must be one of the 13 §2 sources (else 422) and its product must exist and be active (else 422).
- **AC4** `end_date < start_date` → 422 (API and DB CHECK).
- **AC5** (backlog negative) A `telecaller` (or any non-manager) POST/PATCH → 403; a duplicate product name in a group (case-insensitive)
  → 409; a duplicate campaign name (case-insensitive, global) → 409.
- **AC6** (edge) Renaming a product keeps its id (links survive); changing an "Other" product's team only changes the row (no lead
  exists yet to re-route — tel-007 reads it at distribution time).
- **AC7** (P2) An IT/Overseas product with a team ≠ its group → 422; a course link on a non-IT product → 422; the group cannot change → 422.

## 3. Data model (migration `0076_tel_catalogue`)

`tel_products`: `id` uuid PK; `product_group` varchar(20) NOT NULL CHECK in (`it`,`overseas`,`other`); `name` varchar(120) NOT NULL;
`team` varchar(20) NULL CHECK in (`it`,`overseas`); CHECK `product_group = 'other' OR team = product_group`; `program_id` uuid NULL FK
`programs.id`; CHECK `program_id IS NULL OR product_group = 'it'`; `active` bool NOT NULL default true; `sort_order` int NOT NULL default 0;
timestamps. Unique index `uq_tel_products_group_name` on (`product_group`, `lower(name)`).

`tel_campaigns`: `id` uuid PK; `name` varchar(160) NOT NULL; `source` varchar(30) NOT NULL CHECK in the 13 keys; `product_id` uuid NOT
NULL FK `tel_products.id`; `start_date` date NOT NULL; `end_date` date NULL; CHECK `end_date IS NULL OR end_date >= start_date`; `active`
bool NOT NULL default true; timestamps. Unique index `uq_tel_campaigns_name` on `lower(name)`; index `ix_tel_campaigns_product`.

Sources (§2, fixed — not manager-edited): `instagram, facebook, google, website, whatsapp, walk_in, college, school, agent, referral,
exhibition_event, bdm, other` with labels Instagram … Exhibition/Event, BDM, Other.

Migration: table creation is guarded (0001 builds from the current models — the 0075 idiom); the seed always runs and inserts only
missing `(group, lower(name))` pairs, so it is idempotent and never overwrites a manager's edits. `downgrade()` refuses while any campaign
exists or any product differs from the seed (both are manager data); otherwise drops both tables. No existing row is read or written.

## 4. API (`app/api/telecaller_catalogue.py`, `app/services/telecaller_catalogue.py`)

Inline authorization (user convention): role check → write. Lists reuse `{items,total,limit,offset}`, `LIMIT/OFFSET/SEARCH`, `_matching`.

| Method | Path | Who | Notes |
|---|---|---|---|
| GET | `/telecaller/products?group=&active=&q=` | P1 readers | non-managers always get active only (an `active` param cannot widen it). Order: group (it, overseas, other), `sort_order`, name |
| POST | `/telecaller/products` | manager, super_admin | 201; body `{group, name, team?, program_id?, sort_order?}`; `team` defaults to the group for it/overseas |
| PATCH | `/telecaller/products/{id}` | manager, super_admin | `{name?, team?, program_id?, active?, sort_order?}`; `group` → 422; unknown id → 404 |
| GET | `/telecaller/campaigns?product_id=&source=&active=&q=` | P1 readers | same active rule. Order: active first, `start_date` desc, name |
| POST | `/telecaller/campaigns` | manager, super_admin | 201; `{name, source, product_id, start_date, end_date?}` |
| PATCH | `/telecaller/campaigns/{id}` | manager, super_admin | `{name?, source?, product_id?, start_date?, end_date?, active?}`; the date rule is checked on the merged row |

Rows: product `{id, group, name, team, program: {id, title} | null, active, sort_order}`; campaign `{id, name, source, product: {id, name,
group, active}, start_date, end_date, active}`. Validation: names trimmed, required, ≤120/160, no control characters; bodies `extra=forbid`;
explicit `null` on a required key → 422. Errors name the field ("Name is required").

Transactions/races: one transaction per write; duplicate names are decided by the unique indexes (`IntegrityError` → 409, rollback). A
campaign's product is read `FOR SHARE` when it is set/changed, so a concurrent product deactivation waits and the "active product" rule
holds. A course link must be an active `programs` row (checked when set/changed). Every write adds an `AuditLog` row
(`telecaller.product_create|product_update|campaign_create|campaign_update`, entity id, changed field names only).

## 5. Frontend

- `TELECALLER_MANAGER_NAV` gains **Products** (`/telecaller/manager/products`) and **Campaigns** (`/telecaller/manager/campaigns`). Both
  are PortalShell pages (middleware already sends signed-out `/telecaller/manager/*` to `/admin/login`; super_admin uses the same URLs,
  as for the Team page).
- `TelecallerProductsPanel` (+ `TelecallerProductRow`) and `TelecallerCampaignsPanel` (+ `TelecallerCampaignRow`): the
  `AdminTelecallerPanel` pattern — create form, list with loading / error+Retry / empty / pager, inline edit (Esc cancels),
  deactivate with inline confirm, reactivate, `role="status"` notices, focus management, double-submit guard (`useRef`), mobile card
  layout via the existing `.telecaller-list` CSS.
- Shared picker source `lib/telecallerCatalogue.ts`: types, `SOURCES` labels (display only — the API decides), `activeProducts()`
  (used by the campaign form; tel-003 reuses it for leads). The IT course link uses the existing public `GET /public/programs`.

## 6. Security review

Auth: every route needs a session (`get_current_user`, inactive users already refused). AuthZ: role sets in the service; no row-level scope
(the catalogue is global, T17). IDOR: ids are catalogue rows, not personal data. Input: Pydantic, extra=forbid, length caps, control
characters refused; React escapes output (no `dangerouslySetInnerHTML`). SQL: ORM + escaped ILIKE (`lookups._pattern`). CSRF: the
existing cookie/session model of `/api/v1` applies unchanged. Logging: ids and field names only. Rate limiting: none added (manager-only
writes on a small table).

## 7. Alternatives considered

- Sources as a managed table — rejected: §2 gives a fixed list and AC3 says "from the §2 list".
- Reusing `programs` as the product list — rejected: T17 says a managed list with overseas/other groups; `program_id` is an optional link.
- One `/telecaller/catalogue` endpoint — rejected: two resources with different rules; separate routes match the backlog's API.

## 8. Regression risk

Low: two new tables, one new router, two nav entries. Touches `main.py` router tuple, `models.py`/`schemas.py` (append-only),
`navigation.ts` (manager nav). Existing `/telecaller/manager/team` and its tests must still pass.
