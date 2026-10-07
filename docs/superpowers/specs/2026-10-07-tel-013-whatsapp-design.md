# tel-013 — WhatsApp click-to-chat + send log (design)

- **Backlog:** `docs/delivery/TELECALLER_CRM_BACKLOG.md` § tel-013 (EVID-019 §11, L416–L452; T8). Dependencies tel-008 (PR #85) and
  tel-012 (PR #83) are merged. Inherits tel-012 C2: `GET /telecaller/leads/{id}/render`.
- **Status:** built on `feature/tel-013`.
- **Decision:** `DEC-SCOPE-099` (WA1–WA4 owner answers 2026-10-07; D1–D9 defaults). Migration `0094_lead_messages`, API contract §12U,
  RBAC §2.27. tel-019 (`0093` / 097 / §12S / 2.25) and tel-018 (098 / §12T / 2.26) are built in parallel and unmerged, so `0094` chains to
  main's `0092_lead_calls` and is re-chained at merge if either lands first.

## 1. Decisions

| ID | Topic | Answer |
|---|---|---|
| WA1 (Q-21 part) | Stored text | The full text as sent (1–1000 characters, tel-012's WhatsApp limit). Logs and audit never carry it |
| WA2 | Who / which leads | Only the lead's telecaller, before handover (403 otherwise; a manager / super_admin is 403). A closed lead → 409 ("A manager can reopen it"), as CL2 / F4. Read: the lead's scope |
| WA3 | Undo | The sender may delete their own row on its IST day (the CL4 gate: lead still theirs, not handed over); audited. No edit |
| WA4 | Template | Optional. With a template the text is rendered and editable; without one it is a free message, labelled "Custom message" |
| D1 | Number | `whatsapp_to` = the digits of `normalise_phone(whatsapp_number)`, else of `normalise_phone(phone)`, else null (AC1). An unparseable WhatsApp number falls back to the mobile. The `+91` default is ENH-014's helper's |
| D2 | No number | The composer's action is disabled with a reason (AC3); the API refuses a send with 409 "This lead has no WhatsApp or mobile number" |
| D3 | Delivery | wa.me can't report delivery. "Open WhatsApp" opens the chat in a new tab; nothing is logged until the telecaller confirms "Yes, I sent it". Cancel / "Not sent" logs nothing (edge case) |
| D4 | Template rules | Active WhatsApp templates only (inactive or email → 422 on `template_id`; unknown → 422). A template for another product is allowed; render returns `product_mismatch: true` and the composer warns (negative scenario) |
| D5 | Render values | `{name}` lead name; `{product}` the lead's product name, else the template's product name, else empty; `{brochure_link}` a fresh 7-day signed link when the template's brochure is active (tel-012 C1), else empty; `{appointment_time}` the lead's open counselling appointment (tel-016) as "Mon 14 Sept 2026, 10:30 AM" IST, else empty |
| D6 | Snapshot | The row keeps `template_id` and the template's name at send time, so a later rename doesn't rewrite history |
| D7 | Pipeline | No stage effect. A send is not a connected call (Appendix B B6/B7). tel-021 counts it (D10) and tel-015 shows it on the timeline |
| D8 | Daily cap | 300 sends per sender per IST day (409), an abuse bound as D9 of tel-010 |
| D9 | Email | The table carries `channel`, `subject` and `delivery_status` for tel-014; this item accepts `channel: "whatsapp"` only (any other value is 422) |

## 2. Data

`lead_messages`: `id`, `lead_id` → enquiries (RESTRICT), `sender_user_id` → users (RESTRICT), `channel` varchar(16), `template_id` →
tel_message_templates (RESTRICT) null, `template_name` varchar(120) null, `subject` varchar(300) null, `body` text, `delivery_status`
varchar(16) null, `sent_at` timestamptz, `created_at`, `updated_at`. Checks: channel in (whatsapp, email); body length 1–5000; a WhatsApp
row has no subject and no delivery status. Indexes `(lead_id, sent_at)` and `(sender_user_id, sent_at)`. The migration is guarded (0092's idiom).

## 3. API (§12U)

| Route | Notes |
|---|---|
| `GET /telecaller/leads/{id}/render?template_id=` | Lead in scope (404). Template: an active WhatsApp or email template (404 "Template not found" otherwise). 200 `{template: {id, name, channel, kind}, subject, body, brochure_link, product_mismatch}` |
| `GET /telecaller/leads/{id}/messages` | Lead in scope (404). Newest first, `{items, total, limit, offset}`; an item is `{id, lead_id, channel, template: {id, name} \| null, subject, body, sent_at, sender, can_delete}` |
| `POST /telecaller/leads/{id}/messages` | Body `{channel: "whatsapp", template_id?, body}`. Order: scope 404 → lead lock → telecaller 403 → handover 403 → closed 409 → no number 409 → template 422 → cap 409 → insert → audit → commit. 201 is the item. Not idempotent: each confirm is one send |
| `DELETE /telecaller/messages/{id}` | Scope 404 → lead lock → the sender (403) → handover 403 → same IST day 409 → 204 |
| Lead detail (`GET /telecaller/leads/{id}`) | Gains `whatsapp_to` (D1), an additive field |

Audit `lead_message.create|delete` carries ids, the channel and the template id. Logs carry the ids and the channel, never the text or a number.

## 4. Web

- `lib/telecallerMessages.ts`: types, URLs, `waHref(to, text)` (`https://wa.me/<digits>?text=<encodeURIComponent>`), guards.
- `WhatsAppComposer`: a template picker (active WhatsApp templates, paged), "Custom message" as the default. Picking a template renders it
  (loading / failure stated in place), the text is editable in a textarea with a 1000-character counter, and the mismatch warning shows.
  "Open WhatsApp" is a link (`target=_blank`, `rel=noopener noreferrer`). After it is clicked, the composer asks "Did you send it?" with
  "Yes, record as sent" and "Not sent". A refusal keeps the text.
- `LeadMessages` on the lead page: "Send WhatsApp" opens the composer, or is disabled with "No WhatsApp or mobile number" (AC3). The list
  shows "WhatsApp sent – 13 Sept 2026 – 10:35 AM", the template (or "Custom message"), the sender and the text, with Delete when
  `can_delete`. The header gets a "WhatsApp" button next to "Call" that opens the composer.

## 5. Tests

API (pytest): render values (name, product, brochure link present / absent, appointment time, mismatch flag), inactive / email / unknown
template, scope 404; send happy path with AC1 number choice and the AC2 row; a free message; 403 manager / other role / handed over; 404
other telecaller; closed 409; no number 409; body empty / too long 422; email channel 422; cap 409; delete same-day / other day / other
sender; list ordering and `can_delete`; `whatsapp_to` on detail; migration round trip. Web: vitest for `waHref` and the composer (render
fill, disabled without a number, confirm logs, "Not sent" logs nothing). Playwright `tel-013`: from the lead page pick a template, open
WhatsApp (the popup goes to wa.me with the number and text), confirm, and the row appears.
