# itc-019 — Faculty profiles and student faculty view (design + plan)

**Source:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` itc-019 (classification `UNVERIFIED` PDF §4 "Faculty & batch: photo, designation,
expertise, contact/office hours"; §6 "Faculty details … configurable to protect personal details"; owner-approved for build in waves by
Q-01, 2026-11-01). **Decision:** `DEC-SCOPE-347`. **Dependencies:** none (backlog). Feeds itc-018 (faculty card) and itc-024.
Open points answered with the recommended calls F1–F8 below (owner: "proceed with recommended answers"), each `NEEDS_CONFIRMATION`.

## Intent

A batch only knows `trainer_id`; a student cannot see who teaches them, how to reach them, or when they are available. itc-019 gives each
trainer a profile they control (with per-field privacy) and shows each student the profiles of their own batches' trainers.

## Behaviour

1. **Table** `trainer_profiles` (`user_id` PK → users ON DELETE CASCADE, `designation` ≤120, `expertise` JSON list, `bio` text,
   `office_hours` ≤160, `contact_route` `in_app|email|phone`, `show_email`, `show_phone`, `show_photo`, `show_bio`, `show_office_hours`
   booleans, `photo_key` ≤255, timestamps). CHECK on `contact_route`. Migration `0231_trainer_profiles` (additive, guarded; the downgrade
   refuses while a profile exists).
2. **Edit own** (trainer) — `GET /it/trainer/profile` (the full profile, with the account email/phone it may show, defaults when no row),
   `PUT /it/trainer/profile` (replace all fields; upsert), `PUT /it/trainer/profile/photo` (multipart `file`), `DELETE
   /it/trainer/profile/photo`. Other roles → 403.
3. **IT Admin edit** — the same four under `/it/trainers/{trainer_id}/profile[/photo]` (IT Admin, Super Admin); the user must be an IT
   `trainer` → else 404; other roles → 403.
4. **Validation (422)** — designation ≤120, expertise ≤12 tags each 1–60 chars (blank dropped, duplicates removed case-insensitively),
   bio ≤2000, office hours ≤160, unknown fields refused. `contact_route=email|phone` requires that field to be visible and present on the
   account. **Photo** — `upload_policy` purpose `trainer_photo` (PNG/JPEG/WebP, ≤2 MB, magic bytes; 413/415), 120–4096 px (422),
   metadata stripped (the PUB-025 `program_media.read_image` path). Stored privately under `private/trainer-photos/<uuid>.<ext>`; every
   read returns a short-lived signed link (`storage.presign_download`, 15 min). The replaced file is deleted after commit (best effort).
5. **Student view** — `GET /it/student/faculty` (it_student): one item per **active** enrolment's batch: `{batch_id, batch, program,
   faculty | null}` (E: a batch with no trainer → `faculty: null`, the card says "Trainer not assigned yet"). `GET /it/faculty/{trainer_id}`
   (it_student): the same public view, **404** unless the trainer teaches one of the student's active batches; other roles 403. The public
   view always has `trainer_id`, `name`, `designation`, `expertise`, `contact_route`; `bio`, `office_hours`, `photo_url`, `email`, `phone`
   are present **only** when visible (hidden keys are omitted, never `null`-filled — AC1). A `contact_route` whose channel is no longer
   shown/present degrades to `in_app`. The `course` portal payload gains a **Trainer** name column.
6. **Audit** — `trainer.profile.update` (changed field names only), `trainer.profile.photo` (`{"removed"|"replaced"}`); actor + subject ids.
7. **UI** — trainer nav gets **Profile** (`/it/trainer/profile`): `TrainerProfileForm` (fields, visibility checkboxes, contact route,
   photo upload/remove, a "What students see" preview). IT Admin **Trainers** page: a "Faculty profiles" panel (pick a trainer → the same
   form). Student **Course** page: a **My faculty** card per batch. Loading / empty / error states throughout.

## Calls made under "proceed with recommended answers" (`NEEDS_CONFIRMATION`)

F1 personal fields default **hidden** (email, phone); bio, office hours and photo default visible (they are what the trainer writes for
students). F2 email/phone come from the user account, not duplicated in the profile. F3 the contact route "in-app" points students to the
existing Questions page. F4 only **active** enrolments count (same as itc-020). F5 the photo is private + signed links, not a public
prefix. F6 the IT Admin may edit any trainer's profile (backlog "IT admin" role). F7 `Program.trainer_name` free text is untouched.
F8 no counselor/HR view (itc-029 360 later).

## Non-goals

Office-hours booking, trainer ratings, counselor or public faculty pages, itc-018 fee card, itc-024 widgets.

## Reviews (Phase 3)

- **API** (`api-and-interface-design`): additive routes only; PUT = full replace (idempotent); 201 not used (profile is a singleton,
  upsert → 200); 404 vs 403 per §5 so another batch's trainer is indistinguishable from a non-trainer id. Single transaction per request;
  the photo is written before commit and the old file removed after commit; a failed commit deletes the new file.
- **Security** (`security-and-hardening`): IDOR — student scope by an `EXISTS` over their active enrolments; hidden fields filtered in one
  serializer (`public_view`) used by every student path; no PII in audit/logs; uploads via `upload_policy` + Pillow decode; keys are
  server-generated; signed links expire. Input lengths bounded by Pydantic. XSS — React escapes text; the bio renders as plain text.
- **Frontend** (`frontend-ui-engineering`): reuse `sendRequest/sendJson`, `card`/`btn` classes, h3 inside sections, labelled controls,
  `role=alert` errors, `aria-live` status, images with `alt`, a grid that wraps at 375 px.

## Plan (TDD)

1. Model + migration 0231 + migration test.
2. `services/trainer_profiles.py`: schema validation, `public_view` (AC1), upsert + audit, photo set/remove, student scope — pytest first.
3. `api/trainer_profiles.py` routes + course payload column — pytest for 200/403/404/413/415/422 and AC1/AC2/+/−/E.
4. Web: `lib/faculty.ts`, `TrainerProfileForm`, `MyFacultyCard`, PortalPage + nav wiring — vitest first.
5. Docs: DEC-SCOPE-347, API §12IS, RBAC §2.247, RTM, backlog status. Playwright spec + browser QA.
