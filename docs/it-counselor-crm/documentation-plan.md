# IT Counselor CRM User Documentation — Implementation Plan (Phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans.
> - Work one session at a time, in this plan's order; later sessions rely on data created earlier.
> - Tick the checkboxes here and update `docs/it-counselor-crm/documentation-progress.md` at the end of every session.

**Goal:** Verified end-user and administrator documentation, with role guides, for the EduSphere **IT Counselor CRM**. Screenshots are captured by Playwright from the running app.

**Scope (owner, 2026-11-18):**
- In: the IT `counselor` portal (`/it/counselor/*`, 8 sidebar items), the counselor-related IT Admin / Super Admin screens (I1), and handoff points with Telecaller, Telecaller Manager, HR and Student (HO-001..004).
- Out: Overseas counselors (see `docs/counselor-crm/`), other IT Admin screens (trainers, programmes, batches, certificates, etc.), recruitment roles (later set `docs/recruitment-crm/`).

**Architecture:**
- **Feature files.** One Markdown file per Doc ID: counselor pages in `docs/it-counselor-crm/user-manual/<module>/`, admin pages in `docs/it-counselor-crm/admin-manual/<module>/`.
- **Screenshots** in `docs/it-counselor-crm/screenshots/<module>/`, indexed in `screenshot-index.md`.
- **Source of behaviour.** Code reviewed in Phase 1 (`documentation-analysis.md`), confirmed in the browser before writing.
- **Reproducibility.** Test-only capture specs in `apps/web/tests/doc-capture/it-counselor/`.

## Global Constraints
- **Scope.** The 62 Doc IDs in analysis §3. Anything else found goes into "Discovered functionality" in the progress file.
- **Do not edit** other doc sets (`docs/counselor-crm/`, `docs/school-crm/`, `docs/bdm-crm/`, Agent CRM docs).
- **Code baseline.** `main` @ `6b61546c`. When `main` moves, re-check features whose files changed (`git diff --stat 6b61546c..<new> -- apps/`).
- **No product code changes.** Only capture tooling under `apps/web/tests/doc-capture/` and `docs/tooling/`.
- **Screenshot settings.** Viewport 1440 × 900, Chromium, light scheme, `deviceScaleFactor: 1`, locale `en-IN`, timezone `Asia/Kolkata`. Viewport shots by default; `fullPage` or `{ element }` only when needed, noted in the index. One 390 px mobile shot for NAV-001.
- **Screenshot path.** `docs/it-counselor-crm/screenshots/<module>/<NN>-<feature>-<step>.png`.
- **Never show secrets.** Mask passwords, the dev "Demo accounts" card and "Development only" boxes (`shoot()` does this). Never put a reset or welcome URL with a token in a doc or screenshot. Never paste the seed password into a file. Never screenshot Mailpit.
- **Test data only.** Personas use `*@example.test`; every lead, student, programme, batch and note created for the docs starts with `Docs `. Phones from `+91 90000 2xxxx`. No real people's data.
- **Fees (owner I3, revised 2026-11-18).** **Do not make any payments.** No payment, refund or correction is recorded and no gateway is called. Payment screens (Fees and reminders card, IT Admin Payments page, record-payment form) are screenshotted as they are, with forms left unsubmitted; steps that need a saved payment are written as text only. Fee amounts on the Docs batch are fictional INR. Razorpay online payment is described in text only.
- **Time-dependent states (owner I2).** Overdue follow-ups, escalations, overdue installments/reminders and at-risk flags are prepared by back-dating rows with SQL **on the `itcdocs` database only**, then running the job with `celery call` (`itc009-escalations`, `itc016-fee-reminders`, `itc023-at-risk`). Mark each such PNG "state prepared by data setup" in the index.
- **VERIFICATION REQUIRED.** Anything not confirmed in the browser is written as **VERIFICATION REQUIRED** and left out of the numbered steps.
- **As-built.** Document behaviour as built, including findings P1–P6 (analysis §10), in neutral wording.
- **Writing style.** Simple English, numbered steps, bold UI labels exactly as on screen, one feature per file, the mandatory template (same as `docs/counselor-crm/`).
- **Terminology.** Roles: **IT Counselor**, **IT Admin**, **Super Admin**, **Telecaller**, **Telecaller Manager**, **HR**, **Student**. Places: sidebar label first, then page title, e.g. "**Students** (page title **My Students**)".
- **Capture helpers.** Every spec calls `noPrefetch(context)`; long cards use `shoot(..., { element })`, messages `{ center }`, scrolls `behavior: "instant"`. Passwords only from `DOCS_PASSWORD` / `DOCS_TEST_PASSWORD`. IDs pass between specs through `DOCS_ITC_FILE` (JSON, scratchpad only).
- **Docker (owner).** Claude may start, seed, reset and snapshot the `itcdocs` project only (web 3060, api 8060, Mailpit 127.0.0.1:8032). Never touch other compose projects. Never load the Caddy override. Worker **and** beat must run.
- **Git.** Commit on `docs/it-counselor-crm-user-guide` as `docs: add <module> IT Counselor CRM guide`. Stage explicit paths only: `docs/it-counselor-crm/`, `apps/web/tests/doc-capture/it-counselor/`, shared tooling when changed. Never stage `graphify-out/`, `.env` or `docker-compose.docs.yml`. The owner pushes.

