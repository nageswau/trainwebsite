import { test, expect } from "@playwright/test";

// SCH-002 -- School Coordinator bulk student roster upload (template-download-first).
// Requires the stack running via `docker compose up` with `python -m app.seed` already
// applied (seeds an `overseas_admin` account, overseasadmin@edusphere.local/Demo@123).

async function onboardCoordinator(page: import("@playwright/test").Page, unique: number) {
  const coordinatorEmail = `sch002-e2e-coord-${unique}@example.local`;
  await page.goto("/overseas/login");
  await page.fill("#login-email", "overseasadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/admin/dashboard");

  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E SCH-002 School ${unique}`);
  await page.fill("#school-coordinator-name", "E2E Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.click('button:has-text("Create school + seed Coordinator")');
  await expect(page.getByText(/School created\./)).toBeVisible();

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", "ChangeMe@12345");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/coordinator/dashboard");
  return coordinatorEmail;
}

test("coordinator downloads the template, uploads a filled roster, and sees a row-level report (SCH-002)", async ({ page }) => {
  const unique = Date.now();
  await onboardCoordinator(page, unique);

  await page.goto("/school/coordinator/students/bulk-upload");

  // Content-Disposition: attachment triggers a real browser download, not a page
  // navigation/popup -- window.open() with such a response never actually opens a tab.
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.click('button:has-text("Download template (.csv)")'),
  ]);
  expect(download.suggestedFilename()).toBe("school-roster-template.csv");

  const csv = "full_name,date_of_birth,grade_or_class,assigned_teacher_email\nJane Doe,2015-04-12,Grade 5,\n,2015-04-12,Grade 5,\n";
  await page.setInputFiles("#roster-file", { name: "roster.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.click('button:has-text("Upload roster")');

  await expect(page.getByText(/1 of 2 rows accepted, 1 rejected/)).toBeVisible();
  await expect(page.getByRole("cell", { name: "Added" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "Rejected" })).toBeVisible();

  await page.goto("/school/coordinator/students");
  await expect(page.getByRole("cell", { name: "Jane Doe" })).toBeVisible();
});
