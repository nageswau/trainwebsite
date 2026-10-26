# nehn-036 — Course/program icons (design)

**Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-036` (§17 L476, L493-495; §26 L803; action 17,
**Optional**; `UNVERIFIED` backlog). Decision `DEC-SCOPE-284`. No upstream dependency (nehn-003 is needed only for upload, which is not
built).

## Intent

The Overseas Education section should not show courses as plain text where a visual is suitable. A small subject icon beside each course
helps students, the public and staff tell an AI course from a Business one at a glance. Course icons stay **optional**: a course with no
chosen icon still shows one, derived from its category.

## Builder's defaults (owner pre-authorised recommended answers; `NEEDS_CONFIRMATION`)

- **I1 Scope:** overseas courses (`overseas_courses`, the §16 course master), because the source requirement is the Overseas Education
  section. IT training programs (`programs`) are not changed; whether they get icons is open.
- **I2 Curated set only, no upload.** Twelve subject icons plus a general (graduation cap) default, drawn as inline SVG in the web app (no
  icon library, no image files, no SVG from users, so no XSS surface). Upload stays open (it would need nehn-003 and the nehn-035 SVG rules).
- **I3 Storage:** `overseas_courses.icon` `varchar(20)` nullable, CHECK one of the curated keys. `NULL` = automatic. Migration
  `0197_course_icons` adds the column only when missing; existing rows keep `NULL` (automatic). Downgrade drops it.
- **I4 Keys** (`models.COURSE_ICONS`, mirrored by `web/lib/courseIcons.ts`): `ai`, `security`, `data`, `computing`, `engineering`,
  `business`, `health`, `hospitality`, `law`, `education`, `arts`, `science`, `general`.
- **I5 Automatic icon:** the web client matches the category, case-insensitively and on word boundaries, against each key's keywords in the
  order above, so "Data Science" is data (not science), "Computer Science" is computing, "Cyber Security" is security and "Artificial
  Intelligence" is ai. No match gives `general`. An explicitly chosen icon always wins.
- **I6 API (additive):** `CourseIn`/`CourseUpdate` take `icon` (one of the keys, or `null` = automatic; anything else is a `422`).
  Course payloads (`course_out`: university course list, `/partnership/courses`, create/update responses) and the public
  `GET /public/overseas-courses` and `GET /public/universities/{slug}` course rows gain `icon` (key or `null`). Who may write is
  unchanged (the course write rule, CO1). A changed icon is named in the course's audit row like any field. The CSV import is unchanged
  (imported courses are automatic).
- **I7 Display:** a decorative icon (`aria-hidden`, the category or title is always beside it) on the public course cards
  (`/overseas/courses`), the public university page's course cards, the university master's course list, and the Courses & Programs table.
  Same size on desktop and mobile (20px inline, 36px on public cards), colours from the theme (`currentColor`).
- **I8 Picker:** the course form gets an **Icon** select: "Automatic (from category)" (default) and the twelve subjects plus General, with
  a live preview of the icon that will show. Choosing Automatic on an edit sends `null`.

## Non-goals

Upload, IT program icons, icons in the apply form's `<select>` (options cannot hold images), any change to filters or permissions.

## Acceptance criteria

1. A course with a chosen icon shows that icon; a course without one shows its subject default; on desktop and mobile.
2. A CS course (no icon set) shows the computing (code) icon; an unknown category shows the general icon.
3. A course writer can choose, change and clear (Automatic) the icon; a value outside the set is refused with `422`.
4. The public course payloads carry `icon` and still never carry commission.
5. The migration chains after `0196`, keeps one head, round-trips, and existing courses become automatic.

## Plan

1. **API (TDD):** `tests/test_nehn_036_course_icons.py` — create/patch/clear an icon, `422` for an unknown key, `icon` in course_out
   and both public payloads, audit row names `icon`. Then `models.COURSE_ICONS` + column + CHECK, `schemas.CourseIcon`, `FIELDS`,
   `course_out`, `public.py`. Update the upc-017 public KEYS pin (additive key).
2. **Migration:** `0197_course_icons.py` + `tests/test_nehn_036_migration.py` (chain/single head, models match, round trip on a scratch DB
   using the upc-017 migration-test helpers).
3. **Web (TDD, vitest):** `lib/courseIcons.ts` (keys, labels, `courseIconKey`), `components/CourseIcon.tsx` (server-safe SVG);
   tests for the fallback rules and rendering. Then the form picker (`CourseForm`), `UniversityCourses`, the Courses & Programs table, the
   public courses and university pages, `Course` type.
4. **e2e:** `tests/e2e/nehn-036-course-icons.spec.ts` — an admin sets an icon, it shows on the master list and the public pages;
   automatic icon on mobile width.
5. **Docs:** `DEC-SCOPE-284`, API §12GJ, `DATA_MODEL` note if the course master table is documented there, backlog status line.

## Risks

Card layout snapshots (none found for these pages); the upc-017 public KEYS pin (updated deliberately); the migration chain if a sibling
takes `0197` first (renumber in Phase 9).
