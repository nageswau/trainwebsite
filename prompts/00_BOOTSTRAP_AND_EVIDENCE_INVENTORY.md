# 00 — Bootstrap and Evidence Inventory

Read `CLAUDE.md`, `docs/evidence/VERIFIED_REVIEW_NOTES.md`,
`docs/evidence/SOURCE_MANIFEST.csv`, and `docs/decisions/APPROVAL_GATES.md`.

NO CODE.

1. Verify all files under `docs/sources/`.
2. Recompute or verify SHA-256 hashes.
3. Identify exact duplicates.
4. Build an evidence register with:
   - Evidence ID
   - filename/source
   - document date if explicitly present
   - evidence type
   - topics covered
   - duplicate-of
   - authority level
   - reliability caveat
5. Do not infer chronology from filename suffixes.
6. Do not treat "approved" inside a derived file as explicit approval without evidence.

Create:
- `docs/evidence/EVIDENCE_REGISTER.md`
- `docs/evidence/DUPLICATE_ANALYSIS.md`

STOP.
