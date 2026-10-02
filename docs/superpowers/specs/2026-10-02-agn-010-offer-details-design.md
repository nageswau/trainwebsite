# AGN-010 — Offer details (Step 6) — design

**Status:** design approved in-session 2026-10-02 (`EXPLICIT_APPROVAL`, recorded as `DEC-SCOPE-054`). Source item:
`docs/delivery/AGENT_CRM_BACKLOG.md` ang-010. Depends on AGN-008 (`DEC-SCOPE-050`) and AGN-009 (`DEC-SCOPE-052`), both on `main`.

## 1. Requirement and acceptance

Business requirement (EVID-015 §5 Step 6): conditional/unconditional offer, offer date, deadline, conditions and offer document.

Backlog acceptance: an offer deadline before the offer date → 422; a conditional offer requires conditions; switching to
unconditional is recorded in history; the offer counts in dashboards (fixes the §0 defect for this path).

## 2. Decisions (`DEC-SCOPE-054`, answered by the owner 2026-10-02)

| ID | Decision |
|---|---|
| O1 | **One current offer per application**, stored as columns on `overseas_applications`. Recording again replaces it; the previous values survive in the application's status history notes. |
| O2 | **The offer deadline is the existing `offer_deadline` column** (AGN-008 A3). The Create/Edit forms keep editing it; the nearest-deadline rule (QA8-13) is unchanged. `offer_deadline < offer_date` is refused (422) wherever both are set, on the offer PUT and on the AGN-008 PATCH. |
| O3 | **The offer document is optional and is picked from AGN-009 documents**: type `"Offer letter"`, attached to this application, inside the caller's scope. Download stays on the AGN-009 route (scope, audit, presigned link). |
| O4 | **`offer_letter_url` is untouched.** Agent offers never write it; other roles' views and counts of it are unchanged. |
| O5 | **Offers count = stage `offer` or later (plus the legacy `offer_received`/`accepted`) OR an offer recorded** — so an application withdrawn after an offer still counts. Applied to the agent pages only: the Reports "Offers" row and a new dashboard "Offers" KPI. The other stale counts (`portal.py` student dashboard, operations dashboard, university-rep offer letters) stay for ang-018 (RAID). |
| O6 | **Conditions are free text** (≤ 2000 characters). |
| O7 | **Concurrent offer saves: last write wins**, both recorded in history (the row lock serialises them). No offer version token. |

## 3. Data (migration `0060_agent_offer_details`)

Four nullable columns on `overseas_applications`; no existing row is read or rewritten.

| Column | Type | Rule |
|---|---|---|
| `offer_type` | `VARCHAR(20) NULL` | `ck_overseas_applications_offer_type`: `offer_type IS NULL OR offer_type IN ('conditional','unconditional')` |
| `offer_date` | `DATE NULL` | `ck_overseas_applications_offer_dated`: `(offer_type IS NULL) = (offer_date IS NULL)` |
| `offer_conditions` | `TEXT NULL` | — |
| `offer_document_id` | `UUID NULL` FK `student_documents.id` `ON DELETE SET NULL` | named `fk_overseas_applications_offer_document_id`, `use_alter=True` (cycle with `student_documents.application_id`) |

