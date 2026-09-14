# Product / Architecture Decision Register — Template

All rows start as `UNCONFIRMED` unless explicit approval evidence is present.

Allowed statuses:
- UNCONFIRMED
- CONFIRMED_CURRENT
- CONFIRMED_FUTURE
- OUT_OF_SCOPE
- SUPERSEDED
- BLOCKED
- REJECTED

| Decision ID | Topic | Options / Conflict | Evidence | Proposed Recommendation | Decision | Status | Approved By | Approval Date |
|---|---|---|---|---|---|---|---|---|
| DEC-SCOPE-001 | Custom CRM | Older docs include CRM; later blueprint excludes it | Source audit | TBD |  | UNCONFIRMED |  |  |
| DEC-SCOPE-002 | Employer Portal | Older docs future; later blueprint current | Source audit | TBD |  | UNCONFIRMED |  |  |
| DEC-SCOPE-003 | Overseas Education | Newer transcript requirements | Transcript | TBD |  | UNCONFIRMED |  |  |
| DEC-SCOPE-004 | Agent Portal | Newer transcript; some future wording | Transcript | TBD |  | UNCONFIRMED |  |  |
| DEC-SCOPE-005 | Agent Commissions | Transcript asks view/claim commission | Transcript | TBD |  | UNCONFIRMED |  |  |
| DEC-SCOPE-006 | Visa Workflow | Transcript requirements | Transcript | TBD |  | UNCONFIRMED |  |  |
| DEC-SCOPE-007 | Internal Meeting Platform | Transcript says separate project | Transcript | Keep separate unless changed |  | UNCONFIRMED |  |  |
| DEC-ROLE-001 | Student vs Overseas Applicant identity | Not fully defined | Multiple | TBD |  | UNCONFIRMED |  |  |
| DEC-WF-001 | Overseas application state machine | Not fully normalized | Transcript | TBD |  | UNCONFIRMED |  |  |
| DEC-DATA-001 | Applicant document checklist | Examples exist, complete list absent | Transcript | TBD |  | UNCONFIRMED |  |  |
| DEC-DATA-002 | University/course data source | Manual vs provider/institution integration | Transcript | TBD |  | UNCONFIRMED |  |  |
| DEC-NOT-001 | Email/WhatsApp notification rules | Requested, providers/rules unresolved | Multiple | TBD |  | UNCONFIRMED |  |  |
| DEC-LIVE-001 | Live class provider | Zoom/Teams/other unresolved | Multiple | TBD |  | UNCONFIRMED |  |  |
| DEC-PAY-001 | Payment gateway | Provider unresolved | Multiple | TBD |  | UNCONFIRMED |  |  |
| DEC-PAY-002 | Currency/tax/invoice rules | Incomplete | Multiple | TBD |  | UNCONFIRMED |  |  |
| DEC-LMS-001 | External LMS | Need/provider/API unresolved | Multiple | TBD |  | UNCONFIRMED |  |  |
| DEC-PRIV-001 | UK GDPR retention/export/delete | Blueprint requests confirmation | Blueprint | TBD |  | UNCONFIRMED |  |  |
| DEC-TECH-001 | Application stack | Preferred Next.js/FastAPI/PostgreSQL; alternatives permitted | Tech-stack doc | TBD |  | UNCONFIRMED |  |  |
| DEC-ARCH-001 | Architecture style | Blueprint recommends modular monolith | Blueprint | TBD |  | UNCONFIRMED |  |  |
| DEC-INFRA-001 | Production cloud | Source says AWS; later discussion considered DigitalOcean | Multiple | Compare then confirm |  | UNCONFIRMED |  |  |
| DEC-ENV-001 | Dev/UAT/Prod environments | Production vs local/dev boundaries | Transcript | TBD |  | UNCONFIRMED |  |  |
| DEC-UX-001 | Canva reference authority | Reference exists but not fully inspectable | UX register | TBD |  | UNCONFIRMED |  |  |
| DEC-DATE-001 | Release/UAT date | Transcript mentions dates; feasibility not validated | Transcript | Re-baseline |  | UNCONFIRMED |  |  |
