# EduSphere — Claude Code Constitution (NO-ASSUMPTION MODE)

## Prime directive
You are starting this project from scratch. Do not treat any derived backlog, blueprint, quotation,
transcript statement, Canva design, test case, architecture recommendation, or prior AI-generated
document as final truth unless its authority is explicitly established.

When evidence is incomplete, say `NEEDS_CONFIRMATION`. Do not guess.

## Evidence classifications
Use these labels:
- ORIGINAL_REQUIREMENT
- COMMERCIAL_QUOTATION
- TECH_STACK_PREFERENCE
- MEETING_TRANSCRIPT_REQUEST
- DERIVED_BLUEPRINT
- DERIVED_WORKBOOK
- UX_REFERENCE
- EXPLICIT_APPROVAL
- SUPERSEDED
- UNVERIFIED

A source's own use of words such as "approved" is not automatically `EXPLICIT_APPROVAL`.
Require an actual approval record/user/client confirmation.

## Source immutability
`docs/sources/` is evidence. Never modify those files.

## Duplicate handling
Use `docs/evidence/SOURCE_MANIFEST.csv`.
Byte-identical duplicates count as one evidence item, not multiple independent votes.

## UX URL
Reference:
https://vnsitcareer.my.canva.site

Known connected design:
DAHRWCa0RLw — OneCampus ERP — Customer-Friendly Responsive UX

Do not infer product features from this URL.
If you can access/render it, create a documented UX audit with evidence.
If you cannot, state that clearly and require inspectable screenshots/PDF/HTML before claiming visual fidelity.

## Approval gates
Read `docs/decisions/APPROVAL_GATES.md`.
Do not bypass gates.

## Required traceability
Evidence -> Decision -> BRD -> PRD Requirement -> Feature ID -> Acceptance Criteria ->
UX/Screen -> Architecture/DB/API/RBAC/Integration -> Test -> Code -> Release Evidence.

## Scope
Do not assume:
- CRM included or excluded,
- Employer current or future,
- Overseas current or future,
- Agent Portal current or future,
- agent commissions current,
- visa current,
- internal meeting platform included,
- provider selections.

Resolve them through Decision IDs.

## Technology
The source material proposes Next.js/TypeScript + FastAPI + PostgreSQL + AWS, and a later blueprint
recommends a modular monolith/ECS Fargate. These are evidence-backed proposals, not automatic final
decisions.

Do not generate provider-specific production infrastructure until `DEC-TECH-001`,
`DEC-ARCH-001`, and `DEC-INFRA-001` are confirmed.

## Testing
The workbook contains 824 tests, all marked Draft.
Treat them as input to an audit, not authority.

Never alter product behavior merely to make a draft test pass.

Audit specifically for:
- public endpoints wrongly requiring authentication,
- webhooks using wrong authentication semantics,
- pagination/filtering tests on non-list endpoints,
- vague "where applicable" assertions,
- uncontracted idempotency/ETag assumptions,
- missing resource-scope/security/accessibility/integration/UAT cases.

## Coding
No business code before the coding gate.
Foundation code only after stack/architecture/contracts are approved.

Implement one approved Feature ID at a time.

## Token-efficient operation
- never dump all 824 tests/3161 steps into context
- query/filter small ranges
- use local scripts for deterministic tests
- inspect compact summaries first
- open detailed logs/screenshots/traces only for failures
- use fresh sessions for major phases
- do not delete `.claude-cache` routinely

## Completion
A feature is COMPLETE only when its applicable acceptance, security, RBAC/resource scope,
test, build, migration, responsive, accessibility and documentation gates pass.
