# rec-011 — Candidate skill profile (design)

Backlog: `docs/delivery/RECRUITER_CRM_BACKLOG.md` rec-011. Source: EVID-018 S2-§1 (lines 1094–1124), S2-§3 (1218–1233), S2-§17
(1645–1675). Depends on rec-006 (merged PR #150) and rec-009 (merged PR #155). rec-006's owner answer S1 moved the skill **merge** here.

**Numbering (re-chained 2026-10-09 after rec-026 and rec-017 merged; drafted as `0120` / DEC-SCOPE-135 / §12BC / §2.61):** `DEC-SCOPE-137`, migration `0122_candidate_skills` (after `0121_job_application_tracking`),
API §12BE, RBAC §2.63. Re-check origin/main before the merge and re-chain if needed.

## 1. Answers (2026-10-08)
The owner asked to proceed with the recommended answers, so nothing was asked. Every row below is **UNVERIFIED** (a recorded default).

| ID | Question | Default |
|---|---|---|
| SK1 (Q-12) | Level values | `beginner`, `intermediate`, `advanced`, `expert`. The level is **required** (S2-§3 puts it on every row; the source example says "Advanced"). |
| SK2 | Experience and last used | `experience_months` 0–600, optional. `last_used_year` 1950 to the current year, optional (a future year is 422). |
| SK3 | Source | The six S2-§17 values. Defaults to `resume` when not sent. Editable. |
| SK4 (Q-13) | Who verifies | Any candidate **writer** (recruiter, placement manager, `super_admin`; R11 lets every recruiter edit the whole pool). It is not tied to the source. A new row is always `claimed`; the status changes only through `POST …/status`, which records who and when. Back to `claimed` clears them (the audit row keeps the history). |
| SK5 | Skill input | `skill` is text resolved by `services/skills.resolve` (a name or an alias, active skills only). Not found → 422 naming the text and telling the user to pick a listed skill or ask their manager to add it or an alias. An alias of a skill the candidate has → the same 409 as the name. |
| SK6 | Size | At most 100 skills per candidate (422). The list is not paged. |
| SK7 (S1) | Skill merge | A manager merges skill A **into** skill B (see §5). A disappears and its name becomes an alias of B, so old spellings still resolve. |

Also: an archived candidate's skills are read-only (409 "Restore this candidate first", the rec-009 rule). A candidate outside the pool is
404. `hr_team` reads (rec-009's roles line), and the Skills Master stays closed to it (rec-006 S3), so it sees names only.

## 2. Data (migration `0122_candidate_skills`)
**`candidate_skills`**
| Column | Type | Rule |
|---|---|---|
| `id` | uuid PK | |
| `candidate_id` | FK → candidates RESTRICT | |
| `skill_id` | FK → skills RESTRICT | The merge re-points before it deletes a skill |
| `level` | varchar(16) | CHECK in SK1 |
| `experience_months` | int null | CHECK 0–600 |
| `last_used_year` | smallint null | CHECK ≥ 1950 (the upper bound is the current year, checked by the schema) |
| `source` | varchar(24) | CHECK in the six values |
| `status` | varchar(12) default `claimed` | CHECK in `claimed`, `verified`, `assessed` |
| `verified_by_user_id`, `verified_at` | null | CHECK: both null exactly when `status = 'claimed'` |
| `added_by_user_id`, `updated_by_user_id` | FK users | |
| timestamps | | |

- `uq_candidate_skills_skill` UNIQUE (candidate_id, skill_id): one row per skill (AC1), and the 409 backstop under a race (AC2).
- `ix_candidate_skills_skill_candidate` (skill_id, status, candidate_id): rec-013's search index ("verified only").
- Created with a guard (the 0119 idiom). `downgrade()` refuses while any row exists. The CHECK strings live in
  `app.models.CANDIDATE_SKILL_CHECKS`, and the migration repeats them (a test asserts they are equal).

## 3. Service `app/services/candidate_skills.py`
Functions only; the route commits. Reuses `services/candidates` (`require_reader`, `require_writer`, `load`, `ARCHIVED`, `audit`, `log`)
and `services/skills.resolve`.
- `writable(db, candidate_id)`: role is checked by the route first; loads the candidate `FOR UPDATE` and refuses an archived one.
- `skill_for_add(db, text)`: `resolve`, then re-reads that skill `FOR SHARE` and requires it active, so a concurrent merge or deactivation
  waits for this commit (or the add sees the skill gone → 422).
- `items_out(db, candidate)`: one query joining skill, category and the verifier/adder; ordered by `lower(skill.name)`.

## 4. API (§12BE), prefix `/api/v1/recruiter/candidates/{candidate_id}/skills`
| Method | Path | Who | Result |
|---|---|---|---|
| GET | `` | readers | `{items, can_edit}` |
| POST | `` | writers | `{skill, level, experience_months?, last_used_year?, source?}` → 201 item. 422 unknown skill; 409 duplicate; 422 over 100 |
| PATCH | `/{sid}` | writers | `{level?, experience_months?, last_used_year?, source?}` → item. Not the skill or the status (extra fields 422) |
| DELETE | `/{sid}` | writers | 204 |
| POST | `/{sid}/status` | writers | `{status}` → item. The same status → 409. verified/assessed sets `verified_by`/`verified_at`; claimed clears them |

- The backlog named the status route `…/verify`; it is `…/status` because it also sets `claimed` and `assessed`. Recorded deviation.
- Item: `id, skill{id,name,active}, category{id,name}, level, experience_months, last_used_year, source, status, verified_by{id,full_name},
  verified_at, added_by{id,full_name}, created_at, updated_at`.
- Bodies are untyped dicts parsed by `services/telecaller._parse` (`extra="forbid"`), so a 422 is one sentence naming the field.
- An unknown `sid`, or one belonging to another candidate → 404 "Skill not found on this candidate".
- Every write locks the candidate row, writes one `AuditLog` row (`candidate.skill_add`, `candidate.skill_update` with field names,
  `candidate.skill_remove`, `candidate.skill_status` with from/to) and commits once. A PATCH that changes nothing writes no audit row.
  Logs carry ids only.

## 5. Skill merge (SK7) — `POST /api/v1/recruiter/skills/{id}/merge` `{into_skill_id}`
Writers of the Skills Master only (placement manager, `super_admin`). One transaction under `lock_terms`, with both skills locked
`FOR UPDATE`:
1. Refused: merging into itself (422), an unknown skill (404), an unknown or inactive target (422).
2. **Candidate skills** of A move to B. When a candidate has both, the row with the stronger status (assessed > verified > claimed) is kept,
   and B's row on a tie; the other is deleted.
3. **Requirement skills** (`job_skills.skill_id`, rec-007) of A point to B. Their typed names are unchanged.
4. A's **aliases** move to B. A's **related** links are re-made on B (skipping B itself and links B already has). A's tags are dropped.
5. A is **deleted**, then A's name is added as an alias of B. (A deactivated skill would keep its name in the term space, so the old
   spelling could never resolve; S6's "never deleted" covers deactivation, and the audit row keeps A's id and name.)
6. One audit row `recruiter.skill_merge`: A's id and name, B's id, and the counts moved and dropped. Answers the updated B (`skill_out`).

## 6. Web
- **`lib/recruiterCandidateSkills.ts`:** types, the URL helper, level, source and status labels, and the form ⇄ body mapping.
- **`RecruiterCandidateSkills`** (a card on the candidate detail, between the profile and the resume):
  - A table on wide screens and stacked rows on narrow ones (the `.telecaller-list` idiom): Skill (with category), Level, Experience,
    Last used, Source, Status (with "by X on date"), and the actions.
  - Writers get **Add skill**: a server-mode `SearchableSelect` over the Skills Master (`skillSearch("")`), level, experience, last used
    and source. Each row has Edit (inline), a status control (Mark verified / Mark assessed / Back to claimed), and Remove with a confirm.
  - Loading, error-with-Retry and empty states. A ref guards double submits; focus moves to the feedback line after a write.
  - `hr_team` and an archived candidate see no write controls.
- **`RecruiterSkillDetail`** (the manager Skills Master) gains **Merge into another skill**: a picker plus a confirm that names what
  happens. On success the detail shows the kept skill (with the merged name among its aliases) and the list reloads.

## 7. Acceptance criteria
1. Each skill is stored as its own row: adding Java (Advanced, 36 months, 2026, resume) answers 201 with status `claimed` (AC1).
2. Adding the same skill again, by name in another case or by an alias → 409 (AC2).
3. A status change records who and when; back to `claimed` clears them; each change is audited (AC3).
4. A skill that is not in the master (or inactive) → 422 that tells the user how to get it added.
5. Recruiters, the manager and `super_admin` write; `hr_team` reads only (403 on writes); other roles 403; outside the pool 404;
   archived 409.
6. Merging A into B re-points candidate skills (keeping the stronger on a clash) and requirement skills, moves the aliases, deletes A,
   and A's name then resolves to B. Recruiters cannot merge (403).
7. The Skills card works on desktop, tablet and mobile, with loading, empty and error states, and is keyboard operable.

## 8. Tests
- `test_rec_011_migration.py`: CHECKs equal the model, the indexes, single head, downgrade refusal.
- `test_rec_011_candidate_skills.py`: AC1–AC5, PATCH rules, delete, the 100 cap, validation 422s, the race backstop.
- `test_rec_011_skill_merge.py`: AC6.
- vitest: the lib mapping and the Skills card; Playwright `rec-011-candidate-skills.spec.ts`: add, duplicate 409, verify, hr_team reads.

## 9. Risks
- `models.py`, `schemas.py` and `main.py` are append hotspots shared with parallel items (rec-017 also planned a migration number).
- The merge deletes a skill row: every FK to `skills` must be re-pointed or cascade first. Today those are `job_skills` (re-pointed),
  `candidate_skills` (re-pointed), and tags, aliases and related links (cascade or moved).
