# pob-005 — Contact status, decision-maker, source/verification and per-contact timeline (design)

- **Source:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` pob-005 (§3.2 "Record the contact's role, professional email, phone,
  LinkedIn URL, source and verification date"; §3.3 decision-maker, preferred contact method, contact status set, "timeline against both
  the contact and the company", "reminders and tasks for each contact", duplicate prevention). Source classified `UNVERIFIED`; Q-00
  (owner, 2026-11-01) approved the backlog for build in waves. The owner assigned pob-005 on 2026-11-05 and said to proceed with recommended
  answers, so D1–D11 are **the builder's calls (`NEEDS_CONFIRMATION`)**. pob-005 has **no dependencies** (backlog §3.2). Decision
  `DEC-SCOPE-410`.

## Intent
A Placement Officer working a company needs to know, per person: are they the decision-maker, where did we find them and when was that
checked, how far has outreach got with them (not contacted → contacted → replied → meeting), whether they asked not to be contacted (and
the system must then stop sends), what happened with that one person, and whether this person is already on file (here or at another
company).

**Non-goals:** BD company stages (pob-004, which will consume the HR-contact event); import/merge (pob-006); reminder cadence (pob-008);
LinkedIn message logging (pob-007). **Anti-goals:** a send to a Do Not Contact person; a duplicate warning that reveals another recruiter's
company or contact; an upgrade that changes existing contacts' data other than the derived status backfill.

## Rules (builder's calls)

**D1 — New contact fields** on `company_contacts`: `is_decision_maker` (bool, default false), `source` (one of `linkedin`,
`company_website`, `referral`, `job_portal`, `event`, `inbound`, `other`; nullable), `verified_on` (date, nullable, not in the future → 422),
`status` (NOT NULL, default `not_contacted`), `status_changed_at` (timestamptz, nullable). Create and PATCH accept the first three and
`status`; the list returns them all plus `follow_up_due`.

**D2 — LinkedIn as a preferred channel.** `ck_company_contacts_channel` widens to `call | whatsapp | email | linkedin`.

**D3 — Statuses.** Stored: `not_contacted`, `contacted`, `replied`, `meeting_scheduled`, `not_interested`, `do_not_contact`.
"Follow-up Due" is **derived**, not stored: `follow_up_due = true` when the contact has an open follow-up due now or earlier (rec-024).

**D4 — Automatic moves** (forward only through `not_contacted < contacted < replied < meeting_scheduled`; never out of `not_interested` or
`do_not_contact`), in the same transaction as the activity:
- a message sent to the contact (WhatsApp/email; a profile share; an interview invite email), an outgoing call that did not connect → `contacted`;
- an incoming call, a connected call, or a **reply logged on a message** (D7) → `replied`;
- a meeting scheduled with the contact (its contact or a participant contact) → `meeting_scheduled`.
Each move writes an audit row `recruiter_company.contact_status` `{contact_id, from, to, cause}` (cause = `call|message|share|interview|
reply|meeting|manual`). A deactivated contact is not moved (no activity can be logged on it anyway).

**D5 — Manual status.** `PATCH /recruiter/contacts/{id}` `status` sets any stored status (`can_edit` on the company, as every contact
edit); audited as a field change plus the `contact_status` row (cause `manual`). Reopening a Do Not Contact person is a deliberate manual
edit by a `can_edit` user and is audited (`NEEDS_CONFIRMATION`: manager-only?).

**D6 — Do Not Contact is enforced server-side** with **409** "This contact has asked not to be contacted": message send to the contact,
logging an **outgoing** call (an incoming call is still logged — they called us), a profile share to the contact, scheduling a meeting
with them (as contact or participant). An interview invite does not fail: the contact's email is skipped and the summary says
`do_not_contact`.

**D7 — Logging a reply.** `POST /recruiter/messages/{id}/reply` `{replied_at?}` (default now; not before `sent_at`, not in the future →
422). Contact messages only (a candidate message → 422). `can_edit` on the company (403; out of scope 404; archived 409). Sets the new
nullable `recruiter_messages.replied_at` once — a second call returns the message unchanged (200, no audit). Moves the contact to
`replied` (D4). Audit `recruiter_message.reply`. Message output gains `replied_at`. A reply is not blocked by Do Not Contact.

**D8 — Duplicate check (warn, not block).** `GET /recruiter/companies/{id}/contacts/duplicates?mobile=&email=&exclude=` (company read
scope, 404) returns other contacts (active or not, any company) with the same `mobile_normalized` or the same lower-cased email:
`{matches, others}`. `matches` lists only contacts whose company is **in the caller's scope** (`{id, name, active, company: {id, name},
same_company, on: ["mobile"|"email"]}`, ≤ 10); `others` counts the rest with no detail (no IDOR/PII leak). The contact editor calls it
before saving and asks "Save anyway?" when anything matches. Saving is never refused for a duplicate: shared switchboard numbers are real,
and the existing tests/seed reuse one mobile across companies (a hard 409 would be a behaviour change beyond "warn"). A new
`ix_company_contacts_email` index backs the lookup.

**D9 — Q-05 (contact moves company).** No move: add them at the new company (D8 warns and links the old record), then deactivate the old
one. History stays with the company where it happened. `NEEDS_CONFIRMATION`.

**D10 — Per-contact timeline.** `GET /recruiter/companies/{id}/timeline?contact_id=` — the contact must belong to the company (404 "Contact
not found"). Rows: the contact's calls, messages, message replies, meetings (contact or participant), follow-ups, profile shares and their
responses, and the contact's status changes. Without `contact_id` the company timeline is unchanged except that message replies appear
(status changes stay contact-only, so activity is not doubled).

**D11 — Follow-ups by contact.** `GET /recruiter/companies/{id}/follow-ups?contact_id=` filters the company's list (same 404 rule).

**Backfill (migration):** status from existing activity — a non-cancelled meeting with the contact → `meeting_scheduled`; else an incoming
or connected call → `replied`; else any call / message / share → `contacted`; else `not_contacted`. Nothing else is rewritten.

## Web
- Contact editor: Decision-maker (checkbox), Source (select), Verified on (date), Status (select); Preferred communication gains LinkedIn.
  The "+ Add Recruiter" form (rec-004 `RECRUITER_FIELDS`) is unchanged.
- Contact card: status badge, "Decision-maker" and "Follow-up due" badges, Source and Verified on rows, a Do Not Contact notice; an
  **Activity** disclosure per contact showing its timeline (the shared timeline list with `?contact_id=`) and its follow-ups.
- Duplicate warning: before saving a new/changed mobile or email the editor runs the check and lists the matches (name at company; "N more
  at companies outside your list") with **Save anyway** / Cancel.
- Messages section: a contact message shows "Reply received …" once logged; writers get **Log reply** on contact messages without one.

## Acceptance (testable)
1. A reply logged on a message moves the contact to Replied (and an outgoing message → Contacted; a meeting → Meeting scheduled; never out
   of Not interested / Do not contact; forward only).
2. Do Not Contact refuses message sends, outgoing call logging, profile shares and meeting scheduling with 409; an incoming call and a reply
   are still recorded.
3. A duplicate mobile (or email) across companies warns (the duplicates check lists it; the editor asks before saving); out-of-scope
   matches are counted, never named.
4. Decision-maker, source, verified-on, LinkedIn channel and status save and read back; invalid values 422; follow-up due is derived.
5. The per-contact timeline and follow-ups filters return only that contact's rows; a contact of another company is 404.
6. rec-004/024/025/026/027/028 behaviour is otherwise unchanged (additive payload fields only).

## Regression risks
rec-004 contact tests and the frozen `COMPANY_CONTACT_CHECKS` copy (0110), rec-025/026/028/019 and hrc-028 write paths (one extra status
UPDATE), rec-027 timeline (new `message_reply` rows only when a reply exists), rec-038 route matrix (one new route), web fixtures for
`Contact` and `MessagesSection` (optional props only).

## Numbering
Migration `0288_contact_status` (siblings: pob-023 holds 0286, pob-013 may take 0287), `DEC-SCOPE-410`, API §12LD, RBAC §2.303 —
re-checked at merge.
