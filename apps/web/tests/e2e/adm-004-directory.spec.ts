import { test, expect } from "@playwright/test";

// ADM-004 -- Directory management: Students, Trainers, Employers. Requires the stack
// running via `docker compose up` with `python -m app.seed` already applied.

test("admin views a role-scoped student directory and edits detail fields (ADM-004-AC01)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");

  // `GET /admin/users` caps at the 500 most-recently-created accounts, and the backend
  // pytest suite has no test-database isolation (creates real, permanent rows in this
  // same shared dev database) -- the long-lived seeded demo student can be pushed out of
  // that window entirely. Create a fresh throwaway student via the real admin API instead
  // of relying on seed data staying visible, same "never depend on shared state that can
  // silently disappear" principle as ADM-005's/ADM-003's own throwaway-record specs.
  const uniqueName = `ADM-004 Directory Student ${Date.now()}`;
  const trainerName = `ADM-004 Directory Trainer ${Date.now()}`;
  const created = await page.request.post("/api/v1/admin/users", {
    data: { role: "it_student", email: `adm004-${Date.now()}@example.com`, full_name: uniqueName, password: "Sup3r-Secret-Pass!" },
  });
  expect(created.ok()).toBeTruthy();
  const createdTrainer = await page.request.post("/api/v1/admin/users", {
    data: { role: "trainer", email: `adm004-trainer-${Date.now()}@example.com`, full_name: trainerName, password: "Sup3r-Secret-Pass!" },
  });
  expect(createdTrainer.ok()).toBeTruthy();

  await page.goto("/it/admin/students");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Directory" }) });
  await panel.getByLabel("Search by name, email, or role").fill("ADM-004 Directory");
  // Role-scoped: the freshly created student shows on the Students directory, the
  // freshly created trainer does not, even though both match the search text.
  await expect(panel.locator("table")).toContainText(uniqueName);
  await expect(panel.locator("table")).not.toContainText(trainerName);

  const row = panel.locator("tr", { hasText: uniqueName });
  await row.getByRole("button", { name: "Edit details" }).click();
  const newPhone = `+91-90000${Date.now() % 100000}`;
  await row.getByLabel("Phone").fill(newPhone);
  await row.getByRole("button", { name: "Save details" }).click();
  await expect(row.getByText("Details updated.")).toBeVisible();

  await row.getByRole("button", { name: "Edit details" }).click();
  await expect(row.getByLabel("Phone")).toHaveValue(newPhone);
});

test("employers directory is an honest empty state, not broken (no EMP-001 accounts yet)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");

  await page.goto("/it/admin/employers");
  await expect(page.getByText(/No employer accounts exist yet/)).toBeVisible();
});

test("directory requires authentication", async ({ page }) => {
  await page.goto("/it/admin/students");
  await expect(page).toHaveURL(/\/it\/login/);
});
