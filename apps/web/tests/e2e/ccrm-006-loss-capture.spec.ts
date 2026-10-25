import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// ccrm-006 (DEC-SCOPE-261): the manager adds a lost reason (D8); a telecaller closes one lead as a Duplicate of another (D3, the Lead ID
// is required) and another as Lost with that reason and "lost to" (D4); Wrong Number reads Invalid Contact (D1); the Lost Reasons report
// counts it (D9). Throwaway accounts; phone width has no sideways scroll; no console errors.
test.describe.configure({ timeout: 240_000 });

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test("a lead closes as Duplicate of another and as Lost with a reason the report counts", async ({ page }) => {
  const stamp = Date.now();
  const reasonName = `E2E Reason ${stamp}`;
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const post = async (data: object) => {
    const response = await page.request.post("/api/v1/admin/users", { data });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  };
  const manager = await post({ role: "telecaller_manager", division: "global", full_name: `E2E LC Manager ${stamp}`, email: `ccrm006-m-${stamp}@example.local` });
  const caller = await post({
    role: "telecaller", full_name: `E2E LC Telecaller ${stamp}`, email: `ccrm006-t-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `LC-${stamp}`, reporting_manager_user_id: manager.id },
  });

  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  // D8: the reason list page
  await page.goto("/telecaller/manager/lost-reasons");
  await expect(page.getByRole("heading", { name: "Lost reasons", level: 2 })).toBeVisible();
  await page.fill("#lost-reason-name", reasonName);
  await page.click("button:has-text('Create lost reason')");
  await expect(page.locator("#lost-reason-feedback")).toHaveText(`Created ${reasonName}.`);
  await expect(page.getByRole("region", { name: "Lost reasons" })).toContainText(reasonName);
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, caller.development_welcome_token);

  // the telecaller's three leads
  await signIn(page, "it", caller.email, E2E_PASSWORD, "/telecaller/dashboard");
  const products = (await (await page.request.get("/api/v1/telecaller/products?group=it&active=true&limit=100")).json()).items;
  const make = async (tag: string) => {
    const phone = `8${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;
    const created = await page.request.post("/api/v1/telecaller/leads", {
      data: { name: `LC ${tag} ${stamp}`, email: `ccrm006-${tag}-${stamp}@example.local`, phone, product_id: products[0].id, source: "walk_in" },
    });
    expect(created.status(), await created.text()).toBe(201);
    return created.json() as Promise<{ id: string; lead_code: string }>;
  };
  const survivor = await make("a");
  const dup = await make("b");
  const lost = await make("c");

  // D3: Duplicate needs the surviving lead's Lead ID; D1: Invalid Contact
  await page.goto(`/telecaller/leads/${dup.id}`);
  const dupName = `LC b ${stamp}`;
  await page.getByRole("button", { name: `Change stage for ${dupName}` }).click();
  const picker = page.getByLabel(`New stage for ${dupName}`);
  await expect(picker.locator("option", { hasText: "Invalid Contact" })).toHaveCount(1);
  await expect(picker.locator("option", { hasText: "Wrong Number" })).toHaveCount(0);
  await picker.selectOption("duplicate");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Enter the Lead ID of the lead this one duplicates.")).toBeVisible();
  await page.getByLabel("Duplicate of Lead ID (required)").fill(dup.lead_code.toLowerCase());
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("A lead cannot be a duplicate of itself")).toBeVisible(); // the API's sentence
  await page.getByLabel("Duplicate of Lead ID (required)").fill(survivor.lead_code.toLowerCase());
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Stage updated.")).toBeVisible();
  await expect(page.getByText(`Duplicate of ${survivor.lead_code}`)).toBeVisible();
  await page.reload();
  await expect(page.getByText(`Duplicate of ${survivor.lead_code}`)).toBeVisible();

  // D4: Lost with a reason from the list and "lost to"
  await page.goto(`/telecaller/leads/${lost.id}`);
  const lostName = `LC c ${stamp}`;
  await page.getByRole("button", { name: `Change stage for ${lostName}` }).click();
  await page.getByLabel(`New stage for ${lostName}`).selectOption("lost");
  const reason = page.getByLabel("Lost reason (required)");
  await expect(reason.locator("option", { hasText: reasonName })).toHaveCount(1);
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Choose why the lead was lost.")).toBeVisible();
  await reason.selectOption({ label: reasonName });
  await page.getByLabel("Lost to (optional)").fill("Canada");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Stage updated.")).toBeVisible();
  await expect(page.getByText(`Lost reason: ${reasonName} · Lost to: Canada`)).toBeVisible();
  await page.setViewportSize({ width: 375, height: 800 });
  await page.reload();
  await expect(page.getByText(`Lost reason: ${reasonName} · Lost to: Canada`)).toBeVisible();
  expect(await noSideScroll(page)).toBe(true);

  // D9: the Lost Reasons report counts it
  await page.setViewportSize({ width: 1280, height: 900 });
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  await page.goto("/telecaller/manager/reports?report=lost");
  await expect(page.getByRole("heading", { name: "Lost Reasons Report" })).toBeVisible();
  await expect(page.getByRole("row", { name: new RegExp(reasonName) })).toContainText("1");
  expect(consoleErrors).toEqual([]);
});
