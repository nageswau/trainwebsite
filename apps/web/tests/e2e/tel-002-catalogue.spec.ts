import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-002 (AC1-AC4, P1-P4): a telecaller manager maintains the product catalogue and campaigns; a telecaller can read but not write.
// Throwaway accounts via the real admin API; every name carries a stamp because the database is shared.

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function accounts(page: Page, stamp: number) {
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E Cat Manager ${stamp}`, email: `tel002-m-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E Cat Telecaller ${stamp}`, email: `tel002-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `TC-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, manager.development_welcome_token);
  await activateWithToken(page.request, caller.development_welcome_token);
  return { manager, caller };
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test("manager: seeded products, create + deactivate a product, campaign with date rule; telecaller reads only", async ({ page }) => {
  test.setTimeout(60_000);
  const stamp = Date.now();
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  const { manager, caller } = await accounts(page, stamp);

  await signIn(page, "admin", manager.email, "/telecaller/manager/team");
  await page.getByRole("link", { name: "Products" }).first().click();
  await page.waitForURL("**/telecaller/manager/products");
  await page.getByLabel("Show").selectOption("other");
  const guidance = page.getByRole("row", { name: /^Career Guidance/ });
  await expect(guidance).toContainText("Unassigned queue"); // AC1 / T18
  await expect(page.getByRole("row", { name: /^Job Assistance/ })).toContainText("IT");

  const product = `E2E Coaching ${stamp}`;
  await page.getByLabel("Group (required)").selectOption("other");
  await page.getByLabel("Name (required)").fill(product);
  await page.getByLabel("Team", { exact: true }).selectOption("overseas");
  await page.getByRole("button", { name: "Create product" }).click();
  await expect(page.getByText(`Created ${product}.`)).toBeVisible();
  await page.getByRole("button", { name: `Deactivate ${product}` }).click();
  await page.getByRole("button", { name: "Confirm deactivate" }).click();
  await expect(page.getByText(`Deactivated ${product}.`)).toBeVisible();

  await page.getByRole("link", { name: "Campaigns" }).first().click();
  await page.waitForURL("**/telecaller/manager/campaigns");
  const picker = page.getByLabel("Product (required)");
  await expect(picker.locator("option", { hasText: "Cyber Security" })).toHaveCount(1);
  await expect(picker.locator("option", { hasText: product })).toHaveCount(0); // AC2: gone from pickers
  const campaign = `E2E Sep 2026 Cyber Security ${stamp}`;
  await page.getByLabel("Campaign name (required)").fill(campaign);
  await page.getByLabel("Source (required)").selectOption("instagram");
  await picker.selectOption({ label: "Cyber Security" });
  await page.getByLabel("Start date (required)").fill("2026-09-30");
  await page.getByLabel("End date").fill("2026-09-01");
  await page.getByRole("button", { name: "Create campaign" }).click();
  await expect(page.getByText("End date cannot be before the start date")).toBeVisible(); // AC4
  await page.getByLabel("Start date (required)").fill("2026-09-01");
  await page.getByLabel("End date").fill("2026-09-30");
  await page.getByRole("button", { name: "Create campaign" }).click();
  await expect(page.getByText(`Created ${campaign}.`)).toBeVisible();
  await page.getByRole("searchbox", { name: "Search campaigns" }).fill(String(stamp));
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByRole("row", { name: new RegExp(campaign) })).toContainText("Instagram");

  // Refresh keeps the page working; tablet and phone widths never scroll sideways.
  await page.reload();
  await expect(page.getByRole("heading", { name: "Campaigns", level: 2 })).toBeVisible();
  for (const [width, height] of [[768, 1024], [390, 844]]) {
    await page.setViewportSize({ width, height });
    for (const path of ["/telecaller/manager/campaigns", "/telecaller/manager/products"]) {
      await page.goto(path);
      await expect(page.getByRole("region", { name: path.endsWith("products") ? "Products" : "Campaigns" })).toBeVisible();
      expect(await noSideScroll(page), `${path} at ${width}px`).toBe(true);
      // QA-02: the list comes first below 980px, so its card links to the create form.
      await page.getByRole("link", { name: path.endsWith("products") ? "Create product" : "Create campaign" }).click();
      await expect(page.locator(path.endsWith("products") ? "#prod-group" : "#camp-name")).toBeFocused();
    }
  }
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.request.post("/api/v1/auth/logout");

  // P1 / AC5: a telecaller reads active rows only and cannot write; the manager pages refuse it.
  await signIn(page, "it", caller.email, "/telecaller/dashboard");
  const list = await (await page.request.get(`/api/v1/telecaller/products?q=${stamp}`)).json();
  expect(list.total).toBe(0); // the deactivated product is not readable to a telecaller
  expect((await page.request.post("/api/v1/telecaller/campaigns", { data: { name: `x ${stamp}` } })).status()).toBe(403);
  await page.goto("/telecaller/manager/products");
  await expect(page.getByText("Telecaller manager role required")).toBeVisible();
  expect(errors).toEqual([]);
});
