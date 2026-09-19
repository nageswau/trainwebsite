import { test, expect } from "@playwright/test";

// ADM-001 -- User/course/batch administration. Requires the stack running via `docker
// compose up`. Creates its own throwaway program/batch/trainer via the real admin API so
// it never touches the shared seeded program that other specs depend on.

async function loginAsAdmin(page: import("@playwright/test").Page) {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");
}

test("admin can deactivate and reactivate a user with no active dependents (ADM-001-AC01)", async ({ page, request }) => {
  await loginAsAdmin(page);
  const cookies = await page.context().cookies();
  const access = cookies.find((c) => c.name === "edusphere_access")?.value;

  const trainerName = `E2E Trainer ${Date.now()}`;
  const created = await request.post("/api/v1/admin/users", {
    headers: { cookie: `edusphere_access=${access}` },
    data: { full_name: trainerName, email: `trainer-${Date.now()}@example.com`, division: "it", role: "trainer" },
  });
  expect(created.ok()).toBeTruthy();

  await page.goto("/it/admin/users");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Manage users" }) });
  await panel.getByLabel("Search by name, email, or role").fill(trainerName);
  const row = panel.locator("tr", { hasText: trainerName });
  await expect(row).toContainText("Active");
  await row.getByRole("button", { name: "Deactivate" }).click();
  await expect(row).toContainText("Inactive");
  await expect(row.getByRole("button", { name: "Reactivate" })).toBeVisible();
});

test("admin deactivating a program with active batches is blocked until explicitly confirmed (ADM-001-AC02)", async ({ page, request }) => {
  await loginAsAdmin(page);
  const cookies = await page.context().cookies();
  const access = cookies.find((c) => c.name === "edusphere_access")?.value;

  const title = `E2E Program ${Date.now()}`;
  const program = await request.post("/api/v1/admin/programs", {
    headers: { cookie: `edusphere_access=${access}` },
    data: { slug: `e2e-program-${Date.now()}`, category: "Software Development", title, duration: "8 weeks", fees: 5000 },
  });
  expect(program.ok()).toBeTruthy();
  const programId = (await program.json()).id;
  const batch = await request.post("/api/v1/admin/batches", {
    headers: { cookie: `edusphere_access=${access}` },
    data: {
      program_id: programId,
      name: `E2E Batch ${Date.now()}`,
      start_date: new Date().toISOString().slice(0, 10),
      end_date: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
      schedule: "Mon-Fri 7pm",
      status: "active",
    },
  });
  expect(batch.ok()).toBeTruthy();

  await page.goto("/it/admin/programs");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Manage programs" }) });
  await panel.getByLabel("Search by title, category, or slug").fill(title);
  const row = panel.locator("tr", { hasText: title });
  await expect(row).toContainText("Active");

  await row.getByRole("button", { name: "Deactivate" }).click();
  await expect(row).toContainText(/active\/upcoming batch/);
  await expect(row.getByRole("button", { name: "Confirm deactivate" })).toBeVisible();
  await expect(row).toContainText("Active"); // not yet deactivated

  await row.getByRole("button", { name: "Confirm deactivate" }).click();
  await expect(row).toContainText("Inactive");
});

test("admin management requires authentication", async ({ page }) => {
  await page.goto("/it/admin/users");
  await expect(page).toHaveURL(/\/it\/login/);
});

// RAID.md I-31 (ADM-001 follow-up) -- the Create User form's Division/Role fields used to
// offer choices the backend's own division-lock + per-division role allow-list
// (admin.py's `allowed_by_division`) would always reject: a division option for the
// "wrong" side that just 403s after submit, and no reachable way at all for a Super Admin
// to create another Super Admin. Fixed to scope both dropdowns per caller; these three
// cases lock that in.
test("IT Admin's Create user form only offers the IT division and IT roles (RAID.md I-31)", async ({ page }) => {
  await loginAsAdmin(page);
  await page.goto("/it/admin/users");
  const form = page.locator(".action-card", { has: page.getByRole("heading", { name: "Create user" }) });
  const divisionOptions = await form.locator('select[name="division"] option').allTextContents();
  const roleOptions = await form.locator('select[name="role"] option').allTextContents();
  expect(divisionOptions).toEqual(["Select", "it"]);
  expect(roleOptions).toEqual(["Select", "it student", "trainer", "placement team", "hr team", "it admin"]);
});

test("Overseas Admin's Create user form only offers the overseas division and overseas roles (RAID.md I-31)", async ({ page }) => {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/users");
  const form = page.locator(".action-card", { has: page.getByRole("heading", { name: "Create user" }) });
  const divisionOptions = await form.locator('select[name="division"] option').allTextContents();
  const roleOptions = await form.locator('select[name="role"] option').allTextContents();
  expect(divisionOptions).toEqual(["Select", "overseas"]);
  expect(roleOptions).toEqual(["Select", "overseas student", "counselor", "university rep", "agent", "overseas admin"]);
});

test("Super Admin sees every division/role and can create another Super Admin through the real form (RAID.md I-31)", async ({ page }) => {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");

  await page.goto("/admin/users");
  const form = page.locator(".action-card", { has: page.getByRole("heading", { name: "Create user" }) });
  const divisionOptions = await form.locator('select[name="division"] option').allTextContents();
  const roleOptions = await form.locator('select[name="role"] option').allTextContents();
  expect(divisionOptions).toEqual(["Select", "it", "overseas", "global"]);
  expect(roleOptions).toEqual(["Select", "it student", "trainer", "placement team", "hr team", "it admin", "overseas student", "counselor", "university rep", "agent", "overseas admin", "super admin"]);

  const email = `e2e-second-super-admin-${Date.now()}@example.com`;
  await form.locator('input[name="full_name"]').fill("E2E Second Super Admin");
  await form.locator('input[name="email"]').fill(email);
  await form.locator('select[name="division"]').selectOption("global");
  await form.locator('select[name="role"]').selectOption("super_admin");
  await form.getByRole("button", { name: "Create user" }).click();
  await expect(form.getByText("User created.")).toBeVisible();
});
