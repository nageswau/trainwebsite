# Feature Traceability Matrix

Full chain: Evidence → Decision → BRD (BR ID) → PRD ID → Feature ID, per `CLAUDE.md`'s required traceability. Base-codebase-inherited features (`[base]`) trace to `DEC-ARCH-001` (the decision to extend the reference implementation) and `docs/evidence/REFERENCE_IMPLEMENTATION_FINDINGS.md` in place of an independent PRD ID — flagged as a PRD-backfill gap in `FEATURE_QUESTIONS.md`.

| Feature ID | BR ID(s) | PRD ID(s) | Decision ID(s) | Traceable? |
|---|---|---|---|---|
| `FND-001` | — | — | DEC-ARCH-001, DEC-TECH-001 | Yes |
| `FND-002` | — | PRD-AUTH-002, NFR-SEC-001 | DEC-ARCH-001 | Yes |
| `AUTH-001` | — | PRD-AUTH-001 | DEC-ROLE-001 | Yes |
| `AUTH-002` | — | PRD-AUTH-002 | — | Yes |
| `AUTH-003` | — | PRD-AUTH-003 | — | Yes |
| `PUB-001` | BR-PUB-001 | PRD-PUB-001, PRD-PUB-004, PRD-PUB-005, PRD-PUB-006, PRD-PUB-007, PRD-PUB-008, NFR-RESP-001 | — | Yes |
| `PUB-002` | BR-PUB-001 | PRD-PUB-002 | DEC-SCOPE-001 | Yes |
| `PUB-003` | BR-PUB-001 | PRD-PUB-003 | — | Yes |
| `PUB-004` | BR-PUB-001 | PRD-PUB-009 | — | Yes |
| `PUB-005` | — | — | DEC-ARCH-001 | Partial — [base] role action, no independent PRD ID (see note above) |
| `PUB-010` | — | PRD-PUB-010 | — | Yes |
| `STU-001` | BR-STU-001 | PRD-STU-001 | DEC-WF-002 | Yes |
| `STU-002` | — | PRD-STU-002 | — | Yes |
| `STU-003` | BR-LIVE-001 | PRD-STU-003 | DEC-LIVE-001 | Yes |
| `STU-004` | — | PRD-STU-004 | — | Yes |
| `STU-005` | — | PRD-STU-005 | — | Yes |
| `STU-006` | — | PRD-STU-006, PRD-STU-007 | — | Yes |
| `STU-007` | — | PRD-STU-008 | — | Yes |
| `STU-008` | — | PRD-STU-009 | — | Yes |
| `STU-009` | — | PRD-STU-010 | DEC-PRIV-001 | Yes |
| `STU-010` | BR-PAY-001 | PRD-STU-011, PRD-PAY-001, PRD-PAY-002, PRD-PAY-003 | DEC-PAY-001, DEC-PAY-002 | Yes |
| `STU-011` | — | PRD-STU-012 | — | Yes |
| `TRN-001` | — | PRD-TRN-001 | DEC-ROLE-002 | Yes |
| `TRN-002` | — | PRD-TRN-002 | DEC-WF-002 | Yes |
| `TRN-003` | — | PRD-TRN-003 | DEC-LIVE-001 | Yes |
| `TRN-004` | — | PRD-TRN-004, PRD-TRN-005 | DEC-LIVE-001 | Yes |
| `TRN-005` | — | PRD-TRN-006 | DEC-ROLE-002 | Yes |
| `TRN-006` | — | PRD-TRN-007 | — | Yes |
| `TRN-007` | — | PRD-TRN-008 | — | Yes |
| `TRN-008` | — | PRD-TRN-009 | — | Yes |
| `TRN-009` | — | PRD-TRN-010 | — | Yes |
| `ADM-001` | BR-ADM-001 | PRD-ADM-001 | DEC-SCOPE-001 | Yes |
| `ADM-002` | BR-ADM-001 | PRD-ADM-002 | DEC-SCOPE-001 | Yes |
| `ADM-003` | — | PRD-ADM-003 | DEC-WF-002 | Yes |
| `ADM-004` | — | PRD-ADM-006 | — | Yes |
| `ADM-005` | — | PRD-ADM-007 | — | Yes |
| `ADM-006` | — | PRD-ADM-009 | — | Yes |
| `ADM-007` | — | — | DEC-ARCH-001 | Partial — [base] role action, no independent PRD ID (see note above) |
| `ADM-008` | — | — | DEC-ARCH-001 | Partial — [base] role action, no independent PRD ID (see note above) |
| `ADM-009` | — | PRD-ADM-008 | — | Yes |
| `ADM-010` | — | PRD-ADM-010 | — | Yes |
| `ADM-011` | — | PRD-ADM-011 | DEC-NOT-001 | Yes |
| `ADM-012` | — | PRD-ADM-013 | — | Yes |
| `ADM-013` | — | PRD-ADM-012 | — | Yes |
| `ADM-014` | — | — | DEC-ARCH-001 | Partial — [base] role action, no independent PRD ID (see note above) |
| `EMP-001` | BR-EMP-001 | PRD-EMP-001 | DEC-SCOPE-002 | Yes |
| `EMP-002` | BR-EMP-001 | PRD-EMP-002 | DEC-SCOPE-002 | Yes |
| `EMP-003` | BR-EMP-001 | PRD-EMP-003 | DEC-SCOPE-002, DEC-PRIV-001 | Yes |
| `EMP-004` | BR-EMP-001 | PRD-EMP-004, PRD-EMP-005 | DEC-SCOPE-002 | Yes |
| `EMP-005` | — | PRD-EMP-006 | — | Yes |
| `EMP-006` | — | PRD-EMP-007 | — | Yes |
| `OVS-001` | BR-OVS-001 | PRD-OVS-001 | DEC-SCOPE-003, DEC-DATA-002 | Yes |
| `OVS-002` | BR-OVS-001 | PRD-OVS-002 | DEC-SCOPE-003, DEC-ROLE-001 | Yes |
| `OVS-003` | BR-OVS-001 | PRD-OVS-003 | DEC-WF-001 | Yes |
| `OVS-004` | BR-OVS-001 | PRD-OVS-004 | DEC-WF-001, DEC-NOT-001 | Yes |
| `OVS-005` | BR-OVS-001 | PRD-OVS-005 | DEC-DATA-001 | Yes |
| `OVS-006` | BR-OVS-001 | PRD-OVS-006 | DEC-SCOPE-003 | Yes |
| `OVS-007` | BR-OVS-001 | PRD-OVS-007 | DEC-SCOPE-003 | Yes |
| `VISA-001` | BR-VISA-001 | PRD-VISA-001 | DEC-SCOPE-006 | Yes |
| `VISA-002` | BR-VISA-001 | PRD-VISA-002 | DEC-SCOPE-006 | Yes |
| `VISA-003` | BR-VISA-001 | PRD-VISA-003 | DEC-SCOPE-006 | Yes |
| `AGT-001` | BR-AGT-001 | PRD-AGT-001, PRD-ADM-004, NFR-SEC-002 | DEC-SCOPE-004 | Yes |
| `AGT-002` | BR-AGT-001 | PRD-AGT-002 | DEC-SCOPE-004 | Yes |
| `AGT-003` | BR-AGT-002 | PRD-AGT-003 | DEC-SCOPE-005 | Yes |
| `AGT-004` | BR-AGT-002 | PRD-AGT-004, PRD-ADM-005, NFR-SEC-002 | DEC-SCOPE-005 | Yes |
| `CNS-001` | — | — | DEC-ARCH-001 | Partial — [base] role action, no independent PRD ID (see note above) |
| `UNI-001` | — | — | DEC-ARCH-001 | Partial — [base] role action, no independent PRD ID (see note above) |
| `NOT-001` | BR-NOT-001 | PRD-NOT-001 | DEC-NOT-001 | Yes |
| `NOT-002` | BR-NOT-001 | PRD-NOT-002 | DEC-NOT-001 | Yes |
| `NOT-003` | — | PRD-NOT-003 | DEC-NOT-001 | Yes |
| `PAY-001` | BR-PAY-001 | PRD-PAY-001 | DEC-PAY-001 | Yes |
| `LMS-001` | — | PRD-LMS-001 | DEC-LMS-001 | Yes |
| `RPT-001` | — | PRD-RPT-001 | — | Yes |
| `RPT-002` | — | PRD-RPT-002 | — | Yes |
| `SEC-001` | — | NFR-AUDIT-001 | DEC-SCOPE-004, DEC-SCOPE-005 | Yes |
| `SEC-002` | BR-PRIV-001 | NFR-PRIV-001 | DEC-PRIV-001 | Yes |
| `OPS-001` | — | — | DEC-INFRA-001 | Yes |
| `OPS-002` | — | — | DEC-ARCH-001, DEC-INFRA-001 | Yes |
| `SCH-001` | BR-SCH-001 | PRD-SCH-001, PRD-SCH-002, PRD-SCH-004, PRD-SCH-005, PRD-SCH-006 | DEC-SCOPE-009, DEC-SCOPE-011, DEC-ROLE-005 | Yes |
| `SCH-002` | BR-SCH-002 | PRD-SCH-003 | DEC-SCOPE-010, DEC-SCOPE-011 | Yes |
| `SCH-003` | BR-SCH-003 | PRD-SCH-007 | DEC-SCOPE-012 | Yes |
| `SCH-004` | BR-SCH-005 | PRD-SCH-009 | DEC-ROLE-006 | Yes |
| `SCH-005` | BR-SCH-006 | PRD-SCH-010 | DEC-ROLE-006 | Yes |
| `SCH-006` | BR-SCH-004 | PRD-SCH-008 | DEC-SCOPE-010, DEC-ROLE-006 | Yes |
| `SCH-007` | BR-SCH-007 | PRD-SCH-011 | DEC-SCOPE-011, DEC-ROLE-006, DEC-SCOPE-015, DEC-NOT-001 | Yes |
| `SCH-008` | BR-SCH-008 | PRD-SCH-012 | DEC-SCOPE-011, DEC-SCOPE-015, DEC-SCOPE-016 | Yes |

