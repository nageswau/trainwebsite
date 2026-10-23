import { test, expect } from "@playwright/test";

import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-012 (DEC-SCOPE-246) -- the overseas counselor's quick search finds their own student by phone and never another counselor's
// (backlog acceptance); the Leads and Applications lists keep their new filters in the URL. Requires the stack with `python -m app.seed`.

test("quick search stays inside the counselor's caseload and the lists filter (ccrm-012)", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const digits = String(unique).slice(-8);
  const theirs = `9${digits}1`;
  const mine = `8${digits}2`;

  await signInAsFreshCounselor(page, "ccrm012b");
  expect((await page.request.post("/api/v1/counselor/students", { data: { full_name: `Their Student ${unique}`, email: `ccrm012-b-${unique}@example.local`, phone: theirs } })).status()).toBe(201);
  await page.request.post("/api/v1/auth/logout");

  await signInAsFreshCounselor(page, "ccrm012a");
  const student = `Searchable Student ${unique}`;
  expect((await page.request.post("/api/v1/counselor/students", { data: { full_name: student, email: `ccrm012-a-${unique}@example.local`, phone: mine } })).status()).toBe(201);

  await page.goto("/overseas/counselor/dashboard");
  const box = page.getByLabel("Name, phone, email or ID");
  await box.fill(`+91 ${theirs.slice(0, 5)} ${theirs.slice(5)}`);
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByText(/Nothing in your leads, students or applications matches/)).toBeVisible();

  await box.fill(mine.slice(0, 5) + "-" + mine.slice(5));
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.getByRole("heading", { name: "Students (1)" })).toBeVisible();
  await page.getByRole("link", { name: student }).click();
  await expect(page.getByRole("heading", { name: `Notes: ${student}` })).toBeVisible();

  await page.goto("/overseas/counselor/leads");
  await page.getByLabel("Priority").selectOption("hot");
  await expect(page).toHaveURL(/\/overseas\/counselor\/leads\?priority=hot$/);
  await expect(page.getByText("No leads match these filters.")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Priority")).toHaveValue("hot");
  await page.getByRole("link", { name: "Clear filters" }).click();
  await expect(page.getByText("No leads have been handed to you yet.")).toBeVisible();

  await page.goto("/overseas/counselor/applications");
  await page.getByLabel("Stage").selectOption("offer");
  await expect(page).toHaveURL(/\/overseas\/counselor\/applications\?stage=offer$/);
  await expect(page.getByRole("heading", { name: "No applications match these filters" })).toBeVisible();
  await page.goto("/overseas/counselor/applications?from=2026-03-01&to=2026-02-01");
  await expect(page.locator("p.form-error[role=alert]")).toContainText("The start date must be on or before the end date -- showing all applications.");
  expect(consoleErrors).toEqual([]);
});
