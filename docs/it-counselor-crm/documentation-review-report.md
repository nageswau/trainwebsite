# IT Counselor CRM Documentation — Final Review Report (S12)

> Review date 2026-11-18 · Code baseline `main` @ `6b61546c` (unchanged since S1) · Docs branch `docs/it-counselor-crm-user-guide`

## 1. Result
| | |
|---|---|
| Features in scope | 62 (`DOC-ITC-*`, analysis §3) |
| Browser-verified and documented | 62 |
| Complete / partial | 62 / 0 |
| Pages | 62 feature pages, 2 manual indexes, 2 role guides, README, demo-accounts, FAQ, troubleshooting |
| Screenshots | 176 PNGs, all indexed, all referenced, secrets masked |
| Link check | `node docs/tooling/check-doc-links.mjs docs/it-counselor-crm` → All links OK |
| Structure check | Every feature page has its Doc ID / "Verified on" line, Purpose, Who Can Use, Prerequisites, How to Access and Related Features |
| PDFs | `node docs/tooling/build-pdfs.mjs it-counselor` → User Manual, Admin Manual, Role Guides, FAQ and Troubleshooting (`pdf/`) |
| Payments | None recorded (owner decision I3). ADM-008 is screens only; the docs database holds only the two seed `paid` rows |

## 2. How the review was done
Two independent reviewers worked in parallel. Each reported findings only, and the main session made every fix.
1. **User manual accuracy.** It checked 34 of 43 pages (all of leads, conversion, students, fees and resume, plus notes, dashboard, appointments, auth-002 and auth-003) and opened 26 screenshots. Result: 2 HIGH, 7 MEDIUM, 6 LOW.
2. **Admin manual, role guides, README, demo-accounts, FAQ and troubleshooting.** It checked 26 files and opened all 64 admin and hand-off screenshots. Result: 0 HIGH, 5 MEDIUM, 8 LOW. It confirmed that `demo-accounts.md` matches the seed data and contains no secrets.

The main session also ran a script over every page. It checked links, the template, and screenshots that were missing, unindexed or unused. It also opened the login, set-password and forgot-password screenshots: password inputs, the demo-accounts card and the dev-only reset link are all masked.

## 3. Changes made in review
| Area | Change |
|---|---|
| LEAD-005 change stage | The reason is required for **Not Eligible**. **Not Interested** and **Lost** need a **Lost reason (required)**, with optional **Lost to**. Closing a lead cancels its open follow-ups and appointments. Three messages added. |
| CONV-001 convert | Installment rules: each needs an amount above 0 and a due date, they must add up to the fee, and at most 12. Two messages added. |
| AUTH-003 reset | A reset link expires after 30 minutes. The wrong "only the newest link works" tip was replaced. |
| LEAD-013 return | Return needs no linked student (not "not converted"). It moves the lead to Follow-up, cancels follow-ups and appointments, and clears the next action. Added a note that the header in the screenshot shows the old stage until the page reloads. |
| LEAD-008 calls | Documented the follow-up block for certain outcomes, remarks required for Duplicate Lead, the 4-hour cap, that the outcome can't be edited, and that only the caller can edit or delete, on the same day. |
| LEAD-009, LEAD-004, CONV-004, LEAD-003 | Delete rules and messages for WhatsApp records; next-action due date and where its message appears; unlink is hidden once the lead is Converted; product interest is not editable. |
| APPT-001 | No-show and cancel move the lead back to Follow-up (complete moves it to Counselling Completed). |
| FEE-002 | Only one pending request per enrolment. The discount comes off bills latest due first. |
| RES-002 | Next-action texts for every HR stage. |
| ADM-002 | Deactivating or reactivating cancels open set-password links, so a counselor still **Awaiting setup** needs **Re-send link**. The sign-in link is named **Forgot your password?** |
| ADM-003 | An inactive previous counselor gets no notice. Screenshot 23 was retaken (read only) so it no longer shows another row's error. |
| ADM-009 | The screenshot 32 caption now explains the left-over messages. |
| ADM-011, ADM-012, ADM-013, ADM-014 | Fixed a column name and a caption. A programme rule applies to new reviews only. The **Set by hand** column is a count. Added Nurture and inactive-manager escalation rules. |
| ADM-015 | Screenshot 59 was retaken (form filled, not saved) without the earlier error. The S9b script now reloads first. |
| S7 script | `admin/23` is now captured before the Overseas-student attempt. |

## 4. Accepted as is
- `leads/21-call-edit-form.png` still shows the "Call logged." message from the step before. The edit form itself is correct.
- `students/03-student-360.png` and `students/05-student-record.png` are full-page captures, so the sticky header and sidebar repeat part-way down. The content is correct.
- Pages the user-manual reviewer did not open (auth-001/004/005/006, dash-002, nav-001, notif-001, task-001, tt-001) were written from the same verified captures. The S12 script checked them for structure and links.

## 5. Product findings for the owner (from analysis §9)
P1 no bulk reassign · P2 no Tasks/Calendar page · P3 no lead export · P4 escalation hours live on the Telecaller Manager's page · P5 no retention purge · P6 itc-002/016 still NEEDS_CONFIRMATION · P7 no Sign out in the phone menu · P8 "Phone calls" preference on staff profiles · P9 only the telecaller books counselling, and only before handover · P10 IT Admin Leads table and merge form are cramped · P11 **Change counsellor** fails for a student who joined IT from Overseas · P12 bare 404 for another counselor's student · P13 deactivation leaves students on the inactive counselor · P14 onboarding checklist never ticked automatically.
