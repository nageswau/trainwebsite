import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

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
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();

  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", coordinatorEmail);
  await page.fill("#login-password", E2E_PASSWORD);
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

test("the template carries the Student Master columns after the original seven, and a filled row loads them (ENH-025)", async ({ page }) => {
  const unique = Date.now();
  await onboardCoordinator(page, unique);

  await page.goto("/school/coordinator/students/bulk-upload");
  const [download] = await Promise.all([page.waitForEvent("download"), page.click('button:has-text("Download template (.csv)")')]);
  const header = (await (await download.createReadStream()).toArray()).join("").split(/\r?\n/)[0];
  expect(header.startsWith("full_name,date_of_birth,grade_or_class,assigned_teacher_email,parent_name,parent_email,grade_level,")).toBe(true);
  expect(header).toContain("section,roll_number,gender,student_mobile,city");

  await page.getByText("Column reference").click();
  await expect(page.getByRole("cell", { name: "roll_number" })).toBeVisible();

  const csv = "full_name,grade_level,section,roll_number,gender,city,subjects\nMaster Row,5,A,5,Female,Pune,Maths;Science\nClash Row,5,a,5,male,,\n";
  await page.setInputFiles("#roster-file", { name: "roster.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.click('button:has-text("Upload roster")');
  await expect(page.getByText(/1 of 2 rows accepted, 1 rejected/)).toBeVisible();
  await expect(page.getByRole("cell", { name: /roll_number '5' is already used/ })).toBeVisible();

  await page.goto("/school/coordinator/students");
  const row = page.locator("tr", { hasText: "Master Row" });
  await expect(row.getByRole("cell", { name: "A", exact: true })).toBeVisible();
  await expect(row.getByRole("cell", { name: "5", exact: true })).toBeVisible();
});
