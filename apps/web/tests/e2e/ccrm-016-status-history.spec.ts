import { test, expect } from "@playwright/test";

import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-016 (DEC-SCOPE-247) -- the counselor opens an application's status history on the Evaluate Applications card and sees each change
// with its author, sub-status, outcome and reason (AC 6); the open history reloads after a write on the card. Requires the stack running
// with `python -m app.seed` applied. The spec makes its own counselor, walk-in student and application, so no seeded record changes.

test("the counselor reads who changed an application and why (ccrm-016)", async ({ page }) => {
  test.setTimeout(90_000);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const studentName = `Status History ${unique}`;

  await signInAsFreshCounselor(page, "ccrm016"); // full name "ccrm016 Counselor"
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: studentName, email: `ccrm016-s-${unique}@example.local` } });
  expect(created.status()).toBe(201);
  const studentId = (await created.json()).student.id as string;
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string }[];
  const app = await page.request.post("/api/v1/workflows/overseas/applications", { data: { student_id: studentId, university_id: universities[0].id, intake: "Fall 2027" } });
  expect(app.status()).toBe(201);
  const appId = (await app.json()).id as string;
  const base = `/api/v1/workflows/overseas/applications/${appId}`;
  expect((await page.request.post(`${base}/advance`, { data: { to_status: "university_selection" } })).ok()).toBeTruthy();
  expect((await page.request.post(`${base}/sub-status`, { data: { sub_status: "documents_pending" } })).ok()).toBeTruthy();
  const review = new Date(Date.now() + 7 * 86_400_000).toISOString().slice(0, 10);
  expect((await page.request.post(`${base}/outcome`, { data: { outcome: "on_hold", reason: "Awaiting funds", review_date: review } })).ok()).toBeTruthy();

  await page.goto("/overseas/counselor/applications");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Evaluate Applications" }) }).locator(".card", { hasText: studentName }).first();
  const toggle = card.getByRole("button", { name: "Status history" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.click();
  const list = card.getByRole("list", { name: "Status history" });
  await expect(list.getByRole("listitem").last()).toContainText("On hold");
  await expect(list.getByRole("listitem").last()).toContainText("Outcome: On hold -- Awaiting funds");
  await expect(list).toContainText("Enquiry → University selection");
  await expect(list.getByRole("listitem").filter({ hasText: "University selection (Documents pending)" })).toHaveCount(2); // the move, then the hold
  await expect(list.getByRole("listitem").last()).toContainText("ccrm016 Counselor");

  await card.getByRole("button", { name: "Resume" }).click(); // ReopenOutcomeButton: a reason prompt
  await card.getByLabel("Reason").fill("Funds arrived");
  await card.getByRole("form", { name: "Resume application" }).getByRole("button", { name: "Resume" }).click();
  await expect(list.getByRole("listitem").last()).toContainText("Resumed (On hold) -- Funds arrived");
  await expect(list.getByRole("listitem").last()).toContainText("Cleared");

  await card.getByRole("button", { name: "Hide status history" }).click();
  await expect(card.getByRole("list", { name: "Status history" })).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});
