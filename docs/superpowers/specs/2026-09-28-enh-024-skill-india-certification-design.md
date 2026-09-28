# ENH-024 — Skill India Certification Tracking — Design

**Status:** Design approved in-session, 2026-09-28 (clarifying answers, approaches, design sections, then an
API / frontend / security review pass whose amendments are folded in below). Superpowers architectural path:
brainstorming → this design doc → `writing-plans` next. Written spec awaiting user review.

**Source requirement:** the brochure, page 2, "Skill India Certification" (standalone callout; no section in
`School CRM.md`). **Backlog item:** `docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-024 (`DERIVED_BLUEPRINT`).
**Decision record:** `docs/decisions/PRODUCT_DECISION_REGISTER.md` → `DEC-SCOPE-031` (added by the implementation plan's first task; records §3 below as
`EXPLICIT_APPROVAL`, user, 2026-09-28). If another branch claims `DEC-SCOPE-031` first, renumber on merge
(precedent: `DEC-SCOPE-024`/`025`/`027`/`029`/`030`).
**Branch:** `feature/enh-024-skill-india-certification`.

## 1. Scope

**Acceptance criterion (backlog):** a Skill India certification can be recorded per student and appears
correctly on their Portfolio/360° view.

**Existing behaviour (Graphify-oriented investigation, 2026-09-28).** ENH-012's `PortfolioEntry`
(`portfolio_entries`, `models.py:1133`) is one generic table with a `section` discriminator; `certification`
is one of its 10 sections (`schemas.py:906`). ENH-013's 360° Certificates tab renders exactly
`portfolio_payload()["entries"]["certification"]` (`student_360.py:102`). A Skill India certificate can
therefore already be typed in as a plain certification entry, but it cannot be identified as Skill India and
carries no status, certificate number or issue date.

**In scope:** a Skill India tag on certification entries, plus status / certificate number / issue date for
tagged entries; capture in the Digital Portfolio form; display on the Portfolio and the 360° Certificates tab.

**Out of scope:** any external Skill India / NCVET / government registry integration (D9); the other
certificate-shaped records — `Certificate` (IT LMS, keyed to `users`), `Program.certification`,
`SchoolSkillEnrollment` `certified` (ENH-011), `SchoolLanguageRecord.certification_status` (SCH-009) — are not
touched; ENH-021 (internship certificate) and every other ENH item.

## 2. Approaches considered

1. **Chosen — four nullable columns on `portfolio_entries` + CHECK constraints; existing endpoints extended
   additively.** Matches ENH-012's one-table decision and the backlog's "reuse, don't add a fourth parallel
   certificate table"; database-enforced invariants; no new endpoint, no join.
2. Rejected — one JSON `details` column: the database cannot enforce "certified ⇒ number + date".
3. Rejected — a 1:1 details table: a join on every read and a two-row write on every create, for no gain.

## 3. Decisions (in-session, `EXPLICIT_APPROVAL`, 2026-09-28)

- **D1 Storage:** tag on the existing `certification` section (`certification_type = 'skill_india'`); no new
  portfolio section, so `completion_percentage` is unchanged for every student.
- **D2 Fields:** status, certificate number, issuing body, issue date.
- **D3 Field scope:** status / number / issue date are accepted **only** on Skill India–tagged entries; other
  certification entries behave exactly as today.
- **D4 Issuing body:** reuses the existing `organization` column (labelled "Issuing body" for tagged entries).
- **D5 Status values:** `enrolled`, `in_progress`, `certified`. Any status may change to any other (manual
  record; staff correct mistakes) — unlike ENH-011, `certified` is not terminal.
- **D6 Required fields:** a tagged entry always has a status; `certified` additionally requires certificate
  number **and** issue date. Issuing body is always optional.
- **D7 Uniqueness:** none on certificate number.
- **D8 Tag lifecycle:** set at creation only (like `section`); not changeable by PATCH. To change it, delete
  and re-add.
- **D9 Integration:** none — an internal record entered by staff.
- **D10 Writers:** the existing portfolio writers (`school_coordinator`, assigned `school_teacher`,
  `academic_team`) via `_can_edit_portfolio`, unchanged.
- **D11 Tier and transfer:** the existing `digital_portfolio_creation` gate with ENH-023 grandfathering on
  update/delete; reads stay ungated (ENH-022 D3); entries follow the student on transfer (FK to
  `school_students`).
- **D12 UI entry:** a "Skill India certification" checkbox in the Certifications section's Add form.
- **D13 Future issue dates:** not rejected (same as `date_from` today).
- **D14 Create idempotency:** POST stays non-idempotent (unchanged); the form's `inFlight` guard prevents
  double submits.
- **D15 Rate limiting:** none added — authenticated staff-only writes, no existing limiter on portfolio
  writes; adding one is a throttling change outside this item. Accepted.
- **D16 Log/audit minimisation:** the certificate number (an identifier belonging to a minor) is never written
  to application logs or `AuditLog` metadata.

## 4. Data model — migration `0042_skill_india_certification`

New nullable columns on `portfolio_entries` (model `PortfolioEntry` gains the same, plus the CHECKs in
`__table_args__`, so a fresh database built by `0001_initial`'s `create_all()` matches):

| Column | Type | Meaning |
|---|---|---|
| `certification_type` | `String(30)` NULL | `'skill_india'` or NULL |
| `certification_status` | `String(20)` NULL | `enrolled` / `in_progress` / `certified` |
| `certificate_number` | `String(100)` NULL | free text, single line |
| `issued_on` | `Date` NULL | issue date |

CHECK constraints (last line of defence; the API rejects all of these first):

- `ck_portfolio_cert_type`: `certification_type IS NULL OR (certification_type = 'skill_india' AND section = 'certification')`
- `ck_portfolio_cert_status`: `certification_status IS NULL OR certification_status IN ('enrolled','in_progress','certified')`
- `ck_portfolio_cert_fields`: `(certification_type IS NULL AND certification_status IS NULL AND certificate_number IS NULL AND issued_on IS NULL) OR (certification_type IS NOT NULL AND certification_status IS NOT NULL)`
- `ck_portfolio_cert_certified`: `certification_status IS DISTINCT FROM 'certified' OR (certificate_number IS NOT NULL AND issued_on IS NOT NULL)`

Existing rows get NULL in all four columns and satisfy every CHECK: no backfill, no data rewritten. Every
upgrade step is guarded (column / constraint already present → skip), as `0041` does. `downgrade()` drops
the four CHECKs and four columns only; entries survive as plain certifications (only Skill India details are
lost). No new index (nothing filters by tag).

## 5. Backend / API

No new endpoint, no URL change. All changes are additive.

**`schemas.py`**
- `CertificationType = Literal["skill_india"]`, `CertificationStatus = Literal["enrolled","in_progress","certified"]`.
- `PortfolioEntryCreate` gains `certification_type`, `certification_status`, `certificate_number`
  (`max_length=100`, stripped, blank → None, `_no_control_characters`), `issued_on: date | None`, all default
  None. A `model_validator(mode="after")` enforces, in plain language (422 list):
  - tag on a non-`certification` section → "Only a certification can be marked as Skill India";
  - tag without status → "Choose a status for the Skill India certification";
  - status / number / issue date without the tag → "Status, certificate number and issue date apply only to Skill India certifications";
  - `certified` without number or issue date → "A certified Skill India certification needs a certificate number and issue date".
- `PortfolioEntryUpdate` gains `certification_status`, `certificate_number`, `issued_on` (same field rules). It
  does **not** gain `certification_type`; `extra="forbid"` already makes sending it a 422 (D8).
- `PortfolioEntryOut` gains the four fields (`| None`).
- The four messages are module constants shared by the schema validators and the router's post-merge check
  (the `DATE_RANGE_ERROR` precedent), not duplicated strings.

**`api/portfolio.py`**
- `_entry_out` adds the four fields → `GET /portfolio` and `GET /360-view` pick them up through
  `portfolio_payload` unchanged (`test_enh_013_refactor` keeps holding; `build_360` is not edited).
- **Create:** persists the new fields. Order unchanged: reader scope → write role → tier gate → insert + audit →
  commit.
- **Update:** the entry is loaded **with `SELECT … FOR UPDATE`** (`populate_existing`) instead of `db.get`,
  then tier gate (grandfathered on `entry.created_at`), then the `model_fields_set` merge extended to the three
  fields, then post-merge validation (date range as today, plus: detail field set on an untagged entry → 422;
  explicit `certification_status: null` on a tagged entry → 422; `certified` without number/date → 422) with
  `HTTPException(422, <constant>)`, then audit + commit. The lock serialises concurrent PATCHes so each
  validates against the other's committed result; without it two individually valid PATCHes could combine
  into a CHECK violation (500). One row is locked; transfers never lock portfolio entries, so no deadlock
  path. A tier denial commits only its audit row (ENH-022), which also releases the lock.
- **Delete:** unchanged flow; audit metadata adds `certification_type`.
- **Audit metadata (D16):** create adds `certification_type` and `certification_status`; update adds
  `{"old_status", "new_status"}` when the status changes; delete adds `certification_type`. Never the
  certificate number. Application log lines add `certification_type` only.

**HTTP semantics (unchanged helpers):** 401 unauthenticated; 403 wrong role / unassigned teacher / tier denied;
404 student outside scope or entry belonging to another student (`_load_portfolio_entry`'s
`school_student_id` check — the IDOR guard); 422 validation; 201 / 200 / 204 on success.

**Transaction failure:** every write is one transaction (row + audit → commit). Any exception before commit
leaves nothing written (the request session closes without committing). The CHECKs make an invalid state
unrepresentable even if a code path is missed.

## 6. Frontend

Reuse: `PortfolioEntryForm`, `PortfolioPanel`, `StatusChip` (already labels `enrolled`/`in_progress`/
`certified`), `detailMessage`, `refocus`, `formatCalendarDate`, CSS `.badge`, `.status`, `.pf-*`, `.s360-list`.

- **`lib/portfolio.ts`:** `PortfolioEntry` gains `certification_type`, `certification_status`,
  `certificate_number`, `issued_on` (all `string | null`).
- **`components/CertificationDetails.tsx` (new, the only new component):** hook-free, so it renders inside
  both the client `PortfolioPanel` and the server `Student360Panels`. Renders nothing unless
  `certification_type === "skill_india"`; otherwise a "Skill India" `.badge`, `StatusChip`, "Certificate no. …"
  and "Issued <date>" on one wrapping line (`.pf-cert`). All text is React-escaped; nothing becomes a link.
- **`PortfolioPanel`:** renders `CertificationDetails` under each entry title; passes the four fields into the
  edit form's `initial`.
- **`Student360Panels`:** the shared `Entries` list renders `CertificationDetails` (a no-op for the Activities
  and Skills tabs that also use `Entries`). Empty text unchanged.
- **`PortfolioEntryForm`:**
  - create + `section === "certification"`: native checkbox "Skill India certification";
  - ticked (or editing a tagged entry): `<fieldset><legend>Skill India details</legend>` with Status `<select>`
    (placeholder "Choose status", no default), Certificate number (hint "Required once certified",
    `aria-describedby`), Issue date (`type="date"`); the Organization label becomes "Issuing body (optional)";
  - edit mode: no checkbox; "Skill India certification" shown as text; PATCH never sends `certification_type`;
  - client checks mirror D6 ("Choose a status." / "Enter the certificate number." / "Enter the issue date."),
    each with `aria-invalid` + linked error id; focus moves to the first invalid field; the server remains
    authoritative and its message shows in the existing `role="alert"`;
  - unticking hides the fieldset and omits the fields from the body;
  - busy state ("Saving…") disables every field, as today; no optimistic UI; `router.refresh()` after save.
- **CSS:** one rule, `.pf-cert { display:flex; flex-wrap:wrap; gap:.5rem; align-items:center; overflow-wrap:anywhere }`.
- **States:** loading via the existing `loading.tsx` pages and the form's busy state; empty via the existing
  texts; error via the existing alert (including tier 403 and "The save could not be confirmed").
- **Responsive / a11y:** stacked form fields as today; details line wraps; verified at 320 / 768 / 1024 /
  1440 px; all controls native and labelled; status conveyed by text, never colour alone.

## 7. Security

| Concern | Treatment |
|---|---|
| Authentication | unchanged (`get_current_user`, httpOnly `SameSite=lax` cookie) |
| Authorization / role escalation | unchanged writers + tier gate; `extra="forbid"` blocks `section`, `school_student_id`, `created_by_user_id`, `certification_type` on PATCH |
| IDOR | entry must belong to the scope-checked student → 404 |
| Input validation | Literal enums, length caps, control-character rejection, date parsing, cross-field rules, DB CHECKs |
| XSS | React text rendering only |
| CSRF | unchanged: `SameSite=lax` + CORS restricted to `frontend_url` + JSON body |
| SQL injection | ORM only |
| Secrets / tokens | not touched |
| Sensitive logs | D16 |
| Rate limiting | D15 |
| Audit | §5 |

## 8. Acceptance criteria

- **AC-01** A writer can create a Skill India certification (tag + status, optional number / issue date /
  issuing body); 201 returns all four new fields.
- **AC-02** It appears in `GET /portfolio` under `entries.certification` and in the 360° Certificates tab for
  every role that can read the student (coordinator, assigned teacher, principal, parent, academic_team,
  career_counselor, psychometric_team), with identical field values.
- **AC-03** A writer can PATCH status / number / issue date; the rules of D6 hold after merging with stored
  values.
- **AC-04** Each rule in §5 produces a 422 with its plain-language message; nothing is written.
- **AC-05** `certification_type` in a PATCH is a 422; the tag never changes after creation.
- **AC-06** Non-writers (principal, parent, career_counselor, psychometric_team) and an unassigned teacher get
  403; a caller outside the student's scope gets 403/404 as today; another student's entry id gets 404.
- **AC-07** Below-tier create is 403; grandfathered update/delete of a pre-downgrade entry is allowed
  (ENH-023).
- **AC-08** Two concurrent PATCHes on one entry never produce a 500 / CHECK violation; the later one validates
  against the earlier one's committed result.
- **AC-09** The database rejects every invalid combination directly (CHECKs).
- **AC-10** Migration upgrades a database with existing portfolio entries without changing them, and
  downgrades cleanly.
- **AC-11** Audit rows carry the metadata of §5 and never the certificate number.
- **AC-12** Untagged entries, completion percentage and every existing ENH-012/013/022/023 test are unchanged.
- **AC-13** The portfolio form shows the checkbox only when adding a certification; the Skill India fieldset,
  label switch, client validation, focus movement, create / edit bodies behave as §6.
- **AC-14** Portfolio and 360° Certificates render the badge, status, certificate number and issue date; the
  layout holds at 320 px; keyboard-only operation works.

## 9. Tests (written first, per behaviour)

- **Backend** `apps/api/tests/test_enh_024_skill_india.py`: AC-01…AC-11 (reusing `enh005_helpers` /
  ENH-012 test builders); concurrency via two sessions as in the ENH-013 career-goal transfer-race test;
  migration test modelled on `test_enh_013_migration.py` (columns, CHECKs, head includes 0042, existing rows untouched), plus a manual `alembic downgrade -1` / `upgrade head` run recorded in the RTM.
- **Frontend (vitest):** `PortfolioEntryForm.test.tsx`, `PortfolioPanel.test.tsx`, `Student360Panels.test.tsx`
  extended; new `CertificationDetails.test.tsx`.
- **Playwright** `apps/web/tests/e2e/enh-024-skill-india-certification.spec.ts`: coordinator adds `enrolled`,
  edits to `certified`, sees it on Portfolio and 360°; parent sees it; principal read-only; 320 px viewport.
- **Regression:** ENH-012, ENH-013 (incl. refactor), ENH-022, ENH-023 backend + frontend + E2E suites.

## 10. Regression risks

1. Shared `Entries` (360°) also renders Activities / Skills — `CertificationDetails` is a no-op without the tag.
2. `test_enh_013_refactor` builder/route equality — both go through `_entry_out`.
3. PATCH `model_fields_set` clear semantics — new fields follow the same merge loop.
4. PATCH now takes a row lock — scoped to one entry row; tier-denial commit releases it.
5. Completion % — untouched by design (D1).
6. Migration on a fresh DB — guarded steps + CHECKs declared on the model.

## 11. Completion gates (not claimed by implementation alone)

Backend, frontend and E2E tests; lint / type-check / build; migration up/down; browser validation (responsive,
keyboard, accessibility); independent Codex review; RTM and backlog updates.
