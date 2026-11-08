# pob-026 — Client and candidate satisfaction feedback (design + plan)

Source: `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` §pob-026 (DERIVED_BLUEPRINT, `UNVERIFIED`). Dependency pob-024
(`DEC-SCOPE-432`, PR #497) is built. The owner asked for the recommended answers without a question round, so every call below is the
builder's (`NEEDS_CONFIRMATION`), recorded as `DEC-SCOPE-435`.

## Intent
After a candidate joins, nobody asks the client or the candidate how it went, and the placement holds no satisfaction result. pob-026
sends each of them one short survey (a 1–5 rating and an optional comment) through a no-login link, resends it once, and shows the
answers on the placement. It also makes a manual "Closed" on a requirement carry a reason (the auto-close on the last joining is unchanged).

## Goals (AC)
1. A survey is sent once per respondent and exactly one response is recorded.
2. Reusing the token (after a response) returns 410.
Edge: the client contact has left (deactivated) → the survey goes to the company's primary contact.

## Non-goals / anti-goals
No survey template editor, no NPS/multi-question form, no WhatsApp channel, no reporting roll-up (pob-029 owns reports), no in-app
notification on a response. Anti-goals: PII in the URL; a second response overwriting the first; a link that works after the response;
an email to a contact marked do-not-contact.

## Builder's calls (S1–S12)
- **S1 Timing.** A daily beat sweep (09:00 IST) sends a placement's surveys when its offer is Joined and the actual joining date is
  `SURVEY_AFTER_DAYS = 30` days ago or more, and no more than `SURVEY_LOOKBACK_DAYS = 120` days ago (no flood of old placements).
- **S2 Rows.** `placement_surveys`: one row per (placement, respondent ∈ client/candidate), unique. A row is written once, when the
  sweep first handles it: sent, or skipped with a reason (`no_contact`, `no_email`, `no_sender`) so the sweep never retries it daily.
- **S3 Client recipient.** The contact the candidate was submitted to for this requirement (the newest pob-021 share item) when it
  belongs to the end client, is active, has an email and is not `do_not_contact`; otherwise the company's primary contact under the same
  rules (the "contact has left" edge); otherwise skipped `no_contact`.
- **S4 Candidate recipient.** The candidate's email; an archived candidate or no email → skipped `no_email`.
- **S5 Delivery.** Reuses the rec-026 email queue: a `recruiter_messages` email row (company + contact, or candidate), so it shows on
  the company/candidate timeline and gets the worker's retries. Sender = the PO owner, else the recruiter owner, else the placement's
  creator, the first that is an active user; none → skipped `no_sender`. Fixed text; the only variable parts are the role, the company
  name, the respondent's name in the greeting and the link.
- **S6 Token.** A signed JWT (the tel-007 brochure-link pattern): `{sub: survey id, type: "placement_survey", exp}`, valid
  `SURVEY_LINK_DAYS = 30` from each send. Only the survey id is in it — no PII in the URL. Nothing about the token is stored.
- **S7 Resend once.** Still unanswered `SURVEY_RESEND_DAYS = 7` days after the first send → one reminder (a new link; the first link
  still works until it expires). `resent_at` makes it once.
- **S8 Public API.** `GET /api/v1/public/placement-surveys/{token}` → `{respondent, role, company}`; bad signature, wrong type or unknown
  survey → 404; answered or expired → 410. `POST` same path `{rating: 1–5, comment?: ≤1000 chars}` → 201; the row is locked and the
  answer set only while empty, so a second POST (or a race) is 410.
- **S9 Rate limit.** Each refused lookup (404/410) writes an audit row with the caller's IP (`client_ip`); 20 in an hour from one IP
  → 429 with `Retry-After` on every survey request from it (DB-backed, so it holds across instances — the website-intake idiom).
- **S10 Results on the placement.** `GET /recruiter/placements/{id}` gains `satisfaction: {client, candidate}`, each null (not yet
  due) or `{status, status_label, sent_at, resent_at, responded_at, rating, comment, skip_reason, skip_reason_label}`; read scope is the
  placement's (P14). The response is audited (`placement_survey.responded`, ids and the rating only).
- **S11 Manual close.** `POST /recruiter/requirements/{id}/status` to `closed` needs a note (422 on `note`: "Enter a reason for
  closing"). The employer / IT-jobs legacy words and the joining auto-close are unchanged. The web label says so.
- **S12 Web.** A public page `/feedback/[token]` (outside every protected prefix): loading, the form (five rating radio buttons,
  comment, submit), a thank-you state, and one message for a gone (410) or unknown (404) link. The placement page gets a
  "Satisfaction" section showing both rows.

## DB — migration `0316_placement_surveys` (guarded; after `0314_vendor_bills`)
`placement_surveys`: id, placement_id (FK, RESTRICT), respondent (CHECK client/candidate), contact_id (FK company_contacts, null),
message_id / resend_message_id (FK recruiter_messages, null), sent_at, resent_at, skip_reason (CHECK), rating (CHECK 1–5),
comment, responded_at, timestamps. Unique (placement_id, respondent). CHECKs: sent ⇔ no skip reason; rating ⇔ responded_at.

## Plan (TDD, focused tests)
1. Model + migration + `test_pob_026_migration.py` (checks frozen, guarded, single head).
2. `services/placement_surveys.py`: recipient choice, sweep (send, skip, resend once), token encode/decode; tests for AC1 + the edge.
3. Public routes (GET/POST, 404/410/429/201); tests for AC2 + throttle + race.
4. `placements.out` gains `satisfaction`; test.
5. Requirement manual close needs a reason; update rec-007 tests that closed without one.
6. Beat entry + worker task; web: public page, placement section, status label; vitest; e2e spec.
7. Docs: DEC-SCOPE-435, API §12MB, RBAC §2.326, DATA_MODEL, RTM, backlog status.

Regression risks: rec-007 status tests, rec-038 route matrix, single-head migration tests, placement read shape (pob-024 vitest/e2e).
