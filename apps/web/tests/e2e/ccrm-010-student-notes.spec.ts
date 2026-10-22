import { test, expect } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-010 (DEC-SCOPE-241) -- a counselor writes an internal note on a walk-in student from the walk-in list; the Overseas Admin reads
// it from the Users directory and adds one of their own. Requires the stack running with `python -m app.seed` applied.

test("a counselor writes a note on a student and the Overseas Admin reads it (ccrm-010)", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const student = `Noted Student ${unique}`;

  await signInAsFreshCounselor(page, "ccrm010");
  const created = await page.request.post("/api/v1/counselor/students", { data: { full_name: student, email: `ccrm010-s-${unique}@example.local` } });
  expect(created.status()).toBe(201);

  await page.goto("/overseas/counselor/students");
  await page.getByRole("link", { name: `Notes for ${student}` }).click();
  await expect(page.getByRole("heading", { name: `Notes: ${student}` })).toBeVisible();
  await expect(page.getByText("No notes yet.")).toBeVisible();
  await page.getByLabel("New note").fill("First counselling call.\nWants the UK, September intake.");
  await page.getByRole("button", { name: "Save note" }).click();
  await expect(page.getByText("Note saved.")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Wants the UK, September intake.")).toBeVisible();
  const notesPath = new URL(page.url()).pathname;
  // QA-02: the admin address sends a counselor to their own portal's page; QA-01: a malformed id is a plain 404.
  await page.goto(notesPath.replace("/overseas/counselor/", "/overseas/admin/"));
  await expect(page).toHaveURL(new RegExp(`${notesPath}$`));
  await expect(page.locator(".role-pill")).not.toContainText("Overseas Administrator");
  expect(await page.request.get("/overseas/counselor/students/not-a-uuid/notes").then((r) => r.status())).toBe(404);
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/users");
  await page.getByRole("row").filter({ hasText: student }).getByRole("link", { name: `Notes for ${student}` }).click();
  await expect(page.getByText("Wants the UK, September intake.")).toBeVisible();
  await expect(page.getByText("ccrm010 Counselor")).toBeVisible();
  await page.getByLabel("New note").fill("Escalation reviewed.");
  await page.getByRole("button", { name: "Save note" }).click();
  await expect(page.getByRole("listitem").first()).toContainText("Escalation reviewed.");
  await expect(page.getByText("2 notes")).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
