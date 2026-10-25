import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { activateWalkInStudent, signInAsFreshCounselor } from "./helpers/counselor";
import { E2E_PASSWORD } from "./helpers/welcome";

// ccrm-040 (DEC-SCOPE-275): a counselor archives a walk-in student once the student's application is closed (an open one is refused,
// named), the student leaves the working lists and shows on Archived students; the Overseas Admin restores them (AR1-AR7). The student
// gives both consents on their dashboard and the counselor's 360 shows them (CN2-CN4). Requires the stack with `python -m app.seed`.

const ADMIN = ["overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard"] as const;

async function noSidewaysScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

test("archive with a closed caseload, restore by the admin, and the student's consents (ccrm-040)", async ({ page, request }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  const unique = Date.now();
  const name = `Archive Student ${unique}`;
  const email = `ccrm040-s-${unique}@example.local`;

  const counselorEmail = await signInAsFreshCounselor(page, "ccrm040");
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: name, email, phone: "98765 43210" } });
  expect(created.status()).toBe(201);
  const studentId = (await created.json()).student.id as string;
  const university = (await (await page.request.get("/api/v1/public/universities?limit=1")).json())[0].id as string;
  const application = await page.request.post("/api/v1/workflows/overseas/applications", { data: { university_id: university, student_id: studentId } });
  expect(application.status()).toBe(201);
  const applicationId = (await application.json()).id as string;

  // AR2: an open application blocks the archive, and the refusal names it
  await page.goto(`/overseas/counselor/students/${studentId}`);
  await page.getByRole("button", { name: "Archive student" }).click();
  await page.getByRole("button", { name: "Archive student" }).click();
  await expect(page.locator(".form-error")).toHaveText("Give a reason of at least 3 characters.");
  await page.getByLabel("Reason").fill("Moved to another agency");
  await page.getByRole("button", { name: "Archive student" }).click();
  await expect(page.locator(".form-error")).toContainText("Close or withdraw the student's open applications first: APP-");

  const withdrawn = await page.request.post(`/api/v1/workflows/overseas/applications/${applicationId}/outcome`, { data: { outcome: "withdrawn", reason: "Student withdrew", requested_by: "student" } });
  expect(withdrawn.ok()).toBeTruthy();
  await page.getByRole("button", { name: "Archive student" }).click();
  const banner = page.getByRole("status").filter({ hasText: "Reason: Moved to another agency" });
  await expect(banner).toContainText("Only the Overseas Admin can restore them.");
  await expect(page.getByRole("button", { name: "Restore student" })).toHaveCount(0);

  // AR5/AR7: out of the working lists, on Archived students
  await page.goto("/overseas/counselor/applications");
  await expect(page.getByRole("heading", { name: "Application Tracking" })).toBeVisible();
  await expect(page.getByText(name)).toHaveCount(0);
  await page.getByRole("link", { name: "Archived Students" }).click();
  await expect(page).toHaveURL(/\/overseas\/counselor\/archived-students$/);
  await expect(page.getByRole("link", { name })).toBeVisible();
  await page.setViewportSize({ width: 375, height: 800 });
  await noSidewaysScroll(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.request.post("/api/v1/auth/logout");

  // AR1: only the Overseas Admin restores
  await signIn(page, ...ADMIN);
  await page.goto("/overseas/admin/archived-students");
  const item = page.getByRole("listitem").filter({ has: page.getByRole("link", { name }) });
  await item.getByRole("button", { name: "Restore student" }).click();
  await expect(page.getByRole("link", { name })).toHaveCount(0);
  await page.request.post("/api/v1/auth/logout");

  // CN2/CN3: the student gives both consents on their dashboard (phone width first)
  await activateWalkInStudent(request, email);
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page, email, E2E_PASSWORD, "/overseas/student/dashboard");
  const consent = page.getByRole("form", { name: "Your consent" });
  await expect(consent.getByText("Consent to process my personal data")).toBeVisible();
  await noSidewaysScroll(page);
  for (const box of await consent.getByRole("checkbox", { name: "I agree" }).all()) await box.check();
  await consent.getByRole("button", { name: "Save consent" }).click();
  await expect(page.getByRole("form", { name: "Your consent" })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("form", { name: "Your consent" })).toHaveCount(0);
  expect((await page.request.get("/api/v1/counselor/students/archived")).status()).toBe(403); // a student never lists archives
  await page.request.post("/api/v1/auth/logout");
  await page.setViewportSize({ width: 1280, height: 800 });

  // CN4: the counselor's 360 shows what was given; the restored student is back in their list
  await signIn(page, counselorEmail, E2E_PASSWORD, "/overseas/counselor/dashboard");
  await page.goto(`/overseas/counselor/students/${studentId}`);
  const card = page.locator(".card").filter({ has: page.getByRole("heading", { name: "Consent" }) });
  await expect(card.getByText(/^Given /)).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Archive student" })).toBeVisible();
  expect(errors.filter((e) => !e.includes("status of 409"))).toEqual([]); // the refused archive above is an expected 409
});