## Orphan check

**None.** Every feature traces to at least one BR ID, PRD ID, or Decision ID.

## Approved BR ID coverage (from `docs/product/BRD.md` §19)

| BR ID | Covered by Feature(s) |
|---|---|
| `BR-PUB-001` | `PUB-001`, `PUB-002`, `PUB-003`, `PUB-004` |
| `BR-STU-001` | `STU-001` |
| `BR-ADM-001` | `ADM-001`, `ADM-002` |
| `BR-EMP-001` | `EMP-001`, `EMP-002`, `EMP-003`, `EMP-004` |
| `BR-OVS-001` | `OVS-001`, `OVS-002`, `OVS-003`, `OVS-004`, `OVS-005`, `OVS-006`, `OVS-007` |
| `BR-VISA-001` | `VISA-001`, `VISA-002`, `VISA-003` |
| `BR-AGT-001` | `AGT-001`, `AGT-002` |
| `BR-AGT-002` | `AGT-003`, `AGT-004` |
| `BR-LIVE-001` | `STU-003` |
| `BR-PAY-001` | `STU-010`, `PAY-001` |
| `BR-NOT-001` | `NOT-001`, `NOT-002` |
| `BR-PRIV-001` | `SEC-002` |
| `BR-SCH-001` | `SCH-001` |
| `BR-SCH-002` | `SCH-002` |
| `BR-SCH-003` | `SCH-003` |
| `BR-SCH-004` | `SCH-006` |
| `BR-SCH-005` | `SCH-004` |
| `BR-SCH-006` | `SCH-005` |

