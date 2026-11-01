import { test } from "@playwright/test";

import { COUNSELOR_ROOT, noPrefetch, shoot, signIn } from "../shoot";

// Counselor CRM S12 review fixes (read-only re-captures): arrival panel open (ARR-002), counselor tasks filtered to Overdue (ESC-001).
const root = COUNSELOR_ROOT;

test("Counselor CRM S12 re-captures", async ({ browser }) => {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const c = await ctx.newPage();
  await signIn(c, "docs.counselor.a@example.test", "test", /\/overseas\/counselor\/dashboard/);
  await c.goto("/overseas/counselor/students");
  await c.waitForTimeout(2500);
  const ev = c.locator(".action-card").filter({ hasText: "Evaluate Applications" }).first();
  const a2 = ev.locator("xpath=.//h4[normalize-space()='Docs Walk-in Student']/ancestor::div[contains(concat(' ',@class,' '),' card ')][1]").first();
  await a2.getByRole("button", { name: "Arrival and orientation" }).click();
  await c.waitForTimeout(1200);
  const panel = a2.locator("section[aria-label='Arrival and orientation']");
  console.log(`VERIFY ARR-002 panel: ${(await panel.innerText()).replace(/\s+/g, " ")}`);
  await shoot(c, "arrival", "05-arrival-saved.png", { root, element: panel });

  const actx = await browser.newContext();
  await noPrefetch(actx);
  const a = await actx.newPage();
  await signIn(a, "overseasadmin@edusphere.local", "seed", /\/overseas\/admin\//);
  await a.goto("/overseas/admin/counselor-tasks");
  await a.waitForTimeout(2500);
  await a.selectOption("#filter-band", { label: "Overdue" });
  await a.getByRole("button", { name: "Apply" }).click();
  await a.waitForTimeout(2500);
  console.log(`VERIFY ESC-001 overdue url ${a.url()}`);
  await a.locator("#filter-band").evaluate((el) => el.scrollIntoView({ block: "start", behavior: "instant" }));
  await a.evaluate(() => window.scrollBy(0, -120));
  await shoot(a, "escalation", "03-counselor-tasks-overdue.png", { root });
});
