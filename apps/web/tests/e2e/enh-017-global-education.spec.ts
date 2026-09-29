import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-017 (DEC-SCOPE-036): a Coordinator sees a bridged student's high-level stage on the Global Education page, and neither the
// page nor its API response carries application detail planted by the Overseas side (§19). Fixture steps use the admin APIs,
// as sch-010 does; the page under test is driven through the UI.

async function signIn(page: import("@playwright/test").Page, email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("coordinator sees high-level stage only for a bridged student (ENH-017)", async ({ page }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const coordinatorEmail = `enh017-e2e-coord-${unique}@example.local`;
  const studentName = `E2E ENH-017 Student ${unique}`;

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E ENH-017 School ${unique}`);
  await page.fill("#school-coordinator-name", "E2E ENH-017 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.selectOption("#school-tier", "platinum");
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();
  const university = await page.request.post("/api/v1/admin/universities", { data: { country_slug: "usa", slug: `e2e-enh017-${unique}`, name: `PLANTED-UNI-${unique}` } });
  expect(university.ok()).toBeTruthy();
  const universityId = (await university.json()).id as string;

  await signIn(page, coordinatorEmail, E2E_PASSWORD, "/school/coordinator/dashboard");
  await page.goto("/school/coordinator/students");
  await page.fill("#new-full-name", studentName);
  await page.click('button:has-text("Add student")');
  await expect(page.getByRole("row", { name: new RegExp(studentName) })).toBeVisible();
  const studentHref = await page.getByRole("row", { name: new RegExp(studentName) }).getByRole("link", { name: "Timeline" }).getAttribute("href");
  const studentId = studentHref!.split("/").pop()!;

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  const bridged = await page.request.post(`/api/v1/overseas-admin/school-students/${studentId}/applications`, { data: { university_id: universityId, intake: "Fall 2027" } });
  expect(bridged.status()).toBe(201);
  const applicationId = (await bridged.json()).id as string;
  const patched = await page.request.patch(`/api/v1/workflows/overseas/applications/${applicationId}`, {
    data: { application_reference: `PLANTED-REF-${unique}`, next_action: `PLANTED-NEXT-${unique}`, notes: `PLANTED-NOTES-${unique}` },
  });
  expect(patched.ok()).toBeTruthy();
  expect((await page.request.get("/api/v1/school/global-education/pipeline")).status()).toBe(403); // overseas admin is not a school reader

  await signIn(page, coordinatorEmail, E2E_PASSWORD, "/school/coordinator/dashboard");
  await page.getByRole("link", { name: "Global Education" }).first().click();
  await page.waitForURL("**/school/coordinator/global-education");
  await expect(page.getByRole("heading", { level: 1, name: "Global education" })).toBeVisible();
  const row = page.getByRole("row", { name: new RegExp(studentName) });
  await expect(row).toContainText("Global education pathway");
  await expect(page.getByRole("list", { name: "Global education funnel" })).toContainText("Global education pathway1");
  await expect(page.locator("body")).not.toContainText("PLANTED");

  const api = await page.request.get("/api/v1/school/global-education/pipeline");
  expect(api.status()).toBe(200);
  const text = await api.text();
  expect(text).not.toContain("PLANTED");
  expect(text).not.toContain(applicationId);

  await page.selectOption("#pipeline-grade", "12");
  await page.getByRole("button", { name: "Show" }).click();
  await page.waitForURL(/\/school\/coordinator\/global-education\?grade=12/);
  await expect(page.getByText("No students in this grade are on the global education pathway.")).toBeVisible(); // student has no grade
});
