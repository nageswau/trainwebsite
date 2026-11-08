# pob-011 — Vendor requirements, vendor submissions and candidate-visibility control (DEC-SCOPE-427)

**Evidence:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` pob-011 (`UNVERIFIED` requirements draft). V1–V12 below are the builder's
calls and are `NEEDS_CONFIRMATION`.

**Dependency note:** pob-021 (submission record with per-submission consent) is not built. The owner chose on 2026-11-08 to build pob-011
now **with a consent stub**, as the backlog's wave plan allows ("pob-011 (after pob-021 or stubbed)"). pob-021 replaces the stub (V7).

**Non-goals:** the pob-021 submission record (SUB- code, statuses, SLA, skills-match block, per-candidate consent records, the redacted
resume rendition); vendor payables and performance (pob-012); anonymised shares to clients.

## Decisions

- **V1 The end client is the requirement's company.** pob-010 V10 already fixed `jobs.company_id` as the end client (a vendor-only company
  is refused there). So there is no separate `end_client_id`/`end_client_name`. An end client that is in the CRM is linked by being the
  company, which covers the backlog's "+/−/E". Deviation from the backlog's DB line: `end_client_name`/`id` are dropped.
- **V2 Via a vendor.** `jobs.via_vendor_id` (nullable, FK companies, RESTRICT). Set on create or PATCH; it must be a vendor-type company
  (`vendor` | `vendor_client`) in the caller's company scope, not suspended, and not the requirement's own company (CHECK too). Otherwise 422.
  A since-suspended vendor that is already linked is kept. Clearing it is allowed. It is a material field: it shows in revisions (pob-002)
  and in the audit diff by name.
- **V3 Disclosure flag.** `jobs.end_client_disclosure` is `external` (default, today's behaviour) | `internal`. When it is `internal`, the
  end client's name shows only to staff. Public visitors and students see "Confidential client" in the public job list, the student job
  board, and the student's applications and interviews. Staff views are unchanged.
- **V4 Recipient.** A share has `recipient`: `client` (default; today's behaviour) | `vendor`. A vendor share goes to the requirement's
  `via_vendor_id`: the contact must be one of the vendor's own active contacts, and `profile_shares.company_id` is the vendor. A vendor
  share cannot use the Portal channel (422): vendors have no employer portal. Without a vendor on the requirement, a vendor share is 422.
- **V5 Vendor gate (409, server-side).** In order: the vendor must be `active` (pob-010 status); it must have a current vendor agreement
  that reads Signed or Active (pob-010 left the expiry check to this item); and it must have an `nda` document on file. This holds for
  every vendor share, anonymised or full (AC2).
- **V6 Visibility.** A vendor share is **anonymised** by default: the text holds "Candidate <code>", no name, no current company and no
  resume link ("Resume on request"). **Full** details (name, email, mobile, resume link) need the consent stub (V7); without it, 409.
  Client shares keep today's named summary (R8 is unchanged for clients).
- **V7 Consent stub.** A full vendor share needs `consent_confirmed: true` and a `consent_reference` (how and when the candidates agreed,
  at most 300 characters). Both are stored on the share, with the sharer as the person who confirmed them. pob-021 replaces this with
  per-candidate consent records.
- **V8 Duplicate check across routes (AC1).** The repeat warning (409 `{message, duplicates}`; `repeat: true` overrides it) covers:
  - the same requirement (today's rule), and
  - another requirement of the same end client, when this share or the earlier one went through a vendor.

  Direct-to-direct shares across requirements stay unwarned, so rec-019 behaviour is unchanged.
- **V9 Side effects.**
  - A vendor share advances the vendor contact's status and the vendor's last contact (as a client share does).
  - It does **not** move the end client's BD pipeline: the end client did not receive the profiles from us (pob-010 V10: vendor relationships never drive the client pipeline).
  - Applications move to Profile Shared as before.
- **V10 Output.**
  - The requirement detail: `via_vendor {id, code, name} | null` and `end_client_disclosure`. List rows carry `end_client_disclosure`
    only, so the list needs no extra query.
  - A share: `recipient`, `detail` (`named` | `anonymised` | `full`) and `consent_reference`.
  - The audit row carries the recipient and detail, never the consent text.
- **V11 Migration `0308_vendor_requirements`.** It is additive and guarded (0001 runs `create_all`). Existing shares become
  `recipient='client'`, `detail='named'` through the server defaults. Existing jobs become `end_client_disclosure='external'`. The
  downgrade drops what it added.
- **V12 AuthZ.** No new grants. The requirement scope and writer rules govern (`load_scoped`, `require_writer`). The vendor's identity is
  not a commercial term.

## Security review (Phase 3)

- **IDOR:** a vendor is picked from the caller's company scope (otherwise 422), and a share resolves through the requirement scope. A
  contact of another company is refused (422).
- **Escalation:** none; no new roles or grants.
- **Data exposure:** the vendor text is built server-side from an allowlist per detail level. The anonymised level holds no name, contact or
  resume token. Full details need NDA, agreement, active status and consent, all checked under a FOR SHARE lock on the vendor row.
- **XSS:** React escapes; the consent reference uses the existing control-character validator.
- **CSRF/session:** unchanged.
- **Logs:** the audit carries ids, the recipient and the detail level; the consent text and names are never logged.

## API (§12LT) / UI

- `POST /recruiter/requirements` and `PATCH /{id}` take `via_vendor_id` and `end_client_disclosure`.
- `POST /recruiter/shares` takes `recipient`, `detail` (`anonymised` | `full`, vendor only), `consent_confirmed` and `consent_reference`.
- The UI changes in three places:
  - **Requirement form:** a "Source" section with a vendor picker (vendor companies only) and a disclosure select.
  - **Requirement detail:** shows "Via vendor" and the disclosure.
  - **Share dialog:** a recipient choice ("End client" or "Vendor: <name>") when the requirement has a vendor. Choosing the vendor loads its contacts, hides the Portal channel and adds the detail choice, with a consent checkbox and reference for Full. The shares list shows "to vendor · anonymised".

## Plan (TDD)

1. Backend tests in `test_pob_011_vendor_requirements.py`:
   - V2 validation and the revisions label
   - V3 masking
   - V4–V8 share rules
   - V10 output
   - the migration file shape
2. Model, migration and schemas, then the services and routes, until the tests are green. Then rerun the rec-019, rec-007 and pob-010/002 tests.
3. Web, in vitest: the share dialog's recipient, detail and consent handling; the form's source fields; the requirement detail lines.
4. Playwright `pob-011-vendor-submissions.spec.ts`: create a vendor requirement, then share to the vendor anonymised; a full share without
   consent shows the error.
5. Docs: DEC-SCOPE-427, API §12LT, DATA_MODEL, RBAC §2.318 (no change, noted), RTM, the backlog status.

## Regression risks

rec-019 share tests (payload defaults keep the old behaviour), emp-* portal shares (vendor shares are never Portal), the pob-002 revision
LABELS test, rec-007 serializer shape (additive keys), public/student job lists (masking only when `internal`).
