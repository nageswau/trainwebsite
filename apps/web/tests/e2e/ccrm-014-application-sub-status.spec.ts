import { test, expect } from "@playwright/test";

import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-014 (DEC-SCOPE-238) -- the counselor sets an application's sub-status from the Evaluate Applications card; a later stage's
// sub-status advances the stage, and both survive a reload. Requires the stack running with `python -m app.seed` applied. The spec
// makes its own counselor, walk-in student and application, so no seeded record changes.

test("the counselor moves an application through sub-statuses (ccrm-014)", async ({ page }) => {
  test.setTimeout(60_000); // two saves, a reload and the card list loading twice
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const studentName = `Sub Status ${unique}`;

  await signInAsFreshCounselor(page, "ccrm014");
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: studentName, email: `ccrm014-s-${unique}@example.local` } });
  expect(created.status()).toBe(201);
  const studentId = (await created.json()).student.id as string;
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string }[];
  const app = await page.request.post("/api/v1/workflows/overseas/applications", { data: { student_id: studentId, university_id: universities[0].id, intake: "Fall 2027" } });
  expect(app.status()).toBe(201);

  await page.goto("/overseas/counselor/applications");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Evaluate Applications" }) }).locator(".card", { hasText: studentName });
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Update sub-status" }).click();
  await card.getByLabel("Sub-status", { exact: true }).selectOption("documents_pending");
  await card.getByRole("button", { name: "Update sub-status" }).click();
  await expect(card.getByText(/Sub-status updated to Documents pending/)).toBeVisible();
  await expect(card.getByText("University Selection")).toBeVisible();
  await expect(card.getByText("Documents pending", { exact: true })).toBeVisible();

  await card.getByRole("button", { name: "Update sub-status" }).click();
  await card.getByLabel("Sub-status", { exact: true }).selectOption("conditional_offer");
  await card.getByRole("button", { name: "Update sub-status" }).click();
  await expect(card.getByText(/Sub-status updated to Conditional offer/)).toBeVisible();

  await page.reload();
  const again = page.locator(".action-card", { has: page.getByRole("heading", { name: "Evaluate Applications" }) }).locator(".card", { hasText: studentName });
  await expect(again.getByText("Offer", { exact: true })).toBeVisible();
  await expect(again.getByText("Conditional offer", { exact: true })).toBeVisible();
  const status = await page.request.get(`/api/v1/workflows/overseas/applications/${(await app.json()).id}/status`);
  const history = (await status.json()).history as { to_sub_status: string | null }[];
  expect(history.map((h) => h.to_sub_status).filter(Boolean)).toEqual(["documents_pending", "conditional_offer"]);
  expect(consoleErrors).toEqual([]);
});
