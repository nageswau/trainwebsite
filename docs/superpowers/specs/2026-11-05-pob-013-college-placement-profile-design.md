# pob-013 — College/TPO placement profile on the BDM organisation (design)

- **Feature:** `pob-013` (`docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md`), decision `DEC-SCOPE-410`.
- **Source:** backlog §6.1 institution profile, TPO contacts, placement profile, status; §6.2 research/identify; §18 AC "Placement
  Officer can create and track TPO records for colleges and universities". Source classified `UNVERIFIED`.
- **Authority:** the owner assigned pob-013 on 2026-11-05 and said to proceed with the recommended answers, so P1–P14 below are
  **the builder's calls (`NEEDS_CONFIRMATION`)** answering Q-10. Dependency pob-001 (`DEC-SCOPE-403`) is merged.

## Intent

A placement officer (recruiter, `placement_team`) works with college Training & Placement Officers (TPOs). Today the college lives in
the BDM CRM (`BdmOrganization`, bdm_type `college`) and a recruiter cannot open it. pob-013 lets the placement side read those colleges
and keep a **placement profile** on them (courses, graduating batches, a placement calendar, the drive process and eligibility rules,
TPO office details and preferred contact method, and a log of TPO interactions), while the BDM keeps owning the record, the MoU and every
commercial field.

## Goals / non-goals

- Goals: AC1 a PO views a college, adds a batch and a calendar entry, and logs a TPO meeting. AC2 a PO cannot edit the BDM-owned
  commercial/MoU fields. AC3 search by course (also by graduating year and location).
- Non-goals: a new institution master; student data (pob-014); vacancy sharing and campus outcomes (pob-015); changing any BDM route.
- Anti-goals: widening `services.bdm_organizations.caller_scope` (it gates MoUs, appointments, activities, metrics, tasks…); a PO write
  that bumps the BDM organisation's `updated_at` or appears in BDM metrics.

## Builder's calls (`NEEDS_CONFIRMATION`)

- **P1 Extend, don't duplicate.** Side tables keyed by `bdm_organizations.id`; the organisation row itself is never written by pob-013.
- **P2 Which organisations.** `bdm_type = 'college'` and `org_type IN ('college','university')`. A university in the Agent module (an
  overseas UPC partner) is not a placement institution (backlog edge case: keep separate).
- **P3 Readers.** `placement_team` (with a recruiter profile) and `placement_manager`: every such organisation that is not archived.
  `bdm` / `bdm_manager`: their existing bdm-002 scope (archived included, read-only). `super_admin`: all. Others 403; out of scope 404.
- **P4 Writers.** `placement_team`, `super_admin` and the organisation's assigned BDM (bdm-002 `can_edit`). `placement_manager` and
  `bdm_manager` read only (the recruiter-manager convention, e.g. drives). Archived = 409 "Restore this organization first".
- **P5 Placement profile.** One row per organisation: drive process and eligibility rules (≤ 2000 chars each, multi-line). PUT replaces.
- **P6 Courses.** Structured department (optional) + course (required), ≤ 120 chars each, unique per organisation case-insensitively
  (409), ≤ 100 per organisation. The bdm-003 free-text `courses` stays and is shown as "Courses (BDM notes)".
- **P7 Batches.** Pass-out year (2000–2100, required), optional course (one of the organisation's), pass-out date (its year must equal
  the pass-out year), student count (0–100,000), notes ≤ 500. ≤ 200 per organisation. A course used by a batch cannot be deleted (409).
- **P8 Calendar.** Title ≤ 200, kind (`pre_placement_talk`, `campus_drive`, `assessment`, `interview`, `exam`, `holiday`, `other`),
  start date, optional end date ≥ start, notes ≤ 500. ≤ 500 per organisation. Delete allowed (no history).
