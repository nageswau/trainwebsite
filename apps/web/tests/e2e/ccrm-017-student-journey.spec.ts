import { test, expect } from "@playwright/test";

import { signIn } from "./helpers/agency";

// ccrm-017 (DEC-SCOPE-258) -- the counselor's student 360 Overview shows the student's derived journey stage: six steps, the current one
// marked, the state as text, matching the overview API; the Overseas Admin sees the same stage. Uses only seeded accounts. Requires
// `python -m app.seed`.

const LABELS = ["Lead", "Counselling", "Applying", "Offer", "Visa", "Enrolled"];

test("the student 360 shows the derived journey stage (ccrm-017)", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  await signIn(page, "counselor@edusphere.local", "Demo@123", "/overseas/counselor/dashboard");
  await page.goto("/overseas/counselor/students");
  await page.getByRole("link", { name: /^Open / }).first().click();
  await expect(page).toHaveURL(/\/overseas\/counselor\/students\/[0-9a-f-]{36}$/);
  const id = new URL(page.url()).pathname.split("/").pop();
  const { journey } = await (await page.request.get(`/api/v1/counselor/students/${id}/overview`)).json();

  await expect(page.getByRole("heading", { name: `Journey stage: ${journey.label}` })).toBeVisible();
  const steps = page.getByRole("list", { name: "Student journey" }).getByRole("listitem");
  await expect(steps).toHaveCount(6);
  for (const [i, label] of LABELS.entries()) await expect(steps.nth(i)).toContainText(label);
  const current = page.locator('.jny-step[aria-current="step"]');
  await expect(current).toHaveCount(1);
  await expect(current).toContainText(journey.label);
  await expect(current).toContainText("Current");
  if (journey.application) await expect(page.getByText(`Furthest application: ${journey.application.application_code}`)).toBeVisible();

  const tabs = page.getByRole("navigation", { name: "Student record sections" });
  await tabs.getByRole("link", { name: "History" }).click();
  await expect(page.getByRole("list", { name: "Student journey" })).toHaveCount(0); // Overview only

  await page.goto(`/overseas/counselor/students/${id}`);
  await page.setViewportSize({ width: 375, height: 812 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.request.post("/api/v1/auth/logout");

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto(`/overseas/admin/students/${id}`);
  await expect(page.getByRole("heading", { name: `Journey stage: ${journey.label}` })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
