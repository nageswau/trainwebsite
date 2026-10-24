import { test, expect } from "@playwright/test";

import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-019 (DEC-SCOPE-257) -- AC 5 in block mode: the counselor creates the application's checklist from the matching admission
// template, Ready for Submission is refused with the missing items listed, and once every required item is complete it is accepted.
// Requires the stack running with `python -m app.seed` applied. The spec makes its own counselor, walk-in student, application and a
// template scoped to a per-run intake, so no seeded record or other spec's template changes.

test("the checklist gate blocks Ready for Submission until the required items are complete (ccrm-019)", async ({ page }) => {
  test.setTimeout(90_000);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const studentName = `Checklist Gate ${unique}`;
  const intake = `E2E ${unique}`;

  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string; country_id: string }[];
  const university = universities[0];
  await page.request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } });
  const template = await page.request.post("/api/v1/overseas-admin/checklists", {
    data: {
      name: `E2E admission ${unique}`, kind: "admission", country_id: university.country_id, university_id: null, course_level: null, intake, gate_mode: "block", notes: null,
      items: [
        { document_type: "Passport", label: null, required: true, allowed_statuses: [], notes: null },
        { document_type: "Other", label: "Bank letter", required: true, allowed_statuses: [], notes: null },
      ],
    },
  });
  expect(template.status()).toBe(201);

  await signInAsFreshCounselor(page, "ccrm019");
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: studentName, email: `ccrm019-s-${unique}@example.local` } });
  expect(created.status()).toBe(201);
  const studentId = (await created.json()).student.id as string;
  const app = await page.request.post("/api/v1/workflows/overseas/applications", { data: { student_id: studentId, university_id: university.id, intake } });
  expect(app.status()).toBe(201);

  await page.goto("/overseas/counselor/applications");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Evaluate Applications" }) }).locator(".card", { hasText: studentName }).first();
  await card.getByRole("button", { name: "Document checklist" }).click();
  await card.getByRole("button", { name: /Create checklist from E2E admission/ }).click();
  await expect(card.getByText("0 of 2 required complete")).toBeVisible();

  await card.getByRole("button", { name: "Update sub-status" }).click();
  await card.getByLabel("Sub-status", { exact: true }).selectOption("ready_for_submission");
  await card.getByRole("button", { name: "Update sub-status" }).click();
  await expect(card.getByRole("alert").filter({ hasText: "needs every required checklist document complete" })).toBeVisible();
  await expect(card.getByText("Bank letter — Missing")).toBeVisible();

  const checklist = card.getByRole("region", { name: "Document checklist" });
  for (const name of ["Passport", "Bank letter"]) {
    await checklist.locator("li", { hasText: name }).getByRole("button", { name: "Mark not required" }).click();
    await expect(checklist.locator("li", { hasText: name }).getByText("Not required", { exact: true })).toBeVisible();
  }
  await expect(card.getByText("2 of 2 required complete")).toBeVisible();

  await card.getByLabel("Sub-status", { exact: true }).selectOption("ready_for_submission");
  await card.getByRole("button", { name: "Update sub-status" }).click();
  await expect(card.getByText(/Sub-status updated to Ready for submission/)).toBeVisible();
  await expect(card.getByText("Ready for submission", { exact: true })).toBeVisible();
  // the browser logs the gate's deliberate 409 as a failed resource; anything else is a defect
  expect(consoleErrors.filter((e) => !e.includes("status of 409"))).toEqual([]);
});
