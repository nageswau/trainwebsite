# hrc-025 — New Website Registrations workspace (design)

- **Feature ID:** `hrc-025` · **Decision:** `DEC-SCOPE-402` · **Numbering:** no migration, API §12KU, RBAC §2.295
- **Requirement:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-025` (PDF §6.2 list and filters; first-contact time, follow-up date,
  activities, conversion; PDF classified `UNVERIFIED`). Scope approved by the owner 2026-11-01 (backlog Q-00). Dependencies merged: hrc-024
  (`DEC-SCOPE-393`), hrc-016 (`DEC-SCOPE-387`), hrc-021 (`DEC-SCOPE-397`).
- The owner said to proceed with the recommended answers, so N1–N10 below (Q-26 included) are **the builder's calls
  (`NEEDS_CONFIRMATION`)**.

## Intent
People who register on the public website (hrc-023 job application, hrc-022 portal verification) become candidates with source
**Website** and are routed to a recruiter or the unassigned queue (hrc-024). Nobody has one place to see these fresh sign-ups, whether they
have been contacted yet, when the next follow-up is due, and whether they converted. hrc-025 adds a read-only list for that.

**Non-goals:** a new status, a stored `first_contacted_at` column, assigning from the list (the candidate's ownership panel does that,
hrc-012), a configurable SLA, dashboards. **Anti-goal:** a first-contact time that can disagree with the logged calls and messages.

## Builder's calls
- **N1 Who is listed.** A pool candidate (`candidates.pool_filter()`), not archived, whose source is the catalogue value **Website** (the
  source hrc-022/hrc-023 give every candidate the website creates). Q-26 (b): imported and recruiter-added candidates are **not** shown —
  they carry other sources. Registration date = `candidates.created_at`. Newest first, paginated (`limit`/`offset`).
- **N2 Who reads what.** `placement_team` (recruiter): their own (hrc-012 "My candidates": primary recruiter, officer or collaborator) **and**
  the unassigned queue. `placement_manager`, `super_admin`, `hr_manager` and `hr_team` (who already read the whole pool): all. Anyone else
  403. hrc-012 O5 left "HR Manager sees all" to this item: `hr_manager` gains this **read-only list only** — no contact details in the
  payload, and the row links to the candidate only for candidate readers (`can_open`); `hr_manager` still has no candidate screen.
- **N3 Filter `view`** (one value, URL-kept): `unassigned` (no primary recruiter), `new` / `contacted` / `screened` / `active` /
  `inactive` (hrc-021's derived engagement, the same SQL expression), `duplicate_review` (an open hrc-014 duplicate pair names the
  candidate). No value = all. An unknown value is 422.
- **N4 Columns.** Name and code; registration date; skills (up to 3 names, primary first, plus "+n"); location (city, else location);
  completeness % (hrc-010 Appendix B, hrc-019's SQL expression); assignment (primary recruiter or "Unassigned"); engagement chip; first
  contact; next follow-up; conversion.
- **N5 First contact (AC3) is derived** — the earliest logged call (`recruiter_calls.occurred_at`) or message
  (`recruiter_messages.sent_at`) of the candidate; both indexed by candidate. The backlog allowed "or derived"; derived cannot drift and
  needs no migration or backfill.
- **N6 Next follow-up** = the earliest due date of the candidate's open hrc-016 task (`candidate_tasks`, status `open`). rec-024 follow-ups
  belong to companies, not candidates.
- **N7 Conversion** `registered → applied → placed`: placed = an application `joined` or stored status `placed` (hrc-021's placed test);
  applied = any job application or website application; else registered.
- **N8 Contact SLA (Q-26 a): 24 hours** from registration to the first call or message. `contact_sla`: `met` (first contact within 24 h),
  `pending` (not contacted, still within 24 h), `breached` (contacted late, or not contacted after 24 h). Measured on the database clock.
  A breached row is highlighted with an "SLA breached" badge; the page states the target.
- **N9 Freshness (AC1).** The list reads live on each request (client fetch, no cache), so a registration shows on the next load.
- **N10 Navigation.** "Website Registrations" for recruiters, placement managers, super_admin and the HR Manager portal; one page
  `/recruiter/website-registrations` in each role's shell.

## API (§12KU)
`GET /api/v1/recruiter/candidates/website-registrations?view=&limit=&offset=` → `{items, total, limit, offset, sla_hours}`; each item
`{id, candidate_code, name, registered_at, skills[], skill_count, location, completeness, owner{id,name}|null, engagement{key,label},
first_contact_at, next_follow_up_at, conversion, contact_sla, duplicate_review, can_open}`. Read only; no audit row; no contact details.
One count query + one page query (all derived columns are correlated sub-queries on indexed columns) + one owners query + one skills query.

## UI
`/recruiter/website-registrations`: title, SLA note, a "Show" select (All / Unassigned / New / Contacted / Screened / Active / Inactive /
Duplicate review) kept in the URL (`useUrlList`), a table, Previous/Next pager. Loading, error + Retry, empty ("No website registrations
yet." / "… match this filter.") states. The table scrolls horizontally on narrow screens inside a focusable labelled region.

## Tests
pytest: listing only Website-sourced candidates (AC1, import excluded), each filter (AC2), first contact from the first call or message
(AC3), next follow-up, conversion, SLA states, recruiter scope (own + queue, another recruiter's hidden), hr_manager reads all with no
`can_open`, other roles 403, unknown view 422, rec-038 matrix row. vitest: rows, filter in URL, states. e2e: website apply → listed →
log a call → first contact shown.

## Regression risks
rec-038 matrix (new row), navigation tests that pin menus, hr_manager access (only this endpoint).
