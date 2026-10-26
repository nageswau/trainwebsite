# nehn-042 — Audit log search and filters (design)

**Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-042` (§23 L606, "appropriate activity history/audit
information"; `UNVERIFIED` backlog). Decision `DEC-SCOPE-288`. No upstream dependency.

## Intent

Activity history is kept (`audit_logs`), but it cannot be found: `GET /admin/audit` returns the newest 500 rows with no filters, and a
division admin's rows are picked in Python *after* that cap, so an IT Admin can see fewer than 500 of their own rows and nothing older.
An admin must be able to trace, for example, who applied a discount to one payment, however old the row is.

## Builder's defaults (owner pre-authorised recommended answers; `NEEDS_CONFIRMATION`)

- **A1 Filters (additive query parameters on `GET /admin/audit`):** `actor` (user id), `action` (prefix, case-sensitive, so `payment.`
  finds every payment action and `payment.discount` exactly that one; `%`/`_` are literal), `entity_type` (exact), `entity_id` (exact),
  `division` (`it` | `overseas` | `global`: the actor's division), `date_from` / `date_to` (India calendar days, inclusive, as Management
  activity MA6). `date_to` before `date_from` is a `422`; an unknown `division` is a `422`; a malformed `actor` or date is FastAPI's `422`.
- **A2 Paging:** `limit` (1-500, default 500 = today's page) and `offset` (≥ 0, no cap), newest first with `id` as the tie-break so pages
  are stable. **The response stays a JSON array** (existing clients and tests read it as one); the web asks for one row more than it shows
  to know whether a next page exists, so no `COUNT(*)` runs over the whole table.
- **A3 Division scope in SQL:** super_admin sees every row. it_admin / overseas_admin see rows whose actor is in their own division, plus
  system rows (no actor) — exactly today's rule, now a `WHERE` clause, so the cap and paging apply after scoping. A `division` filter
  narrows within that scope (an IT Admin asking for `overseas` gets an empty list, never overseas rows).
- **A4 Rows gain `actor`** (`{id, full_name, email, division}` or `null`), additive. A row whose actor was removed keeps `user_id` and has
  `actor: null`; rows of deleted entities still show (audit rows have no FK to their entity).
- **A5 Unchanged:** who may read (`ensure_admin`: the three admin roles; anyone else `403`); MA8 (finance and partner-only management
  rows stay hidden); `POST /admin/audit/export` (Super Admin, newest 2000, self-audited).
- **A6 Indexes:** `ix_audit_logs_created_at (created_at)` is new; `ix_audit_logs_user_id` already exists from the model (`index=True`).
  Migration `0199_audit_log_indexes` adds each only when missing (0067's idiom); downgrade drops only the created_at index. No row is
  read or written.
- **A7 Web — one Audit log page, three portals:** `/admin/security-logs` (Super Admin; keeps the Export panel),
  `/it/admin/audit-log` and `/overseas/admin/audit-log` (new nav item "Audit Log"). A GET form (refresh, back and a shared link keep the
  filters): Done by (user reference), Action, Entity type, Entity reference, Division (Super Admin only), From, To, Apply, Clear filters.
  A table (stacked on phones) of When (IST), Done by, Action, Entity, Entity reference, Outcome. Previous / Next links, 50 rows a page.
- **A8 History in one click:** a row's entity reference links to that entity's full history (`entity_type` + `entity_id` filter), and the
  actor's name links to everything that person did. This is the "History" view for students, leads and payments: no admin lead or
  payment detail page exists to carry a tab, and the overseas student 360 already has its History tab (ccrm-009), which is unchanged.
  Dedicated History tabs on future detail pages stay `NEEDS_CONFIRMATION`.

## Acceptance criteria

1. Filtering by `entity_type=payment&entity_id=<id>` returns that payment's whole history (create, discount, …) and nothing else.
2. An it_admin never receives a row whose actor is overseas, including with `division=overseas`, and including rows older than the newest
   500 (the scope is in the SQL, before `LIMIT`).
3. `offset=500` returns rows 501+.
4. A non-admin gets `403`; no filter changes that.
5. The UI filters, pages and links to entity/actor history for all three admin roles, on desktop, tablet and phone.

## Non-goals

Retention (open question), full-text search of `metadata`, new detail pages, changes to the export, Management activity, or MA8.
