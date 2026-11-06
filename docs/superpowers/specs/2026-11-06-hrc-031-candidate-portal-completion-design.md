# hrc-031: Candidate portal completion -- design

**Status:** builder's design (`NEEDS_CONFIRMATION`; the owner asked for recommended answers instead of a question round). Register entry:
`DEC-SCOPE-412`. Backlog: `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` hrc-031 (`UNVERIFIED` source PDF §11, §15).

**Intent:** a signed-in external candidate or IT student can follow every §11 portal section in their own portal, reading only their own
records. **Non-goals:** new notification rules or delivery exceptions (hrc-032), a document-request notice (hrc-032), phone OTP (hrc-022 C,
waits for an SMS provider), accepting an offer from the portal, a combined candidate/student account (one user has one role, hrc-022).
**Anti-goal:** an unreleased result, another person's record or an internal stage/rejection reason reaching a portal read.

## 1. What exists and what is missing

| §11 section | Candidate shell (`/it/careers/portal`) | Student shell (`/it/student`) |
|---|---|---|
| My Profile | yes | yes |
| Recommended / All jobs | yes | yes |
| My Applications (stage, date, next action) | **missing** | stage only: **add date + next action** |
| Interviews | **missing** (notices link to a student page they cannot open) | yes |
| My Results | card on Jobs only: **add the section** | card on Job Applications only: **add the section** |
| Documents (requested + completion) | **missing** (route refuses the role) | card on Placement Status: **add the section + completion** |
| Notifications (filter by type) | **missing** | list yes; type filter hidden because recruitment notices are untyped |
| Privacy (consent, data request, contact verification) | consent + deletion: **add contact** | **missing as a section** |

## 2. Calls made (P1-P10, `NEEDS_CONFIRMATION`)

- **P1 One payload, one table.** `GET /candidate/applications` and `GET /candidate/interviews` return the same payload shape as the student
  sections, built by the same functions in `services/portal.py`, and both shells render it with `PortalSection`/`DataTable`.
- **P2 Next action** is derived, never stored, from what the candidate may already see (`candidate_status`, open interview, offer):
  an upcoming interview > an offer to review > waiting for a result > nothing to do. An unreleased decision leaves `candidate_status` at
  Interview, so it can only read "Wait for your interview result".
- **P3 Submission date** is the application's `created_at`, as an IST calendar date.
- **P4 Documents** reuse `/account/candidate-documents` (hrc-015 D8), widened to the `candidate` role, rather than a parallel `/candidate`
  copy. A candidate's own row does not need pool consent: leaving the pool keeps existing applications (hrc-022 C12), and requested
  documents belong to those. A student still needs the pool (D8 unchanged).
- **P5 Completion** is shown as "N of M requested documents received"; cancelled requests do not count.
- **P6 Offers:** `/workflows/it/student/offers` (and its letter) are widened to `candidate`, because an offer notice and next action must lead
  somewhere. The candidate sees the "My offers" card on My applications.
- **P7 Notification links** go to the page the recipient can open: a candidate's application, result and offer notices open My applications,
  interview notices open Interviews (hrc-027 J10 linked to Jobs before this page existed). Student links are unchanged.
- **P8 Type filter:** `SchoolNotificationList` gains `typeByTitle`: an untyped notice's fixed title names its type, so older notices filter too
  without a data change. Only these two portals pass it; other portals are unchanged.
- **P9 Student sections** `results`, `documents`, `privacy` are header-only portal payloads, never fee-locked, with the existing cards. Existing
  cards stay where they are (hrc-015/030 behaviour preserved).
- **P10 Contact verification** is a read-only card: email with verified/pending state, mobile (not verified until an SMS provider is chosen), and
  a link to where it is changed. The change flow itself is hrc-022's (candidate) and the student profile's.

A candidate shell page refuses any other role (403 card), including students. All reads take no person id; ids that are taken (document link,
offer letter, notification read) answer 404 for someone else's record.

## 3. API, data, security

No migration, no new RBAC key. New: `GET /candidate/applications`, `GET /candidate/interviews` (`_job_seeker`). Widened: the three
`/account/candidate-documents*` routes and the two student offer routes. Serializers stay allow-listed; fixed query count per read (no N+1).

## 4. Tests

- pytest `test_hrc_031_portal.py`: both roles for each read, next-action rules, leak check for an unreleased decision, cross-candidate 404s, staff
  403, fixed query count, consent-independent documents, notice links.
- vitest: contact card, completion, title-typed filter, nav.
- e2e `hrc-031-portal-completion.spec.ts`: every section in both shells, phone layout, wrong-role refusal.

## 5. Plan

1. Backend tests (red), then `portal.py` functions, routes, widening, notice links (green).
2. Web tests (red), then nav, candidate pages, student mounts, contact card, completion, filter (green).
3. e2e and browser QA; fixes; simplification; docs (register, API, RBAC, RTM, backlog status); merge.
