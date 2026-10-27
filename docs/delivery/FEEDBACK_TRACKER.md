# EduSphere — Feedback Tracker for the Next Review

**What this is.** One list for the next client review. It covers every item raised in the *EduSphere Portal – Consolidated Review & Requirements* document (its 25 action items and the 43 backlog items `nehn-001` … `nehn-043` derived from it), with what is done, what is waiting, and what the client needs to supply or decide.

**Snapshot.** Status as of `origin/main` @ `1c00985f`, 26 Oct 2026. A row is **Done** only when its work is merged on the main branch. Refreshed by hand before each review. Item rows are also in `FEEDBACK_TRACKER.csv` (opens in Excel).

**Status key.**

| Status | Meaning |
|---|---|
| Done | Built and merged. |
| Done — confirm defaults | Built and merged using our recommended answers to open questions. Please confirm them (§2). |
| Superseded | Delivered by other work, named in the row. |
| Partly done | Some of the item is delivered; the row says what remains. |
| Ready to start | Nothing blocks it. |
| Waiting — dependency | Waits for another item in this list. |
| Waiting — client input | Waits for material from the client (§5). |
| Waiting — decision | Waits for a client/owner decision (§6). |

**Target** is the delivery wave from the backlog's recommended order (Wave 0 first). No calendar dates are agreed yet.

## 1. Summary

| Status | Items |
|---|---|
| Done | 2 |
| Done — confirm defaults | 11 |
| Superseded | 1 |
| Partly done | 0 |
| Ready to start | 11 |
| Waiting — dependency | 6 |
| Waiting — client input | 5 |
| Waiting — decision | 7 |
| **Total** | **43** |

## 2. Please confirm at the review

These items are built. Where a question was open, we used the recommended answer. Each can be changed if the client prefers otherwise.

| Item | Recommended answer now in place |
|---|---|
| nehn-003 Private file storage | Files stay on the current server volume, and are private unless deliberately public. Moving to cloud storage later is a configuration change. Upload limits per purpose: assignment 5 MB (PDF, Word, images), materials 20 MB, signature PNG 1 MB, university logo 1 MB (no SVG), CV 5 MB. No virus scanning yet. |
| nehn-004 Excel downloads | Every report that downloads as CSV also downloads as Excel. CSV stays. Row limits unchanged. |
| nehn-005 Permission engine | Permissions are set per role and module. Only the Super Admin edits them. No custom roles yet. The first modules on the engine are admin payments and telecaller reports; other modules follow. |
| nehn-022 Razorpay mode | The site runs in test mode until the live account is ready. A test-mode banner shows on payment screens. Still open: who performs the live ₹1 check at go-live. |
| nehn-023 Attendance corrections | The trainer is notified in-app and by instant email (no daily digest). The student is notified of the decision, with the reviewer's comment. |
| nehn-029 Live classes | Reschedule or cancel only before the class starts. The Zoho or Google Meet meeting is updated by hand for now (the trainer is reminded). Students are notified. |
| nehn-034 Country cards | A country with no universities yet shows "Coming soon" instead of being hidden. Standard flags until the client supplies country images. |
| nehn-036 Course icons | A curated set of 13 subject icons, chosen automatically from the course category, overridable per course. No upload. |
| nehn-040 Student ID | Every student, including agency students without a login, has a Student ID that admin and agency screens can search. No Agent ID, as decided on 15 Sep 2026. |
| nehn-012 Lead list export | Lead lists filter by creation date (India time) and counselor. Admins and telecaller managers download the filtered list as Excel, with contact details; telecallers and counselors do not. One row per lead. Each download is recorded and limited to 30 per 10 minutes. |
| nehn-043 This tracker | Markdown plus an Excel-compatible CSV, written for the client. |

## 3. Backlog items

