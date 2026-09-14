import { test, expect } from "@playwright/test";

// TRN-005 -- Assignment create and edit. Requires the stack running via `docker compose
// up` with `python -m app.seed` already applied (seeds assignments for the demo
// trainer's batch).

test("trainer can create and then edit an assignment, selected by name not a raw ID (TRN-005-AC01)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "trainer@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/trainer/dashboard");

  await page.goto("/it/trainer/assignments");
  const title = `E2E Assignment ${Date.now()}`;
  await page.getByLabel("Batch").selectOption({ index: 1 });
  await page.getByLabel("Title").fill(title);
  await page.getByLabel("Due date and time").fill("2026-12-01T10:00");
  await page.getByRole("button", { name: "Create assignment" }).click();
  await expect(page.getByText("Assignment created.")).toBeVisible();

  const optionValue = await page.locator("#assignment-edit-select option", { hasText: title }).getAttribute("value");
  await page.locator("#assignment-edit-select").selectOption(optionValue!);
  const newTitle = `${title} (edited)`;
  await page.locator("#assignment-edit-title").fill(newTitle);
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Assignment updated.")).toBeVisible();
});

test("assignment editing requires authentication", async ({ page }) => {
  await page.goto("/it/trainer/assignments");
  await expect(page).toHaveURL(/\/it\/login/);
});
