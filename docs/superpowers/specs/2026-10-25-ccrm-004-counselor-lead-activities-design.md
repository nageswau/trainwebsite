# ccrm-004 — Counselor activity logging on leads (design)

NO-ASSUMPTION MODE. Backlog item `ccrm-004` in `docs/delivery/COUNSELOR_CRM_BACKLOG.md` (source: Counselor CRM Specification PDF §3,
§14 — `UNVERIFIED`; owner request 2026-10-22 "implement all this"). Dependency `ccrm-003` is merged (PR #305). The owner asked
for the recommended answers to be used without a question round, so every LG answer below is a **builder's call, NEEDS_CONFIRMATION**.

Numbers on `origin/main` @ `6941d5dc` (ccrm-017 took DEC-SCOPE-258 / 12FK): migration `0181_lead_meetings`, `DEC-SCOPE-259`, API §12FL, RBAC §2.173.

## Intent

A counselor works the leads handed to them. Today every call / WhatsApp / email write is telecaller-only (403), and nothing records a
meeting or the outcome of a counselling session. The counselor needs to log those on their own leads, and the lead timeline should show
them. Telecaller metrics must not count the counselor's work.

## Goals

1. The counselor logs calls (outcome, type, duration, remarks) on their own open leads, and edits / deletes their own on the same IST day.
2. The counselor sends WhatsApp (wa.me + confirm) and email (queued, ENH-032 / SMTP worker) to their own open leads with the existing
   composers and template library.
3. The counselor records a generic **meeting** (date/time, mode, notes).
4. Completing a lead counselling appointment takes optional outcome notes.
5. All of it appears in the lead timeline (tel-015) for everyone who can read it.
6. Telecaller metrics, targets, day counts and the management telecalling funnel do not count the counselor's calls / messages.

## Non-goals

- No new provider integration (wa.me links and the existing email worker only).
- Consent / opt-out (`ccrm-040` not built) — deferred to that item.
- No copying of lead activity to the student record: the timeline stays on the lead and the student 360 (ccrm-009) links to the lead.

## Decisions (builder's calls, NEEDS_CONFIRMATION)

| ID | Decision |
| --- | --- |
| LG1 | **Calls.** `GET/POST /counselor/leads/{id}/calls`, `PATCH/DELETE /counselor/calls/{id}` reusing `services/lead_calls.py`: same outcomes, call types, time rules (7 days back, no future), daily cap 300, CL2 closed lead → 409, CL3/D4 outcome rules, CL4 same-day edit/delete by the caller. **A counselor's call has no pipeline effect** (no `call_connected` event, no closing outcome move) — the counselor moves stages through the CC8 control (ccrm-003). The optional/required next follow-up uses tel-011 with the counselor's rules. |
| LG2 | **Messages.** `GET /counselor/leads/{id}/render`, `GET/POST /counselor/leads/{id}/messages`, `DELETE /counselor/messages/{id}` reusing `services/lead_messages.py`: WA1–WA4 and EM1–EM4 unchanged (From "<Counselor> via EduSphere", Reply-To the counselor; separate caps; WhatsApp same-day delete; email never deleted). The counselor is added to the template library's **readers** (active rows only; no write). |
| LG3 | **Meetings.** New append-only table `lead_meetings` (id, lead_id, author_user_id, occurred_at, mode ∈ Online / Phone / In person, notes 1–2000, created_at). `GET/POST /counselor/leads/{id}/meetings`. Same time rules as a call (no future, up to 7 days back); a closed lead → 409. No edit/delete (as ccrm-002 notes). |
| LG4 | **Appointment outcome notes.** `appointments.outcome_notes` (text ≤ 2000, nullable). `POST /lead-appointments/{id}/complete` accepts an optional body `{ "outcome_notes": "…" }`; no body = today's behaviour. Shown on the appointment and as the completed event's text in the timeline. |
| LG5 | **Metrics exclusion.** tel-021/022/023/024 metrics already count by telecaller ids (unchanged). The mgmt funnel "Telecalling" step counts telecaller calls only (counselor callers filtered out). `/telecaller/calls/day-counts` stays telecaller / manager / super_admin. |
| LG6 | **Backlog open question** "should counselor calls count in management counselor performance?" → **yes**: mgmt-018's Calls figure becomes tracked = the calls each counselor logged in the period. |
| LG7 | Counselor lead detail gains `whatsapp_to` and `permissions.activity` (= lead not closed). Calls, messages and meetings sections sit on `CounselorLeadDetail`, reusing `LeadCalls` / `CallLogForm` / `LeadMessages` with an injected API (as ccrm-003 did for follow-ups). |
| LG8 | Logs and audit rows carry ids, outcome / channel / mode — never remarks, bodies or notes. |

## Authorisation

`lead_handover.counselor_scope`: role counselor (else 403), `owner_id = self` and same division; another counselor's lead / call /
message → 404. Writes lock the lead first. Telecaller-side routes unchanged; a telecaller still gets read-only lists on a handed-over
lead (rows the counselor wrote show `can_change: false`).

## Regression risks

Telecaller call/message routes (shared service), tel-015 timeline union (new branch), mgmt-018 tests asserting `calls: null`,
mgmt funnel telecalling step, lead appointment complete route.
