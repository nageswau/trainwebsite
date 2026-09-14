# Deployment Decision Guide — Do Not Preselect

Source evidence includes an AWS preference/meeting statement and later AWS ECS Fargate architecture
recommendation. A later product discussion also considered DigitalOcean.

This package does not choose one automatically.

## Decision criteria
Compare:
- actual peak concurrent users / RPS
- UK data-residency/compliance needs
- HA/SLA requirement
- operational skill/team size
- managed PostgreSQL/Redis/Valkey
- object-storage bandwidth
- workers/schedulers
- observability/security requirements
- expected monthly traffic
- cost including networking/load balancers/NAT/logs
- portability
- client contractual cloud preference

## DigitalOcean
Strong when simplicity, predictable cost and low DevOps overhead dominate.

## AWS ECS Fargate
Strong when enterprise security controls, HA depth, ecosystem and very high-scale evolution dominate.

Do not use registered-user count alone as sizing evidence.

Final choice must be written to `DEC-INFRA-001`.
