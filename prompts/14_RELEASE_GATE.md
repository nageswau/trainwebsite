# 14 — Release Gate

Audit the release candidate against approved:
- BRD
- PRD
- Product Decisions
- Feature Catalogue
- UX Catalogue
- ADRs/contracts
- Test Strategy/RTM
- Implementation Plan

Do not silently fix issues during audit.

Classify:
BLOCKER / HIGH / MEDIUM / LOW

Verify:
- required features complete
- no unapproved scope shipped
- migrations
- RBAC/resource scope
- public endpoint security
- webhook security/replay/idempotency
- file security
- privacy/GDPR
- tests
- responsive/browser
- accessibility
- performance/reliability
- secret/dependency/container scanning
- logs/metrics/traces
- backup/restore drill
- deployment/rollback
- UAT evidence
- documentation/runbooks
- change log

Finish with exactly:
READY
or
NOT READY
