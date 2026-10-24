import { test, expect } from "@playwright/test";

import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-008 (DEC-SCOPE-252) -- an overseas counselor converts their own walk-in lead into a student in one step: before Qualified only a
// hint shows; at Qualified the form is prefilled from the lead, the account is created and linked (Application/Enrollment), and the
// lead's city and qualification land in the new student's profile. Requires the stack with `python -m app.seed` applied (Overseas products).
test.describe.configure({ timeout: 240_000 });

const mobile = () => `9${String(Date.now()).slice(-9)}`;

test("a counselor converts a qualified lead into a student with nothing re-typed (ccrm-008)", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && !m.text().includes("status of 409") && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));
  await signInAsFreshCounselor(page, "ccrm008");

  const stamp = Date.now();
  const name = `Convert Lead ${stamp}`;
  const email = `ccrm008-l-${stamp}@example.local`;
  await page.goto("/overseas/counselor/leads/new");
  await page.getByLabel(/Student name/).fill(name);
  await page.getByLabel(/Mobile number/).fill(mobile());
  await page.getByLabel(/^Email/).fill(email);
  await page.getByLabel(/^City/).fill("Kochi");
  await page.getByLabel(/^Qualification/).fill("B.Com");
  const product = page.getByLabel(/Product interest/);
  await expect(product.locator("option").nth(1)).toBeAttached();
  await product.selectOption({ index: 1 });
  await page.getByRole("button", { name: "Create lead" }).click();
  await page.waitForURL(/\/overseas\/counselor\/leads\/[0-9a-f-]{36}$/);

  // before Qualified: a hint, no convert button
  await expect(page.getByText("Move the lead to Qualified to convert it to a new student.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Convert to student" })).toHaveCount(0);

  // move it to Qualified (ccrm-003: a next action first)
  await page.getByRole("button", { name: "Set next action" }).click();
  await page.getByLabel("Action", { exact: true }).fill("Open the student account");
  await page.getByLabel("Due date").fill(new Date(Date.now() + 2 * 86_400_000).toISOString().slice(0, 10));
  await page.getByRole("button", { name: "Save next action" }).click();
  await expect(page.getByText("Next action saved.")).toBeVisible();
  await page.getByRole("button", { name: `Change stage for ${name}` }).click();
  await page.getByLabel(`New stage for ${name}`).selectOption("qualified");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Stage: Qualified", { exact: true })).toBeVisible();

  // convert: prefilled, one click
  await page.getByRole("button", { name: "Convert to student" }).click();
  const form = page.getByRole("form", { name: "Convert to student" });
  await expect(form.getByLabel("Full name")).toHaveValue(name);
  await expect(form.getByLabel("Email")).toHaveValue(email);
  await form.getByRole("button", { name: "Create student account" }).click();
  await expect(page.getByText(`Student account created for ${name}`)).toBeVisible();
  await expect(page.getByText("Stage: Application/Enrollment", { exact: true })).toBeVisible();
  await expect(page.getByText(/Linked to/)).toContainText(name);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();

  // the profile holds the lead's details
  await page.getByRole("link", { name: "Open the student's profile" }).click();
  await expect(page.getByRole("heading", { name: `Profile: ${name}` })).toBeVisible();
  await expect(page.getByLabel("City")).toHaveValue("Kochi");
  await expect(page.getByLabel("Qualification 1 qualification")).toHaveValue("B.Com");

  // the student appears in My students
  await page.goto("/overseas/counselor/students");
  await expect(page.getByText(email).first()).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("phone width: the convert form fits without sideways scroll", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signInAsFreshCounselor(page, "ccrm008m");
  await page.goto("/overseas/counselor/leads/new");
  await page.getByLabel(/Student name/).fill(`Phone Lead ${Date.now()}`);
  await page.getByLabel(/Mobile number/).fill(mobile());
  const product = page.getByLabel(/Product interest/);
  await expect(product.locator("option").nth(1)).toBeAttached();
  await product.selectOption({ index: 1 });
  await page.getByRole("button", { name: "Create lead" }).click();
  await page.waitForURL(/\/overseas\/counselor\/leads\/[0-9a-f-]{36}$/);
  await expect(page.getByText("Move the lead to Qualified to convert it to a new student.")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});
