import { expect, test } from "@playwright/test";

import { signIn } from "./helpers/agency";

// ccrm-030 (DEC-SCOPE-268, RM9/RM10) -- the Overseas Admin opens Reminder rules from the sidebar, is stopped by an out-of-range offset,
// changes one rule and puts it back, and runs the reminders twice (the second run sends nothing new); the counselor is refused. Requires
// the stack running with `python -m app.seed` applied.

test("the admin configures and runs the counselor reminder rules (ccrm-030)", async ({ browser }) => {
  test.setTimeout(120_000);
  const consoleErrors: string[] = [];
  const page = await (await browser.newContext()).newPage();
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.getByRole("link", { name: "Reminder rules", exact: true }).click();
  await page.waitForURL("**/overseas/admin/reminder-rules");
  await expect(page.getByRole("heading", { name: "Reminder rules", level: 2 })).toBeVisible();

  const rule = page.getByRole("form", { name: "Application deadline approaching" });
  const offset = rule.getByLabel("Days before the date");
  const original = await offset.inputValue();
  await offset.fill("99");
  await rule.getByRole("button", { name: "Save" }).click();
  await expect(rule.getByText("Choose a whole number from 0 to 60")).toBeVisible();
  await expect(offset).toBeFocused();

  await offset.fill("10");
  await rule.getByRole("button", { name: "Save" }).click();
  await expect(rule.getByRole("status")).toHaveText("Saved.");
  await page.reload();
  await expect(page.getByRole("form", { name: "Application deadline approaching" }).getByLabel("Days before the date")).toHaveValue("10");
  const again = page.getByRole("form", { name: "Application deadline approaching" });
  await again.getByLabel("Days before the date").fill(original);
  await again.getByRole("button", { name: "Save" }).click();
  await expect(again.getByRole("status")).toHaveText("Saved.");

  await expect(page.getByRole("form", { name: "Offer deadline approaching" }).getByLabel(/Also remind the student/)).toBeVisible();
  await expect(page.getByRole("form", { name: "Application deadline approaching" }).getByLabel(/Also remind the student/)).toHaveCount(0);

  const run = page.getByRole("button", { name: "Run reminders now" });
  await run.click();
  await expect(page.getByText(/new reminders? · \d+ already sent/)).toBeVisible();
  await run.click();
  await expect(page.getByText(/^0 new reminders · \d+ already sent/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent reminders", level: 3 })).toBeVisible();

  const counselor = await (await browser.newContext()).newPage();
  await signIn(counselor, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");
  await counselor.goto("/overseas/admin/reminder-rules");
  await expect(counselor.getByText("Overseas Administrator role required")).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
