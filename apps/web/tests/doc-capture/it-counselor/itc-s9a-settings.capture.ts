import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { ITC_ROOT, noPrefetch, shoot, signIn } from "../shoot";

// IT Counselor CRM S9a (docs/it-counselor-crm/documentation-plan.md): DOC-ITC-ADM-011 (thresholds), ADM-014 (escalation hours).
// Runs after itc-s8 and the S9 back-dating SQL (scratchpad s9-backdate.sql, owner I2); the jobs are run with `celery call` afterwards.
const root = ITC_ROOT;
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 1800);
const sec = (p: Page, heading: string) =>
  p.getByRole("heading", { name: heading, exact: true }).first()
    .locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
async function ctxPage(browser: Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  return ctx.newPage();
}
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);

test("IT Counselor CRM S9a settings", async ({ browser }) => {
  test.setTimeout(600_000);
  // ===== ADM-011 at-risk thresholds =====
  const a = await ctxPage(browser);
  await signIn(a, "itadmin@edusphere.local", "seed", /\/it\/admin\//, "/it/login");
  await a.goto("/it/admin/at-risk");
  await settle(a, 2500);
  const th = sec(a, "At-risk thresholds");
  await th.getByRole("button", { name: "Edit thresholds for Docs Full Stack Python" }).click();
  await settle(a, 800);
  const form = th.locator("form").first();
  await form.getByLabel("Minimum attendance %").fill("75");
  await form.getByLabel("Sessions before attendance counts").fill("3");
  await form.getByLabel("Absences in a row").fill("3");
  console.log(`VERIFY ADM-011 form: ${await text(form)}`);
  await shoot(a, "admin", "50-at-risk-threshold-form.png", { root, element: form });
  await form.getByRole("button", { name: "Save thresholds" }).click();
  await settle(a, 2000);
  await say(a, "ADM-011 saved");
  await shoot(a, "admin", "51-at-risk-thresholds.png", { root, element: th.locator("tr", { hasText: "Docs Full Stack Python" }).first().locator("xpath=ancestor::table[1]") });

  // ===== ADM-014 escalation hours (Telecaller Manager, IT team) =====
  const m = await ctxPage(browser);
  await signIn(m, "telecaller.manager@edusphere.local", "seed", /\/telecaller\//, "/admin/login");
  await m.goto("/telecaller/manager/alerts");
  await settle(m, 2500);
  console.log(`VERIFY ADM-014 page: ${await text(m.locator("main"))}`);
  const save = m.getByRole("button", { name: /Save .*IT.* thresholds/ }).first();
  const row = m.locator("form").filter({ has: save }).first();
  await row.getByLabel("Escalate overdue follow-ups after (hours)").fill("1");
  await shoot(m, "admin", "52-escalation-hours.png", { root, element: row });
  await save.click();
  await settle(m, 2000);
  await say(m, "ADM-014 saved");
});
