# 06 — Create the Master Feature Catalogue

Prerequisite:
PRD is approved.

Read:
- approved PRD
- BRD
- Product Decision Register
- evidence/UX audit
- old backlog/screens/APIs/tests only for gap checking

NO CODE.

Create every approved product capability as a stable Feature ID.
Do not create features from old backlog/tests unless they trace to approved requirements.

Suggested prefixes may include:
FND, PUB, AUTH, USR, CRS, BAT, SES, STU, TRN, ADM, ATT, ASN, QNA,
FIN, PAY, AGR, CERT, EMP, PLC, ADMIS, OVS, AGT, VISA, DOC, NOT,
INT, RPT, AUD, SEC, OPS, MIG, SUP.

Do not use a prefix if that domain is not approved.

For each feature capture:
- Feature ID
- module
- name
- description
- primary/secondary actors
- BR IDs
- PRD IDs
- Decision IDs
- scope: CURRENT/FUTURE/BLOCKED
- priority P0/P1/P2/P3
- MoSCoW
- release
- preconditions
- main/alternate/error workflows
- Acceptance Criteria IDs
- dependencies/blockers
- UX required?
- API required?
- DB impact?
- RBAC/resource-scope?
- integration/job/file/audit impact?
- security/privacy/accessibility/responsive/performance needs
- required test types
- complexity XS/S/M/L/XL
- implementation status NOT_STARTED
- test status NOT_STARTED

Decompose large areas into independently testable vertical slices.

Generate acceptance criteria IDs:
`<FEATURE-ID>-AC##`

Generate user stories where useful:
`US-<FEATURE-ID>-##`

Create:
- `docs/features/MASTER_FEATURE_CATALOG.md`
- `docs/features/FEATURE_ACCEPTANCE_CRITERIA.md`
- `docs/features/USER_STORIES.md`
- `docs/features/FEATURE_DEPENDENCY_MAP.md`
- `docs/features/MVP_FEATURES.md`
- `docs/features/DELIVERY_SEQUENCE.md`
- `docs/features/FEATURE_TRACEABILITY.md`
- `docs/features/BACKLOG_GAP_ANALYSIS.md`
- `docs/features/FEATURE_QUESTIONS.md`
- `docs/features/feature_catalog.json`

Report:
- orphan approved requirements
- unsupported old backlog items
- features without AC
- blocked features
- first recommended features in dependency order

STOP for feature-catalog approval.
