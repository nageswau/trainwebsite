import { expect, test } from "@playwright/test";

import { signIn } from "./helpers/agency";

// ccrm-031 (DEC-SCOPE-272, E1/E7/E8) -- the Overseas Admin finds the escalation threshold among the reminder rules, runs the rules, and
// sees "Overdue by counselor" on Counselor tasks; a row's "View tasks" opens that counselor's overdue tasks. The counselor is refused
// the list. Requires the stack running with `python -m app.seed` applied (rows appear only when some counselor has overdue work).

test("the admin sees overdue work by counselor and the escalation rule (ccrm-031)", async ({ browser }) => {
  test.setTimeout(120_000);
  const consoleErrors: string[] = [];
  const page = await (await browser.newContext()).newPage();
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");

  await page.goto("/overseas/admin/reminder-rules");
  const rule = page.getByRole("form", { name: "Overdue work escalation" });
  await expect(rule.getByLabel("Days overdue before the Overseas Admin is told")).toBeVisible();
  await expect(rule.getByLabel(/Also remind the student/)).toHaveCount(0);
  await page.getByRole("button", { name: "Run reminders now" }).click();
  await expect(page.getByText(/new reminders? · \d+ already sent/)).toBeVisible();

  await page.getByRole("link", { name: "Counselor tasks", exact: true }).click();
  await page.waitForURL("**/overseas/admin/counselor-tasks");
  const section = page.getByRole("region", { name: "Overdue by counselor" });
  await expect(section).toBeVisible();
  await expect(section.getByRole("link", { name: "Reminder rules" })).toHaveAttribute("href", "/overseas/admin/reminder-rules");
  const view = section.getByRole("link", { name: /^View .+'s overdue tasks$/ }).first();
  if (await view.count()) {
    await view.click();
    await page.waitForURL(/counselor=[0-9a-f-]{36}&band=overdue/);
    await expect(page.getByLabel("Show")).toHaveValue("overdue");
  }

  const counselor = await (await browser.newContext()).newPage();
  await signIn(counselor, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");
  const refused = await counselor.request.get("/api/v1/counselor/tasks/overdue-by-counselor");
  expect(refused.status()).toBe(403);
  expect(consoleErrors).toEqual([]);
});