Guarded adds (0057's idiom: 0001/0003 build a fresh database from the current models). `downgrade()` refuses while any
`offer_type` is set, then drops the constraints and columns.

## 4. API

### 4.1 `PUT /api/v1/workflows/overseas/agent/crm/applications/{id}/offer`

Authenticated; agent Master or Staff (D8 / `DEC-SCOPE-050` A4) through `_gate` (super_admin refused, unapproved or suspended
agency refused); out of scope → 404 `Application not found`.

Body `AgentApplicationOffer` (`extra="forbid"`):

| Field | Rule |
|---|---|
| `offer_type` | `"conditional"` \| `"unconditional"`, required |
| `offer_date` | date, required, 2000–2100, not after today (UTC + 1 day, as `submitted_on`) → `Offer date cannot be in the future` |
| `offer_deadline` | date \| null, 2000–2100; before `offer_date` → `Offer deadline cannot be before the offer date` |
| `conditions` | `clean_free_text(…, 2000)`; conditional and blank → `A conditional offer needs its conditions`; unconditional and present → `An unconditional offer has no conditions` |
| `offer_document_id` | UUID \| null |
| `expected_status` | optional; differs from the current status → 409 (the AGN-008 `STALE` message) |

Order, one transaction, one commit:

1. `lock_active_org`, then the application `FOR UPDATE` in scope (404).
2. `_refuse_closed`: archived student → 409 `Unarchive this student first`; withdrawn → 409 `This application is withdrawn`.
3. `expected_status` → 409.
4. Document: `agent_documents.load_scoped` (404 `Document not found` outside scope), then `application_id` must equal this
   application and `document_type` must be `Offer letter`, else 422 `Choose an offer letter uploaded for this application`.
5. Compare with the stored offer. No change → 200 with the detail, nothing written (retry-safe; no `Idempotency-Key`, §0.2).
6. Stage sync: before `offer` (or a legacy value outside the stage list) → `check_transition(current, "offer")` and set `offer`;
   at `offer` or later (incl. `enrolled`) → unchanged.
7. Set the four columns + `offer_deadline` (conditions stored only for a conditional offer).
8. One `ApplicationStatusHistory` row (`from_status` = old status, `to_status` = new status, `next_action` unchanged) whose
   `notes` describe the change (§4.3); one `overseas.application.offer` audit row (`{"fields": [...], "offer_type": …,
   "from_status": …, "to_status": …}` — never the conditions text).
9. Commit; `_log("agent_application_offer_recorded", …, fields=…, stage_moved=…)`.

Response `200 {"application": <detail>}`.

### 4.2 Detail additions (additive)

`GET /{id}` and every write response:

```
"offer": null | {"type", "date", "deadline", "conditions", "document": null | {"id", "name", "verification_status"}},
"offer_letters": [{"id", "name", "verification_status", "created_at"}]   // ≤ 20, newest first, in scope, this application
```

`name` = `document_label` or `original_filename` or `"Offer letter"`. No `file_url` anywhere. Not paginated: bounded per
application (§0.1 exception).

### 4.3 History notes

- First offer: `Offer recorded: Conditional, offer date 2026-09-30, deadline 2026-10-30. Conditions: IELTS 6.5`.
- Change: `Offer updated: Conditional → Unconditional; deadline 2026-10-30 → 2026-11-15; conditions removed (were: IELTS 6.5)`.
  Each changed item is listed; unchanged items are not. Dates are ISO (the web shows them as written).

### 4.4 Existing routes

- `PATCH /{id}`: if the application has an `offer_date` and the resulting `offer_deadline` is before it → 422 (same message).
- `POST /workflows/overseas/agent/crm/documents`: `document_type` also accepts `"Offer letter"`; it must come with an
  `application_id`, else 422 `Choose the application this offer letter belongs to`. `document-requests` keep the previous list.
- `/status`, the list, counselor/university/admin routes, `offer_letter_url`: unchanged.

## 5. Offers count

`services/agent_applications.py`: `OFFER_COUNTED_STATUSES = {"offer", "offer_received", "accepted", "visa_documentation",
"status_tracking", "enrolled"}` and `counts_as_offer(app)`. `services/portal._agent`: the Reports "Offers" row uses it, and the
dashboard adds `{"label": "Offers", "value": …}` after Applications for Master and Staff (staff scope already applies).

## 6. Web

- `AgentApplicationOffer.tsx` — the Offer block in `AgentApplicationDetail` (`<h5>Offer</h5>`): empty state *No offer recorded
  yet.* + **Record offer**; recorded offer as a `<dl>` (type in words, dates, conditions with line breaks, offer letter name +
  status + Download via the AGN-009 `downloadUrl`, else *Not attached*); **Edit offer**; no buttons when read-only.
- `AgentApplicationOfferForm.tsx` — radio `fieldset` for type; `offer_date` (`max` today); deadline (`min` offer date);
  conditions textarea only for conditional (`required`, `maxLength` 2000, hint via `aria-describedby`); offer-letter `<select>`
  from `detail.offer_letters` (no extra fetch), with an empty-state hint linking to Documents; `inFlight` guard, *Saving…*; 422
  keeps input and focuses the notice; 409/404 use the existing reload path; success → *Offer saved*.
- `AgentApplicationDetail` — one form at a time (`mode`: view / edit / offer).
- `lib/agentDocuments.ts` — `UPLOAD_DOCUMENT_TYPES` = `DOCUMENT_TYPES` + `Offer letter`; the upload form requires the
  application for it; the request form keeps `DOCUMENT_TYPES`.
- `lib/agentStaff.ts` — activity label `overseas.application.offer` → *Recorded an offer*.

## 7. Security

AuthN unchanged (cookie JWT). AuthZ `_gate` + scope in the WHERE clause (404 mask). Document IDOR: scoped load first (404),
then same-application + type (422). No escalation: stage via `check_transition` (never `enrolled`, no commission). Input:
Pydantic `extra="forbid"`, `Literal`, date ranges, `clean_free_text` (NUL / bidi overrides). XSS: React text only. CSRF: existing
SameSite=Lax cookie + JSON. SQL: ORM only. No storage key or `file_url` returned. Logs/audit: ids and field names only. No new
throttle (writes are idempotent; existing PATCH/status have none). Audit in the same transaction; AGN-021 activity lists it.

## 8. Acceptance criteria

| AC | Criterion |
|---|---|
| AC01 | Deadline before offer date → 422 on PUT and on PATCH (when an offer exists); same day accepted. |
| AC02 | Conditional + blank conditions → 422; unconditional + conditions → 422; missing type → 422; future offer date → 422. |
| AC03 | Conditional → unconditional writes one history row naming both types and the removed conditions; conditions cleared. |
| AC04 | Pre-offer (or legacy) → stage `offer` + history; `offer` or later → stage unchanged; withdrawn / archived / stale → 409. |
| AC05 | Agent dashboard "Offers" and Reports "Offers" equal a hand count (stage, offer record, withdrawn-after-offer); staff scoped. |
| AC06 | Other agency / out-of-scope application → 404; other application's document → 422; out-of-scope document → 404; wrong type → 422; super_admin refused. |
| AC07 | Identical PUT → 200, no history and no audit row. |
| AC08 | `offer_letter_url` and non-agent offer counts unchanged; document requests refuse `Offer letter`; upload of `Offer letter` without an application → 422. |
| AC09 | UI: empty state, conditional-only conditions, keyboard completion, focus on error/success, read-only, 320 px no horizontal scroll. |

## 9. Out of scope

Several offers per application; removing an offer; notifications (ang-017); fixing the non-agent offer counts (ang-018);
deposit (ang-011); visa (ang-012).