| ID | Area | Item | Type | Status | Owner | Target | Client input needed |
|---|---|---|---|---|---|---|---|
| nehn-001 | Overseas | Overseas student sees offers advanced by a counselor | Bug | Done | Dev | Wave 0 · next review | — |
| nehn-002 | Certificates | Trainer certificate override always sends a reason | Bug | Done | Dev | Wave 0 | — |
| nehn-003 | Files and storage | Private file storage with per-purpose upload rules | Bug | Done — confirm defaults | Dev + Client | Wave 0 | Confirm storage location and upload limits (§2) |
| nehn-004 | Reporting | Excel download beside every CSV report; Excel import reader | Enhancement | Done — confirm defaults | Dev | Wave 1 | — |
| nehn-005 | Permissions | Permission engine (role × module × action), first two modules | Enhancement | Done — confirm defaults | Dev + Client | Wave 1 | Confirm who edits permissions; custom roles needed? (OD-04) |
| nehn-006 | Permissions | Admin permission-matrix screen and permission-driven menus | Enhancement | Done — confirm defaults | Dev + Client | Wave 2 | Per role only; non-applicable actions shown as "—" (DEC-SCOPE-295) |
| nehn-007 | Permissions | Per-user permission overrides | Enhancement | Done — confirm defaults | Dev + Client | Wave 4 | Built with reason + optional expiry; confirm OD-03 (DEC-SCOPE-299) |
| nehn-008 | Permissions | Role-based column policy for screens and downloads | Enhancement | Done — confirm defaults | Dev + Client | Wave 3 | Financial columns follow a permission (DEC-SCOPE-300); per-role column lists still wait on CI-02 |
| nehn-009 | Reporting | Report framework: standard filters, CSV/Excel, audited (DEC-SCOPE-303) | Enhancement | Done — confirm defaults | Dev + Client | Wave 3 | Export row cap (10,000) and who else reads training reports |
| nehn-010 | Reporting | Training reports: student, trainer, course, completion, attendance | Enhancement | Waiting — dependency | Dev + Client | Wave 3 | Admin report template (CI-02); needs nehn-009 |
| nehn-011 | Reporting | Admin dashboard: enrolments, progress, course-wise and fee tiles | Enhancement | Waiting — dependency | Dev + Client | Wave 3 | Tile list from the report template (CI-02); needs nehn-010 |
| nehn-012 | Internal CRM | Lead list date-range and counselor filters; filtered Excel export | Enhancement | Done — confirm defaults | Dev + Client | Wave 2 | Admins and telecaller managers export; telecallers and counselors do not (DEC-SCOPE-298) |
| nehn-013 | Internal CRM | CRM reports: lost, conversion rate, counselor-wise, date-wise, pending follow-ups (DEC-SCOPE-301) | Enhancement | Done — confirm defaults | Dev + Client | Wave 4 | Conversion-rate definition |
| nehn-014 | Internal CRM | Lead notes and counselor lead actions — delivered by counselor CRM items ccrm-002 and ccrm-003 | Enhancement | Superseded | Dev | — | — |
| nehn-015 | Internal CRM | Internal CRM workflow reconciliation | Enhancement | Waiting — client input | Dev + Client | Wave 4 | Internal CRM workflow document (CI-01) |
| nehn-016 | Placement | Nearing-completion list; recruiter read-only training progress | Enhancement | Waiting — dependency | Dev + Client | Wave 3 | Recruiters see opted-in students only, or all? (OD-08); needs nehn-010 |
| nehn-017 | HR | HR access to permitted progress, attendance and documents; HR reports | Enhancement | Waiting — dependency | Dev + Client | Wave 3 | HR population and document types (OD-09); needs nehn-008 and nehn-010 |
| nehn-018 | Student portal | Student feature access by enrolment and payment status | Enhancement | Waiting — decision | Dev + Client | Wave 4 | Payment unlock rules per feature (OD-06) |
| nehn-019 | Payments | Discount ledger and complete receipt | Enhancement | Ready to start | Dev + Client | Wave 3 | Are receipts fixed once issued? |
| nehn-020 | Payments | Retire student-facing invoices where not required | Enhancement | Waiting — decision | Client | Wave 3 | Is a GST/tax invoice legally required? (OD-11) |
| nehn-021 | Payments | Discount and scholarship authority through a finance permission | Enhancement | Waiting — decision | Dev + Client | Wave 3 | Does the Overseas Admin keep discount rights? (OD-12) |
| nehn-022 | Payments | Razorpay test/live mode switch and go-live runbook | Enhancement | Done — confirm defaults | Dev + Client | Before go-live | Razorpay live account and webhook (CI-07); who runs the live ₹1 check |
| nehn-023 | Attendance | Attendance correction usability and notifications | Enhancement | Done — confirm defaults | Dev | Wave 4 | Confirm notification channel (§2) |
| nehn-024 | Assignments | Direct file upload for assignment submissions | Enhancement | Ready to start | Dev + Client | Wave 2 | Multiple files per submission? Keep link submissions? |
| nehn-025 | Assessments | Trainer question upload from a standard Excel template | Enhancement | Ready to start | Dev | Wave 2 | — |
| nehn-026 | Assessments | Keyword-based auto-scoring for descriptive answers | Enhancement | Waiting — decision | Dev + Client | Wave 4 | Keyword scoring rule (OD-07); needs nehn-025 |
| nehn-027 | Trainer portal | Learning materials: file upload and manage | Enhancement | Ready to start | Dev + Client | Wave 4 | Video uploads, or links only? |
| nehn-028 | Trainer portal | Per-student progress view for trainers | Enhancement | Ready to start | Dev | Wave 4 | — |
| nehn-029 | Trainer portal | Live class reschedule and cancel | Enhancement | Done — confirm defaults | Dev | Wave 4 | Confirm meeting provider is updated by hand for now (§2) |
| nehn-030 | Certificates | IT Coordinator role and account model | Enhancement | Waiting — decision | Dev + Client | Wave 3 | Coordinator account model and duties (OD-05) |
| nehn-031 | Certificates | Coordinator certificate workflow: eligibility, recommend, issue, override | Enhancement | Done — confirm defaults | Dev + Client | Wave 3 | Confirm the builder defaults (DEC-SCOPE-297 W1-W9): coordinator overrides, global thresholds, recommendation optional (OD-05) |
| nehn-032 | Certificates | Certificate signatures (Founder + Coordinator) and designation | Enhancement | Done — confirm defaults | Dev + Client | Wave 3 | Upload the signature PNGs and confirm the builder defaults (DEC-SCOPE-302 S1-S9); final certificate design (CI-03) |
| nehn-033 | Overseas | Overseas student Overview / Progress page | Enhancement | Waiting — decision | Dev + Client | Wave 2 · next review | Mapping of the client's 10 stages onto the portal's stages (OD-10) |
| nehn-034 | Overseas | Country cards with flags and university count | Enhancement | Done — confirm defaults | Dev + Client | Wave 2 · next review | Custom country images, if wanted (CI-04) |
| nehn-035 | Overseas | University logo upload and richer university cards | Enhancement | Ready to start | Dev + Client | Wave 2 · next review | Logo usage and copyright guidance (CI-04) |
| nehn-036 | Overseas | Course and program icons (optional) | Enhancement | Done — confirm defaults | Dev | Wave 4 | Confirm icons are wanted this cycle (§2) |
| nehn-037 | Overseas | Counselor tools — document requests, checklist, scholarship and notes delivered by counselor CRM items ccrm-010, 013, 018, 019, 020; admission interviews built (DEC-SCOPE-296) | Enhancement | Done — confirm defaults | Dev + Client | Wave 4 | Are admission interviews needed? |
| nehn-038 | Agent portal | Agent performance dashboard: remaining KPIs | Enhancement | Waiting — client input | Dev + Client | Wave 4 | Agent KPI list and definitions (CI-06) |
| nehn-039 | School portal | School documents and statuses, application detail, bulk-upload reconfirmation | Enhancement | Waiting — client input | Dev + Client | Wave 0 · next review | School fields and visibility (CI-05); keep bulk upload? (OD-13) |
| nehn-040 | Identification | Student ID for every student, and search by it; no Agent ID | Enhancement | Done — confirm defaults | Dev + Client | Wave 3 | Confirm no Agent ID (OD-01) |
| nehn-041 | Search | Unified admin and operations student search | Enhancement | Done — confirm defaults | Dev + Client | Wave 3 | Include leads in the same search? |
| nehn-042 | Search | Audit log search and filters | Enhancement | Ready to start | Dev + Client | Wave 4 | Audit log retention period |
| nehn-043 | Process | This feedback tracker | Enhancement | Done — confirm defaults | Dev | Wave 0 · next review | Confirm format and audience (§2) |

