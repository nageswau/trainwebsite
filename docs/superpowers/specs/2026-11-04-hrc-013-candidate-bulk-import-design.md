# hrc-013 — Candidate bulk import (design)

**Status:** built on `worktree-hrc-013` under `DEC-SCOPE-391`. **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-013`
(PDF §5.1 "bulk import", §16 "imports with validation, duplicate detection, error reports and safe retry", §14 "failed imports"; PDF
classified `UNVERIFIED`). Dependencies hrc-010 (`DEC-SCOPE-383`) and hrc-014 (`DEC-SCOPE-377`) are merged. The owner said to proceed with
the recommended answers, so Q-13 and I1–I12 below are **the builder's calls (`NEEDS_CONFIRMATION`)**.

## Intent
Recruiters receive candidate lists as spreadsheets (campus lists, job-fair sign-ups, partner sheets). Typing them in one at a time is
slow and invites duplicates. The import must check the file before anything is written, never create a second record for a known
person, report every row and be safe to retry after a dropped connection.

**Anti-goals:** an import that silently changes an existing candidate; a retry that creates people twice; a spreadsheet report that runs
a formula; contact data kept in import tables.

## Decisions (builder's calls)
- **Q-13 / I1 — who and how much.** Candidate writers (`placement_team`, `placement_manager`, `super_admin`) who hold `candidates.import`.
  Migration seeds the grant for `placement_team` and `placement_manager` (super_admin holds every key). `hr_team` never imports (a reader
  role). Q-13 reverses the recruiter backlog's Q-32 (manual entry only), as the HR backlog proposes. Cap: **1,000 rows** (AC1's size) and
  1 MB per file.
- **I2 — file.** `.csv` (UTF-8, with or without a BOM) or `.xlsx` through the shared hardened reader `services/tabular.read_tabular`
  (zip-bomb, macro and DTD checks, no formula evaluation). Headers are trimmed and lower-cased; an unknown, repeated or missing required
  column is a 422 that lists every problem. Nothing is read further.
- **I3 — columns.** `name` (required column) and, per row, a `mobile` or an `email`; optional `source_detail, location, country, state,
  city, qualification, college, passing_year, experience_months, relevant_experience_months, current_company, notice_days,
  preferred_role, preferred_locations, tools, languages, linkedin, available_from, willing_to_relocate`. Lists are `;`-separated;
  `available_from` is `YYYY-MM-DD`; `willing_to_relocate` is yes/no. Each row goes through `CandidateCreate`, so an import accepts
  exactly what the manual form accepts. **Not imported:** salary (grant-restricted), education / employment / certification rows, skills,
  status (new candidates are `available`), owner. These are edited on the candidate afterwards.
- **I4 — source.** One active candidate source is chosen for the whole file (the wizard's select; `source_id` form field). `source_detail`
  may differ per row.
- **I5 — preview.** `POST /recruiter/candidate-imports/preview` (multipart `file`, `source_id`) is read-only: no row, batch or audit is
  written and the file is not stored. Each row is `new`, `matched` (the existing candidate's code, or "same person as row N") or `error`
  (one sentence naming the field). The answer shows the name the file gives, so the recruiter can recognise the row.
- **I6 — commit.** `POST /recruiter/candidate-imports` sends the same file again with the source and an `Idempotency-Key`. Every row is
  re-checked (the preview is advisory: the pool may have changed). One transaction, a savepoint per row; the outcome is `created`,
  `matched` or `error`.
- **I7 — matching ("duplicates are matched, not duplicated").** Q-07's exact keys — the E.164 mobile or the lower-cased email — against
  every candidate, archived ones too; a merged record leads to its survivor. **Nothing on the matched candidate changes.** A later row of
  the same file with the same mobile or email matches the candidate an earlier row created. A unique-index race with a concurrent manual
  create is caught in the row's savepoint and reported as matched. Probable duplicates (hrc-014's fuzzy signals) of a new candidate go to
  the review queue, as for a manual create.
- **I8 — safe retry.** The key is scoped to the uploader: the same key with the same file and source replays the stored report; with a
  different file or source it is a 422. The same file (SHA-256) already imported by the same user with the same source under another key
  also replays (`replayed: true`) — "a retry of the same file creates nothing new" even after a page reload. Imports are serialised by
  one transaction-scoped advisory lock with a 5 s `lock_timeout` (409 "still being processed; retry shortly").
- **I9 — storage.** `candidate_import_batches` (uploader, source, key, file SHA-256, file name ≤ 200, counts) and `candidate_import_rows`
  (batch, row number, status, candidate, reason). No name, mobile or email is stored in either; the report shows a created or matched
  row's code and name by joining the candidate. Error rows carry only the row number and the reason (the uploader has the file).
- **I10 — each created candidate** follows the manual create: CAN code, `mobile_normalized`, `created_by_user_id`, hrc-012 ownership
  (a recruiter importer becomes the primary recruiter), a `candidate.create` audit row with `{"fields", "import_batch_id"}`, hrc-014
  detection. The batch writes one `candidate.import` audit row with the counts and the file hash. Log lines carry ids and counts only.
- **I11 — reading back.** `GET /recruiter/candidate-imports/template` (CSV header row), `GET /recruiter/candidate-imports` (history,
  newest first; recruiters see their own, `placement_manager` and `super_admin` see all), `GET /recruiter/candidate-imports/{id}` (the
  report, 404 outside the caller's scope) and `GET /recruiter/candidate-imports/{id}/report.csv` (every text cell formula-escaped with
  `_safe_cell`). Every route needs the grant. The rows are the data-quality source hrc-034 will read ("failed imports").
- **I12 — screen.** `/recruiter/candidates/import`, reached by an "Import candidates" button beside "+ Add candidate" (candidate writers;
  the API decides the grant and its refusal is shown). Steps: 1 download the template and see the column reference; 2 choose the source
  and the file, "Check file"; 3 the preview — counts and a table of every row (new / already a candidate / error) — with "Import N new
  candidates" and "Choose another file"; 4 the result with the counts, links to matched/created candidates and "Download the full report
  (.csv)". The import history is listed below. A double click never sends twice; a dropped connection says to import again (same key).

## Out of scope
Updating existing candidates from a file, salary columns, structured education/employment rows, skills, resumes, scheduled or
background imports, the data-quality dashboard itself (hrc-034).

## Numbering
Migration `0268_candidate_imports`; API §12KJ; RBAC §2.285; `DEC-SCOPE-391`.
