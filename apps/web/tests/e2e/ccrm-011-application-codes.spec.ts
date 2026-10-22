import { test, expect } from "@playwright/test";

import { signIn } from "./helpers/agency";

// ccrm-011 (DEC-SCOPE-238) -- every overseas application shows its APP- code as "EduSphere ID". Requires the stack running with
// `python -m app.seed` applied (the demo counselor has seeded applications).

test("the counselor sees and finds applications by their EduSphere ID (ccrm-011)", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  await signIn(page, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");

  const rows = await (await page.request.get("/api/v1/workflows/overseas/applications")).json();
  expect(rows.length).toBeGreaterThan(0);
  const code: string = rows[0].application_code;
  expect(code).toMatch(/^APP-\d{6,}$/);

  await page.goto("/overseas/counselor/applications");
  await expect(page.getByRole("columnheader", { name: /EduSphere ID/ })).toBeVisible();
  await page.getByLabel("Search records").fill(code);
  await expect(page.getByRole("row").filter({ hasText: code })).toHaveCount(1);

  const found = await (await page.request.get(`/api/v1/lookups/overseas-applications?q=${encodeURIComponent(code.toLowerCase())}`)).json();
  expect(found.items.map((i: { id: string }) => i.id)).toEqual([rows[0].id]);
  expect(consoleErrors).toEqual([]);
});
