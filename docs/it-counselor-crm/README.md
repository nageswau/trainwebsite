# EduSphere IT Counselor CRM — Documentation

Verified user and administrator documentation for the **IT Counselor CRM**: how IT counselors take leads from telecallers, counsel and convert them into IT students, and then look after those students' fees, resume and progress; and how the IT Admin sets it all up.

Every page was checked in the running application (`main` @ `6b61546c`, 18 Nov 2026) with fictional **Docs** data on a separate documentation stack. Screenshots were captured by Playwright. Where a state depends on time passing (overdue fees, at-risk flags, escalations), the data was moved with a documented data setup and the page says "state prepared by data setup". No payment was recorded.

## Start here
| If you are… | Read |
|---|---|
| An IT counselor | [Role guide: IT Counselor](role-guides/it-counselor.md), then the [User manual](user-manual/README.md) |
| The IT Admin | [Role guide: IT Admin](role-guides/it-admin-counselors.md), then the [Administrator manual](admin-manual/README.md) |
| Stuck | [FAQ](faq.md) · [Troubleshooting](troubleshooting.md) |
| Trying it on a demo system | [Demo and Docs accounts](demo-accounts.md) |

## Contents
- [User manual](user-manual/README.md): 43 pages for IT counselors.
- [Administrator manual](admin-manual/README.md): 19 pages for the IT Admin, with the hand-offs to telecallers, students and HR.
- [Role guides](role-guides/it-counselor.md): quick starts for the IT Counselor and the [IT Admin](role-guides/it-admin-counselors.md).
- [PDFs](pdf/): the same content as printable books.

## For maintainers
- [Documentation analysis](documentation-analysis.md): scope, the 62 Doc IDs and product findings P1–P14.
- [Documentation plan](documentation-plan.md) and [progress](documentation-progress.md).
- [Screenshot index](screenshot-index.md): every screenshot, its page and the capture script.
- [Review report](documentation-review-report.md).
- Capture scripts: `apps/web/tests/doc-capture/it-counselor/`.
