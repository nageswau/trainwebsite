import path from "node:path";

import { test, type Page } from "@playwright/test";

import { COUNSELOR_ROOT, noPrefetch, shoot, signIn } from "../shoot";

// Counselor CRM S10b (LEAD-009 Converted badge). Part 1 links Docs Divya Student to Divya's lead and enrols her application; the runner
// then fires the tel-018 conversion sweep by hand; part 2 (-g "part 2") captures the converted lead.
const root = COUNSELOR_ROOT;
const file = (n: string) => path.join(process.env.DOCS_FILES_DIR!, n);
const IST = 5.5 * 3600_000;
const istDate = (days = 0) => new Date(Date.now() + IST + days * 86_400_000).toISOString().slice(0, 10);
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const sec = (p: Page, id: string) => p.locator(`#${id}`).locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ')][1]");

async function counselor(browser: import("@playwright/test").Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const c = await ctx.newPage();
  await signIn(c, "docs.counselor.a@example.test", "test", /\/overseas\/counselor\/dashboard/);
  return c;
}

test("Counselor CRM S10b part 1", async ({ browser }) => {
  test.setTimeout(600_000);
  const c = await counselor(browser);
  await c.goto("/overseas/counselor/leads");
  await c.waitForTimeout(2000);
  await c.getByRole("link", { name: "LD-000007" }).click();
  await c.waitForTimeout(2500);
  const link = sec(c, "lead-link-heading");
  await link.getByRole("button", { name: "Link Docs Divya Student" }).click();
  await link.getByRole("button", { name: "Yes, link" }).click();
  await c.waitForTimeout(2000);
  await say(c, "linked");
  // Application for Docs Divya Student.
  await c.goto("/overseas/counselor/students");
  await c.waitForTimeout(2500);
  const my = c.locator(".action-card").filter({ has: c.locator("#my-students-source") }).last();
  await c.fill("#my-students-q", "Docs Divya Student");
  await my.getByRole("button", { name: "Search" }).click();
  await c.waitForTimeout(1500);
  await my.getByRole("link", { name: "Open" }).first().click();
  await c.waitForURL(/\/students\/[^/?]+/);
  await c.goto(`${c.url().split("?")[0]}?tab=applications`);
  await c.waitForTimeout(2000);
  await c.locator("summary", { hasText: "Add application" }).click();
  await c.selectOption("#apply-country", { label: "United Kingdom" });
  await c.waitForTimeout(800);
  await c.selectOption("#apply-university", { label: "Docs University -- Docs City" });
  await c.waitForTimeout(1200);
  await c.selectOption("#apply-intake", { label: "September" });
  await c.selectOption("#apply-intake-year", { label: "2027" });
  await c.locator("form").filter({ has: c.locator("#apply-university") }).getByRole("button", { name: "Create application" }).click();
  await c.waitForTimeout(2000);
  await say(c, "application");
  // Advance to Offer and confirm enrolment.
  await c.goto("/overseas/counselor/students");
  await c.waitForTimeout(2500);
  const ev = c.locator(".action-card").filter({ hasText: "Evaluate Applications" }).first();
  const card = () => ev.locator("xpath=.//h4[normalize-space()='Docs Divya Student']/ancestor::div[contains(concat(' ',@class,' '),' card ')][1]").first();
  await card().getByRole("button", { name: "Advance stage" }).click();
  await card().locator("form").filter({ hasText: "Advance to" }).locator("select").selectOption({ label: "Offer" });
  await card().locator("form").filter({ hasText: "Advance to" }).getByRole("button", { name: "Advance" }).click();
  await c.waitForTimeout(2000);
  await card().getByRole("button", { name: "Enrolment" }).click();
  await c.waitForTimeout(800);
  await card().getByRole("button", { name: /Confirm enrolment/ }).first().click();
  const en = card().locator("form").filter({ hasText: "Enrolment date" }).first();
  await en.getByLabel("Enrolment date").fill(istDate(0));
  await en.getByLabel("Course start date").fill("2027-09-20");
  await en.locator("input[type=file]").setInputFiles(file("docs-offer-letter.pdf"));
  await en.getByLabel(/pre-enrolment checklist is complete/).check();
  await en.getByRole("button", { name: "Continue" }).click();
  await card().getByRole("button", { name: "Yes, confirm enrolment" }).click();
  await c.waitForTimeout(2500);
  await say(c, "enrolled");
});

test("Counselor CRM S10b part 2", async ({ browser }) => {
  const c = await counselor(browser);
  await c.goto("/overseas/counselor/leads");
  await c.waitForTimeout(2000);
  await c.getByRole("link", { name: "LD-000007" }).click();
  await c.waitForTimeout(2500);
  console.log(`VERIFY LEAD-009 converted: ${(await c.locator("main").innerText()).replace(/\s+/g, " ").slice(0, 300)}`);
  const ms = c.getByRole("heading", { name: "Student and milestones" }).locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ')][1]");
  console.log(`VERIFY LEAD-009 panel: ${(await ms.innerText()).replace(/\s+/g, " ")}`);
  await shoot(c, "leads", "25-milestones-converted.png", { root, element: ms });
  await shoot(c, "leads", "26-converted-lead.png", { root });
});
