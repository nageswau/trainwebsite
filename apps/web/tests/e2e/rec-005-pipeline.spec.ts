import { expect, test, type Page } from "@playwright/test";

// rec-005 (AC1, AC2, AC4, P5, P7): the seeded recruiter moves a new company through the manual stages (back needs a reason) and marks it
// lost; the seeded placement manager reopens it and finds it on the board.

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("a recruiter moves and loses a company; the manager reopens it", async ({ page }) => {
  test.setTimeout(90_000);
  const name = `E2E Rec005 ${Date.now()} Ltd`;
  await signIn(page, "it", "placement@edusphere.local", "/recruiter/dashboard");
  await page.goto("/recruiter/companies/new");
  await page.getByLabel("Company name (required)").fill(name);
  await page.getByRole("button", { name: "Save company" }).click();
  await page.waitForURL(/\/recruiter\/companies\/[0-9a-f-]{36}$/);
  const detailUrl = page.url();
  const pipeline = page.getByRole("region", { name: "Pipeline" });
  await expect(pipeline.locator("li[aria-current='step']")).toContainText("New Lead");

  await pipeline.getByLabel("Move to").selectOption({ label: "Meeting Scheduled" });
  await pipeline.getByRole("button", { name: "Move" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Moved to Meeting Scheduled." })).toBeVisible();
  await pipeline.getByLabel("Move to").selectOption({ label: "Contacted" });
  await pipeline.getByLabel("Reason (required when moving back)").fill("Wrong contact");
  await pipeline.getByRole("button", { name: "Move" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Moved to Contacted." })).toBeVisible();
  const history = page.getByRole("region", { name: "Stage history" });
  await expect(history).toContainText("Meeting Scheduled → Contacted");
  await expect(history).toContainText("Note: Wrong contact");

  await page.getByRole("button", { name: "Mark lost" }).click();
  await pipeline.getByLabel("Reason").fill("Hiring freeze");
  await page.getByRole("button", { name: "Yes, mark lost" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Marked lost." })).toBeVisible();
  await expect(page.getByRole("button", { name: "Reopen" })).toHaveCount(0);

  await page.context().clearCookies();
  await signIn(page, "admin", "placement.manager@edusphere.local", "/recruiter/manager/team");
  await page.goto("/recruiter/pipeline?stage=lost");
  await expect(page.getByRole("link", { name })).toBeVisible();
  await page.goto(detailUrl);
  await page.getByRole("button", { name: "Reopen" }).click();
  await page.getByRole("region", { name: "Pipeline" }).getByLabel("Reason").fill("Freeze lifted");
  await page.getByRole("button", { name: "Yes, reopen" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Reopened." })).toBeVisible();
  await expect(page.getByRole("region", { name: "Stage history" })).toContainText("Reopened at Contacted");
  await page.goto("/recruiter/pipeline?stage=contacted");
  await expect(page.getByRole("link", { name })).toBeVisible();
});