## 4. Review action items (1–25)

| # | Action item | Owner / priority | Tracker items | Status |
|---|---|---|---|---|
| A01 | Granular role/page/action permission matrix | Dev, High | nehn-005, 006, 007 | Done — confirm defaults (engine, matrix screen, per-user overrides) |
| A02 | Excel download with filters | Dev, High | nehn-004, 009, 012 | Partly done — Excel beside every CSV report; filters and new exports to follow |
| A03 | Downloads respect role permissions | Dev, High | nehn-008 | Partly done — downloads are already limited to each role's records; per-role columns wait on CI-02 |
| A04 | Provide CRM workflow document | Client, required | CI-01 | Waiting — client input |
| A05 | Review and finalize CRM functional flow | Dev + Client | nehn-015 | Waiting — client input (CI-01) |
| A06 | Implement Internal CRM | Dev, High | nehn-012, 013, 014, 015 | Partly done — core CRM and lead notes/actions built; filters, reports and reconciliation remain |
| A07 | Configure CRM roles, statuses, assignment | Dev | nehn-015 | Waiting — client input (CI-01) |
| A08 | Direct assignment file upload | Dev, High | nehn-003, 024 | Ready to start — private storage done; upload screen next |
| A09 | Assignment text submission | Dev, High | — | Done — already in the portal |
| A10 | Trainer Excel question upload | Dev, High | nehn-004, 025 | Ready to start — Excel reader done; upload screen next |
| A11 | Founder + Coordinator signatures | Dev, High | nehn-032 | Done — PNGs to upload (CI-03) |
| A12 | Provide signature PNGs | Client, required | CI-03 | Waiting — client input |
| A13 | Coordinator certificate workflow | Dev, High | nehn-030, 031 | Waiting — decision (OD-05) |
| A14 | Overseas Student Overview / Progress | Dev, High | nehn-033, 001 | Waiting — decision (OD-10); offer fix done |
| A15 | Country icons, flags, images | Dev, High | nehn-034 | Done — confirm defaults |
| A16 | University logos, icons, images | Dev, High | nehn-035 | Ready to start — logo guidance welcome (CI-04) |
| A17 | Course/program icons | Dev, Optional | nehn-036 | Done — confirm defaults |
| A18 | School/Institution login | Dev | nehn-039 | Done — school logins in place; remaining detail in nehn-039 |
| A19 | Confirm Phase-1 bulk school upload | Client + Dev, next review | nehn-039 | Waiting — client input (CI-05, OD-13); bulk upload is already built |
| A20 | Agent Performance Dashboard | Dev, Medium | nehn-038 | Waiting — client input (CI-06) |
| A21 | Business-facing Student/Agent ID | Dev, High | nehn-040 | Done — confirm defaults (Student ID everywhere; no Agent ID, OD-01) |
| A22 | Student/agent search | Dev, High | nehn-040, 041 | Done — confirm defaults (Student ID search; unified student search, leads not included) |
| A23 | Admin report template | Client, pending | CI-02 | Waiting — client input |
| A24 | Role-specific reports | Dev, after report definition | nehn-010, 016, 017 | Waiting — dependency (CI-02, nehn-009) |
| A25 | Feedback tracker | Dev, before next review | nehn-043 | Done — confirm defaults (this document) |

