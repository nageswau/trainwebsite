import { test, expect } from "@playwright/test";

import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-013 (DEC-SCOPE-256) -- the counselor opens Application details on the Evaluate Applications card, is stopped by the
// currency-with-fee rule, saves the fields and dates, and they survive a reload. Requires the stack running with `python -m app.seed`
// applied. The spec makes its own counselor, walk-in student and application, so no seeded record changes.

test("the counselor records application details and dates (ccrm-013)", async ({ page }) => {
  test.setTimeout(90_000);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const studentName = `App Details ${unique}`;

  await signInAsFreshCounselor(page, "ccrm013");
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: studentName, email: `ccrm013-s-${unique}@example.local` } });
  expect(created.status()).toBe(201);
  const studentId = (await created.json()).student.id as string;
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string }[];
  const app = await page.request.post("/api/v1/workflows/overseas/applications", { data: { student_id: studentId, university_id: universities[0].id, intake: "Fall 2027" } });
  expect(app.status()).toBe(201);
  const appId = (await app.json()).id as string;

  await page.goto("/overseas/counselor/applications");
  const cardOf = () => page.locator(".action-card", { has: page.getByRole("heading", { name: "Evaluate Applications" }) }).locator(".card", { hasText: studentName }).first();
  const card = cardOf();
  await card.getByRole("button", { name: "Application details" }).click();
  await card.getByRole("button", { name: "Edit details" }).click();

  await card.getByLabel("Faculty").fill("Faculty of Engineering");
  await card.getByLabel("Course start date").fill("2027-09-20");
  await card.getByLabel("Tuition fee").fill("18500");
  await card.getByRole("button", { name: "Save details" }).click();
  await expect(card.getByRole("alert")).toContainText("Currency is required");

  await card.getByLabel("Currency").selectOption("GBP");
  await card.getByLabel("Scholarship", { exact: true }).selectOption("awarded");
  await card.getByLabel("Scholarship amount").fill("2000");
  await card.getByLabel("Application deadline").fill("2026-11-30");
  await card.getByRole("button", { name: "Save details" }).click();
  await expect(card.getByText("Application details saved.")).toBeVisible();
  await expect(card.getByText("GBP 18,500.00")).toBeVisible();
  await expect(card.getByText("Awarded — GBP 2,000.00")).toBeVisible();

  await page.reload();
  const again = cardOf();
  await again.getByRole("button", { name: "Application details" }).click();
  await expect(again.getByText("Faculty of Engineering")).toBeVisible();
  await expect(again.getByText("2026-11-30")).toBeVisible();
  const saved = await (await page.request.get(`/api/v1/workflows/overseas/applications/${appId}/details`)).json();
  expect(saved).toMatchObject({ faculty: "Faculty of Engineering", course_start_date: "2027-09-20", currency: "GBP", scholarship_status: "awarded", application_deadline: "2026-11-30" });
  expect(consoleErrors).toEqual([]);
});
