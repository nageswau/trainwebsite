import { test, expect } from "@playwright/test";

import { signIn } from "./helpers/agency";

// ccrm-033 (DEC-SCOPE-271, RR1) -- replacing a student's counsellor needs a reason; the student 360 History shows it. Requires the stack
// running with `python -m app.seed` applied. The spec makes its own counsellors and student (first assignment through the API, no reason).

test("the Overseas Admin gives a reason to replace a student's counsellor and History shows it (ccrm-033)", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const student = `Reason Student ${unique}`;
  const target = `Reason Target ${unique}`;
  const reason = "Student asked for a Hindi-speaking counsellor";

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  const make = (email: string, full_name: string, role: string) =>
    page.request.post("/api/v1/admin/users", { data: { email, full_name, role, division: "overseas" } }).then(async (r) => {
      expect(r.status()).toBe(201);
      const body = await r.json();
      return (body.user ?? body).id as string;
    });
  const first = await make(`ccrm033-a-${unique}@example.local`, `Reason First ${unique}`, "counselor");
  await make(`ccrm033-b-${unique}@example.local`, target, "counselor");
  const studentId = await make(`ccrm033-s-${unique}@example.local`, student, "overseas_student");
  expect((await page.request.put(`/api/v1/admin/users/${studentId}/counselor`, { data: { counselor_id: first } })).ok()).toBeTruthy();

  await page.goto("/overseas/admin/users");
  const row = page.getByRole("row").filter({ hasText: student });
  await row.getByRole("button", { name: "Change counsellor" }).click();
  await page.getByRole("combobox", { name: "EduSphere counsellor" }).fill(target);
  await page.getByRole("option", { name: new RegExp(target) }).click();
  const save = page.getByRole("button", { name: "Save" });
  await expect(save).toBeDisabled(); // no reason yet
  await page.getByRole("textbox", { name: "Reason for the change" }).fill(reason);
  await save.click();
  await expect(page.getByRole("row").filter({ hasText: student }).getByText(target)).toBeVisible();

  await page.goto(`/overseas/admin/students/${studentId}`);
  await page.getByRole("link", { name: "History", exact: true }).click();
  await expect(page.getByText(`Reason: ${reason}`)).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
