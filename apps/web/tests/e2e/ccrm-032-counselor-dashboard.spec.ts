import { expect, test } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-032 (DEC-SCOPE-277, D1-D10): the overseas counselor's action dashboard. A fresh counselor owns nothing, so every section starts
// empty and an overdue task they add shows up -- exact, whatever else the shared stack DB holds.

const SECTIONS = [
  "New and not-contacted leads", "Today's appointments", "Calls logged today", "Follow-ups due", "Tasks due", "Leads without a next action",
  "Students with pending documents", "Applications not ready", "Submitted, awaiting decision", "Offer deadlines and conditions",
  "Visa appointments and decisions", "Enrolment and arrival",
];

function today(): string {
  return new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10); // India date
}

test("a fresh counselor sees every section empty, then their new lead and its follow-up", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await signInAsFreshCounselor(page, "ccrm032");
  await expect(page.getByRole("search")).toBeVisible(); // ccrm-012's quick search stays on top
  for (const title of SECTIONS) {
    await expect(page.getByRole("region", { name: new RegExp(`^${title} 0$`) })).toBeVisible();
  }
  await expect(page.getByText("No tasks due in the next 7 days.")).toBeVisible();

  // A task due today is listed, not flagged overdue (ccrm-029 accepts no past due date); a walk-in lead with a follow-up later today shows up.
  const stamp = Date.now();
  expect((await page.request.post("/api/v1/counselor/tasks", { data: { title: `Chase passport ${stamp}`, due_on: today() } })).status()).toBe(201);
  const products = (await (await page.request.get("/api/v1/telecaller/products?group=overseas&active=true&limit=100")).json()).items;
  const phone = `8${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;
  const created = await page.request.post("/api/v1/counselor/walk-in-leads", { data: { name: `Dash Lead ${stamp}`, phone, product_id: products[0].id, source: "walk_in" } });
  expect(created.status(), await created.text()).toBe(201);
  const lead = await created.json();
  const due = new Date(Date.now() + 2 * 60_000).toISOString();
  const fu = await page.request.post(`/api/v1/counselor/leads/${lead.id}/follow-ups`, { data: { due_at: due, reason: "counselor_call", next_action: "Call about the intake" } });
  expect(fu.status(), await fu.text()).toBe(201);

  await page.reload();
  await expect(page.getByRole("region", { name: /^Tasks due 1$/ })).toBeVisible(); // ccrm-042: due this week
  const followUps = page.getByRole("region", { name: /^Follow-ups due 1$/ });
  const link = followUps.getByRole("link", { name: new RegExp(`Dash Lead ${stamp}`) });
  await expect(link).toBeVisible();
  await expect(followUps.getByText("Call about the intake")).toBeVisible();
  await expect(followUps.getByText("Overdue", { exact: true })).toHaveCount(0);
  await link.click();
  await expect(page).toHaveURL(new RegExp(`/overseas/counselor/leads/${lead.id}$`));
  expect(errors).toEqual([]);
});

test("the Overseas Admin's dashboard has no counselor sections and the API refuses them", async ({ page }) => {
  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await expect(page.getByRole("region", { name: /^Tasks due/ })).toHaveCount(0);
  expect((await page.request.get("/api/v1/counselor/dashboard")).status()).toBe(403);
});

test("the dashboard fits a phone screen without sideways scrolling", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signInAsFreshCounselor(page, "ccrm032m");
  await expect(page.getByRole("region", { name: /^Enrolment and arrival/ })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
