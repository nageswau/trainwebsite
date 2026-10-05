import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-015 (DEC-SCOPE-037 provisional): a Coordinator downloads the School Summary PDF from the Reports page, a Parent downloads
// their own child's Progress Report from the child page, and the same Parent cannot fetch an unlinked sibling's report or the
// school-wide report. Fixture steps use the APIs, as sch-007 does; the downloads are driven through the UI.

async function signIn(page: import("@playwright/test").Page, email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("coordinator downloads the school report; parent downloads only their own child's report (ENH-015)", async ({ page }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const coordinatorEmail = `enh015-e2e-coord-${unique}@example.local`;
  const parentEmail = `enh015-e2e-parent-${unique}@example.local`;

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E ENH-015 School ${unique}`);
  await page.fill("#school-coordinator-name", "E2E ENH-015 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.selectOption("#school-tier", "platinum");
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();

  await signIn(page, coordinatorEmail, E2E_PASSWORD, "/school/coordinator/dashboard");
  const linkedRes = await page.request.post("/api/v1/school/students", { data: { full_name: "ENH015 Linked Child", grade_or_class: "Grade 9", parent_name: "E2E ENH015 Parent", parent_email: parentEmail } });
  expect(linkedRes.status()).toBe(201);
  const linked = await linkedRes.json();
  const unlinked = await (await page.request.post("/api/v1/school/students", { data: { full_name: "ENH015 Unlinked Sibling", grade_or_class: "Grade 10" } })).json();

  // Coordinator: the Reports page's download button saves school-report.pdf.
  await page.goto("/school/coordinator/reports");
  await expect(page.getByRole("heading", { level: 2, name: "Download reports" })).toBeVisible();
  const [schoolDownload] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download school report (PDF)" }).click()]);
  expect(schoolDownload.suggestedFilename()).toBe("school-report.pdf");
  await expect(page.getByRole("status")).toContainText("Report downloaded.");

  // Parent: accept the invite, download the linked child's report from the child page.
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${linked.development_invite_token}/accept`);
  await page.fill("#invite-password", E2E_PASSWORD);
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/parent/dashboard");
  await page.goto(`/school/parent/children/${linked.id}`);
  const [childDownload] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download progress report (PDF)" }).click()]);
  expect(childDownload.suggestedFilename()).toBe("progress-report.pdf");

  // The same parent is refused the sibling's report and the school-wide report.
  expect((await page.request.get(`/api/v1/school/students/${unlinked.id}/progress-report`)).status()).toBe(403);
  expect((await page.request.get("/api/v1/school/reports/school-summary")).status()).toBe(403);
});
