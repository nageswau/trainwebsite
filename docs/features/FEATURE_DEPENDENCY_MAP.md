# Feature Dependency Map

Edges below are `depends_on` relationships captured per-feature in `MASTER_FEATURE_CATALOG.md`. A feature cannot start before every feature in its dependency list is at least in progress, and should not be considered complete before they are done.

| Feature | Depends on |
|---|---|
| `FND-001` Reference-implementation extension baseline | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `FND-002` Division-aware RBAC & identity framework | `FND-001` |
| `AUTH-001` Division-aware authenticated login | `FND-002` |
| `AUTH-002` Role-based access control enforcement (UI) | `AUTH-001`, `FND-002` |
| `AUTH-003` Google OAuth login | `AUTH-001` |
| `PUB-001` Corporate & IT marketing content | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `PUB-002` Enquiry submission synced to CRM | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `PUB-003` Course catalogue and detail | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `PUB-004` Webinar listing and registration | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `PUB-005` News and gallery (CMS-managed) | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `PUB-010` Site search, FAQ, and legal pages | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `STU-001` Trainer/batch slot enrolment | `FND-002`, `PUB-003` |
| `STU-002` Student dashboard | `STU-001` |
| `STU-003` Live class access | `TRN-003` |
| `STU-004` Assignment submission | `TRN-005` *(corrected `prompts/13`, 2026-09-01 — was TRN-006, which is Assessment not Assignment)* |
| `STU-005` Support ticket | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `STU-006` Attendance and progress view | `TRN-008` |
| `STU-007` Certificate download | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `STU-008` Feedback submission | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `STU-009` Digital agreement / consent | `STU-001` |
| `STU-010` Fee payment, EMI, invoices, receipts | `STU-001` |
| `STU-011` Profile and document management | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `TRN-001` My Batches | `ADM-003` |
| `TRN-002` Batch detail (roster and schedule) | `TRN-001`, `STU-001` |
| `TRN-003` Upcoming sessions and live-class join | `TRN-001` |
| `TRN-004` Recording list and resource upload | `TRN-002` |
| `TRN-005` Assignment create and edit | `TRN-002` |
| `TRN-006` Assessment create and edit | `TRN-002` |
| `TRN-007` Submission review and grading | `STU-004` |
| `TRN-008` Attendance marking | `TRN-002` |
| `TRN-009` Q&A response | `TRN-002` |
| `ADM-001` User/course/batch administration | `FND-002` |
| `ADM-002` CRM-linked enquiry/lead management | `PUB-002` |
| `ADM-003` Batch creation and trainer assignment | `ADM-001` |
| `ADM-004` Directory management: Students, Trainers, Employers | `ADM-001` |
| `ADM-005` Enrolment review and approval | `ADM-002` |
| `ADM-006` Certificate administration | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `ADM-007` Placement Team workspace | `FND-002` |
| `ADM-008` HR Team workspace | `FND-002` |
| `ADM-009` Resources/recordings oversight | `TRN-004` |
| `ADM-010` Agreement/consent oversight | `STU-009` |
| `ADM-011` Notification template management | `NOT-001`, `NOT-002`, `NOT-003` |
| `ADM-012` Roles/permission administration | `FND-002` |
| `ADM-013` Operational-tooling cluster | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `ADM-014` Super Admin cross-division console | `FND-002` |
| `EMP-001` Employer registration | `FND-002` |
| `EMP-002` Job posting | `EMP-001` |
| `EMP-003` Candidate profile search | `EMP-001`, `STU-011` |
| `EMP-004` Interview scheduling and shortlist | `EMP-003` |
| `EMP-005` Interview list and status | `EMP-004` |
| `EMP-006` Placement status tracking | `EMP-004` |
| `OVS-001` Destination/university/course discovery | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `OVS-002` Overseas application submission | `OVS-001`, `AUTH-001` |
| `OVS-003` Eligibility evaluation | `OVS-002` |
| `OVS-004` Application status tracking and notifications | `OVS-002`, `NOT-001`, `NOT-002` |
| `OVS-005` Document upload against checklist | `OVS-002` |
| `OVS-006` Scholarship listing and application | `OVS-001` |
| `OVS-007` Events and workshops | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `VISA-001` Visa checklist and documentation | `OVS-005` |
| `VISA-002` Visa interview preparation | `VISA-001` |
| `VISA-003` Visa approval status tracking | `VISA-001` |
| `AGT-001` Agent self-registration and approval gate | `FND-002` |
| `AGT-002` Referred-student roster and status | `AGT-001`, `OVS-002` |
| `AGT-003` Commission accrual (automatic trigger) | `AGT-002`, `OVS-004` |
| `AGT-004` Commission payout request and approval | `AGT-003` |
| `CNS-001` Counselor workspace | `FND-002` |
| `UNI-001` University Representative portal | `FND-002` |
| `NOT-001` Email notifications | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `NOT-002` WhatsApp notifications (Twilio) | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `NOT-003` SMS notifications | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `PAY-001` Payment gateway integration | `FND-001` |
| `LMS-001` Native LMS module extensions | `STU-004`, `TRN-005`, `TRN-006` |
| `RPT-001` Domestic/Employer reporting | `ADM-005`, `ADM-007` |
| `RPT-002` Overseas reporting | `OVS-004`, `AGT-003` |
| `SEC-001` Approval-gate audit trail | `AGT-001`, `AGT-004` |
| `SEC-002` GDPR consent capture and self-service export/delete | — (no dependency; can start immediately once FND/AUTH baseline exists) |
| `OPS-001` DigitalOcean deployment | `FND-001` |
| `OPS-002` Database migration execution and seed-data decision | `OPS-001` |

## Root features (no dependencies — earliest possible start)

- `FND-001` — Reference-implementation extension baseline (CURRENT)
- `PUB-001` — Corporate & IT marketing content (CURRENT)
- `PUB-002` — Enquiry submission synced to CRM (CURRENT)
- `PUB-003` — Course catalogue and detail (CURRENT)
- `PUB-004` — Webinar listing and registration (CURRENT)
- `PUB-005` — News and gallery (CMS-managed) (CURRENT)
- `PUB-010` — Site search, FAQ, and legal pages (BLOCKED)
- `STU-005` — Support ticket (CURRENT)
- `STU-007` — Certificate download (CURRENT)
- `STU-008` — Feedback submission (CURRENT)
- `STU-011` — Profile and document management (CURRENT)
- `ADM-006` — Certificate administration (CURRENT)
- `ADM-013` — Operational-tooling cluster (BLOCKED)
- `OVS-001` — Destination/university/course discovery (CURRENT)
- `OVS-007` — Events and workshops (CURRENT)
- `NOT-001` — Email notifications (CURRENT)
- `NOT-002` — WhatsApp notifications (Twilio) (CURRENT)
- `NOT-003` — SMS notifications (CURRENT)
- `SEC-002` — GDPR consent capture and self-service export/delete (CURRENT)

## Longest dependency chains (illustrative, not exhaustive)

- `FND-001` → `FND-002` → `AUTH-001` → `AUTH-002` → `STU-001` → `STU-009` → `STU-010` (enrolment through payment)
- `ADM-003` → `TRN-001` → `TRN-002` → `TRN-005`/`TRN-006` → `STU-004` → `TRN-007` (batch through grading)
- `FND-002` → `OVS-001` → `OVS-002` → `OVS-003` → `OVS-004`/`OVS-005` → `VISA-001` → `VISA-003` (Overseas application through visa)
- `FND-002` → `AGT-001` → `AGT-002` → `OVS-004` → `AGT-003` → `AGT-004` (agent referral through commission payout)