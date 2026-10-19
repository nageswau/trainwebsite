# csc-004 — Counselor creates a walk-in lead (design)

`DEC-SCOPE-229`, API `12EO`, RBAC `2.151`, no migration. Backlog: `docs/delivery/COUNSELOR_WALKIN_BACKLOG.md` §3 `csc-004`; owner answers
W1 (Overseas `counselor` only), W2 (a walk-in may be captured as a lead; existing functionality unchanged), W4 (the counselor owns the
lead and a telecaller is distributed too), W5 (the telecaller is read-only — D1/T19 unchanged).

## Intent

A student walks into the office but is not ready for an account. The counselor records them as a lead on the spot, keeps working it
(appointments, student link — tel-016/tel-018), and the telecaller team still sees it.

## API — new router `/counselor/walk-in-leads` (Overseas counselor only; everyone else 403)

A separate prefix, so nothing collides with `GET /counselor/leads/{lead_id}` and the tel-026 route inventory (which covers
`/counselor/leads` and `/counselor/appointments`) is untouched.

| Route | Behaviour |
|---|---|
| `GET /counselor/walk-in-leads/duplicate-check?phone=&email=` | tel-005's §18 check (R2): the panel for a mobile and/or email; `in_scope` = the counselor's own leads. Same 422s. |
| `POST /counselor/walk-in-leads` | Body `TelecallerLeadCreate` (tel-005: name, mobile, product, source…). `lead_intake.create_lead` unchanged in its rules (catalogue checks, advisory locks, duplicate 409 with the panel), plus: the lead's `owner_id` is the counselor, its division is the counselor's (`overseas`; another team's product → the existing 422), and it goes through tel-007 distribution like a manager's lead (W4). 201 with the counselor's lead detail (`lead_handover.detail`) and `in_scope: true`; CRM sync queued after the commit, as tel-005. |
| `POST /counselor/walk-in-leads/{lead_id}/enquiries` | tel-005 I5 "Add enquiry to this lead" from the duplicate panel: append-only, no read access, audited — so a walk-in who is already someone's lead is not lost. |

The lead is then in the counselor's existing *My Leads* (`GET /counselor/leads`, `owner_id` scope) and detail page. The distributed
telecaller sees it read-only (D1/T19, `telecaller_leads.require_writable`); the telecaller manager still acts.

## Code changes (smallest)

- `lead_intake.create_lead`: a counselor caller sets `owner_id` and passes its division; every other caller is unchanged.
- `lead_intake.panel`: the in-scope filter is the counselor's scope for a counselor, the pipeline scope for everyone else (today it
  would 403 a counselor).
- New `api/counselor_walk_in_leads.py`; `main.py` router list.
- `lead_intake.duplicate_matches`: the duplicate-check body, shared by the telecaller and counselor routes (Phase 7: no copy).
- Web: `NewLeadForm` gains optional props — `apiBase` (the intake prefix: create, `/duplicate-check`, `/{id}/enquiries`; a string so the
  server page can pass it, QA-01), initial values, a fixed division — used by a new
  `/overseas/counselor/leads/new` page (source preset to Walk-in, division fixed to Overseas, IT-team products hidden). A **New
  walk-in lead** button on the overseas counselor's Leads panel.

## Builder's calls (owner: proceed with recommended answers; backlog §5 csc-004 questions)

- C8 — **Telecaller conversion credit unchanged** (tel-021 DB2): a converted walk-in counts for the distributed telecaller exactly as
  any converted lead does. No metrics code changes.
- C9 — **Counselor handover metrics unchanged** (`management_counseling`): they count handovers; a walk-in was never handed over.
- C10 — **Telecaller targets/dashboards unchanged**: the distributed lead counts like any assigned lead.
- C11 — the counselor may add an enquiry to an existing lead from the duplicate panel (tel-005 I5 semantics).
- C12 — source preset to `walk_in` but editable (a walk-in may have come from a referral or an event).

All of C8–C10 keep existing behaviour (W2); changing any of them is a later decision.

## Not changed

`/telecaller/*` routes and their role gates, `lead_distribution`, `telecaller_leads` (D1/T19), every metrics module, `lead_handover`.

## Security

Role gate per route (overseas counselor); the counselor's division is forced (no cross-division leads); `TelecallerLeadCreate` is
`extra="forbid"` (no `owner_id`/`telecaller_user_id` injection); the duplicate panel never exposes phone/email (R3); logs/audit ids only.

## Tests

`test_csc_004_walk_in_leads.py`: create → owner = counselor, division overseas, distributed to an active overseas telecaller (stage
`assigned`), in the counselor's My Leads and detail; the telecaller reads it but cannot act (D1); duplicate → 409 with the panel and
`in_scope` for the counselor's own lead; duplicate-check endpoint; add-enquiry; IT-team product → 422; IT counselor / telecaller /
admin → 403; anonymous 401; no active telecaller → stays unassigned but still the counselor's; injected `owner_id` → 422. Regression:
tel-005 intake tests, tel-007 distribution, tel-008 D1, tel-018 counselor routes, tel-026 matrix. Vitest for the form props; e2e:
counselor creates a walk-in lead and lands on it.
