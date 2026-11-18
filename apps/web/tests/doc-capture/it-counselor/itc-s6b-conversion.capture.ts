import { readFileSync } from "node:fs";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { ITC_ROOT, noPrefetch, shoot, signIn } from "../shoot";

// IT Counselor CRM S6b (docs/it-counselor-crm/documentation-plan.md): DOC-ITC-CONV-001..005, LEAD-015 (linked), ADM-006, ADM-007.
// Runs after itc-s6a. Converting sets up the fee schedule only; no payment is recorded (owner I3).
const root = ITC_ROOT;
const C = "conversion";
const A = "docs.itc.a@example.test";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 1800);
const istDate = (days = 0) => new Date(Date.now() + 5.5 * 3600_000 + days * 86_400_000).toISOString().slice(0, 10);
const sec = (p: Page, heading: string) =>
  p.getByRole("heading", { name: heading, exact: true }).first()
    .locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
async function ctxPage(browser: Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  return ctx.newPage();
}

test("IT Counselor CRM S6b conversion", async ({ browser }) => {
  test.setTimeout(900_000);
  const ids = JSON.parse(readFileSync(process.env.DOCS_ITC_FILE!, "utf8"));
  const leads = ids.leads as Record<string, string>;
  const c = await ctxPage(browser);
  await signIn(c, A, "test", /\/it\/counselor\/dashboard/, "/it/login");
  const open = async (key: string) => { await c.goto(`/it/counselor/leads/${leads[key]}`); await c.waitForTimeout(2000); };

  // ===== CONV-001 Arjun -> new IT student, CONV-003 checklist, LEAD-015 milestones =====
  await open("arjun");
  await c.getByRole("button", { name: "Convert to IT student" }).click();
  await c.waitForTimeout(1500);
  const cf = c.getByRole("form", { name: "Convert to IT student" });
  console.log(`VERIFY CONV-001 form: ${await text(cf)} fee=${await cf.getByLabel("Fee (INR)").inputValue()}`);
  await cf.getByLabel("Batch").selectOption({ label: /Docs FSP Batch 1/ } as never).catch(async () => {
    const v = await cf.getByLabel("Batch").locator("option", { hasText: "Docs FSP Batch 1" }).getAttribute("value");
    await cf.getByLabel("Batch").selectOption(v!);
  });
  await c.waitForTimeout(500);
  console.log(`VERIFY CONV-001 fee after batch: ${await cf.getByLabel("Fee (INR)").inputValue()}`);
  await cf.getByLabel("Fee (INR)").fill("45000");
  await shoot(c, C, "01-convert-form.png", { root, element: cf });
  for (const [i, amount, due] of [[1, "20000", istDate(7)], [2, "25000", istDate(37)]] as const) {
    await cf.getByRole("button", { name: "Add installment" }).click();
    await cf.getByLabel(`Installment ${i} amount`).fill(amount);
    await cf.getByLabel(`Installment ${i} due date`).fill(due);
  }
  await shoot(c, C, "02-convert-form-installments.png", { root, element: cf });
  await cf.getByRole("button", { name: "Convert and enrol" }).click();
  await c.waitForTimeout(3000);
  await say(c, "CONV-001 converted");
  console.log(`VERIFY CONV-001 after: ${await text(c.locator("main"))}`);
  await shoot(c, C, "03-converted.png", { root, element: sec(c, "Student account") });
  console.log(`VERIFY LEAD-015 linked: ${await text(sec(c, "Student and milestones"))}`);
  await shoot(c, "leads", "35-student-and-milestones-linked.png", { root, element: sec(c, "Student and milestones") });

  // ===== CONV-002 Bhavna -> existing IT student account =====
  await open("bhavna");
  await c.getByRole("button", { name: "Set next action" }).click();
  await c.getByLabel("Action", { exact: true }).fill("Confirm batch start with Bhavna");
  await c.getByLabel("Due date", { exact: true }).fill(istDate(1));
  await c.getByRole("button", { name: "Save next action" }).click();
  await c.waitForTimeout(1200);
  await c.getByRole("button", { name: "Change stage" }).click();
  await c.getByLabel("New stage for Docs IT Lead Bhavna").selectOption("qualified");
  await c.locator("form", { has: c.getByLabel("New stage for Docs IT Lead Bhavna") }).getByRole("button", { name: "Save" }).click();
  await c.waitForTimeout(1500);
  await say(c, "CONV-002 qualified");
  console.log(`VERIFY CONV-002 student account before: ${await text(sec(c, "Student account"))}`);
  await c.getByRole("button", { name: "Convert to IT student" }).click();
  await c.waitForTimeout(1500);
  const bf = c.getByRole("form", { name: "Convert to IT student" });
  const bv = await bf.getByLabel("Batch").locator("option", { hasText: "Docs FSP Batch 1" }).getAttribute("value");
  await bf.getByLabel("Batch").selectOption(bv!);
  await bf.getByLabel("Fee (INR)").fill("45000");
  await bf.getByRole("button", { name: "Convert and enrol" }).click();
  await c.waitForTimeout(2500);
  await say(c, "CONV-002 exists");
  console.log(`VERIFY CONV-002 form after: ${await text(bf)}`);
  await shoot(c, C, "05-student-exists.png", { root, element: bf });
  await bf.getByRole("button", { name: /^Enrol Docs IT Student Bhavna/ }).click();
  await c.waitForTimeout(800);
  await shoot(c, C, "06-enrol-existing-chosen.png", { root, element: bf });
  await bf.getByRole("button", { name: "Enrol existing student" }).click();
  await c.waitForTimeout(3000);
  await say(c, "CONV-002 enrolled");
  console.log(`VERIFY CONV-002 after: ${await text(sec(c, "Student account"))}`);
  await shoot(c, C, "07-enrolled-existing.png", { root, element: sec(c, "Student account") });

  // ===== CONV-004 Esha: link, then unlink =====
  await open("esha");
  const sa = sec(c, "Student account");
  console.log(`VERIFY CONV-004 before: ${await text(sa)} buttons ${JSON.stringify(await sa.getByRole("button").allInnerTexts())}`);
  await shoot(c, C, "08-link-suggestion.png", { root, element: sa });
  const link = sa.getByRole("button", { name: /^Link/ }).first();
  if (await link.count()) {
    await link.click();
    await c.waitForTimeout(1000);
    await shoot(c, C, "09-link-confirm.png", { root, element: sec(c, "Student account") });
    await sec(c, "Student account").getByRole("button", { name: "Yes, link" }).click();
    await c.waitForTimeout(2500);
    await say(c, "CONV-004 linked");
    console.log(`VERIFY CONV-004 linked: ${await text(sec(c, "Student account"))}`);
    await shoot(c, C, "09-linked.png", { root, element: sec(c, "Student account") });
    const unlink = sec(c, "Student account").getByRole("button", { name: /Unlink/ }).first();
    await unlink.click();
    await c.waitForTimeout(1000);
    console.log(`VERIFY CONV-004 unlink step: ${await text(sec(c, "Student account"))}`);
    await shoot(c, C, "10-unlink-confirm.png", { root, element: sec(c, "Student account") });
    const yes = sec(c, "Student account").getByRole("button", { name: /Yes|Confirm|Unlink/ }).first();
    if (await yes.count()) await yes.click();
    await c.waitForTimeout(2000);
    await say(c, "CONV-004 unlinked");
    await shoot(c, C, "11-unlinked.png", { root, element: sec(c, "Student account") });
  } else console.log("VERIFY CONV-004 no Link button");

  // ===== CONV-005 Enrol Existing (Overseas student Farah) =====
  await c.goto("/it/counselor/enrol-existing");
  await c.waitForTimeout(1500);
  await c.getByLabel("Overseas student's email or Student ID").fill("docs.overseas.farah@example.test");
  await c.getByRole("button", { name: "Find student" }).click();
  await c.waitForTimeout(2000);
  const ef = c.getByRole("form", { name: "Enrol in IT" });
  console.log(`VERIFY CONV-005 found: ${await text(c.locator("main"))}`);
  await ef.getByLabel("IT counselor").selectOption({ label: "Docs IT Counselor A" }).catch(async () =>
    console.log(`VERIFY CONV-005 counselor options ${JSON.stringify(await ef.locator("select option").allInnerTexts())}`));
  await ef.getByRole("checkbox").check();
  await shoot(c, C, "12-enrol-existing-form.png", { root });
  await ef.getByRole("button", { name: "Enrol in IT" }).click();
  await c.waitForTimeout(2500);
  await say(c, "CONV-005 enrolled");
  await shoot(c, C, "13-enrol-existing-done.png", { root });

  // ===== ADM-006 / ADM-007 IT Admin leads =====
  const a = await ctxPage(browser);
  await signIn(a, "itadmin@edusphere.local", "seed", /\/it\/admin\//, "/it/login");
  await a.goto("/it/admin/leads");
  await a.waitForTimeout(2000);
  const panel = a.locator(".lead-management");
  await a.getByLabel("Search leads").fill("Docs IT Lead");
  await panel.getByRole("button", { name: "Search" }).click();
  await a.waitForTimeout(2000);
  console.log(`VERIFY ADM-006 panel: ${await text(panel)}`);
  await shoot(a, "admin", "10-admin-leads.png", { root, element: panel });
  // The table is wider than the card: scroll it to the Student / Action columns.
  await panel.locator(".table-wrap, [role=region]").first().evaluate((el) => { el.scrollLeft = el.scrollWidth; }).catch(async () =>
    panel.locator("table").first().evaluate((el) => { (el.parentElement as HTMLElement).scrollLeft = 1e6; }));
  await a.waitForTimeout(500);
  await shoot(a, "admin", "11-admin-leads-actions.png", { root, element: panel });
  const conv = panel.getByRole("button", { name: "Convert Docs IT Lead Esha to an IT student" });
  if (await conv.count()) {
    await conv.click();
    await a.waitForTimeout(1500);
    const af = a.getByRole("form", { name: "Convert to IT student" });
    console.log(`VERIFY ADM-006 convert form: ${await text(af)}`);
    await shoot(a, "admin", "12-admin-convert-form.png", { root, element: af });
    await af.getByRole("button", { name: "Cancel" }).click();
  } else console.log("VERIFY ADM-006 no convert button for Esha");

  // ===== ADM-007 merge, on the Telecaller Manager's full-width lead page (the IT Admin's merge form opens inside a narrow table column) =====
  const m = await ctxPage(browser);
  await signIn(m, "telecaller.manager@edusphere.local", "seed", /\/telecaller\//, "/admin/login");
  await m.goto(`/telecaller/manager/leads/${leads.deepa}`);
  await m.waitForTimeout(2000);
  const deepaCode = ((await m.locator("main").innerText()).match(/LD-\d+/) ?? ["LD-000006"])[0];
  await m.getByRole("button", { name: `Merge a duplicate into ${deepaCode}` }).click();
  await m.waitForTimeout(800);
  const mf = m.locator("section", { has: m.getByRole("heading", { name: `Merge a duplicate into ${deepaCode}` }) });
  await mf.getByLabel("Lead ID of the duplicate").fill(ids.deepaDuplicateCode);
  await shoot(m, "admin", "13-merge-enter-code.png", { root, element: mf });
  await mf.getByRole("button", { name: "Compare" }).click();
  await m.waitForTimeout(2000);
  console.log(`VERIFY ADM-007 compare: ${await text(mf)}`);
  await mf.getByLabel("Reason (optional)").fill("Same person enquired twice with a second email.");
  await shoot(m, "admin", "14-merge-compare.png", { root, element: mf });
  await mf.getByRole("button", { name: "Merge into this lead" }).click();
  await m.waitForTimeout(2500);
  await say(m, "ADM-007 merged");
  console.log(`VERIFY ADM-007 after: ${await text(m.locator("main"))}`);
  await shoot(m, "admin", "15-merged.png", { root });
  await a.reload();
  await a.waitForTimeout(2000);
  await a.getByLabel("Search leads").fill("Docs IT Lead Deepa");
  await panel.getByRole("button", { name: "Search", exact: true }).first().click();
  await a.waitForTimeout(2000);
  console.log(`VERIFY ADM-007 admin list after: ${await text(panel)}`);
  await shoot(a, "admin", "16-admin-leads-after-merge.png", { root, element: panel });
});
