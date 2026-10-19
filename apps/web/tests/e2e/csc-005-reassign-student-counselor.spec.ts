import { test, expect } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { signInAsFreshCounselor } from "./helpers/counselor";

// csc-005 (DEC-SCOPE-230) -- the Overseas Admin moves a walk-in student from one counselor to another in the Users directory, with
// AGN-023's picker. Requires the stack running with `python -m app.seed` applied. The spec makes its own counselors and student, so
// the seeded walk-in (csc-001's spec) stays with the demo counselor.

test("the Overseas Admin moves a walk-in student to another counselor (csc-005)", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const student = `Moving Student ${unique}`;
  const target = `Target ${unique} Counselor`;

  await signInAsFreshCounselor(page, "csc005");
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: student, email: `csc005-s-${unique}@example.local` } });
  expect(created.status()).toBe(201);
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  const made = await page.request.post("/api/v1/admin/users", { data: { email: `csc005-t-${unique}@example.local`, full_name: target, role: "counselor", division: "overseas" } });
  expect(made.status()).toBe(201);

  await page.goto("/overseas/admin/users");
  const row = page.getByRole("row").filter({ hasText: student });
  await expect(row.getByText("csc005 Counselor")).toBeVisible();
  await row.getByRole("button", { name: "Change counsellor" }).click();
  await page.getByRole("combobox", { name: "EduSphere counsellor" }).fill(String(unique));
  await page.getByRole("option", { name: new RegExp(target) }).click();
  await page.getByRole("button", { name: "Save" }).click();

  await expect(page.getByRole("row").filter({ hasText: student }).getByText(target)).toBeVisible();
  await page.reload();
  await expect(page.getByRole("row").filter({ hasText: student }).getByText(target)).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
