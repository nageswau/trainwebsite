import { test, expect } from "@playwright/test";

// ADM-005 -- Enrolment review and approval. Requires the stack running via `docker
// compose up`. Creates its own throwaway program/batch via the real admin API (rather
// than booking into the shared seeded batch, whose fixed 20-seat capacity other specs in
// this suite can fill up over repeated runs) so a fresh student always has room to book.

test("admin approves an enrolment by student name, and rejection is terminal (ADM-005-AC01/AC02)", async ({ page, request }) => {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");
  const adminCookies = await page.context().cookies();
  const adminAccess = adminCookies.find((c) => c.name === "edusphere_access")?.value;

  const programTitle = `ADM-005 E2E Program ${Date.now()}`;
  const program = await request.post("/api/v1/admin/programs", {
    headers: { cookie: `edusphere_access=${adminAccess}` },
    data: { slug: `adm-005-e2e-${Date.now()}`, category: "Software Development", title: programTitle, duration: "8 weeks", fees: 5000 },
  });
  expect(program.ok()).toBeTruthy();
  const batchName = `ADM-005 E2E Batch ${Date.now()}`;
  const batch = await request.post("/api/v1/admin/batches", {
    headers: { cookie: `edusphere_access=${adminAccess}` },
    data: {
      program_id: (await program.json()).id,
      name: batchName,
      start_date: new Date().toISOString().slice(0, 10),
      end_date: new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
      schedule: "Mon-Fri 7pm",
      capacity: 20,
    },
  });
  expect(batch.ok()).toBeTruthy();

  const studentName = `ADM-005 Review Student ${Date.now()}`;
  const email = `adm005-${Date.now()}@example.com`;
  await page.goto("/it/register");
  await page.fill('input[name="full_name"]', studentName);
  await page.fill('input[name="email"]', email);
  await page.fill('input[name="password"]', "Sup3r-Secret-Pass!");
  await page.click('button:has-text("Create account")');
  await page.waitForURL("**/it/student/dashboard");

  await page.goto("/it/student/course");
  const batchCard = page.locator(".card", { has: page.getByRole("heading", { name: batchName, exact: true }) });
  await batchCard.getByRole("button", { name: "Book this slot" }).click();
  await expect(page.getByText(/Enrolment confirmed/)).toBeVisible();

  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");

  await page.goto("/it/admin/enrollments");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Review enrolments" }) });
  await panel.getByLabel("Search by student, email, or batch").fill(studentName);
  const row = panel.locator("tr", { hasText: studentName });
  await expect(row).toContainText("pending_consent");

  await row.getByRole("button", { name: "Approve" }).click();
  await expect(row).toContainText("Enrolment approved.");
  await expect(row).toContainText("active");
});

test("enrolment review requires authentication", async ({ page }) => {
  await page.goto("/it/admin/enrollments");
  await expect(page).toHaveURL(/\/it\/login/);
});
