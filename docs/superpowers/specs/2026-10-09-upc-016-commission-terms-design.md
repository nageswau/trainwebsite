# upc-016 — Commercial / commission terms, restricted (design + plan)

**Status:** design written 2026-10-09. The owner's standing instruction for this session is "proceed with the recommended answers;
ask only if genuinely blocking". So Q-18, Q-19 and the item answers CM1–CM15 (§1) are **recommended defaults accepted under that
instruction** (`NEEDS_CONFIRMATION` as separate per-question approvals) and are registered that way in `DEC-SCOPE-143`.

**Branch:** `feature/upc-016`, cut from `origin/main` @ `7ba4cb36`.
**Backlog:** `docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-016. Dependency upc-014 (`0127`, `DEC-SCOPE-142`, PR #187) is merged
on main — verified in code (`UniversityAgreement`, `services/university_agreements.py`, `api/university_agreements.py`).
**Source:** `EVID-020` §15 (lines 515–543: 9 terms, the example trigger "visa approval + student enrolment", "Finance manages receipts"),
§32 menu "💰 Commercial Terms" (1080), line 1129 "Commissions should not be seen by anyone." + U2 (visibility) + U4 (universities pay
EduSphere).
**Numbering:** migration `0128_university_commission_terms`, `DEC-SCOPE-143`, API §12BK, RBAC §2.69.
**Gate:** `APPROVAL_GATES.md` GATE-09.

## 1. Decisions (recommended defaults)

| # | Question | Answer |
|---|---|---|
| CM1 | Q-19 trigger values | `enrolment` (Student enrolment), `visa_and_enrolment` (Visa approval + enrolment — §15's example), `tuition_paid` (Tuition paid). Required on every term. Whether Expected counts only once the trigger is met is upc-019's (recommended: yes) |
| CM2 | Q-18 rate (backlog edge "both % and fixed set") | **Exactly one** of commission % (0 < % ≤ 100, two decimals) or fixed amount (> 0, ≤ 99,999,999.99) per term; both or neither → 422. A "% with a minimum" arrangement is written in Conditions. Keeps upc-019's Expected unambiguous |
| CM3 | Q-18 currency | Required, from the project's currency list (`COUNSELING_CURRENCIES`: INR, USD, GBP, EUR, CAD, AUD, NZD). No FX conversion anywhere; upc-019 totals per currency. Other currencies `NEEDS_CONFIRMATION` |
| CM4 | Q-18 precedence (recorded for upc-019) | A term naming the student's programme beats an all-programmes term; a term naming the student's country beats an all-countries term. upc-016 only stores terms |
| CM5 | Shape | Terms belong to one agreement ("per agreement, optionally per course/program group"). Eligible programmes = course ids **of the agreement's university** (empty = all programmes); eligible countries = country ids (empty = all countries). ≤ 200 courses, ≤ 250 countries, ≤ 20 terms per agreement |
| CM6 | The 9 §15 terms | commission %, fixed amount, currency, conditions (≤ 2000), eligible programmes, eligible countries, payment timeline (≤ 500), trigger, payment terms (≤ 2000) |
| CM7 | Who reads (U2) | `partnership_access.can_see_commission`: `super_admin`, `partnership_head`, `partnership_manager` (with a profile). **Every other role 403** — overseas_admin (the backlog's negative), counselor, BDM, agent, university_rep, student, anonymous (401). Management M3's `partner` joins `COMMISSION_ROLES` when that role exists |
| CM8 | Who writes | The agreement's university `can_manage_agreements` (owners, their head, super_admin; active university) |
| CM9 | When | While the agreement's terms are editable (draft, sent, under review, negotiation — upc-014 AG11). From approval on → 409 "renew to change" |
| CM10 | Renewal | Renewing an agreement (upc-014 AG8) copies its commission terms into the new draft |
| CM11 | Delete | Allowed while editable (CM9) — a mistaken draft row otherwise feeds upc-019. Audited |
| CM12 | `strip_commission` | `partnership_access.strip_commission(user, payload)` drops `COMMISSION_FIELDS` (`commission_terms`; upc-017 adds the course `commission`) from a payload for non-commission roles. Every agreement payload passes through it: agreements carry `commission_terms` for commission roles only |
| CM13 | Audit / logs | `university_commission_term.create|update|delete`: ids, agreement, MoU number, field names only — never rates, amounts or texts |
| CM14 | Menu page | `/partnership/commercial-terms`: every term (newest first) with its agreement and university, filtered by trigger, currency and MoU-number/university search, paged 50. Live in the manager and head sidebars |
| CM15 | Concurrency | Writes lock university → agreement → term rows (upc-014 order); last write wins for a PATCH; the 20-term cap is checked under the agreement lock |

## 2. Data model — migration `0128_university_commission_terms`

`university_commission_terms`: id, agreement_id FK `university_agreements` RESTRICT, commission_percent Numeric(5,2)?, fixed_amount
Numeric(12,2)?, currency String(3), conditions Text?, course_ids JSON, country_ids JSON, payment_timeline String(500)?, trigger
String(30), payment_terms Text?, created_by_user_id, updated_by_user_id FK users, created_at, updated_at.
CHECKs: exactly one rate; 0 < % ≤ 100; fixed > 0; currency in list; trigger in list. Index `(agreement_id, created_at)`.
Created only when missing (0001 builds from models); downgrade refuses while any term exists. No existing row changes.

## 3. Backend

`services/university_commission.py` (functions, no commit; imports nothing from `university_agreements`), `api/university_commission.py`,
`services/partnership_access.py` (`COMMISSION_FIELDS`, `strip_commission`, `require_commission_reader`).

| Route | Who | Notes |
|---|---|---|
| `GET /partnership/agreements/{id}/commission-terms` | CM7 | `{items,total,limit,offset}` oldest first |
| `POST /partnership/agreements/{id}/commission-terms` | CM8 + CM9 | → 201 `{term}` |
| `PATCH /partnership/agreements/{id}/commission-terms/{term_id}` | CM8 + CM9 | only the fields sent; switching rate kind sends the other as null |
| `DELETE /partnership/agreements/{id}/commission-terms/{term_id}` | CM8 + CM9 | → 204 |
| `GET /partnership/commission-terms` | CM7 | CM14 menu list (`trigger`, `currency`, `q`) |

Order of refusals: 401 → 403 role → 404 agreement/term → 403 scope → 409 inactive university → 409 agreement frozen → 422 values → 409 cap.
`university_agreements.agreements_out` adds `commission_terms` (one extra query per page) and returns each item through `strip_commission`.

## 4. Frontend

- `lib/commissionTerms.ts`: types, trigger labels, currencies, `rateText`, URLs, menu query helpers.
- `components/CommissionTermForm.tsx`: create / edit (rate kind radio, %, or amount, currency, trigger, programmes checklist, countries
  chips via `SearchableSelect`, three texts).
- `components/CommissionTerms.tsx`: inside each agreement card, rendered **only when the payload has `commission_terms`** — "Commission
  terms (restricted)", a row per term, Add / Edit / Delete when `permissions.can_edit_terms`.
- `app/partnership/commercial-terms/page.tsx` menu page; `navigation.ts` entry goes live; the head nav gains it.

## 5. Acceptance criteria

| AC | Statement | Proven by |
|---|---|---|
| AC1 | counselor, overseas_admin, BDM, agent, university_rep, anonymous: no commission field anywhere (API and HTML) | pytest per role (routes 401/403, `strip_commission`), vitest (section absent), e2e (overseas_admin page has no "Commission") |
| AC2 | A manager sees and edits | pytest, e2e |
| P1 | 15% on first-year tuition, trigger visa + enrolment | pytest, e2e |
| N1 | % > 100 → 422; overseas_admin GET → 403 | pytest |
| E1 | both % and fixed → 422 (CM2) | pytest, vitest |
| CM9 | approved/signed agreement → 409; renewal copies terms (CM10) | pytest |

## 6. Tasks (TDD, in order)

1. Migration + model + parity test (`test_upc_016_migration.py`).
2. `strip_commission` unit tests → code; routes tests (create/read/validation, access per role, freeze, delete, cap, renewal copy, menu,
   agreement payload embedding) → service + routes.
3. Frontend lib + form + section + menu page + nav, vitest.
4. Playwright `upc-016-commission-terms.spec.ts`; docs (DEC-SCOPE-143, API §12BK, RBAC §2.69, DATA_MODEL, SCREEN_CATALOG, backlog).

## 7. Regression set (lite)

`test_upc_014_*.py`, `test_upc_026_*.py`, `UniversityAgreements.test.tsx`, `UniversityDetailPage.test.tsx`, `navigation.partnership.test.ts`,
the upc-014 e2e spec.
