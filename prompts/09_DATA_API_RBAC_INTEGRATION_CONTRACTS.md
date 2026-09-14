# 09 — Data, API, RBAC and Integration Contracts

Prerequisite:
Architecture approved.

NO PRODUCTION CODE.

For each CURRENT Feature ID, define only necessary contracts.

Data:
- entities/relationships
- ownership
- constraints
- lifecycle/status
- indexes justified by access patterns
- audit/retention

API:
- endpoint only when needed
- method/path
- request/response schema
- auth type
- permission/resource scope
- validation/errors
- pagination only for collections that need it
- idempotency only where required
- OpenAPI ownership

RBAC:
- roles/bundles
- permissions/actions
- resource scope
- explicit deny rules
- support/admin audit controls

Integrations:
- provider abstraction
- credentials
- timeout/retry
- webhook verification/replay
- inbox/outbox/idempotency where needed
- failure/compensation
- ownership and unresolved provider choices

Create:
- `docs/architecture/DATA_MODEL.md`
- `docs/architecture/API_CONTRACT.md`
- `docs/architecture/RBAC_MATRIX.md`
- `docs/architecture/INTEGRATION_CONTRACTS.md`
- `docs/architecture/SECURITY_CONTROLS.md`

Run a traceability check back to Feature IDs and ACs.

STOP for contract approval.
