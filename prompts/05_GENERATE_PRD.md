# 05 — Generate Product Requirements Document (PRD)

Prerequisite:
BRD is approved.

Read:
- approved BRD
- Product Decision Register
- evidence/UX audit
- confirmed NFR inputs

NO CODE.

Create the authoritative PRD.

For every requirement capture:
- PRD Requirement ID
- source BR ID / Decision ID
- actor
- requirement statement
- business rule
- preconditions
- main behavior
- error/edge behavior
- security/privacy requirement
- measurable acceptance direction
- scope/release status

Include:
- product vision/goals/non-goals
- personas/roles
- confirmed modules
- user journeys/state machines
- functional requirements
- NFRs
- responsive/accessibility
- performance/reliability
- security/privacy/UK GDPR
- audit
- file/document requirements
- notifications
- integrations
- finance if confirmed
- Employer if confirmed
- Overseas/Agent/Visa only if confirmed
- reporting
- migration/operations
- MVP/release
- risks/dependencies/open questions

Use IDs such as:
`PRD-AUTH-001`, `PRD-STU-001`, `NFR-SEC-001`.

Do not insert DB tables, API paths or cloud services unless they are themselves product constraints.

Create:
- `docs/product/PRD.md`
- `docs/product/PRD_OPEN_ITEMS.md`
- `docs/product/PRD_CHANGE_LOG.md`

Generate a PRD coverage check against all approved BR IDs.

STOP for PRD approval.
