import { expect, test } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-032 (DEC-SCOPE-277, D1-D10): the overseas counselor's action dashboard. A fresh counselor owns nothing, so every section starts
// empty and an overdue task they add shows up -- exact, whatever else the shared stack DB holds.

const SECTIONS = [
  "New and not-contacted leads", "Today's appointments", "Calls logged today", "Follow-ups due", "Overdue tasks", "Leads without a next action",
  "Students with pending documents", "Applications not ready", "Submitted, awaiting decision", "Offer deadlines and conditions",
  "Visa appointments and decisions", "Enrolment and arrival",
];

function day(offset: number): string {
  const d = new Date(Date.now() + 5.5 * 3600_000 + offset * 86_400_000); // India date
  return d.toISOString().slice(0, 10);
}

test("a fresh counselor sees every section empty, then their overdue task", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await signInAsFreshCounselor(page, "ccrm032");
  await expect(page.getByRole("search")).toBeVisible(); // ccrm-012's quick search stays on top
  for (const title of SECTIONS) {
    const region = page.getByRole("region", { name: new RegExp(`^${title.replace(/[()]/g, "\\$&")} 0$`) });
    await expect(region).toBeVisible();
  }
  await expect(page.getByText("No overdue tasks.")).toBeVisible();

  const title = `Chase passport ${Date.now()}`;
  expect((await page.request.post("/api/v1/counselor/tasks", { data: { title, due_on: day(-2), priority: "high" } })).status()).toBe(201);
  expect((await page.request.post("/api/v1/counselor/tasks", { data: { title: `${title} today`, due_on: day(0) } })).status()).toBe(201);
  await page.reload();
  const overdue = page.getByRole("region", { name: /^Overdue tasks 1$/ });
  await expect(overdue.getByRole("link", { name: title, exact: true })).toBeVisible();
  await expect(overdue.getByText("Overdue", { exact: true })).toBeVisible();
  await expect(overdue.getByText("High priority")).toBeVisible();
  await overdue.getByRole("link", { name: title, exact: true }).click();
  await expect(page).toHaveURL(/\/overseas\/counselor\/tasks$/);
  expect(errors).toEqual([]);
});

test("the Overseas Admin's dashboard has no counselor sections and the API refuses them", async ({ page }) => {
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await expect(page.getByRole("region", { name: /^Overdue tasks/ })).toHaveCount(0);
  expect((await page.request.get("/api/v1/counselor/dashboard")).status()).toBe(403);
});

test("the dashboard fits a phone screen without sideways scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signInAsFreshCounselor(page, "ccrm032m");
  await expect(page.getByRole("region", { name: /^Enrolment and arrival/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
