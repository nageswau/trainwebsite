# pob-030 — Data controls: the share gate (design)

- **Date:** 2026-11-09. **Decision:** `DEC-SCOPE-440` (builder's calls G1–G8, `NEEDS_CONFIRMATION`). **API:** §12MG. **RBAC:** §2.330.
- **Backlog:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` pob-030 (§17 bullets 6–9; §18 AC "Permissions prevent unauthorised users
  from accessing candidate data, resumes or commercial information" and "Audit history shows who changed key records and when").
- **Dependencies (all built):** pob-001 (`DEC-SCOPE-403`), pob-011 (`427`), pob-014 (`425`), pob-018 (`428`), pob-021 (`430`); reuse of
  hrc-001 (`371`), hrc-004 (`376`), hrc-034 (`416`).

## What existed

The checks the backlog asks for already ran, but inline in `profile_sharing.create` and only at share time: requirement open, vendor
standing/agreement/NDA (pob-011), consent reference and interest (pob-021), the compensation grant (pob-001), pool membership, the
institution's placement purpose (pob-014) and the candidate's permission to be represented (pob-018). After a share, the emailed resume
link, the employer-portal download and an employer panel member's download only checked "archived".

## Design

`app/services/share_gate.py` is the single gate, with two moments:

| Moment | Function | Used by |
|---|---|---|
| share | `request()` (purpose, vendor, consent, compensation) then `people()` (pool, institution placement, permission) | `profile_sharing.create` → `POST /recruiter/shares` (client, vendor, portal) |
| delivery | `deliverable()` / `deliverable_ids()` (batched) | `GET /public/shared-resume/{token}`, `GET /employer/shared-profiles/{id}/resume`, `GET /interviewer/interviews/{id}/resume` (employer members), and each of those lists' `has_resume` |

`share_gate.OUTWARD` is the route inventory (AC1): every route that can carry candidate data out of the team, classified `share`,
`delivery`, `record` or `internal`. `tests/test_pob_030_share_gate.py` finds the routes by path shape in the OpenAPI document and fails when
one is unclassified, when an entry names a missing route, or when a `share`/`delivery` route stops calling the gate.

## Builder's calls (`NEEDS_CONFIRMATION`)

- **G1** One module with two moments rather than one `check()`: the share path and the delivery path need different facts (a payload vs a
  stored share).
- **G2** The share path keeps its existing status codes and messages (409 consent/vendor/closed requirement, 422 pool/permission/purpose,
  403 compensation). The backlog's "409 with reasons" is not applied as a new shape: the share dialog and the e2e suites already show
  these messages inline, and changing codes would break the rec-019/pob-011/014/018/021 contracts for no user gain.
- **G3** "Institution share" in the backlog maps to the pob-014 institution-student path inside `POST /recruiter/shares` (the placement
  purpose and the sharer on an active permission). pob-015's vacancy shares to a college carry no candidate data and are not gated.
- **G4** A permission withdrawn (pob-018 `outreach_status` no longer `consented`), an institution permission revoked/expired/without
  placement, or an archived/anonymised candidate blocks every *future* delivery of an earlier share: the link and portal download answer
  their existing 404, and `has_resume` turns false so no dead link is offered. The share rows, items and `profile_share.create` audit rows
  remain (past shares stay logged).
- **G5** `record` routes (the employer's list of its shared profiles and its response, the panel member's interview list) keep showing the
  summary of a share already made to that party; only the resume file is gated.
- **G6** Exports (`POST /recruiter/candidates/search/export`) and the staff resume download/link are `internal`: staff inside the
  system, gated by `candidates.export` / the pool reader scope and the pob-001 compensation grant, and audited (hrc-015/hrc-020). They are
  not a share to a third party, so consent is not required there.
- **G7** An internal panel interviewer (staff) keeps the resume after a withdrawal; an employer panel member does not.
- **G8** "Communications are covered by the hrc-004 diff audit" and "failed sends and imports appear on the hrc-034 data-quality page"
  are already true (`recruiter_messages` audit per message; data-quality `failed_imports` and `failed_notifications`, which include
  recruiter share emails). Nothing new is built for them.

## Not built

A "409 with a reasons list" response shape (G2); gating the `record` summaries (G5); consent for internal exports (G6).

## Tests

`tests/test_pob_030_share_gate.py`: the route inventory (AC1); no consent → 409 and no permission → 422 on every share channel and on the
vendor route, a vendor without NDA → 409 (AC2); a withdrawal after a submission blocks the next share, the link, the portal download and
an employer panel member's download, with `has_resume` false and the past share still logged (+/−/E); a permitted candidate still
downloads; `deliverable()` follows the institution permission.