- **P9 TPO interactions.** Append-only: channel (`meeting`, `call`, `email`, `whatsapp`, `visit`, `other`), occurred at (not more than
  5 min in the future), optional contact (one of the organisation's; its name is snapshotted, kept if the BDM deletes the contact),
  summary (required, ≤ 2000), next step ≤ 500, the author. Separate from `bdm_activities`, so BDM metrics and daily reports are unchanged.
  The detail lists the latest 50 with the total.
- **P10 TPO contact details.** Two nullable columns on `bdm_organization_contacts`: `office_details` (≤ 300) and
  `preferred_contact_method` (`email`, `phone`, `whatsapp`, `in_person`, `linkedin`). Writers set them through the placement route;
  the BDM contact routes and their output are unchanged.
- **P11 Search.** `q` (name/code), `city` (city or state), `course` (structured course/department or the BDM `courses` text),
  `pass_out_year` (has such a batch); ANDed, case-insensitive literal substrings, paged `{items,total,limit,offset}`, ordered by name, id.
- **P12 Status labels.** The spec's §6.1 status labels are not in the repository (`docs/sources` is empty), so no mapping is invented:
  the placement view shows the bdm-004 stage label read-only as "Relationship stage". **Status mapping stays `NEEDS_CONFIRMATION`.**
- **P13 AC2.** The placement view carries no MoU, pipeline write, assignment or commercial data; every BDM route keeps refusing
  `placement_team` (403 "BDM role required"), now pinned by a test.
- **P14 Drives.** The organisation's rec-029 drives are listed read-only (code, date, job role, status; no company), newest first, ≤ 20.
- **P15 `placement_officer`.** DEC-SCOPE-403 C1 names hrc-002's `placement_officer` as the Placement Officer, but that role holds no
  recruiter route (rec-038 invariant) and this backlog item names `placement_team` and the recruiter nav. pob-013 grants
  `placement_team`; granting `placement_officer` is `NEEDS_CONFIRMATION`.

## API (`/api/v1`, §12LD)

| Method | Path | Who |
|---|---|---|
| GET | `/recruiter/colleges` | readers (P3) |
| GET | `/recruiter/colleges/{org_id}` | readers |
| PUT | `/recruiter/colleges/{org_id}/profile` | writers (P4) |
| POST / DELETE | `/recruiter/colleges/{org_id}/courses[/{course_id}]` | writers |
| POST / DELETE | `/recruiter/colleges/{org_id}/batches[/{batch_id}]` | writers |
| POST / DELETE | `/recruiter/colleges/{org_id}/calendar[/{event_id}]` | writers |
| POST | `/recruiter/colleges/{org_id}/interactions` | writers |
| PATCH | `/recruiter/colleges/{org_id}/contacts/{contact_id}` | writers |

Every write: scope (404), row lock on the organisation (`FOR UPDATE` by id, as bdm-025), role (403), archived (409), change, audit row
(`bdm_organization.placement_*`, ids and field names only), one commit; it returns the whole placement detail. Lists are bounded.

## Data (migration `0288_college_placement`, guarded)

`bdm_org_placement_profiles` (organization_id PK), `bdm_org_courses`, `bdm_org_placement_batches`, `bdm_org_placement_events`,
`bdm_org_tpo_interactions`; two columns on `bdm_organization_contacts`. All FKs `ON DELETE RESTRICT` except the interaction's contact
(`SET NULL`). Indexes on `(organization_id, …)`. Downgrade drops them.

## Web

- `CollegePlacement` — one self-loading section (loading / error / read-only / editable), used on the BDM organisation detail for
  college-module college/university organisations and on the new recruiter pages.
- `/recruiter/colleges` (search) and `/recruiter/colleges/[id]` (summary + placement), "Colleges" in both recruiter menus.

## Tests

API: scope and role matrix, every write's 403/404/409/422, AC1–AC3, audit rows, migration guard, rec-038 matrix rows. Web: vitest for
the section and list; a Playwright spec for AC1 and AC3 as a recruiter.
