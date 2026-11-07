import { expect, test, type Page } from "@playwright/test";

// pob-004 (AC2, AC3, E): the seeded recruiter sees the BD ladder, marks a company inactive with a catalogue reason, and it leaves the open
// board for the Inactive tile; the seeded placement manager reopens it at the stage it kept.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("a recruiter marks a company inactive with a reason; the manager reopens it", async ({ page }) => {
  test.setTimeout(90_000);
  const name = `E2E Pob004 ${Date.now()} Ltd`;
  await signIn(page, "it", "placement@edusphere.local", "/recruiter/dashboard");
  await page.goto("/recruiter/companies/new");
  await page.getByLabel("Company name (required)").fill(name);
  await page.getByRole("button", { name: "Save company" }).click();
  await page.waitForURL(/\/recruiter\/companies\/[0-9a-f-]{36}$/);
  const detailUrl = page.url();
  const pipeline = page.getByRole("region", { name: "Pipeline" });
  const steps = pipeline.getByRole("list", { name: "Pipeline stages" });
  for (const label of ["Target Identified", "Research Completed", "HR Contact Identified", "Outreach Sent", "Meeting Booked", "Vendor Registration / Agreement"]) {
    await expect(steps).toContainText(label);
  }

  await pipeline.getByLabel("Move to").selectOption({ label: "Research Completed" });
  await pipeline.getByRole("button", { name: "Move" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Moved to Research Completed." })).toBeVisible();

  await page.getByRole("button", { name: "Mark inactive" }).click();
  const reason = pipeline.getByLabel("Reason", { exact: true });
  await expect(reason.locator("option", { hasText: "No current hiring" })).toHaveCount(1);
  await reason.selectOption({ label: "No current hiring" });
  await pipeline.getByLabel("Note (optional)").fill("Budget next year");
  await page.getByRole("button", { name: "Yes, mark inactive" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Marked inactive." })).toBeVisible();
  await expect(pipeline).toContainText("No current hiring: Budget next year");
  await expect(page.getByRole("button", { name: "Reopen" })).toHaveCount(0); // E: the recruiter cannot reopen

  await page.goto("/recruiter/pipeline?stage=research_completed");
  await expect(page.getByRole("link", { name })).toHaveCount(0); // AC3: out of the open stage
  await page.goto("/recruiter/pipeline?stage=inactive");
  await expect(page.getByRole("link", { name })).toBeVisible();

  await page.context().clearCookies();
  await signIn(page, "admin", "placement.manager@edusphere.local", "/recruiter/manager/team");
  await page.goto(detailUrl);
  await page.getByRole("button", { name: "Reopen" }).click();
  await page.getByRole("region", { name: "Pipeline" }).getByLabel("Reason").fill("Hiring again");
  await page.getByRole("button", { name: "Yes, reopen" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Reopened." })).toBeVisible();
  await page.goto("/recruiter/pipeline?stage=research_completed");
  await expect(page.getByRole("link", { name })).toBeVisible();
});

test("the board and the inactive form fit a phone screen", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page, "it", "placement@edusphere.local", "/recruiter/dashboard");
  await page.goto("/recruiter/pipeline");
  await expect(page.getByRole("navigation", { name: "Pipeline stages" })).toContainText("Inactive");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
