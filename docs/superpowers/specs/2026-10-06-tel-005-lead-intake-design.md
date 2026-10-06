# tel-005 — Manual lead creation, duplicate detection, website-enquiry intake/attach (design)

- **Backlog:** `docs/delivery/TELECALLER_CRM_BACKLOG.md` § tel-005 (EVID-019 §18, T12, T15). Dependencies tel-003 (PR #75) and tel-004 (PR #81) are merged.
- **Decision:** `DEC-SCOPE-086` · **Migration:** `0085_lead_enquiries` (after bdm-018's `0084_bdm_onboarding`) · **API contract:** §12K.

## 1. Owner answers (2026-10-06)

| ID | Question | Answer |
|---|---|---|
| I1 (Q-03) | Email on a manual lead | `enquiries.email` becomes **nullable**. A manual lead requires a valid mobile; email is optional. The website form still requires email. |
| I2 | Who owns a manual lead (tel-007 not built) | **The creator keeps it:** a telecaller's lead is assigned to them (pipeline event `assigned` → stage Assigned). A manager's/admin's lead goes to its team's unassigned queue (stage New). tel-007 adds rule-based distribution later. |
| I3 | Public reply on attach | Same 201 and keys. `id` + `lead_code` are the existing lead's; `status` is always `"new"` and `crm_sync_status` always `"pending"` on both paths, so the body never reveals the lead's real stage. |
| I4 | CRM webhook on attach | **Per lead:** an attached enquiry queues no webhook. A new lead still queues exactly as today. |
| I5 | Who may "Add enquiry to this lead" | **Any telecaller / manager / super_admin**, on any lead (another telecaller's, handed over, or closed). Append-only; it grants no read access beyond the duplicate panel. A closed lead stays closed (T13: only a manager reopens). |

Recorded defaults (no owner question needed):

- **R1:** the duplicate match is `phone_normalized = normalise_phone(phone)` OR `lower(email) = lower(email)`, across **all** leads (every division, closed, BDM-entered). A blank or unparseable phone matches nothing on phone.
- **R2:** the panel lists up to 5 matches, newest first. Each match shows the Lead ID, name, stage, telecaller, counselor, last contact, the fields that matched, up to 5 previous enquiries (the lead's own first enquiry plus its `lead_enquiries`, newest first) and `in_scope` (whether the caller can open it). It never includes another lead's phone or email.
- **R3:** "Last contact" is `null` until tel-010 (calls) / tel-013 (messages) exist; the UI says "No contact logged yet".
- **R4:** a website enquiry that matches several leads attaches to the **newest** matching lead.
- **R5:** a manual lead needs a product. Its division is the product's team; an `other` product without a team needs an explicit `division`. A campaign is optional; when it is given it must be active and belong to the same product and source (422 otherwise).
- **R6:** a manual lead's `subject` defaults to the product name, and `message` defaults to an empty string.
- **R7:** races: every intake path takes `pg_advisory_xact_lock` on the normalised phone and email keys (sorted, so there is no deadlock) before the match query. Two concurrent creates of one person serialise, and the second sees the first.
- **R8:** BDM lead entry (bdm-017) is unchanged. It keeps its own per-organization duplicate rule and isn't routed through the new intake.
- **R9:** a website lead that doesn't match is created exactly as today (stage New, unassigned; Q-05 is decided in tel-007).

## 2. Data

`0085_lead_enquiries`:

- `ALTER TABLE enquiries ALTER COLUMN email DROP NOT NULL` (I1). On downgrade, a null email becomes `''` before NOT NULL is restored.
- `lead_enquiries`: `id` uuid PK, `lead_id` → `enquiries.id` (RESTRICT), `subject` varchar(180), `message` text, `source` varchar(30) CHECK in TEL_SOURCES, `campaign_id` → `tel_campaigns.id` NULL, `metadata_json` JSON default `{}`, `created_by_user_id` → `users.id` NULL (NULL = website), `created_at`. Index `(lead_id, created_at)`.

## 3. Backend

`services/lead_intake.py` is shared by manual and website intake, and later by tel-006 CSV. It holds functions only and never commits.

- `lock_identity(db, phone_normalized, email)`: the advisory locks (R7).
- `matches(db, phone_normalized, email)`: matching leads, newest first, at most 5.
- `panel(db, user, leads)`: the R2 rows (`in_scope` from `lead_pipeline.scope`).
- `create_lead(db, user, payload)`: resolve the product/campaign/division (R5), take the locks, and raise 409 `{message: "Lead already exists.", code: "duplicate_lead", matches}` when there's a match. Otherwise insert the lead (the telecaller is the creator for role `telecaller`) and fire `lead_pipeline.apply_event("assigned")` when assigned. Writes the audit row `lead.create`.
- `add_enquiry(db, user, lead, payload)` → `LeadEnquiry` + audit `lead.enquiry_add`.
- `website_intake(db, payload)` → `(lead, attached)`.

Routes (`api/telecaller.py`; role gate = `lead_pipeline.scope`, so other roles get 403):

| Method | Path | Result |
|---|---|---|
| GET | `/telecaller/leads/duplicate-check?phone=&email=` | 200 `{matches: [...]}`. 422 when neither is given, or the phone can't be parsed. |
| POST | `/telecaller/leads` | 201 → the lead detail (tel-008 shape). 409 duplicate panel. 422 validation. |
| POST | `/telecaller/leads/{id}/enquiries` | 201 `{id, lead_id, lead_code, subject, source, created_at}` for any existing lead (I5). 404 when the lead is unknown. |

`POST /public/enquiries` calls `website_intake`. It commits, queues the CRM sync only for a new lead (I4), and returns the I3 body.

Timeline (tel-008 W1): `timeline_page` adds `kind: "enquiry"` rows from `lead_enquiries` (`from_value` = source, `to_value` = subject, `reason` = message, `actor` = creator or null for the website).

## 4. Frontend

- A "New lead" button on My Leads / Team leads opens `/telecaller/leads/new` (or `/telecaller/manager/leads/new`). The page has the `NewLeadForm` client component: the §2 fields, product, campaign (filtered by product; picking one sets the source), source, priority, and division (only for a product without a team), plus an optional subject and notes.
- On a mobile/email blur, the form runs `duplicate-check`, and the panel appears early. The submit can still return a 409, which shows the same panel. Each match offers **Add enquiry to this lead**, which posts the form's subject, notes, source and campaign, and **Open lead** when `in_scope`.
- On 201, the form navigates to the new lead's detail page.
- The lead detail Activity shows enquiry rows. The email field isn't required when editing a lead that has no email.
- `email` is typed `string | null` in the lead types and the admin lead panel.

## 5. Acceptance criteria → tests

1. A duplicate by mobile (any formatting) or by email is blocked with the panel → `test_tel_005_intake.py`, `NewLeadForm` vitest, Playwright.
2. A website enquiry from a known email or mobile attaches with an identical response shape and no new lead or webhook → `test_tel_005_public.py`.
3. A closed lead matches; a telecaller adds an enquiry, and the lead stays closed until a manager reopens it → `test_tel_005_intake.py`.
4. A new telecaller lead is assigned to its creator (Assigned); a manager's lead stays New and unassigned in the team queue (the distribution hook for tel-007) → `test_tel_005_intake.py`.
5. Security: the duplicate panel carries no other lead's phone/email; other roles get 403; anonymous gets 401; the public reply is identical in keys and constant values.
6. Migration up/down → `test_tel_005_migration.py`.

## 6. Regression risk

The public enquiry API (PUB-002 and tel-003 intake tests), the CRM sync, the admin lead list (email may now be null), and the tel-008 timeline.
