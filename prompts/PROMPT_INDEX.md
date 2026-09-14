# Prompt Index — From Scratch / No Assumptions

| # | Prompt | Purpose | Code? | Approval after? |
|---|---|---|---|---|
| 00 | BOOTSTRAP_AND_EVIDENCE_INVENTORY | inventory/hash/deduplicate evidence | No | Evidence |
| 01 | SOURCE_CONFLICT_AUDIT | find contradictions/scope deltas | No | No |
| 02 | UX_REFERENCE_AUDIT | inspect or explicitly block Canva visual claims | No | No |
| 03 | DECISION_REGISTER_AND_CLIENT_QUESTIONS | create questions, do not decide | No | Decisions |
| 04 | GENERATE_BRD | business requirements | No | BRD |
| 05 | GENERATE_PRD | product requirements/NFRs | No | PRD |
| 06 | MASTER_FEATURE_CATALOG | create Feature IDs/ACs/stories/dependencies | No | Features |
| 07 | UX_SCREEN_AND_FLOW_CATALOG | route/screen/flow catalogue | No | UX |
| 08 | ARCHITECTURE_AND_ADRS | architecture/provider decisions | No | Architecture |
| 09 | DATA_API_RBAC_INTEGRATION_CONTRACTS | detailed contracts | No | Contracts |
| 10 | TEST_CATALOG_AUDIT_AND_REBUILD | validate draft tests | No | Test strategy |
| 11 | IMPLEMENTATION_PLAN_AND_RELEASE_BACKLOG | dependency plan | No | Coding gate |
| 12 | FOUNDATION_SCAFFOLD | FND-* only | Yes | Foundation |
| 13 | FEATURE_LOOP | one approved vertical slice | Yes | Per feature |
| 14 | RELEASE_GATE | final audit | Audit | Release |

Never jump from source files directly to coding.
