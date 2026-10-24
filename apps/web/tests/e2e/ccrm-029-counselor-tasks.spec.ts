import { test, expect } from "@playwright/test";

import { signIn } from "./helpers/agency";

// ccrm-029 (DEC-SCOPE-250) -- the Overseas Admin gives the demo counselor a task about one of their students; the counselor sees it in
// Today without an Edit button, adds their own task, marks it done, reopens it and cancels it. Requires the stack running with
// `python -m app.seed` applied. Titles carry a unique stamp so reruns never collide; the spec cancels what it creates.

test("the admin assigns a task and the counselor works their tasks (ccrm-029)", async ({ browser }) => {
  test.setTimeout(120_000);
  const unique = Date.now();
  const adminTitle = `E2E review file ${unique}`;
  const ownTitle = `E2E call the bank ${unique}`;
  const consoleErrors: string[] = [];

  const adminPage = await (await browser.newContext()).newPage();
  adminPage.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  await signIn(adminPage, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await adminPage.goto("/overseas/admin/counselor-tasks");
  await expect(adminPage.getByRole("heading", { name: "Counselor tasks", level: 2 })).toBeVisible();
  const adminForm = adminPage.getByRole("form", { name: "New task" });
  await adminForm.getByLabel("Title").fill(adminTitle);
  await adminForm.getByLabel("Counselor").selectOption({ label: "Ritika Counselor" });
  await expect(adminForm.getByRole("option", { name: /^Ananya Sharma/ })).toBeAttached();
  await adminForm.getByLabel("About (optional)").selectOption({ label: (await adminForm.getByRole("option", { name: /^Ananya Sharma/ }).textContent()) ?? "" });
  await adminForm.getByRole("button", { name: "Add task" }).click();
  await expect(adminForm.getByRole("status")).toHaveText("Task added.");

  const page = await (await browser.newContext()).newPage();
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  await signIn(page, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");
  await page.getByRole("link", { name: "Tasks", exact: true }).click();
  await expect(page.getByRole("heading", { name: "My tasks", level: 2 })).toBeVisible();
  const given = page.getByRole("listitem").filter({ hasText: adminTitle });
  await expect(given).toContainText("Given by Overseas Administrator");
  await expect(given.getByRole("link", { name: /^Ananya Sharma/ })).toBeVisible();
  await expect(given.getByRole("button", { name: "Edit" })).toHaveCount(0);

  const form = page.getByRole("form", { name: "New task" });
  await form.getByRole("button", { name: "Add task" }).click();
  await expect(form.getByText("Give the title (2-200 characters)")).toBeVisible();
  await form.getByLabel("Title").fill(ownTitle);
  await form.getByLabel("Priority").selectOption("high");
  await form.getByRole("button", { name: "Add task" }).click();
  await expect(form.getByRole("status")).toHaveText("Task added.");

  const own = () => page.getByRole("listitem").filter({ hasText: ownTitle });
  await expect(page.locator("section", { has: page.getByRole("heading", { name: /^Today/ }) })).toContainText(ownTitle);
  await own().getByRole("button", { name: "Mark done" }).click();
  await expect(page.locator("section", { has: page.getByRole("heading", { name: /^Done/ }) })).toContainText(ownTitle);
  await own().getByRole("button", { name: "Reopen" }).click();
  await expect(own().getByRole("button", { name: "Mark done" })).toBeVisible();
  for (const title of [ownTitle, adminTitle]) {
    const item = page.getByRole("listitem").filter({ hasText: title });
    await item.getByRole("button", { name: "Cancel task" }).click();
    await item.getByRole("button", { name: "Yes, cancel it" }).click();
    await expect(page.getByRole("listitem").filter({ hasText: title })).toHaveCount(0);
  }
  await expect(page.getByRole("heading", { name: /^Overdue follow-ups/ })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
