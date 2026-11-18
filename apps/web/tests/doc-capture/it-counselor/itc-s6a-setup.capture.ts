import { readFileSync, writeFileSync } from "node:fs";

import { test, type Browser, type Page } from "@playwright/test";

import { noPrefetch, signIn } from "../shoot";

// IT Counselor CRM S6a (set-up only, no screenshots): IT student accounts that match Bhavna's and Esha's lead emails, a Docs Overseas
// student for Enrol Existing, and a duplicate of Deepa for the IT Admin merge. Runs after itc-s5.
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const store = (): Record<string, unknown> => {
  try { return JSON.parse(readFileSync(process.env.DOCS_ITC_FILE!, "utf8")); } catch { return {}; }
};
async function ctxPage(browser: Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  return ctx.newPage();
}
async function createUser(p: Page, path: string, who: { name: string; email: string; phone: string }, role: string, division?: string) {
  await p.goto(path);
  await p.waitForTimeout(1500);
  await p.fill("[id='Create user-full_name']", who.name);
  await p.fill("[id='Create user-email']", who.email);
  await p.fill("[id='Create user-phone']", who.phone);
  if (division) await p.selectOption("[id='Create user-division']", division);
  await p.selectOption("[id='Create user-role']", role);
  await p.locator("form:has([id='Create user-full_name'])").getByRole("button", { name: "Create user" }).click();
  await p.waitForTimeout(1500);
  await say(p, `create ${who.name}`);
}

test("IT Counselor CRM S6a set-up", async ({ browser }) => {
  test.setTimeout(600_000);
  const a = await ctxPage(browser);
  await signIn(a, "itadmin@edusphere.local", "seed", /\/it\/admin\//, "/it/login");
  await createUser(a, "/it/admin/users", { name: "Docs IT Student Bhavna", email: "docs.itlead.bhavna@example.test", phone: "+91 90000 20102" }, "it_student", "it");
  await createUser(a, "/it/admin/users", { name: "Docs IT Student Esha", email: "docs.itlead.esha@example.test", phone: "+91 90000 20105" }, "it_student", "it");

  const o = await ctxPage(browser);
  await signIn(o, "overseasadmin@edusphere.local", "seed", /\/overseas\/admin\//);
  await createUser(o, "/overseas/admin/users", { name: "Docs Overseas Student Farah", email: "docs.overseas.farah@example.test", phone: "+91 90000 20201" }, "overseas_student");

  const t = await ctxPage(browser);
  await signIn(t, "docs.itc.telecaller@example.test", "test", /\/telecaller\//, "/it/login");
  await t.goto("/telecaller/leads/new");
  await t.waitForTimeout(1500);
  await t.fill("#new-name", "Docs IT Lead Deepa Kumari");
  await t.fill("#new-phone", "+91 90000 20114");
  await t.fill("#new-email", "docs.itlead.deepa.k@example.test");
  await t.selectOption("#new-product_id", { label: "Python Full Stack" });
  await t.selectOption("#new-source", "google");
  await t.fill("#new-city", "Hyderabad");
  await t.getByRole("button", { name: "Create lead" }).click();
  await t.waitForURL(/\/telecaller\/leads\/(?!new)[^/]+$/, { timeout: 20_000 });
  await t.waitForTimeout(1500);
  const code = ((await t.locator("main").innerText()).match(/LD-\d+/) ?? [""])[0];
  console.log(`VERIFY duplicate lead code ${code}`);
  writeFileSync(process.env.DOCS_ITC_FILE!, JSON.stringify({ ...store(), deepaDuplicateCode: code }, null, 2));
});
