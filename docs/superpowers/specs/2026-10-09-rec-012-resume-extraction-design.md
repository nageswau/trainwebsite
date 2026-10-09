# rec-012 — Resume text + rule-based skill extraction (design)

Backlog: `docs/delivery/RECRUITER_CRM_BACKLOG.md` rec-012. Source: EVID-018 S2-§4 (lines 1235–1285). Owner answer R7 (`DEC-SCOPE-116`):
rule-based, in-house extraction with `pypdf` and `python-docx`, and no AI provider. Depends on rec-006 (merged PR #150), rec-009 (merged
PR #155) and rec-011 (merged PR #180).

**Numbering (re-chained 2026-10-09 after rec-020 and rec-018 merged; drafted as `0133` / DEC-SCOPE-148 / §12BP / §2.74):**
`DEC-SCOPE-150`, migration `0135_resume_extraction` (after `0134_application_screenings`), API §12BR, RBAC §2.76. Re-check
origin/main before the merge.

## 1. Answers (2026-10-09)
The owner asked to proceed with the recommended answers, so nothing was asked. Every row below is **UNVERIFIED** (a recorded default).

| ID | Question | Default |
|---|---|---|
| EX1 | When extraction runs | The upload stays as it is (rec-009). The web client calls **Extract** for the new version right after a successful upload, and writers can re-run it on the current version ("Review extracted details"). Extraction recomputes every time, because the Skills Master changes. |
| EX2 | What extraction stores | Only the resume row: `extracted_text` (capped), `extraction_json` (the suggestions) and `extracted_at`. Nothing reaches the candidate's profile or skills until the recruiter accepts (AC2). |
| EX3 | Skills, technologies, tools | All three come from the Skills Master (names and aliases, active skills only). Each suggestion carries its category, which is how technologies and tools are told apart. |
| EX4 | Matching | The text and every term go through one tokeniser. The longest term wins (so "Spring Boot" does not also suggest "Spring"). A trailing plural "s" is accepted ("REST APIs" → REST API). Single-letter terms and a short stop-word list ("go", "spring", "rest", "swift", "rust", "express", "shell", "less", "access", "excel") must match the master's casing exactly. |
| EX5 | Other suggestions | Qualification (degree patterns, highest first), total experience (years and months near "experience", else the first stated), location (a "Location:" line, else the first known city), job titles (role patterns), certifications (lines that mention certification, plus known acronyms) and industry (keywords). At most 10 of each list. |
| EX6 | What Apply writes | The ticked skills become `candidate_skills` rows (source `resume`, status `claimed`, the level the recruiter picks, default **Intermediate**). The ticked profile fields (qualification, total experience, location) overwrite the candidate's values. Job titles, certifications and industry are kept with the resume only (rec-014 searches them). |
| EX7 | Apply rules | All or nothing. A skill already on the candidate → 409 naming it; an unknown or inactive skill → 422; the same skill twice → 422; nothing chosen → 422. The 100-skill cap (rec-011 SK6) applies. Apply needs the version to have been extracted (409 otherwise). |
| EX8 | Limits | The 5 MB upload cap (rec-009) stays. At most 30 PDF pages are read; text is cut at 100,000 characters (`truncated: true`). A DOCX with more than 2,000 parts or more than 50 MB uncompressed is refused. Extraction runs in a thread (`asyncio.to_thread`) with a 20-second limit; no Celery task. |
| EX9 | Failures | A password-protected PDF → 422 "This PDF is password-protected …". An unreadable file → 422 "Could not read the text …". A timeout → 422. A scanned or empty PDF answers 200 with `no_text: true` (AC3) and stores the empty text. |
| EX10 | Who | Extract and Apply are candidate **writers** (recruiter, placement manager, `super_admin`; R11). `hr_team` reads candidates but cannot extract (Extract writes to the resume row). Archived → 409; outside the pool → 404. |

## 2. Data (migration `0135_resume_extraction`)
`candidate_resumes` gains three nullable columns. No existing row changes. Each step is guarded (the 0132 idiom).
| Column | Type | Rule |
|---|---|---|
| `extracted_text` | text null | Null until extracted; `''` when no text was found |
| `extraction_json` | json null | The last suggestions (see §4) |
| `extracted_at` | timestamptz null | |

`downgrade()` drops the columns. Their data is derived and can be recomputed from the stored file.

## 3. Service `app/services/resume_extract.py` (pure)
Bytes and a term list go in, a dict comes out. No database and no I/O (the `reporting/pdf.py` purity idiom).
- `read_text(data, content_type) -> (text, truncated)`: PDF via `pypdf` (it tries an empty password, then refuses an encrypted file;
  first 30 pages). DOCX via `python-docx` (paragraphs and table cells) after the zip guard. Raises `ExtractError(message)`.
- `suggest(text, terms) -> dict`: `terms` is a list of `(term, skill_id)` built from active skill names and aliases. The result holds
  `skills: [{skill_id, matched}]` in order of first appearance, plus `qualification`, `experience_months`, `location`, `job_titles`,
  `certifications` and `industries`.

The route builds the terms (one query), reads the file (`services/candidates.read_file`), runs `read_text` and `suggest` in a thread under
`asyncio.wait_for`, stores the result, writes the audit row and commits.

## 4. API (§12BR), prefix `/api/v1/recruiter/candidates/{candidate_id}/resume/{version}`
| Method | Path | Who | Result |
|---|---|---|---|
| POST | `/extract` | writers | 200 → the extraction (below). 404 unknown version; 409 archived; 422 encrypted, unreadable or timed out |
| POST | `/apply` | writers | `{skills: [{skill_id, level}], qualification?, experience_months?, location?}` → 200 `{skills_added, fields}`. 409 not extracted, archived or duplicate; 422 rules (EX7) |

Extraction: `{version, no_text, truncated, text_chars, extracted_at, skills: [{skill{id,name,active}, category{id,name}, matched,
on_profile}], qualification, experience_months, location, job_titles[], certifications[], industries[]}`.
- `on_profile` is worked out when the response is built, so a skill added since is shown as already on the profile.
- Apply's profile fields reuse `CandidateUpdate`'s validators (the same 422 sentences). A key that is not sent is left unchanged.
- One audit row each: `candidate.resume_extract` (version, skill count, text length, no_text, truncated) and `candidate.resume_apply`
  (version, skill ids, field names). Each added skill also writes rec-011's `candidate.skill_add` row. Logs carry ids only, never resume
  text.

## 5. Web
- **`lib/recruiterResumeExtract.ts`:** types, URLs and the selection → body mapping.
- **`RecruiterResumeExtraction`** ("Review extracted details", opened inside the Resume card):
  - States: "Reading the resume…", an error with Retry, and "No text found in this resume — it may be a scanned image. Add the details by
    hand." The truncation note shows when it applies.
  - **Skills:** one checkbox row per suggestion (ticked by default) with the category, the matched text and a Level select (default
    Intermediate). A skill already on the profile shows "Already on profile" and cannot be ticked.
  - **Profile fields:** qualification, total experience and location, each with "Suggested X (current Y)". Ticked by default only when
    the current value is empty.
  - **From the resume (not saved to the profile):** job titles, certifications and industry.
  - **Save selected** (guarded against double submits) and **Discard**. On success the candidate and the Skills card reload, and a status
    line names what was saved.
- **`RecruiterCandidateResumes`:** after an upload, it opens the panel for the new version. Writers also get "Review extracted details" on
  the current version.

## 6. Acceptance criteria
1. The source sentence yields exactly Java, Spring Boot, Hibernate, REST API and MySQL (AC1).
2. Extract changes neither the candidate nor their skills; only Apply does (AC2).
3. A scanned or empty PDF reports "no text found" (AC3).
4. A DOCX resume yields its skills plus 36 months for "3 years of experience" (positive scenario).
5. An encrypted PDF → 422 with a readable sentence, not a 500 (negative scenario).
6. Lowercase "go" in prose is not suggested as Go; a resume over the cap is truncated and says so (edge cases).
7. Apply adds the ticked skills as `resume` / `claimed` with the chosen level, writes the ticked fields, and rolls back on any conflict.
8. Writers only; `hr_team` 403; outside the pool 404; archived 409.
9. The panel works on desktop, tablet and mobile, with loading, empty and error states, and is keyboard operable.

## 7. Tests
- `test_rec_012_resume_extract.py` (pure): AC1, plurals, longest match, stop words, the DOCX case, a scanned PDF, an encrypted PDF, a
  corrupt file, truncation, the zip guard, each pattern.
- `test_rec_012_resume_extraction_api.py`: extract stores and changes nothing else, `on_profile`, apply (skills and fields, all or nothing,
  the duplicate 409, unknown 422, not extracted 409), roles, pool and archived.
- `test_rec_012_migration.py`: columns exist, single head.
- vitest for the lib and the panel. Playwright `rec-012-resume-extraction.spec.ts`: upload a DOCX → review → save → skills appear.

## 8. Risks
- New dependencies `pypdf` (BSD-3-Clause) and `python-docx` (MIT), both pinned. The api image must be rebuilt.
- Parsing untrusted files: both libraries are pure Python and run nothing. `python-docx` parses XML through lxml with entity resolution
  off. The limits are in EX8.
- `models.py`, `schemas.py` and `main.py` are append hotspots shared with parallel items.
