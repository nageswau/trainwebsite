import { expect, test } from "@playwright/test";

import { signInAsFreshCounselor } from "./helpers/counselor";

// ccrm-042 (DEC-SCOPE-316; AC1-AC6): the counselor dashboard's follow-ups and tasks cover overdue + the next 7 days, soonest first. A
// fresh counselor owns nothing, so the counts are exact whatever else the shared stack DB holds.

const DAY = 86_400_000;

function indiaDate(offsetDays: number): string {
  return new Date(Date.now() + 5.5 * 3600_000 + offsetDays * DAY).toISOString().slice(0, 10);
}

test("a follow-up added for later this week shows at once, soonest first, and leaves when done", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await signInAsFreshCounselor(page, "ccrm042");
  const followUps = page.getByRole("region", { name: /^Follow-ups due 0$/ });
  await expect(followUps.getByText("No follow-ups in the next 7 days.")).toBeVisible();
  await expect(followUps.getByText("Overdue or due in the next 7 days, soonest first.")).toBeVisible();

  const stamp = Date.now();
  const products = (await (await page.request.get("/api/v1/telecaller/products?group=overseas&active=true&limit=100")).json()).items;
  const phone = `7${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;
  const created = await page.request.post("/api/v1/counselor/walk-in-leads", { data: { name: `Week Lead ${stamp}`, phone, product_id: products[0].id, source: "walk_in" } });
  expect(created.status(), await created.text()).toBe(201);
  const lead = await created.json();
  const add = (days: number, next_action: string) =>
    page.request.post(`/api/v1/counselor/leads/${lead.id}/follow-ups`, { data: { due_at: new Date(Date.now() + days * DAY).toISOString(), reason: "counselor_call", next_action } });
  const later = await add(5, "Visa chat");
  expect(later.status(), await later.text()).toBe(201);
  expect((await add(2, "Intake call")).status()).toBe(201);
  expect((await add(9, "Too far out")).status()).toBe(201);
  for (const [due_on, title] of [[indiaDate(3), `Week task ${stamp}`], [indiaDate(10), `Far task ${stamp}`]]) {
    expect((await page.request.post("/api/v1/counselor/tasks", { data: { title, due_on } })).status()).toBe(201);
  }

  await page.reload();
  const listed = page.getByRole("region", { name: /^Follow-ups due 2$/ });
  await expect(listed.locator("li")).toHaveCount(2);
  await expect(listed.locator("li").nth(0)).toContainText("Intake call");
  await expect(listed.locator("li").nth(1)).toContainText("Visa chat");
  await expect(listed.getByText("Too far out")).toHaveCount(0);
  await expect(listed.getByText("Overdue", { exact: true })).toHaveCount(0);
  const tasks = page.getByRole("region", { name: /^Tasks due 1$/ });
  await expect(tasks.getByRole("link", { name: `Week task ${stamp}` })).toBeVisible();

  expect((await page.request.post(`/api/v1/counselor/follow-ups/${(await later.json()).id}/complete`, { data: {} })).ok()).toBeTruthy();
  await page.reload();
  await expect(page.getByRole("region", { name: /^Follow-ups due 1$/ })).toBeVisible();
  expect(errors).toEqual([]);
});
