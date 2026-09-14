# 13 — One Feature Development Loop

Choose the next approved Feature ID from the approved delivery sequence.

Read only:
- linked PRD requirement(s)
- linked acceptance criteria
- dependencies
- relevant UX
- relevant data/API/RBAC/integration contracts
- relevant tests

Before coding report:
1. Feature ID
2. Requirement IDs
3. AC IDs
4. dependencies
5. actor/role
6. data impact
7. API impact
8. RBAC/resource scope
9. UX/screens
10. integrations/jobs/files
11. exact tests
12. unresolved blockers

If anything mandatory is unresolved: STOP.

Implement ONLY that feature.

Test escalation:
1. changed unit tests
2. module tests
3. impacted API/integration
4. impacted UI/E2E
5. responsive/accessibility/security
6. full regression only at merge/release gate

For PASS results, keep summaries compact.
For failures, inspect only relevant errors, logs, network calls, screenshots and traces.

Update RTM and feature status.

Final:
COMPLETE or NOT_COMPLETE.
