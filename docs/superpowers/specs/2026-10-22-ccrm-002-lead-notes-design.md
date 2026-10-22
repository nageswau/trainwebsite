# ccrm-002 — Lead notes (design + plan)

**Source:** `docs/delivery/COUNSELOR_CRM_BACKLOG.md` `ccrm-002` (supersedes nehn-014 part 1; owner CC1–CC10, 2026-10-22).
**Decision:** `DEC-SCOPE-242`. **API:** `API_CONTRACT.md` §12EU. **RBAC:** `RBAC_MATRIX.md` §2.157. **Migration:** `0166_lead_notes`
(re-chained at merge after the parallel ccrm-010/011/014 `0166_*` files; the DEC/API/RBAC numbers skip those sessions' 239–241 / 12ER–12ET /
2.154–2.156).

## Intent

Counselors and telecallers keep free-text notes on a lead. Notes are history: append-only, shown in the lead timeline, kept when a lead
is returned to the telecaller or closed.

## Builder's calls (the owner pre-authorised recommended defaults for this session)

- **N1** The lead's telecaller may add a note after the handover (the backlog lists "its telecaller" as a writer; a note changes no
  lead state, so tel-008 D1's read-only rule — which guards lead state — does not apply). The manager in T23 scope and super_admin too.
- **N2** No edit or delete (backlog open question default: append-only).
- **N3** Admins write through `/admin/leads/{id}/notes` with the existing admin lead rule (`ensure_admin` + the admin's division,
  super_admin any): unknown lead 404, other division 403 — the same answers as the admin stage-history and timeline routes. `it_admin`
  therefore reaches IT-division leads, as on every other admin lead route.
- **N4** The body is trimmed; empty or > 4000 characters → 422. Stored as plain text; React escapes it on render.
- **N5** The timeline shows a `note` entry (badge "Note", the author, an excerpt of 200 characters — tel-015 TM2); the notes panel shows the
  full text. The admin's lead History gets the same panel, so an admin can write.

## Design

- **DB:** `lead_notes(id, lead_id → enquiries RESTRICT, author_user_id → users RESTRICT, body text, created_at)`, check
  `length(body) BETWEEN 1 AND 4000`, index `ix_lead_notes_lead_created (lead_id, created_at)`. No `updated_at` (append-only). Downgrade
  refuses while notes exist.
- **Service `services/lead_notes.py`:** `page(db, lead_id, limit, offset)` newest first (`created_at desc, id desc`) with the author;
  `add(db, user, lead_id, body)` inserts the note and an `AuditLog` (`lead_note.create`, entity `enquiry`, metadata `{note_id}` — never the
  body) and logs `lead_note_added` (ids only).
- **Timeline:** one more `_branch` in `services/lead_timeline.py` (kind `note`, actor = author, reason = excerpt). `LeadTimelineRow.kind`
  gains `note`.
- **API:** `GET|POST /telecaller/leads/{id}/notes` (`lead_pipeline.scope`), `GET|POST /counselor/leads/{id}/notes`
  (`lead_handover.counselor_scope`), `GET|POST /admin/leads/{id}/notes` (N3). Out of scope → 404; wrong role → 403 (the scopes' own
  answers). `POST` → 201 with the note `{id, at, author{id, full_name}, body}`; `GET` → `{items, total, limit, offset}`.
- **Web:** `components/LeadNotes.tsx` — a form (textarea, `maxLength` 4000, a counter, "Add note") above the list, which reuses
  `LeadTimeline` (loading / failed+retry / empty / "Show older") with a note mapper. Mounted on `CounselorLeadDetail`, `LeadDetailPanel`
  (also when read-only, N1) and the admin History (`AdminLeadStage`). Adding a note re-reads the notes and the activity timeline.

## Reviews (phase 3)

- **API:** additive routes only; existing contracts unchanged. One insert per request, no lock needed (append-only; the lead row is never
  updated). Validation by Pydantic (`LeadNoteIn`).
- **Security:** scope from the session on every route (IDOR → 404); no role can widen its scope; body never logged or put in audit
  metadata; plain text rendered by React (no `dangerouslySetInnerHTML`); CSRF/session handling unchanged (the app's cookie + same-origin
  rule applies to the new POSTs).
- **Frontend:** existing `field` / `btn small` / `jtl` styles; label + `aria-describedby` counter; status/alert roles for feedback;
  double-submit blocked while busy; the textarea keeps its text on a failed save.

## Tests (written first)

`apps/api/tests/test_ccrm_002_lead_notes.py`: counselor adds → GET lists it and the timeline shows `note` with author; another
counselor's lead → 404 (GET and POST); telecaller (handed over, N1), manager, super_admin, overseas_admin write; admin other division →
403; non-writer role → 403; empty / 4001 chars → 422; trimmed body; closed lead allowed; a returned lead keeps its notes; audit row has no
body; newest-first paging. `apps/api/tests/test_ccrm_002_migration.py`: chain, model/migration match, round trip, downgrade refusal.
Web: `tests/components/LeadNotes.test.tsx` (add, validation, failure), `lib` mapper; e2e `tests/e2e/ccrm-002-lead-notes.spec.ts`.

## Plan

1. Migration + model + migration test. 2. Service + schemas + routes + API tests. 3. Timeline branch + test. 4. Web lib/component +
vitest. 5. Mount on three pages. 6. e2e + browser QA. 7. Docs: DEC-SCOPE-242, API §12EU, RBAC §2.157, RTM row, backlog status.
