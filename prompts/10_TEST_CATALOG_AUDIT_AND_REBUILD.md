# 10 — Test Catalogue Audit and Rebuild Plan

Prerequisites:
PRD, features, UX and contracts approved.

Read the existing XLSX test catalogue in batches.
Do not load all 824 cases or 3161 steps into one context.
Do not modify the original XLSX.

Known verified fact:
all 824 existing cases are Draft.

For each old case classify:
KEEP / REWRITE / SPLIT / MERGE / RETIRE / BLOCKED

Every retained/new test must trace to:
PRD/NFR -> Feature ID -> AC -> contract/screen where relevant.

Specifically audit:
- certificate verification public-auth conflict
- public content auth conflict
- provider webhook auth semantics
- nonsensical pagination/filtering templates
- vague "where applicable"
- uncontracted ETag/idempotency
- duplicate templates
- missing BOLA/IDOR/resource-scope checks
- accessibility gaps
- integration gaps
- UAT gaps
- performance/reliability gaps
- negative/error-path gaps

Create:
- `docs/quality/TEST_STRATEGY.md`
- `docs/quality/TEST_CATALOG_AUDIT.md`
- `docs/quality/TEST_REWRITE_PLAN.md`
- `docs/quality/COVERAGE_GAPS.md`
- `docs/quality/RTM.md`
- `docs/quality/test_audit.json`

Do not use test count as quality proof.

STOP for test-strategy approval.
