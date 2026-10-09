# upc-014 — MoU / agreement management (design + plan)

**Status:** design written 2026-10-09. The owner's standing instruction for this session is "proceed with the recommended answers;
ask only if genuinely blocking". So Q-16 and the item answers AG1–AG18 (§1) are **recommended defaults accepted under that instruction**
(`NEEDS_CONFIRMATION` as separate per-question approvals) and are registered that way in `DEC-SCOPE-141`.

**Branch:** `feature/upc-014`, cut from `origin/main` @ `e91932a3`.
**Backlog:** `docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-014. Dependencies upc-003 (`0105`, PR #151) and upc-026 (`0124`,
`DEC-SCOPE-139`, PR #184) are merged on main — verified in code (`University`, `UniversityDocument`, `services/university_documents.py`).
**Source:** `EVID-020` §13 (lines 453–497: "This should be a major module"; 18 tracked rows; 9 statuses), §28 line 489 (agreement document
in the document centre), §32 menu "MoU & Agreements", line 1129 + U2 (commission visibility).
**Numbering:** migration `0126_university_agreements`, `DEC-SCOPE-141`, API §12BI, RBAC §2.67 (drafted as `0125` / `DEC-SCOPE-140` / §12BH / §2.66; renumbered on merging `main` @ `a0725b6d`, where upc-012 took those).
**Gate:** `APPROVAL_GATES.md` GATE-09.

## 1. Decisions (recommended defaults)

| # | Question | Answer |
|---|---|---|
| AG1 | Q-16 MoU number | Server-generated `MOU-000001` from `university_agreement_mou_seq` (the `UNV-`/`VIS-` idiom); a renewal gets its own number; unique; a rolled-back create skips a number |
| AG2 | Agreement type | The three agreement kinds of the document centre (upc-026 DC1): `mou` MoU, `partnership_agreement` Partnership agreement, `commission_agreement` Commission agreement. No other type is evidenced |
| AG3 | The 17 fields (AC1) | §13's 18 rows minus "Commission" (upc-016, restricted): MoU number, university, type, start, expiry, renewal date, commercial-terms summary, exclusivity (`exclusive` / `non_exclusive`), territory, student recruitment rights, courses covered (`all_courses` or course ids of this university), countries covered (country ids), payment terms, marketing rights, agreement document (a upc-026 document), signed by EduSphere (user + date), signed by university (name + date) |
| AG4 | Q-16 statuses | **Stored:** draft, sent, under_review, negotiation, approved, signed, active, renewed. **Derived (never stored):** `expiring` when a signed/active agreement's expiry is today … today + 90 days (IST), `expired` when it is before today (the BDM MoU idiom; upc-015 names "an expired agreement") |
| AG5 | Transitions | draft → sent; sent → under_review, negotiation; under_review → negotiation, approved; negotiation → under_review, approved; approved → signed, negotiation; signed → active. `renewed` only through AG8. An optional note on every move. The client sends `from_status`; a mismatch is a 409 (moved meanwhile) |
| AG6 | Approval | → approved only by a `partnership_head` in the university's scope or `super_admin` (backlog "Approved by the head") — `can_approve_agreements` |
| AG7 | Signing (AC2) | approved → signed needs the agreement document (same university, kind = agreement type) and both signatories (EduSphere user + date, university name + date; signed dates not in the future). DB CHECK backstop: signed/active/renewed rows carry all five |
| AG8 | Q-16 renewal (AC4) | `POST …/renew` on a signed or active agreement without a successor: a new **draft** row (new MoU number) copying the terms, with `previous_agreement_id`; dates from the body. The old row becomes `renewed` when the new one is signed (until then it stays in force and shows Expiring/Expired). One successor per agreement (partial unique index) |
| AG9 | Overlap (edge) | Signing is refused (409) when another signed/active agreement of the same university and type overlaps [start, expiry]; the predecessor being renewed is excluded |
| AG10 | Stage (backlog) | Signing moves the university to **Agreement Signed** when it is behind it (one stage-history `move`, note "Advanced by agreement MOU-…"); at or past it, nothing. A lost university cannot sign (409, reopen first) |
| AG11 | Editing | Terms (AG3 minus signing fields) while draft/sent/under_review/negotiation; signing fields (document, signatories) while not yet signed; nothing after signing (409). An equal value is not a change |
| AG12 | Validation | expiry after start (422 — the backlog's negative); renewal date within [start, expiry]; texts ≤ 2000 (territory ≤ 500, signatory name 2–200); courses must belong to the university and `all_courses` excludes a list; countries must exist; ≤ 200 courses, ≤ 250 countries |
| AG13 | Who reads | `partnership_manager` (with profile), `partnership_head`, `super_admin` read every university's agreements. **overseas_admin and every other role: 403** (commercial content; U14 gives overseas_admin "partnership status", which the stage already shows) |
| AG14 | Who writes | create / edit / status / renew: `can_manage_agreements` = the contacts rule (CONTACT_ROLES ∩ edit scope ∩ active university); approve: `can_approve_agreements` (head/super_admin ∩ scope ∩ active) |
| AG15 | Commission | No commission field here; upc-016 adds terms behind `strip_commission`. All AG13 readers are commission roles today, so nothing leaks |
| AG16 | Delete | Not in this item (append-only, like documents) |
| AG17 | Audit / logs | `university_agreement.create|update|status|renew`, ids, MoU number, statuses, field names only; notes live in `university_agreement_events` |
| AG18 | Menu page | `/partnership/agreements`: every agreement, filtered by effective status, type and a MoU-number/university search, soonest expiry first, paged 50 |

## 2. Data model — migration `0126_university_agreements`

- `university_agreement_mou_seq`.
- `university_agreements`: id, mou_number String(20) unique, university_id FK RESTRICT, agreement_type String(30) CHECK, status String(20) CHECK,
  status_changed_at, start_date, expiry_date, renewal_date?, commercial_terms Text?, exclusivity String(20) CHECK, territory String(500)?,
  recruitment_rights Text?, all_courses bool, course_ids JSON, country_ids JSON, payment_terms Text?, marketing_rights Text?, document_id FK
  university_documents?, edusphere_signatory_user_id FK users?, edusphere_signed_on?, university_signatory_name String(200)?,
  university_signed_on?, previous_agreement_id FK self?, created_by_user_id, created_at, updated_at. CHECKs: dates order, renewal window,
  signed rows complete. Indexes: `uq_university_agreements_previous` (partial), `ix_university_agreements_university`,
  `ix_university_agreements_expiry` (status, expiry_date).
- `university_agreement_events`: id, agreement_id FK, kind (create/update/status/renew) CHECK, from_status?, to_status, actor_user_id,
  note?, changed JSON, position Identity, created_at.
- Created only when missing; downgrade refuses while any agreement exists.

## 3. Backend

`services/university_agreements.py` (functions, no commit) and `api/university_agreements.py`.

| Route | Who | Notes |
|---|---|---|
| `GET /partnership/universities/{id}/agreements` | AG13 | `{items,total,limit,offset}` newest first, each with events, links, permissions, transitions |
| `POST /partnership/universities/{id}/agreements` | `can_manage_agreements` | JSON → 201 `{agreement}` (draft) |
| `GET /partnership/universities/{id}/agreement-options` | `can_manage_agreements` | the university's courses, its agreement-kind documents, EduSphere signatories |
| `GET /partnership/agreements` | AG13 | AG18 menu list (`status` effective, `agreement_type`, `q`) |
| `GET /partnership/agreements/{id}` | AG13 | `{agreement}` |
| `PATCH /partnership/agreements/{id}` | `can_manage_agreements` | AG11 |
| `POST /partnership/agreements/{id}/status` | manage (approve: AG6) | `{from_status, to_status, note?}` |
| `POST /partnership/agreements/{id}/renew` | `can_manage_agreements` | `{start_date, expiry_date, renewal_date?}` → 201 `{agreement}` |

Order of refusals: 403 role → 404 agreement/university → 403 scope → 409 inactive university → 409 state → 422 values → 409 overlap.
Writes: university `FOR UPDATE`, then the agreement `FOR UPDATE` (the predecessor too when signing a renewal), checks, change, event + audit, one commit.

## 4. Frontend

- `lib/universityAgreements.ts`: types, labels, URLs, status tone, menu query helpers.
- `components/AgreementForm.tsx`: create/edit (terms + signing fields), course checklist, countries via `SearchableSelect` chips.
- `components/UniversityAgreements.tsx`: the university page's **Agreements** section — a card per agreement (number, type, effective status
  badge, dates, days to expiry, facts in a `<details>`, history, links to the previous/next agreement), the move buttons the API allows,
  a sign panel, a renew form; `role=status` notices, `.form-error[role=alert]` failures, busy guard.
- `[id]/page.tsx`: reads agreements (+ options when manageable) only for AG13 readers.
- `app/partnership/agreements/page.tsx`: the menu page; `navigation.ts`: "MoU & Agreements" goes live; the head nav gains it.

## 5. Acceptance criteria

| AC | Statement | Proven by |
|---|---|---|
| AC1 | All 17 fields stored and returned | `test_upc_014_agreements.py`, e2e |
| AC2 | Signed requires the document and both signatories | tests, e2e |
| AC3 | Expiring (and Expired) appears automatically from the expiry date | tests, vitest |
| AC4 | Renewed links the old and new rows; the old becomes Renewed when the new is signed | tests, e2e |
| P1 | A 3-year exclusive MoU for India is created, approved by the head, signed and activated | tests, e2e |
| N1 | expiry before start → 422 | tests |
| E1 | overlapping active agreements of the same type → 409 | tests |
| S1 | Signing advances the stage to Agreement Signed (never backwards) | tests |
| R1 | overseas_admin/counselor read → 403; non-owner manager write → 403; manager approve → 403; inactive university → 409 | tests |

## 6. Tasks (TDD, in order)

1. Migration + models + parity/round-trip test (`test_upc_014_migration.py`).
2. Service + routes: create/read/validation tests, then status/approve/sign/stage, renew/overlap, menu, RBAC; then code. Permissions.
3. Frontend lib + components + page wiring + menu page + nav, vitest.
4. Playwright `upc-014-university-agreements.spec.ts`; docs (DEC-SCOPE-141, API §12BI, RBAC §2.67, DATA_MODEL, SCREEN_CATALOG, backlog).

## 7. Regression set (lite)

`test_upc_003_universities.py`, `test_upc_007_*.py`, `test_upc_026_*.py`, `UniversityDetailPage.test.tsx`, `navigation.partnership.test.ts`,
the upc-026 e2e spec.

## 8. QA (Phase 5, 2026-10-09, `upc014` stack on :13214)

Playwright e2e `upc-014-university-agreements.spec.ts` passed. An exploratory script (scratchpad) covered: empty / filtered-empty /
past-end states; a server 422 (renewal date) shown with the form kept; an induced 500 ("could not be saved") and a dropped request (the
shared "did not complete" text); the busy label while sending; a double click (one POST, one card); reload and back; cancel; a no-change
save; unauthenticated (login redirect); a non-owner manager (reads, no buttons); a counselor (refused); the head (approval offered);
desktop / tablet (820 px) / phone (390 px) with no side scroll; focus back on "New agreement"; no broken images. Console and network
errors seen were only the induced ones and Next's cancelled `_rsc` prefetches. **No in-scope defect found.** Noted, not a defect: the
super admin's sidebar has no "MoU & Agreements" entry (as with upc-026 Documents); super admins reach agreements from the university page.

## 9. Phase 3 review notes (api-and-interface-design, frontend-ui-engineering, security-and-hardening)

- **API:** additive only (two permission keys on the university detail). Commands are POSTs with `from_status` (optimistic concurrency, the
  upc-007 idiom) instead of a PATCH on status; PATCH never changes status. Dates are ISO dates; unknown fields are 422 (`extra=forbid`).
- **Security:** reads limited to commission-capable roles (AG13/AG15) so no commercial or (future) commission data reaches overseas_admin,
  counselors, BDMs, agents or the public; ids from the client (courses, countries, document, signatory) are re-validated against the
  university/roles server-side (no IDOR into another university's documents or courses); text is rendered as React text (no HTML);
  audit/logs carry no free text; the document is downloaded through upc-026's audited route (no new file path).
- **Frontend:** reuses the `action-card wide` + `.card` list pattern of contacts/documents, badges for status, `<details>` for long facts,
  labelled inputs, `aria-describedby` hints, busy-disabled buttons as the double-submit guard, notices only rendered when shown (upc-012
  lesson), cards stack on phones.
