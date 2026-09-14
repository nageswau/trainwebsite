import { test, expect, type Page } from "@playwright/test";

// STU-005 -- Support ticket. Requires the stack running via `docker compose up` with
// `python -m app.seed` already applied (seeds the demo IT student and demo IT trainer).
//
// Raises a uniquely-titled ticket per run (rather than acting on "whatever's pending" for
// the shared demo accounts) so this spec stays independent of other concurrently-running
// specs against the same seeded data.

async function loginAs(page: Page, email: string, password: string, dashboardPath: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${dashboardPath}`);
}

test("a student raises a ticket and sees it in their own list (STU-005-AC01)", async ({ page }) => {
  await loginAs(page, "student.it@edusphere.local", "Demo@123", "/it/student/dashboard");
  await page.goto("/it/student/support");

  const subject = `STU-005 Access issue ${Date.now()}`;
  await page.getByLabel("Subject").fill(subject);
  await page.getByLabel("Description").fill("The batch page will not load for me.");
  await page.getByRole("button", { name: "Open support ticket" }).click();
  await expect(page.getByText("Support ticket opened.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Support Tickets" })).toBeVisible();
  await expect(page.getByText(subject)).toBeVisible();
});

test("a trainer sees the ticket in their division queue, even unassigned, and resolves it (STU-005-AC02)", async ({ page }) => {
  const subject = `STU-005 Resolve flow ${Date.now()}`;

  await loginAs(page, "student.it@edusphere.local", "Demo@123", "/it/student/dashboard");
  await page.goto("/it/student/support");
  await page.getByLabel("Subject").fill(subject);
  await page.getByLabel("Description").fill("Please help resolve this test ticket.");
  await page.getByRole("button", { name: "Open support ticket" }).click();
  await expect(page.getByText("Support ticket opened.")).toBeVisible();

  await page.context().clearCookies();
  await loginAs(page, "trainer@edusphere.local", "Demo@123", "/it/trainer/dashboard");
  await page.goto("/it/trainer/support");

  const row = page.locator("tr").filter({ hasText: subject });
  await expect(row).toBeVisible();
  await expect(row.getByText("Unassigned")).toBeVisible();

  await row.getByLabel("Resolution note").fill("Checked and fixed the batch access issue.");
  await row.getByRole("button", { name: "Resolve" }).click();
  await expect(row.getByText("Ticket resolved.")).toBeVisible();
});

test("support ticket workspaces require authentication", async ({ page }) => {
  await page.goto("/it/student/support");
  await expect(page).toHaveURL(/\/it\/login/);
  await page.goto("/it/trainer/support");
  await expect(page).toHaveURL(/\/it\/login/);
});
