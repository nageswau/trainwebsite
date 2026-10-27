import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// nehn-039 (spec D2-D4): a Coordinator sees the document statuses of a bridged student's application checklist -- statuses only, no
// notes and no financial items -- and another school's student is a 404. Fixture steps use the admin APIs, as enh-017 does.

async function signIn(page: import("@playwright/test").Page, email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("coordinator sees allowed document statuses for their own student only (nehn-039)", async ({ page }) => {
  test.setTimeout(150_000);
  const unique = Date.now();
  const coordinatorEmail = `nehn039-e2e-coord-${unique}@example.local`;
  const studentName = `E2E nehn-039 Student ${unique}`;

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E nehn-039 School ${unique}`);
  await page.fill("#school-coordinator-name", "E2E nehn-039 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await page.selectOption("#school-tier", "platinum");
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  await expect(page.getByText(/School created\./)).toBeVisible();
  const university = await page.request.post("/api/v1/admin/universities", { data: { country_slug: "usa", slug: `e2e-nehn039-${unique}`, name: `E2E nehn-039 University ${unique}` } });
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
  const checklistUrl = `/api/v1/workflows/overseas/applications/${(await bridged.json()).id}/checklist`;
  const created = await page.request.post(checklistUrl);
  expect(created.status(), await created.text()).toBe(201);
  const itemIds: Record<string, string> = {};
  for (const item of [
    { document_type: "Passport", notes: "PLANTED-NOTE" },
    { document_type: "Transcripts" },
    { document_type: "Financial documents", label: "PLANTED-BANK" },
  ]) {
    const r = await page.request.post(`${checklistUrl}/items`, { data: item });
    expect(r.status(), await r.text()).toBe(201);
    const items = (await r.json()).checklist.items as { id: string; document_type: string }[];
    itemIds[item.document_type] = items.find((i) => i.document_type === item.document_type)!.id;
  }
  expect((await page.request.patch(`${checklistUrl}/items/${itemIds.Passport}`, { data: { mark: "not_required" } })).ok()).toBeTruthy();

  await signIn(page, coordinatorEmail, E2E_PASSWORD, "/school/coordinator/dashboard");
  await page.goto(`/school/coordinator/students/${studentId}`);
  await expect(page.getByRole("heading", { level: 2, name: "Overseas application documents" })).toBeVisible();
  const table = page.getByRole("table", { name: `Documents for E2E nehn-039 University ${unique}` });
  await expect(table.getByRole("row", { name: /Passport Required Not required/ })).toBeVisible();
  await expect(table.getByRole("row", { name: /Transcripts Required Missing/ })).toBeVisible();
  await expect(table.getByRole("row")).toHaveCount(3); // header + 2: the financial item is not shown
  await expect(page.locator("main")).not.toContainText("PLANTED");

  // D4: a student outside this coordinator's scope reads as missing (another school's student: test_nehn_039 AC2).
  const other = await page.request.get("/api/v1/school/students/00000000-0000-0000-0000-000000000000/document-statuses");
  expect(other.status()).toBe(404);
});
