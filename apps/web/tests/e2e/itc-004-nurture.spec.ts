import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// itc-004 (DEC-SCOPE-338): an IT telecaller parks a lead in Nurture (a reason is required, N3), finds it with the Stage filter (N6),
// re-activates it to Follow-up (N4), parks it again and hands it over: the list then shows "Assigned to Counselor" under Nurture (N1).
// Throwaway accounts; the phone width has no sideways scroll.
test.describe.configure({ timeout: 180_000 });

async function signIn(page: Page, portal: "it" | "admin", email: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function moveStage(page: Page, name: string, value: string, reason?: string) {
  await page.getByRole("button", { name: `Change stage for ${name}` }).click();
  await page.getByLabel(`New stage for ${name}`).selectOption(value);
  if (reason) await page.getByLabel("Reason (required)").fill(reason);
  await page.getByRole("button", { name: "Save", exact: true }).click();
}

test("a telecaller parks a lead in Nurture with a reason, filters it, re-activates it and hands it over", async ({ page }) => {
  const stamp = Date.now();
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const post = async (data: object) => {
    const response = await page.request.post("/api/v1/admin/users", { data });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  };
  const manager = await post({ role: "telecaller_manager", division: "global", full_name: `E2E NU Manager ${stamp}`, email: `itc004-m-${stamp}@example.local` });
  const caller = await post({
    role: "telecaller", full_name: `E2E NU Telecaller ${stamp}`, email: `itc004-t-${stamp}@example.local`,
    telecaller_profile: { team: "it", employee_id: `NU-${stamp}`, reporting_manager_user_id: manager.id },
  });
  const counselorName = `E2E NU Counselor ${stamp}`;
  const counselor = await post({ role: "counselor", division: "it", full_name: counselorName, email: `itc004-c-${stamp}@example.local` });
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, caller.development_welcome_token);
  await activateWithToken(page.request, counselor.development_welcome_token);

  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  await signIn(page, "it", caller.email, E2E_PASSWORD, "/telecaller/dashboard");
  const products = (await (await page.request.get("/api/v1/telecaller/products?group=it&active=true&limit=100")).json()).items;
  const name = `NU Lead ${stamp}`;
  const phone = `7${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`;
  const created = await page.request.post("/api/v1/telecaller/leads", {
    data: { name, email: `itc004-l-${stamp}@example.local`, phone, product_id: products[0].id, source: "walk_in" },
  });
  expect(created.status(), await created.text()).toBe(201);
  const id = (await created.json()).id as string;

  // N3: Nurture needs a reason -- the form says so before the API is asked
  await page.goto(`/telecaller/leads/${id}`);
  await moveStage(page, name, "nurture");
  await expect(page.locator(".form-error", { hasText: "Add a reason for this stage." })).toBeVisible();
  await page.getByLabel("Reason (required)").fill("Exams until next month");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Stage updated.")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("main")).toContainText("Nurture");

  // N6: the Stage filter finds it
  await page.goto("/telecaller/leads");
  await page.getByLabel("Stage").selectOption("nurture");
  await expect(page).toHaveURL(/status=nurture/);
  const row = page.locator("tr", { hasText: name });
  await expect(row).toContainText("Nurture");
  await expect(row).not.toContainText("Assigned to Counselor");

  // N4: re-activated without a reason, then parked again
  await page.goto(`/telecaller/leads/${id}`);
  await moveStage(page, name, "follow_up");
  await expect(page.getByText("Stage updated.")).toBeVisible();
  await moveStage(page, name, "nurture", "Call after the results");
  await expect(page.getByText("Stage updated.")).toBeVisible();

  // N1: handed over, the list shows the derived badge under the stage
  await page.getByRole("button", { name: "Assign to counselor" }).click();
  await page.getByLabel("Counselor", { exact: true }).selectOption({ label: counselorName });
  await page.getByRole("button", { name: "Hand over" }).click();
  await expect(page.getByText(`Handed over to ${counselorName}.`)).toBeVisible();
  await page.goto("/telecaller/leads?status=nurture");
  const handed = page.locator("tr", { hasText: name });
  await expect(handed).toContainText("Nurture");
  await expect(handed).toContainText("Assigned to Counselor");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await expect(page.locator("tr", { hasText: name })).toContainText("Assigned to Counselor");
  expect(await noSideScroll(page)).toBe(true);
  expect(consoleErrors).toEqual([]);
});
