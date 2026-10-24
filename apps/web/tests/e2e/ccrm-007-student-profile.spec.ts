import { test, expect } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-007 (DEC-SCOPE-249) -- a counselor fills a walk-in student's structured profile (two qualifications and an IELTS score); the
// Overseas Admin opens it from the Users directory; another counselor gets a 404; the demo student edits their own My profile.
// Requires the stack running with `python -m app.seed` applied.

test("a counselor fills a student's profile, the admin reads it and another counselor cannot (ccrm-007)", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const student = `Profiled Student ${unique}`;

  await signInAsFreshCounselor(page, "ccrm007");
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: student, email: `ccrm007-s-${unique}@example.local` } });
  expect(created.status()).toBe(201);

  await page.goto("/overseas/counselor/students");
  await page.getByRole("link", { name: `Profile for ${student}` }).click();
  await expect(page.getByRole("heading", { name: `Profile: ${student}` })).toBeVisible();
  await expect(page.getByText("No profile saved yet.")).toBeVisible();

  await page.getByLabel("Nationality").fill("Indian");
  await page.getByRole("button", { name: "Add qualification" }).click();
  await page.getByLabel("Qualification 1 level").selectOption("class_12");
  await page.getByLabel("Qualification 1 institution").fill("Narayana Junior College");
  await page.getByLabel("Qualification 1 score type").selectOption("percentage");
  await page.getByLabel("Qualification 1 score", { exact: true }).fill("91.4");
  await page.getByRole("button", { name: "Add qualification" }).click();
  await page.getByLabel("Qualification 2 level").selectOption("bachelor");
  await page.getByLabel("Qualification 2 qualification").fill("B.Tech CSE");
  await page.getByLabel("Qualification 2 score type").selectOption("cgpa");
  await page.getByLabel("Qualification 2 score", { exact: true }).fill("8.2");
  await page.getByLabel("Add a preferred country").selectOption({ label: "United Kingdom" });
  await page.getByRole("button", { name: "Add English test" }).click();
  await page.getByLabel("English test 1 status").selectOption("taken");
  await page.getByLabel("English test 1 overall score").fill("7.5");
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByText("Profile saved.")).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("Qualification 2 qualification")).toHaveValue("B.Tech CSE");
  await expect(page.getByLabel("English test 1 overall score")).toHaveValue("7.5");
  await expect(page.getByRole("listitem", { name: "United Kingdom" })).toBeVisible();
  await expect(page.getByText(/Last saved by ccrm007 Counselor/)).toBeVisible();
  const profilePath = new URL(page.url()).pathname;
  expect(await page.request.get("/overseas/counselor/students/not-a-uuid/profile").then((r) => r.status())).toBe(404);
  await page.request.post("/api/v1/auth/logout");

  await signInAsFreshCounselor(page, "ccrm007b");
  expect(await page.request.get(profilePath.replace("/overseas/counselor/students/", "/api/v1/counselor/students/")).then((r) => r.status())).toBe(404);
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/users");
  await page.getByRole("row").filter({ hasText: student }).getByRole("link", { name: `Profile for ${student}` }).click();
  await expect(page.getByLabel("Qualification 1 institution")).toHaveValue("Narayana Junior College");
  expect(consoleErrors).toEqual([]);
});

test("the overseas student edits their own profile (ccrm-007 P1)", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const city = `Leeds ${Date.now()}`;
  await signIn(page, "student.overseas@edusphere.local", "Demo@123", "/overseas/student/dashboard");
  await page.goto("/overseas/student/profile");
  await expect(page.getByRole("heading", { name: "My profile", level: 3 })).toBeVisible();
  await page.getByLabel("City").fill(city);
  await page.getByRole("button", { name: "Save profile" }).click();
  await expect(page.getByText("Profile saved.")).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("City")).toHaveValue(city);
  await expect(page.getByRole("button", { name: "Account details" })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