## 5. Client inputs still required

| ID | Input | Blocks | Status |
|---|---|---|---|
| CI-01 | Internal CRM workflow document | nehn-015; final definitions in nehn-013 | Pending — client |
| CI-02 | Admin report template: report names, fields, filters, role access | nehn-008, 010, 011, 016, 017 | Pending — client |
| CI-03 | Founder and Coordinator signature PNGs; final certificate design | nehn-032 | Pending — client |
| CI-04 | Country images, university logos, icon style, logo copyright restrictions | nehn-034 (images), 035 | Pending — client (standard visuals in use meanwhile) |
| CI-05 | Phase-1 school functionality, bulk upload, school report fields, visibility | nehn-039 | Pending — client |
| CI-06 | Agent performance KPIs | nehn-038 | Pending — client |
| CI-07 | Razorpay live account and webhook | nehn-022 go-live | Pending — client |

## 6. Decisions still open

| ID | Decision | Item | Current state |
|---|---|---|---|
| OD-01 | Business-facing Agent ID, or Student ID only? | nehn-040 | Recommended answer in place: Student ID only (decision of 15 Sep 2026) — please confirm |
| OD-02 | Keep files on the server volume, or move to cloud storage? | nehn-003 | Recommended answer in place: server volume; cloud storage is a configuration change — please confirm |
| OD-03 | Are per-user permission overrides needed this release? | nehn-007 | Open — built on the default (DEC-SCOPE-299) |
| OD-04 | Permission unit (page or module), who edits grants, custom roles? | nehn-005 | Recommended answer in place: per module, Super Admin edits, no custom roles — please confirm |
| OD-05 | Coordinator account model and duties; who may override certificate eligibility | nehn-030, 031 | Open |
| OD-06 | Which student features unlock at which payment status | nehn-018 | Open |
| OD-07 | Keyword scoring rule for descriptive answers | nehn-026 | Open |
| OD-08 | Recruiter population: opted-in students only, or all? | nehn-016 | Open |
| OD-09 | HR population and allowed document types | nehn-017 | Open |
| OD-10 | Mapping of the client's 10 overseas stages onto the portal's stages | nehn-033 | Open |
| OD-11 | Is a GST/tax invoice legally required? | nehn-020 | Open |
| OD-12 | Does the Overseas Admin keep discount rights? | nehn-021 | Open |
| OD-13 | Bulk school upload: keep, hide or restrict? | nehn-039 | Open |

## 7. Evidence for Done rows

Merged pull requests on the main branch: nehn-001 #344 (and the counselor offer records, #307), nehn-002 #348, nehn-003 #345, nehn-004 #349, nehn-005 #347, nehn-022 #350, nehn-023 #351, nehn-029 #354, nehn-034 #353, nehn-036 #352, nehn-040 #346. nehn-014 is delivered by #302 and #305. nehn-037's delivered parts are in #304, #310, #319, #320 and #330. nehn-043 is this document.
