# Duplicate Analysis

Generated during Bootstrap (`prompts/00_BOOTSTRAP_AND_EVIDENCE_INVENTORY.md`), NO-ASSUMPTION MODE.

Method: SHA-256 recomputed independently for all 13 files in `docs/sources/` via `sha256sum`,
compared against `docs/evidence/SOURCE_MANIFEST.csv`. All recomputed hashes matched the manifest
exactly — the manifest is confirmed accurate, not merely trusted.

Per `CLAUDE.md`: "Byte-identical duplicates count as one evidence item, not multiple independent
votes." Only byte-identical (matching SHA-256) files are collapsed below. Files that merely share a
title, look visually similar, or carry the same authored content in a different file format are
**not** collapsed — they remain separate evidence items with a noted relationship.

## Confirmed exact-duplicate groups (byte-identical, collapsed to one evidence vote)

### Group 1 — `EVID-002`
SHA-256: `24ee9eb886cf2458269761150351e3b6fe5161a30a8686aee73515d01a884c4e`

| Filename | Size (bytes) |
|---|---|
| `Edusphere UK Website (1)(1).docx` | 57,500 |
| `Edusphere UK Website(1)(1).docx` | 57,500 |
| `Edusphere UK Website(2).docx` | 57,500 |

Three filenames, one document. Counted as a single `ORIGINAL_REQUIREMENT` evidence item
(`EVID-002`). None of the three carries an explicit document date; no chronology may be inferred
from the `(1)`/`(2)` filename suffixes.

### Group 2 — `EVID-008`
SHA-256: `1fcfac3990680c579f0c55f64be27ca5ead74de07dd855eac33580133d9351be`

| Filename | Size (bytes) |
|---|---|
| `Pasted text (2)(2).txt` | 76,368 |
| `Pasted text (3).txt` | 76,368 |

Two filenames, one transcript. Counted as a single `MEETING_TRANSCRIPT_REQUEST` evidence item
(`EVID-008`). No explicit date in the transcript text; no chronology inferred from filename
suffixes.

## Items that look like duplicates but are NOT byte-identical (kept separate — not collapsed)

These are flagged explicitly so they are never mistaken for confirmed duplicates or silently
merged in a later phase.

| Item A | Item B | Relationship observed | Why NOT collapsed |
|---|---|---|---|
| `Edu(2).png` (EVID-001, SHA-256 `75b33890…142`, 2000×2000) | `EduSphere(2).png` (EVID-003, SHA-256 `538244b6…520`, 2048×2048) | Visually identical logo mark ("EduSphere — Learn, Apply, Succeed," blue circular emblem) when rendered | Different SHA-256 and different pixel dimensions — not byte-identical. Treated as two separate evidence items; canonical/authoritative asset is `NEEDS_CONFIRMATION`. |
| `Edusphere_Application_Architecture_Tasks_Testing_UX_Specification(1).docx` (EVID-004, SHA-256 `3354954c…4`) | `Edusphere_Application_Architecture_Tasks_Testing_UX_Specification(1).pdf` (EVID-005, SHA-256 `dedc5b64…8`) | Same title, same author, same "Prepared 1 August 2026" statement, same opening content confirmed via `pdftotext`/docx-XML extraction — the PDF is a rendered export of the DOCX (or vice versa) | Different file formats produce different byte streams and different hashes by construction — never byte-identical even when content matches. Recorded as one authorial source in two formats, not as two independent corroborating sources, and not merged into a single Evidence ID. |

## Files confirmed to have no duplicate (unique SHA-256, no close relative found)

| Filename | Evidence ID |
|---|---|
| `Edusphere_Master_Backlog_RBAC_API_Test_Catalogue(1).xlsx` | EVID-006 |
| `Pasted text (2)(1).txt` | EVID-007 — **excluded from requirements** by user instruction, 2026-09-01 (see `EVIDENCE_REGISTER.md`) |
| `PSC Quotation _03(1).pdf` | EVID-009 |
| `Revised Tech stack for the proposal(1).docx` | EVID-010 |

## Net result

- 13 physical files in `docs/sources/` → **10 unique evidence items** (`EVID-001`…`EVID-010`) after
  collapsing 2 confirmed byte-identical groups.
- 0 hash mismatches between recomputed values and `SOURCE_MANIFEST.csv`.
- 2 pairs deliberately **not** collapsed despite surface similarity (logo pair, blueprint
  docx/pdf pair) — see table above.
- No duplicate-derived "extra vote" was allowed to inflate the weight of any position in the
  CRM / Employer Portal / Overseas / Agent scope conflicts described in
  `docs/evidence/VERIFIED_REVIEW_NOTES.md`.
