import { readFileSync } from "node:fs";
import path from "node:path";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S7b (docs/recruitment-crm/documentation-plan.md): DOC-REC-REQ-001, REQ-003..010, PO-001, HRM-001, ADM-006. Runs after rec-s7a.
// The Super Admin turns approval on for recruiter jobs; REQ-000005 is sent, rejected, resent and approved; the setting goes back to its default.
// Commercial terms are only viewed (R3); the Revenue card (fee override, invoices) is not used.
const root = REC_ROOT;
const R = "requirements";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean).slice(-4))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 1500);
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
const sec = (p: Page, heading: string | RegExp) =>
  p.getByRole("heading", { name: heading, exact: typeof heading === "string" }).first()
    .locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
const plusDays = (n: number) => new Date(Date.now() + 5.5 * 3600_000 + n * 86_400_000).toISOString().slice(0, 10);
async function as(browser: Browser, who: "a" | "lead" | "po" | "hrm" | "sa") {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const p = await ctx.newPage();
  p.on("dialog", (d) => { console.log(`VERIFY dialog: ${d.message()}`); void d.accept(); });
  if (who === "lead") await signIn(p, "docs.rec.lead@example.test", "test", /\/recruiter\/manager\/team/, "/admin/login");
  else if (who === "sa") await signIn(p, "superadmin@edusphere.local", "seed", /\/admin(\/(?!login)|$)/, "/admin/login");
  else if (who === "a") await signIn(p, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");
  else if (who === "po") await signIn(p, "docs.rec.po@example.test", "test", /\/(recruiter\/dashboard|it\/(hr|hr-manager|placement-officer|interviewer)\/dashboard)/, "/it/login");
  else await signIn(p, "docs.rec.hrm@example.test", "test", /\/(recruiter\/dashboard|it\/(hr|hr-manager|placement-officer|interviewer)\/dashboard)/, "/it/login");
  return p;
}
async function pickCombo(p: Page, scope: Locator, name: string | RegExp, typed: string, option: RegExp) {
  const box = scope.getByRole("combobox", { name });
  await box.click();
  await box.fill(typed);
  await settle(p, 1500);
  await p.getByRole("option", { name: option }).first().click();
  await settle(p, 500);
}

test("Recruitment CRM S7b requirement page, approval, owners", async ({ browser }) => {
  test.setTimeout(1_200_000);
  const ids = JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8"));
  const reqUrl = `/recruiter/requirements/${ids.requirements.python}`;
  const settingsBox = (p: Page) => sec(p, "Which jobs need approval");

  // ===== ADM-006 approval sources (Super Admin) =====
  const sa = await as(browser, "sa");
  await sa.goto("/it/hr-manager/approvals");
  await settle(sa, 3000);
  await settingsBox(sa).getByLabel("Recruiter jobs").check();
  await settle(sa, 2000);
  await say(sa, "ADM-006 recruiter jobs on");
  await shoot(sa, "admin", "20-approval-sources.png", { root, element: settingsBox(sa) });

  // ===== REQ-007 submit for approval (Recruiter A) =====
  const a = await as(browser, "a");
  const openReq = async (p: Page) => { await p.goto(reqUrl); await settle(p, 3500); };
  await openReq(a);
  const appr = () => sec(a, "Approval");
  console.log("VERIFY REQ-007 approval card:", await text(appr()));
  await appr().getByLabel("Note for the approver (optional)").fill("Client confirmed two openings on the call.");
  await shoot(a, R, "20-submit-for-approval.png", { root, element: appr() });
  await appr().getByRole("button", { name: "Submit for approval" }).click();
  await settle(a, 2500);
  await say(a, "REQ-007 submitted");
  await shoot(a, R, "21-pending-approval.png", { root, element: appr() });
  console.log("VERIFY REQ-007 header:", (await text(a.locator("main"))).slice(0, 200));

  // ===== HRM-001 reject, then approve =====
  const hrm = await as(browser, "hrm");
  const queue = async () => { await hrm.goto("/it/hr-manager/approvals"); await settle(hrm, 3000); };
  await queue();
  await shoot(hrm, "hr-manager", "01-vacancy-approvals.png", { root });
  console.log("VERIFY HRM-001 queue:", await text(hrm.locator("main")));
  await hrm.getByLabel("Note, or the reason when rejecting").first().fill("Add the salary budget confirmation from the client first.");
  await hrm.getByRole("button", { name: "Reject", exact: true }).first().click();
  await settle(hrm, 2500);
  await say(hrm, "HRM-001 rejected");
  await shoot(hrm, "hr-manager", "02-vacancy-rejected.png", { root });
  await openReq(a);
  console.log("VERIFY REQ-007 after reject:", await text(appr()));
  console.log("VERIFY REQ-007 reject in history:", await text(sec(a, "Status history")));
  console.log("VERIFY REQ-007 reject header:", (await text(a.locator("main"))).slice(0, 400));
  await shoot(a, R, "22-approval-rejected.png", { root, element: appr() });
  await appr().getByLabel("Note for the approver (optional)").fill("Salary budget ₹6–9 lakh confirmed by Docs Priya on email.");
  await appr().getByRole("button", { name: "Submit for approval" }).click();
  await settle(a, 2500);
  await say(a, "REQ-007 resubmitted");
  await queue();
  await hrm.getByLabel("Note, or the reason when rejecting").first().fill("Budget confirmed. Approved.");
  await shoot(hrm, "hr-manager", "03-vacancy-approve.png", { root });
  await hrm.getByRole("button", { name: "Approve", exact: true }).first().click();
  await settle(hrm, 2500);
  await say(hrm, "HRM-001 approved");
  await hrm.context().close();
  // back to the default (recruiter jobs need no approval)
  await sa.reload();
  await settle(sa, 3000);
  await settingsBox(sa).getByLabel("Recruiter jobs").uncheck();
  await settle(sa, 2000);
  await say(sa, "ADM-006 recruiter jobs off");
  console.log("VERIFY ADM-006 settings:", await text(settingsBox(sa)));
  await sa.context().close();

  await openReq(a);
  console.log("VERIFY REQ-007 after approve:", (await text(a.locator("main"))).slice(0, 300));
  await shoot(a, R, "23-approved.png", { root, element: sec(a, "Status history") });

  // ===== REQ-003 edit details =====
  await a.getByRole("button", { name: "Edit", exact: true }).first().click();
  await settle(a, 1500);
  await a.getByLabel("Expected joining date").fill(plusDays(45));
  await shoot(a, R, "06-edit-requirement.png", { root, element: sec(a, "Edit details") });
  await a.getByRole("button", { name: /^Save/ }).first().click();
  await settle(a, 2500);
  await say(a, "REQ-003 edited");

  // ===== REQ-004 JD =====
  const jd = () => sec(a, /^Job description \(JD\)/);
  await jd().getByRole("button", { name: "Create JD" }).click();
  await settle(a, 1500);
  console.log("VERIFY REQ-004 JD form:", await text(jd()));
  await shoot(a, R, "07-create-jd.png", { root, element: jd() });
  await jd().getByRole("button", { name: "Save JD" }).click();
  await settle(a, 2500);
  await say(a, "REQ-004 JD v1");
  await jd().getByRole("button", { name: "Edit JD" }).click();
  await settle(a, 1500);
  const openings = jd().getByLabel(/openings|vacancies/i).first();
  console.log("VERIFY REQ-004 openings field:", await openings.count());
  await openings.fill("3");
  await jd().getByRole("button", { name: "Save JD" }).click();
  await settle(a, 2500);
  await say(a, "REQ-004 JD v2");
  await jd().getByRole("button", { name: "Update requirement from JD" }).click();
  await settle(a, 1000);
  await shoot(a, R, "08-update-from-jd.png", { root, element: jd() });
  await jd().getByRole("button", { name: /^Yes/ }).click();
  await settle(a, 2500);
  await say(a, "REQ-004 applied");
  await jd().locator('input[type="file"]').setInputFiles(path.join(process.env.DOCS_FILES_DIR!, "docs-python-developer-jd.pdf"));
  await jd().getByRole("button", { name: /^Upload$/ }).click();
  await settle(a, 2500);
  await say(a, "REQ-004 JD upload");
  await openReq(a);
  console.log("VERIFY REQ-004 JD card:", await text(jd()));
  await shoot(a, R, "09-jd-versions.png", { root, element: jd() });

  // ===== REQ-005 checklist and tasks =====
  const cl = () => sec(a, "Validation checklist");
  const items = await cl().locator("fieldset.checklist-item legend").allInnerTexts();
  console.log("VERIFY REQ-005 items:", JSON.stringify(items));
  for (const [i, leg] of items.entries()) {
    const choice = leg.startsWith("Commercial terms") ? "Missing" : leg.startsWith("Joining date") ? "Not applicable" : "Confirmed";
    await cl().locator("fieldset.checklist-item").nth(i).getByLabel(choice, { exact: true }).check();
    await settle(a, 1200);
  }
  await say(a, "REQ-005 checklist");
  await openReq(a);
  console.log("VERIFY REQ-005 checklist:", await text(cl()));
  await shoot(a, R, "10-checklist.png", { root, element: cl() });
  const tasks = () => sec(a, "Tasks");
  await tasks().getByRole("button", { name: "Mark done" }).first().click();
  await settle(a, 2500);
  await say(a, "REQ-005 task done");
  console.log("VERIFY REQ-005 tasks:", await text(tasks()));
  await shoot(a, R, "11-tasks.png", { root, element: tasks() });

  // ===== REQ-006 sourcing plan =====
  const sp = () => sec(a, "Sourcing plan");
  await sp().getByRole("button", { name: "Create plan" }).click();
  await settle(a, 1500);
  await sp().getByLabel("Target profile").fill("Python developers with 1–3 years of REST API work, Hyderabad or ready to relocate.");
  await sp().getByRole("button", { name: "Add a search string" }).click().catch(() => undefined);
  await sp().getByLabel("Name").first().fill("Naukri Boolean");
  await sp().getByLabel("Search string").first().fill('("Python" OR "Django") AND ("FastAPI" OR "REST") AND Hyderabad');
  const channels = sp().locator('fieldset:has(legend:text("Planned channels")) input[type="checkbox"]');
  console.log("VERIFY REQ-006 channels:", JSON.stringify(await sp().locator('fieldset:has(legend:text("Planned channels")) label').allInnerTexts()));
  for (let i = 0; i < Math.min(2, await channels.count()); i++) await channels.nth(i).check();
  await sp().getByLabel("Profiles to find").fill("20");
  await sp().getByLabel("Profiles to screen").fill("10");
  await sp().getByLabel("Profiles to submit").fill("5");
  await sp().getByLabel("Deadline").fill(plusDays(14));
  await sp().getByLabel("Source owner").selectOption({ index: 1 });
  await shoot(a, R, "12-sourcing-plan-form.png", { root, element: sp() });
  await sp().getByRole("button", { name: "Save plan" }).click();
  await settle(a, 2500);
  await say(a, "REQ-006 plan saved");
  await shoot(a, R, "13-sourcing-plan.png", { root, element: sp() });

  // ===== REQ-009 owners (Recruiter A adds the Placement Officer and Recruiter B) =====
  const own = () => sec(a, "Owners");
  console.log("VERIFY REQ-009 roles:", JSON.stringify(await own().getByLabel("Owner role").locator("option").allInnerTexts()));
  await own().getByLabel("Owner role").selectOption({ label: "Placement officer owner" });
  await pickCombo(a, own(), "Person", "Docs Placement", /Docs Placement Officer/);
  await shoot(a, R, "14-add-owner.png", { root, element: own() });
  await own().getByRole("button", { name: "Add owner" }).click();
  await settle(a, 2500);
  await say(a, "REQ-009 PO owner");
  await own().getByLabel("Owner role").selectOption({ label: "Collaborator" });
  await pickCombo(a, own(), "Person", "Docs Recruiter B", /Docs Recruiter B/);
  await own().getByRole("button", { name: "Add owner" }).click();
  await settle(a, 2500);
  await say(a, "REQ-009 collaborator");
  await openReq(a);
  await shoot(a, R, "15-owners.png", { root, element: own() });
  await shoot(a, R, "16-ownership-history.png", { root, element: sec(a, "Ownership history") });

  // ===== REQ-010 commercial terms (view) =====
  await shoot(a, R, "17-commercial-terms.png", { root, element: sec(a, "Commercial terms") });

  // ===== REQ-003 change status (put on hold, then back) =====
  const cs = () => sec(a, "Change status");
  console.log("VERIFY REQ-003 status options:", JSON.stringify(await cs().getByLabel("New status").locator("option").allInnerTexts()));
  await cs().getByLabel("New status").selectOption({ label: "On Hold" });
  await cs().getByLabel(/Note \(optional\)|Reason/).fill("Client paused interviews for a week.");
  await shoot(a, R, "18-change-status.png", { root, element: cs() });
  await cs().getByRole("button", { name: "Change status" }).click();
  await settle(a, 2500);
  await say(a, "REQ-003 on hold");
  console.log("VERIFY REQ-003 options on hold:", JSON.stringify(await cs().getByLabel("New status").locator("option").allInnerTexts()));
  await a.context().close();

  // ===== PO-001 the Placement Officer reopens it =====
  const po = await as(browser, "po");
  await po.goto("/recruiter/requirements");
  await settle(po, 3000);
  await shoot(po, R, "24-po-requirements.png", { root });
  await po.getByRole("link", { name: /Docs Python Developer/ }).first().click();
  await settle(po, 3500);
  const pinfo = await po.evaluate(() => ({
    heads: [...document.querySelectorAll("main h2, main h3")].map((h) => h.textContent?.trim()),
    buttons: [...new Set([...document.querySelectorAll("main button")].map((b) => b.textContent?.trim().slice(0, 50)))],
  }));
  console.log("VERIFY PO-001 page:", JSON.stringify(pinfo));
  await shoot(po, R, "25-po-requirement-page.png", { root });
  const pcs = sec(po, "Change status");
  if (await pcs.count()) {
    console.log("VERIFY PO-001 options:", JSON.stringify(await pcs.getByLabel("New status").locator("option").allInnerTexts()));
    await pcs.getByLabel("New status").selectOption({ index: 1 });
    await pcs.getByLabel(/Note \(optional\)|Reason/).fill("Client resumed interviews.");
    await shoot(po, R, "26-po-change-status.png", { root, element: pcs });
    await pcs.getByRole("button", { name: "Change status" }).click();
    await settle(po, 2500);
    await say(po, "PO-001 status");
  }
  await po.goto(reqUrl);
  await settle(po, 3000);
  console.log("VERIFY PO-001 status history:", await text(sec(po, "Status history")));
  await shoot(po, R, "19-status-history.png", { root, element: sec(po, "Status history") });
  await po.context().close();

  // ===== REQ-008 visibility, assignment and fee (Team Lead) =====
  const l = await as(browser, "lead");
  await openReq(l);
  const vis = () => sec(l, "Visibility");
  console.log("VERIFY REQ-008 options:", JSON.stringify(await vis().getByLabel("Who can see this job").locator("option").allInnerTexts()));
  await vis().getByLabel("Who can see this job").selectOption({ label: "Segment (talent pool)" });
  await settle(l, 1500);
  console.log("VERIFY REQ-008 pools:", JSON.stringify(await vis().getByLabel("Talent pool").locator("option").allInnerTexts()));
  await shoot(l, R, "27-visibility-segment.png", { root, element: vis() });
  await vis().getByLabel("Who can see this job").selectOption({ label: "Candidate portal" });
  await vis().getByRole("button", { name: "Save visibility" }).click();
  await settle(l, 2500);
  await say(l, "REQ-008 portal");
  await shoot(l, R, "28-visibility-saved.png", { root, element: vis() });
  await vis().getByLabel("Who can see this job").selectOption({ label: "Public website" });
  await vis().getByRole("button", { name: "Save visibility" }).click();
  await settle(l, 2500);
  await say(l, "REQ-008 back to public");
  const asg = sec(l, "Assignment");
  console.log("VERIFY REQ-009 assignment:", await text(asg));
  await shoot(l, R, "29-assignment.png", { root, element: asg });
  // REQ-010: the Team Lead sees the same terms; the per-requirement fee lives on the Revenue card (Phase 2, not used: R3)
  console.log("VERIFY REQ-010 lead terms:", await text(sec(l, "Commercial terms")));
  await shoot(l, R, "30-commercial-terms-team-lead.png", { root, element: sec(l, "Commercial terms") });

  // ===== REQ-001 list and filters =====
  await l.goto("/recruiter/requirements");
  await settle(l, 3000);
  await shoot(l, R, "31-requirements-team-lead.png", { root });
  await l.getByLabel("Priority").selectOption({ label: "High" });
  await l.getByRole("button", { name: "Search" }).click();
  await settle(l, 2500);
  console.log("VERIFY REQ-001 filtered:", l.url(), (await text(l.locator("main"))).slice(0, 700));
  await l.context().close();
});
