import { test, expect } from "@playwright/test";

import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-015 (DEC-SCOPE-244) -- the counselor rejects ONE of a student's applications (AC 9) and puts another on hold, then resumes it;
// the rejected card loses its stage controls and both survive a reload. Requires the stack running with `python -m app.seed`
// applied. The spec makes its own counselor, walk-in student and applications, so no seeded record changes.

test("the counselor records outcomes on one application at a time (ccrm-015)", async ({ page }) => {
  test.setTimeout(90_000);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const studentName = `Outcome ${unique}`;

  await signInAsFreshCounselor(page, "ccrm015");
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: studentName, email: `ccrm015-s-${unique}@example.local` } });
  expect(created.status()).toBe(201);
  const studentId = (await created.json()).student.id as string;
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string; name: string }[];
  // Two universities whose names tell the cards apart (backend test runs leave same-named fixtures behind).
  const a = universities[0];
  const c = universities.find((u) => !u.name.includes(a.name) && !a.name.includes(u.name))!;
  for (const u of [a, c]) {
    const res = await page.request.post("/api/v1/workflows/overseas/applications", { data: { student_id: studentId, university_id: u.id, intake: "Fall 2027" } });
    expect(res.status()).toBe(201);
  }

  await page.goto("/overseas/counselor/applications");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Evaluate Applications" }) });
  const cardFor = (name: string) => panel.locator(".card", { hasText: studentName }).filter({ hasText: name });
  const cardC = cardFor(c.name);
  await expect(cardC).toBeVisible();
  await cardC.getByRole("button", { name: "Record outcome" }).click();
  await cardC.getByLabel("Outcome", { exact: true }).selectOption("rejected");
  await cardC.getByLabel("Reason").fill("Course full");
  await cardC.getByRole("button", { name: "Record outcome" }).click();
  await expect(cardC.getByText(/Outcome recorded: Rejected/)).toBeVisible();
  await expect(cardC.getByText("Rejected -- Course full")).toBeVisible();
  await expect(cardC.getByRole("button", { name: "Advance stage" })).toHaveCount(0);

  const cardA = cardFor(a.name);
  await expect(cardA.getByRole("button", { name: "Advance stage" })).toBeVisible(); // AC 9: A untouched
  await cardA.getByRole("button", { name: "Record outcome" }).click();
  await cardA.getByLabel("Outcome", { exact: true }).selectOption("on_hold");
  await cardA.getByLabel("Review date").fill("2030-01-15");
  await cardA.getByLabel("Reason").fill("Awaiting funds");
  await cardA.getByRole("button", { name: "Record outcome" }).click();
  await expect(cardA.getByText("On hold until 2030-01-15 -- Awaiting funds")).toBeVisible();

  await page.reload();
  await expect(cardFor(c.name).getByText(/only the Overseas Admin can reopen it/)).toBeVisible();
  const heldA = cardFor(a.name);
  await heldA.getByRole("button", { name: "Resume" }).click();
  await heldA.getByLabel("Reason").fill("Funds arrived");
  await heldA.getByRole("button", { name: "Resume" }).click();
  await expect(heldA.getByText("Application resumed.")).toBeVisible();
  await expect(heldA.getByRole("button", { name: "Advance stage" })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
