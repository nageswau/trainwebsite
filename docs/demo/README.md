# EduSphere CRM Demo Guide

How to prepare and run live demos of the **Agent CRM** and the **School CRM** on
**https://dev.edusphere.org.uk**, for clients, prospects and client stakeholders.

| | Agent CRM | School CRM |
|---|---|---|
| Audience | Education agencies; EduSphere overseas team | Partner schools; EduSphere specialists |
| 1. Prepare (day before) | [Preparation checklist](agent-crm/01-prep-checklist.md) · ~75 min | [Preparation checklist](school-crm/01-prep-checklist.md) · ~90 min |
| 2. Run the demo | [45-minute script](agent-crm/02-demo-script.md) | [45-minute script](school-crm/02-demo-script.md) |
| 3. Detailed check | [UAT checklist](agent-crm/03-uat-checklist.md) | [UAT checklist](school-crm/03-uat-checklist.md) |
| Full manuals | [User manual](../user-manual/README.md) · [Admin manual](../admin-manual/README.md) | [User manual](../school-crm/user-manual/README.md) · [Admin manual](../school-crm/admin-manual/README.md) |

PDF versions: `docs/demo/pdf/` (build with `node docs/tooling/build-pdfs.mjs demo`).

## How the demo works

1. **Prepare the day before.** Each preparation checklist creates demo accounts and data through the screens, so the
   dashboards and reports have content. During the demo you only create the few records that tell the story.
2. **Run the 45-minute script.** Each script is a time-boxed run sheet. Every step gives the action, the expected
   result, and what to say. Each script ends with **Do not show during the demo** (known product findings) and **If
   something goes wrong** (recovery).
3. **Hand over the UAT checklist.** Client stakeholders who want to check each feature use it after the demo. Each row
   links to the manual page and has a pass/fail column and a sign-off.

Agent CRM and School CRM can run back to back (about 1 h 45 min with a break) or on separate days.

## Presenter setup (both demos)

| Item | Why |
|---|---|
| One Chrome profile per role, each signed in before the demo | Switching windows is faster and safer than signing in live |
| Window at least 1440 px wide, zoom 100 % | The screens and manual screenshots are 1440 × 900; narrow layouts hide sign-out (School P6) |
| Your own mailboxes for every demo account | Dev may send real email; never type client or student addresses |
| Passwords in a password manager | No passwords in these documents or on screen |
| The manual screenshots folder ready | Fallback if a screen fails: `docs/screenshots/` (Agent) and `docs/school-crm/screenshots/` (School) |
| Notifications and other apps muted | Screen sharing |

## Open items to confirm before the first demo

| # | Item | Affects | Status |
|---|---|---|---|
| 1 | Which commit dev runs. The scripts follow the manuals verified at `6a9be770` (Agent) and `ce1f07c2` (School) | Both | `NEEDS_CONFIRMATION` |
| 2 | Email delivery on dev (welcome, set-password and invitation emails). The app sends these only when **both** `SMTP_HOST` and `SMTP_FROM_EMAIL` are set (`apps/api/app/services/mailer.py`); otherwise it records `not_configured` and sends nothing. `EMAIL_ENABLED` is not read. Password-reset emails go through `EMAIL_WEBHOOK_URL` instead. The local `.env` checked on 2026-10-06 had working Gmail SMTP credentials but no `SMTP_FROM_EMAIL` | Both | `NEEDS_CONFIRMATION` |
| 3 | Razorpay test mode and its webhook on dev, for the deposit payment | Agent | `NEEDS_CONFIRMATION` |
| 4 | An open new academic year on dev, for Promotion | School | `NEEDS_CONFIRMATION` |
| 5 | Whether the sign-in page shows the development **Demo accounts** card on dev | Both | `NEEDS_CONFIRMATION` |
| 6 | A database snapshot/restore procedure on dev for repeat demos | Both | `NEEDS_CONFIRMATION` |

Rehearse each script once on dev after these are settled. Steps that fail on dev should be recorded and the script
updated before the client demo.

## Sources

The steps, labels and messages come from the browser-verified Agent CRM and School CRM documentation. The known
limitations come from their review reports: `docs/documentation-review-report.md` (P1–P10) and
`docs/school-crm/documentation-review-report.md` (P1–P17, U-items). This guide does not add product behaviour of its
own.
