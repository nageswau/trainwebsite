# 08 — Architecture and ADRs

Prerequisites:
- PRD approved
- Feature catalogue approved
- UX catalogue approved or explicitly deferred
- DEC-TECH-001, DEC-ARCH-001, DEC-INFRA-001 handled

NO CODE.

Do not assume a provider or stack.

Use source evidence:
- preferred Next.js/TypeScript + FastAPI + PostgreSQL stack
- AWS EC2+RDS preference
- blueprint modular-monolith/ECS Fargate recommendation
- transcript production-AWS statement
- later DigitalOcean discussion only as an option unless explicitly approved

If a technical decision remains unconfirmed:
- compare options,
- recommend with cost/scale/maintenance/security rationale,
- STOP provider-specific design at that boundary.

Create:
- system context
- architecture style
- domain/module boundaries
- deployment topology
- storage/cache/jobs
- auth/session approach
- file delivery
- observability
- backup/restore
- portability strategy
- scaling strategy based on concurrency/RPS, not registered users
- threat model outline
- ADRs with status PROPOSED/APPROVED/REJECTED

Create:
- `docs/architecture/ARCHITECTURE.md`
- `docs/architecture/ADRS.md`
- `docs/architecture/DEPLOYMENT.md`
- `docs/architecture/SCALING.md`
- `docs/architecture/THREAT_MODEL.md`

STOP for architecture approval.
