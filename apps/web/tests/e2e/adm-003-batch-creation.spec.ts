import { test, expect } from "@playwright/test";

// ADM-003 -- Batch creation and trainer assignment. Requires the stack running via
// `docker compose up`. Creates its own throwaway program and trainer via the real admin
// API and selects them by name in the pickers -- never by dropdown position/index, since
// other specs (ADM-001, etc.) can concurrently create their own programs/trainers in a
// different Playwright worker, and picking "whichever sorts first" can silently grab and
// mutate a different test's own record (found and fixed once already, in this exact file).

test("admin creates a batch by picking program and trainer, no manual reference typing (ADM-003-AC01)", async ({ page, request }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");
  const cookies = await page.context().cookies();
  const access = cookies.find((c) => c.name === "edusphere_access")?.value;

  const programTitle = `ADM-003 E2E Program ${Date.now()}`;
  const program = await request.post("/api/v1/admin/programs", {
    headers: { cookie: `edusphere_access=${access}` },
    data: { slug: `adm-003-e2e-${Date.now()}`, category: "Software Development", title: programTitle, duration: "8 weeks", fees: 5000 },
  });
  expect(program.ok()).toBeTruthy();
  const trainerName = `ADM-003 E2E Trainer ${Date.now()}`;
  const trainer = await request.post("/api/v1/admin/users", {
    headers: { cookie: `edusphere_access=${access}` },
    data: { full_name: trainerName, email: `adm003-trainer-${Date.now()}@example.com`, password: "Sup3r-Secret-Pass!", division: "it", role: "trainer" },
  });
  expect(trainer.ok()).toBeTruthy();

  await page.goto("/it/admin/batches");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Create batch" }) });
  await expect(panel.getByLabel("Assignment reference")).toHaveCount(0);

  const batchName = `E2E Batch ${Date.now()}`;
  await panel.getByLabel("Program").selectOption({ label: programTitle });
  await panel.getByLabel("Trainer (optional)").selectOption({ label: trainerName });
  await panel.getByLabel("Batch name").fill(batchName);
  await panel.getByLabel("Start date").fill(new Date().toISOString().slice(0, 10));
  await panel.getByLabel("End date").fill(new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10));
  await panel.getByLabel("Fixed schedule").fill("Sat-Sun 10am");
  await panel.getByRole("button", { name: "Create batch" }).click();
  await expect(panel.getByText(`Batch "${batchName}" created.`)).toBeVisible();
});

test("a capacity above 20 is rejected by the form's own input constraint (ADM-003-AC02)", async ({ page }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");

  await page.goto("/it/admin/batches");
  const capacityInput = page.locator("#batch-capacity");
  await expect(capacityInput).toHaveAttribute("max", "20");
});

test("batch creation requires authentication", async ({ page }) => {
  await page.goto("/it/admin/batches");
  await expect(page).toHaveURL(/\/it\/login/);
});
