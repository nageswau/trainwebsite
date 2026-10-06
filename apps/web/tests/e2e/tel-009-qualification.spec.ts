import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-009 (spec §5 AC1-AC4; QF1): an overseas telecaller qualifies their own lead -- Overseas, UK, Masters, intake Sep 2027. A 120%
// is refused in place; the shared city writes through to Lead details; switching the product to an IT course swaps the section and
// switching back shows the overseas values again (kept but hidden, AC3).
test.describe.configure({ timeout: 120_000 });

async function telecaller(page: Page, stamp: number) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E Qual Manager ${stamp}`, email: `tel009-m-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E Qual Telecaller ${stamp}`, email: `tel009-t-${stamp}@example.local`,
      telecaller_profile: { team: "overseas", employee_id: `QF-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, caller.development_welcome_token);
  return caller;
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test("a telecaller qualifies an overseas lead and the section follows the product", async ({ page }) => {
  const stamp = Date.now();
  const caller = await telecaller(page, stamp);
  await page.goto("/overseas/login");
  await page.fill("#login-email", caller.email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/telecaller/dashboard");

  const product = async (group: string, name: string) =>
    (await (await page.request.get(`/api/v1/telecaller/products?group=${group}&active=true&limit=100`)).json()).items.find((p: { name: string }) => p.name === name);
  const uk = await product("overseas", "UK");
  const name = `Qualify Lead ${stamp}`;
  const created = await page.request.post("/api/v1/telecaller/leads", {
    data: { name, phone: `8${String(stamp).slice(-9)}`, product_id: uk.id, source: "walk_in" },
  });
  expect(created.status(), await created.text()).toBe(201);
  const { id } = await created.json();

  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));
  await page.goto(`/telecaller/leads/${id}`);
  await expect(page.getByRole("heading", { name })).toBeVisible();
  const section = page.getByRole("region", { name: "Qualification" });
  await section.getByRole("button", { name: "Edit qualification" }).click();
  await expect(section.getByRole("group", { name: "Basic qualification" })).toBeVisible();
  await expect(section.getByRole("group", { name: "IT training requirement" })).toHaveCount(0);
  const overseas = section.getByRole("group", { name: "Overseas requirement" });
  await section.getByLabel("Qualification").fill("B.Tech");
  await section.getByLabel("City").fill("Chennai");
  await overseas.getByLabel("UG / Master's").selectOption("masters");
  await overseas.getByLabel("Preferred course").fill("MSc Data Science");
  await overseas.getByLabel("Intake").fill("Sep 2027");
  await overseas.getByLabel("Academic percentage").fill("120");
  await section.getByRole("button", { name: "Save qualification" }).click();
  await expect(section.getByText("Enter a percentage from 0 to 100.")).toBeVisible();
  await expect(overseas.getByLabel("Academic percentage")).toHaveAttribute("aria-invalid", "true");
  await overseas.getByLabel("Academic percentage").fill("72.5");
  await section.getByRole("button", { name: "Save qualification" }).click();
  await expect(section.getByText("Qualification saved.")).toBeVisible();
  await expect(section.getByText("Sep 2027")).toBeVisible();
  // QD1: the shared city reaches Lead details at once
  await expect(page.getByRole("region", { name: "Lead details" }).getByText("Chennai")).toBeVisible();

  await page.reload(); // stored, not just shown
  await expect(section.getByText("MSc Data Science")).toBeVisible();
  await expect(section.getByText("Masters")).toBeVisible();
  for (const width of [375, 768]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await noSideScroll(page), `no side scroll at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 900 });

  // AC3: the product moves to an IT course -> the IT section; back to UK -> the overseas values are still there
  await page.getByRole("button", { name: "Edit details" }).click();
  await page.getByLabel("Product interest").selectOption({ label: "Java" });
  await page.getByRole("button", { name: "Save details" }).click();
  await expect(page.getByText("Details saved.")).toBeVisible();
  await expect(section.getByText("IT training requirement")).toBeVisible();
  await expect(section.getByText("Sep 2027")).toHaveCount(0);
  await page.getByRole("button", { name: "Edit details" }).click();
  await page.getByLabel("Product interest").selectOption({ label: "UK" });
  await page.getByRole("button", { name: "Save details" }).click();
  await expect(section.getByText("Sep 2027")).toBeVisible();
  expect(consoleErrors).toEqual([]);
});
