# upc-017 — Course / program master (design + plan)

**Status:** design written 2026-10-09. The owner's standing instruction for this session is "proceed with the recommended answers;
ask only if genuinely blocking". So Q-21, Q-33 (courses) and the item answers CO1–CO16 (§1) are **recommended defaults accepted under
that instruction** (`NEEDS_CONFIRMATION` as separate per-question approvals) and are registered that way in `DEC-SCOPE-146`.

**Branch:** `feature/upc-017`, cut from `origin/main` @ `362cf3ca`.
**Backlog:** `docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-017. Dependencies upc-003 (`0105`, `DEC-SCOPE-120`) and upc-016
(`0129`, `DEC-SCOPE-144`, PR #189) are merged on main — verified in code (`University.catalogue_visible`, `partnership_access.strip_commission`).
**Source:** `EVID-020` §16 (lines 545–579: the 14 fields, "your counselors know exactly what each partner university offers"), §32 menu
"🎓 Courses & Programs" (1082), line 1129 + U2 (commission visibility), U5 (catalogue flag), U6 (extend `overseas_courses`).
**Numbering:** migration `0131_university_courses`, `DEC-SCOPE-146`, API §12BN, RBAC §2.72 (drafted as `0130` / `DEC-SCOPE-145` / §12BM / §2.71; renumbered on merging `main` @ `94dedfba` (upc-009), which took those).
**Gate:** `APPROVAL_GATES.md` GATE-09.

## 1. Decisions (recommended defaults)

| # | Question | Answer |
|---|---|---|
| CO1 | Q-33 (courses) who writes | The university's `can_edit` rule (upc-003 UM4/UM7/UM9): its primary/backup manager, their head, `overseas_admin` (overseas division), `super_admin`; active university only (409 otherwise). Reads: the master's read roles, every university |
| CO2 | Commission (U2) | Per course, optional: `commission = {percent}` (0 < % ≤ 100) **or** `{amount, currency}` (> 0); null = not recorded. Only `COMMISSION_ROLES` read it (stripped by `strip_commission`, `COMMISSION_FIELDS` gains `commission`) or set it — an overseas_admin who sends `commission` gets 403. Never in the public catalogue, audit rows or logs |
| CO3 | Level | New and edited courses use the master's levels (UG, PG, PhD, Diploma, Foundation). Legacy values (e.g. "Masters") stay untouched until someone edits the level |
| CO4 | Tuition (Q-21) | `tuition_amount` (≥ 0, two decimals) + `tuition_currency` (project currency list), both or neither; a negative fee → 422. The legacy text `tuition_fee` is kept and, whenever an amount is saved, re-derived as e.g. `GBP 18,000`, so the catalogue keeps showing a fee with no web change |
| CO5 | Legacy parse (Q-21) | Migration, best effort, only where `tuition_amount` is null: `£ / € / GBP / EUR / CAD / AUD / NZD / USD / US$ / ₹ / INR` + a number (commas allowed) → amount + currency. A bare `$`, text ("See university fee policy") or anything else stays unparsed (null). Intakes are parsed the same way from month names; "Winter"/"Fall" stay unparsed. The legacy texts are never changed |
| CO6 | Application fee | `application_fee` (≥ 0) + `application_fee_currency`, both or neither |
| CO7 | Intakes | A list of months (`Jan` … `Dec`), unique, stored in calendar order; the legacy `intake` text is re-derived ("Jan, Sep") when the list is saved non-empty |
| CO8 | English requirement | `english_test` ∈ IELTS, TOEFL, PTE, Duolingo, Other, plus `english_score` (> 0; ≤ 9 / 120 / 90 / 160 / 999.9). A score needs a test |
| CO9 | Scholarships | `scholarship_ids` (≤ 20) of this university's scholarships or its country's university-wide ones (`university_id` null); others → 422 |
| CO10 | Other §16 fields | `entry_requirements` and `application_process` (text ≤ 2000), `deadline` (date), `duration` (≤ 80), `category` (≤ 80), `title` (≤ 200); country and university come from the university |
| CO11 | Deactivate | `active=false` via PATCH, allowed with open applications (backlog edge): existing applications, shortlists and commission terms keep their `course_id`; the course leaves the public catalogue and shows "Inactive" in the master. No delete |
| CO12 | Duplicates | Same university + title (NFKC/casefold/space-collapsed) + level → 409 on create/update; checked under the university row lock |
| CO13 | Public catalogue (U5) | `/public/overseas-courses` and `/public/universities/{slug}` list only **active** courses of published, active universities; their keys are unchanged (no commission, no new fields) |
| CO14 | CSV import (Q-21) | Per university: `POST /partnership/universities/{id}/courses/import` (multipart + `Idempotency-Key`), by CO1's writers. Columns: required `title, level, category, duration`; optional `tuition_amount, tuition_currency, application_fee, application_fee_currency, intakes (;), english_test, english_score, entry_requirements, application_process, deadline (YYYY-MM-DD), active (yes/no)`. Commission and scholarships are per-record decisions, not imported. Each row → created / duplicate (CO12, master or earlier row) / invalid with a reason. 1 MB, 1,000 rows. Same key + same file replays; same key + other file 422. The batch (`course_import_batches`) keeps counts and per-row results, never the file |
| CO15 | Menu page | `/partnership/courses` "Courses & Programs": every course with its university, filter by level, status (active default / inactive / all) and a title / university search, paged 50; the commission column only for commission roles. Live in the manager and head sidebars |
| CO16 | Audit / logs / locks | `university_course.create|update|import`: ids + field names (never commission values). Writes lock the university row then the course row |

Counselors (backlog "read"): they see active courses through the public catalogue now; the role-sliced 360 view is upc-030 (U14).

## 2. Data model — migration `0131_university_courses`

`overseas_courses` gains (all nullable / defaulted, guarded since 0001 builds from models): `tuition_amount` Numeric(12,2), `tuition_currency`
String(3), `application_fee` Numeric(10,2), `application_fee_currency` String(3), `intakes` JSON default `[]`, `entry_requirements` Text,
`english_test` String(10), `english_score` Numeric(4,1), `scholarship_ids` JSON default `[]`, `application_process` Text, `deadline` Date,
`active` Boolean NOT NULL default true, `commission_percent` Numeric(5,2), `commission_amount` Numeric(12,2), `commission_currency` String(3).
CHECKs: amounts ≥ 0, amount ⇔ currency (tuition, fee), currencies in list, english test in list, score > 0, commission at most one rate,
percent 0–100, amount > 0 ⇔ currency. Index `(university_id, level)`.
`course_import_batches`: id, university_id FK, uploaded_by_user_id FK, idempotency_key, file_sha256, total/created/duplicate/invalid
counts, results_json, timestamps; unique (uploaded_by, key); CHECK counts sum.
Downgrade refuses while any batch exists or any course carries data only these columns hold.

## 3. Backend

`services/university_courses.py` (functions only, no commit), `api/university_courses.py`.

| Route | Who | Notes |
|---|---|---|
| `GET /partnership/universities/{id}/courses` | read roles | `include_inactive`, `limit`/`offset`; `{items,total,limit,offset,can_edit}` by title; commission stripped |
| `GET /partnership/universities/{id}/course-options` | CO1 writers | `{scholarships:[{id,title,amount}]}` (CO9) |
| `POST /partnership/universities/{id}/courses` | CO1 (+ CO2 for commission) | 201 `{course}` |
| `PATCH /partnership/universities/{id}/courses/{course_id}` | CO1 (+ CO2) | only fields sent; course must belong to the URL's university (404) |
| `GET /partnership/universities/{id}/courses/imports/template` · `POST …/courses/import` | CO1 | CO14 |
| `GET /partnership/courses` | read roles | CO15 |

Refusal order (writes): 401 → 403 role → 404 university → 403 scope / 409 inactive → 403 commission (CO2) → 404 course → 422 values → 409 duplicate.

## 4. Frontend

- `lib/courseMaster.ts`: types, levels, months, tests, currency list, money/commission text, URLs, menu query helpers.
- `components/CourseForm.tsx` (create/edit, `noValidate` with own messages), `components/UniversityCourses.tsx` (section on the university
  page: rows with level/duration/intakes/tuition/English/deadline, Inactive badge, Add/Edit, Show inactive, Import), `components/CourseImportPanel.tsx`.
- `app/partnership/courses/page.tsx` (menu); `navigation.ts` entry live; head nav gains it. The public catalogue pages are unchanged.

## 5. Acceptance criteria

| AC | Statement | Proven by |
|---|---|---|
| AC1 | All §16 fields are captured | pytest create/read round trip; vitest form; e2e |
| AC2 | Existing applications keep their `course_id` (incl. after deactivation) | pytest (migration + deactivate with applications) |
| AC3 | `/public/overseas-courses` never includes commission, unpublished universities or inactive courses | pytest |
| P1 | "MSc Cyber Security, PG, 1 yr, Sep/Jan, £18,000, IELTS 6.5" | pytest, e2e |
| N1 | negative fee → 422 | pytest, vitest |
| E1 | deactivated with open applications: allowed, shown inactive | pytest, vitest |
| U2 | overseas_admin / counselor never see commission; overseas_admin cannot set it | pytest |
| Q21 | CSV import report; replay idempotent; legacy tuition parse | pytest |

## 6. Tasks (TDD, in order)

1. Migration + model + parity + legacy parse tests (`test_upc_017_migration.py`).
2. Service + routes: create/read/update, validation, access per role, commission strip, duplicates, deactivate, options, menu (`test_upc_017_courses.py`); public filter (`test_upc_017_public.py`).
3. CSV import (`test_upc_017_import.py`).
4. Frontend lib + form + section + import panel + menu page + nav, vitest.
5. Playwright `upc-017-course-master.spec.ts`; docs (DEC-SCOPE-146, API §12BN, RBAC §2.72, DATA_MODEL, SCREEN_CATALOG, backlog).

## 7. Regression set (lite)

`test_ovs_001_discovery.py`, `test_ovs_002_application.py`, `test_upc_003_public.py`, `test_agn_007_*`, `test_agn_008_*`, `test_upc_016_*`,
`test_upc_014_agreements.py`; `UniversityDetailPage.test.tsx`, `navigation.partnership.test.ts`; the upc-003 / upc-016 e2e specs.

## 8. QA (Phase 5, 2026-10-09, `upc017` stack on :13017)

Playwright `upc-017-course-master.spec.ts` passed, with the upc-001 / upc-003 / upc-016 / OVS-001 specs (OVS-001's country list failed
once on the first ISR hit after `--build`, then passed — the known warm-up). An exploratory script (scratchpad) covered: empty state;
client validation (required, > 2 decimals, half a currency pair, TOEFL > 120); a double click (one POST); the duplicate 409; cancel; an
induced 500 ("could not be saved") and a dropped request (the shared "did not complete" text); a no-change save; reload; import (non-CSV
precheck, wrong header 422 "Unknown column: name", mixed rows report); tablet (820 px) / phone (390 px) with the form open and on the menu,
no side scroll; menu filtered-empty, past-end, level filter and back navigation; a non-owner manager (no buttons); a counselor (menu
refused, API 403); signed out (login redirect); no broken images. Console / network errors were only the induced ones.

| ID | Severity | Role / page | Found | Fix |
|---|---|---|---|---|
| QA-01 | Low (a11y) | manager, university page | After "Add course" / "Edit", focus fell to `<body>` (the button unmounts) | The form's title field takes focus (vitest + browser re-check) |
| QA-02 | Low (copy) | manager, course form + API | "An TOEFL score cannot be above 120." / API "A IELTS score…" | "The {test} score cannot be above {max}." in both (vitest + browser re-check) |

Pre-existing, not touched: `PartnershipTeamTable.test.tsx` ("17 areas still to come") fails on main already.