## Sessions
- [x] **S1 — Analysis and plan.** `documentation-analysis.md`, this plan, `documentation-progress.md`.
- [x] **S2 — Stack and tooling.** Start `itcdocs` (`docker compose -p itcdocs -f docker-compose.yml -f docker-compose.docs.yml up -d`), seed, `docs-env.sh` / `reset-stack.sh` / `restore-snap.sh` in the scratchpad. `shoot.ts`: IT portal root + `/it/login` sign-in. `build-pdfs.mjs`: `it-counselor` mode. IT Admin creates Docs IT Counselor A/B, Docs IT Telecaller, Docs programme + batch. Pages: ADM-001, ADM-002 (create/edit/re-send). Snapshot `after-s2`.
- [x] **S3 — Account access and navigation.** AUTH-001..005, NAV-001 (desktop + 390 px). Snapshot `after-s3`.
- [x] **S4 — Handoff and leads.** Telecaller creates and hands over five Docs IT leads (HO-001), Telecaller Manager changes one (HO-002). LEAD-001..006, LEAD-015, APPT-001. Snapshot `after-s4`.
- [x] **S5 — Lead activity.** LEAD-007..014 (follow-ups, calls, WhatsApp, email, meetings, counseling, return, notes/activity). Snapshot `after-s5`.
- [x] **S6 — Conversion.** CONV-001..005, ADM-006, ADM-007 (merge Deepa). Snapshot `after-s6`.
- [x] **S7 — Students.** STU-001..003, NOTE-001, TT-001, NOTIF-001, TASK-001, ADM-003, ADM-004. Snapshot `after-s7`.
- [x] **S8 — Fees, resume and HR.** FEE-001, FEE-002, ADM-008 (screens only, no submit), ADM-009, ADM-010, RES-001, RES-002, ADM-012, HO-004. Snapshot `after-s8`.
- [x] **S9 — Time states (SQL back-dating, I2).** FEE-003, STU-004, ADM-011, ADM-014, DASH-001, DASH-002, ADM-005, ADM-013, ADM-015. Snapshot `after-s9`.
- [x] **S10 — Student view and lifecycle.** HO-003, AUTH-006 (sign out, deactivated account), ADM-002 (deactivate/reactivate).
- [ ] **S11 — Guides.** `README.md`, role guides (IT Counselor, IT Admin), `demo-accounts.md`, `faq.md`, `troubleshooting.md`.
- [ ] **S12 — Review and PDFs.** Link check, every page against the template, screenshot index complete, `node docs/tooling/build-pdfs.mjs it-counselor`, `documentation-review-report.md`.

## Review Focus
1. **Same screen, different role** (analysis §5): each such page has a **What each role sees** table and one screenshot per differing role.
2. **Scope messages.** Show what an IT counselor sees for a lead or student that is not theirs (not found), without exposing other records.
3. **Provisional items.** Pages for itc-002 / itc-016 behaviour say they describe current defaults (P6).
