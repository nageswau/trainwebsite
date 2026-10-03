import { test, expect } from "@playwright/test";

import { registerApprovedAgency, signIn } from "./helpers/agency";

// AGN-022 (DEC-SCOPE-063) -- Overseas Admin opens the agent network from the sidebar, finds a fresh agency, reads its figures and
// students, suspends it (the Master is denied on the next request), then reinstates it. Requires the stack running with
// `python -m app.seed` applied (seeds the overseas admin).

const ADMIN = { email: "overseasadmin@edusphere.local", password: "Demo@123" };

test("Overseas Admin reads an agency in the network and suspends then reinstates it (AGN-022 AC4, AC9)", async ({ page }) => {
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique, "agn022");
  const agency = `Sigma Overseas agn022 ${unique}`;

  await page.getByRole("link", { name: "Agent network" }).first().click();
  await expect(page.getByRole("heading", { level: 2, name: "Agent network" })).toBeVisible();
  await page.getByLabel("Search agencies").fill(agency);
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("link", { name: new RegExp(agency) }).click();

  await expect(page.getByRole("heading", { level: 2, name: new RegExp(agency) })).toBeVisible();
  const figures = page.getByRole("list", { name: "Agency figures" });
  await expect(figures.getByText("Students")).toBeVisible();
  await page.getByRole("button", { name: "Students", exact: true }).click();
  await expect(page.getByText("No students yet.")).toBeVisible();

  await page.getByRole("button", { name: `Suspend ${agency}` }).click();
  await page.getByRole("button", { name: "Confirm suspend" }).click();
  await expect(page.getByText(`${agency} suspended.`)).toBeVisible();
  await expect(page.getByRole("button", { name: `Reinstate ${agency}` })).toBeFocused();

  await signIn(page, masterEmail, "Sup3r-Secret-Pass!", "/overseas/agent/dashboard");
  await expect(page.getByText("Your agency's account is suspended")).toBeVisible();

  await signIn(page, ADMIN.email, ADMIN.password, "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/agent-network?tab=suspended");
  await page.getByLabel("Search agencies").fill(agency);
  await page.getByRole("button", { name: "Search" }).click();
  await page.getByRole("link", { name: new RegExp(agency) }).click();
  await page.getByRole("button", { name: `Reinstate ${agency}` }).click();
  await expect(page.getByText(`${agency} reinstated.`)).toBeVisible();

  await signIn(page, masterEmail, "Sup3r-Secret-Pass!", "/overseas/agent/dashboard");
  await expect(page.getByText("Your agency's account is suspended")).not.toBeVisible();
});

test("the network pages fit a phone without sideways scrolling, and a crafted id is not found (AGN-022 AC10, AC11)", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await signIn(page, ADMIN.email, ADMIN.password, "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/agent-network");
  await expect(page.getByRole("heading", { level: 2, name: "Agent network" })).toBeVisible();
  await expect(page.getByText("Loading agencies…")).not.toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);

  const response = await page.goto("/overseas/admin/agent-network/not-a-uuid");
  expect(response?.status()).toBe(404);
});

// Browser QA22-01 / QA22-02: a table that fits its page can still hide columns inside its own scroll box; measure the boxes.
const tableOverflow = () => [...document.querySelectorAll(".table-scroll")].map((e) => e.scrollWidth - e.clientWidth);

test("on a tablet the agencies table shows every column without scrolling sideways (QA22-01)", async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await signIn(page, ADMIN.email, ADMIN.password, "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/agent-network");
  await expect(page.locator("tbody tr").first()).toBeVisible();
  expect(await page.evaluate(tableOverflow)).toEqual([0]);
  expect(await page.locator("tbody tr").first().locator('td[data-label="Enrollments"]').isVisible()).toBe(true);
});

test("on a phone the agency's commission table shows the amount column (QA22-02)", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await signIn(page, ADMIN.email, ADMIN.password, "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/agent-network");
  await page.locator("tbody tr").first().getByRole("link").click();
  const commission = page.getByRole("table", { name: "Commission" });
  await expect(commission).toBeVisible();
  for (const overflow of await page.evaluate(tableOverflow)) expect(overflow).toBe(0);
  await expect(commission.locator('td[data-label="Amount"]').first()).toBeVisible();
});