## PRD/NFR requirement coverage check

Every `#### PRD-*`/`#### NFR-*` heading in `docs/product/PRD.md` was extracted and diffed against every feature's `prd` citation list. Result: **86 requirement headings, 86 covered** after two rounds of fixes (initial generation missed `PRD-ADM-004`, `PRD-ADM-005`, and 6 NFR IDs — added to `AGT-001`, `AGT-004`, `FND-002`, `SEC-001`, `SEC-002`, `PUB-001` where each genuinely belongs, not force-fit elsewhere).

**Deliberately left without a dedicated feature** (correct, not a gap):

- `NFR-PERF-001` (response-time target) and `NFR-SCALE-001` (10,000+ user scalability) — both `PROPOSED`/unconfirmed in the PRD itself. Cross-cutting technical targets, not a discrete feature; do not build against them as if confirmed. Revisit once confirmed.
- `NFR-REL-001` (uptime/availability) — genuinely no target exists in any evidence; nothing to trace to.
- `NFR-RESP-001` (responsive design) — `CONFIRMED_CURRENT` and cross-cutting (nearly every feature's own "Accessibility/responsive" field in `MASTER_FEATURE_CATALOG.md` says "Responsive"). Cited once, on `PUB-001`, as the traceability anchor rather than duplicated across all 68 `CURRENT` features.