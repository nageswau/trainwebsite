import { test, expect } from "@playwright/test";

import { signInAsFreshCounselor } from "./helpers/counselor";
import { confirmEnrollment } from "./helpers/enrollment";

// ccrm-028 (DEC-SCOPE-265): after enrolment the counselor records the expected arrival date, then confirms arrival (stamped with their
// name) and orientation. A future confirmed date is refused. Requires the stack running with `python -m app.seed` applied; the spec makes
// its own counselor, student and application.

const day = (offset: number) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);

test("the counselor records arrival and orientation on an enrolled application (ccrm-028)", async ({ page }) => {
  test.setTimeout(120_000);
  const consoleErrors: string[] = [];
  // the refused save below is an expected 422, which the browser logs as a failed resource
  page.on("console", (m) => m.type() === "error" && !m.text().includes("status of 422") && consoleErrors.push(m.text()));
  const unique = Date.now();
  const name = `Arriving ${unique}`;

  await signInAsFreshCounselor(page, "ccrm028");
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: name, email: `ccrm028-${unique}@example.local` } });
  expect(created.status()).toBe(201);
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string }[];
  const app = await page.request.post("/api/v1/workflows/overseas/applications", { data: { student_id: (await created.json()).student.id, university_id: universities[0].id, intake: "Fall 2027" } });
  expect(app.status()).toBe(201);
  const id = (await app.json()).id as string;
  await confirmEnrollment(page.request, id);

  await page.goto("/overseas/counselor/applications");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Evaluate Applications" }) }).locator(".card", { hasText: name }).first();
  await card.getByRole("button", { name: "Arrival and orientation" }).click();
  await expect(card.getByText("Arrival not recorded yet.")).toBeVisible();

  await card.getByRole("button", { name: "Record arrival" }).click();
  await expect(card.getByLabel("Orientation attended")).toBeDisabled();
  await card.getByLabel("Arrival date").fill(day(5));
  await card.getByRole("button", { name: "Save arrival" }).click();
  await expect(card.getByText("Arrival saved.")).toBeVisible();
  await expect(card.getByText("Expected arrival date")).toBeVisible();

  await card.getByRole("button", { name: "Edit arrival" }).click();
  await card.getByLabel("Arrival confirmed").check();
  await card.getByRole("button", { name: "Save arrival" }).click();
  await expect(card.getByRole("alert")).toHaveText("A confirmed arrival date cannot be in the future");

  await card.getByLabel("Arrival date").fill(day(0));
  await card.getByLabel("Orientation attended").check();
  await card.getByLabel("Notes (optional)").fill("Confirmed by the student on a call");
  await card.getByRole("button", { name: "Save arrival" }).click();
  await expect(card.getByText("Arrival saved.")).toBeVisible();

  await page.reload();
  const again = page.locator(".action-card", { has: page.getByRole("heading", { name: "Evaluate Applications" }) }).locator(".card", { hasText: name }).first();
  await again.getByRole("button", { name: "Arrival and orientation" }).click();
  await expect(again.getByText(/^Yes -- by /)).toBeVisible();
  await expect(again.getByText("Confirmed by the student on a call")).toBeVisible();

  const view = (await (await page.request.get(`/api/v1/workflows/overseas/applications/${id}/arrival`)).json()).arrival;
  expect([view.arrival_date, view.arrival_confirmed, view.orientation_attended]).toEqual([day(0), true, true]);
  expect(consoleErrors).toEqual([]);
});
