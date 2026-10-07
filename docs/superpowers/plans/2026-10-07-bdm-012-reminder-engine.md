# bdm-012 implementation plan

Spec: `docs/superpowers/specs/2026-10-07-bdm-012-reminder-engine-design.md` (`DEC-SCOPE-098`, no migration).

Test command (isolated stack `bdm012`, code bind-mounted):

```bash
docker compose -p bdm012 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps \
  -v "$(pwd -W)/apps/api:/app" api-test python -m pytest -q -p no:cacheprovider <files>
```

Lite tests only: bdm-012 files + AGN-017 reminders + ENH-014 delivery/worker + bdm-006/008/010/005 service neighbours + touched web tests.

## Engineering review (Phase 3) folded in

- **API:** no route, schema or status-code change. The only contract is the page query `?action=` (ignored when unknown).
- **Transactions:** each reminder in a savepoint inside a chunk transaction; the dedupe insert is the claim, so overlapping runs and
  retries cannot double-send (ENH-014 publishes deliveries only after the root commit). The finders read without locks — a status that
  changes between the read and the insert at worst sends one reminder that was due a moment earlier.
- **Security:** recipients are owners (active users only); no token in links; GET never mutates (Confirm only focuses its button);
  HTML email escapes all values; user text cleaned/capped; no phone/email; logs ids/counts. No rate-limit concern (no endpoint).
- **Frontend:** reuse `BdmAppointmentActions` groups and `useFocusAfterRender`; notice via the detail's existing `FormMessage`-style
  notice; `history.replaceState` drops `?action` (as `?created=1`), so refresh does not reopen the form; keyboard focus goes to the
  opened form's first field / the Confirm button. No new component.

## Tasks

1. `mailer.send_bdm_reminder_email` — not_configured / sent / failed; escaped HTML; absolute links. Test first.
2. `delivery._send_email` — `bdm_reminder` context goes to the mailer (no webhook). Test first.
3. `services/bdm_reminders.py` — finders per kind, `_remind`, `send_bdm_reminders`, `run_bdm_reminders`. Tests per kind, AC1–AC5, R6.
4. `worker.py` — task + beat entry; beat test.
5. Web — `?action=` on the appointment page; `org-mou` anchor; notifications empty text. Vitest first.
6. Playwright — a seeded reminder's deep link opens the Reschedule form.
7. Docs — decision register `DEC-SCOPE-098`, backlog status line, API contract note, RTM line.
