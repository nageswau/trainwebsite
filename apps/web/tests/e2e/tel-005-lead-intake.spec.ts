import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-005 (AC1-AC4; I1, I2, I3, I5): a telecaller enters a phone-only lead (it is theirs, Assigned), the same mobile in another format
// is caught by the §18 panel and the new enquiry is added to the existing lead instead; a website enquiry from the same email attaches.
test.describe.configure({ timeout: 120_000 });

async function telecaller(page: Page, stamp: number) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E Intake Manager ${stamp}`, email: `tel005-m-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E Intake Telecaller ${stamp}`, email: `tel005-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `LI-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, caller.development_welcome_token);
  await page.goto("/it/login");
  await page.fill("#login-email", caller.email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/telecaller/dashboard");
  return caller;
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test("a telecaller creates a lead, is stopped on the same mobile, and adds the enquiry to the existing lead", async ({ page }) => {
  const stamp = Date.now();
  const mobile = `9${String(stamp).slice(-9)}`;
  const name = `Intake Lead ${stamp}`;
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  await telecaller(page, stamp);

  await page.goto("/telecaller/leads");
  await page.getByRole("link", { name: "New lead" }).click();
  await page.waitForURL("**/telecaller/leads/new");
  await page.getByLabel(/Student name/).fill(name);
  await page.getByLabel(/Mobile number/).fill(`${mobile.slice(0, 5)} ${mobile.slice(5)}`);
  await page.getByLabel(/Product interest/).selectOption({ label: "Cyber Security" });
  await page.getByLabel(/Lead source/).selectOption("instagram");
  await page.getByLabel(/City/).fill("Pune");
  await page.getByRole("button", { name: "Create lead" }).click();
  await page.waitForURL(/\/telecaller\/leads\/[0-9a-f-]{36}$/);
  const leadId = page.url().split("/").pop()!;
  await expect(page.getByText(/^Stage: Assigned · Priority/)).toBeVisible(); // I2: the creator's lead
  const leadCode = (await page.locator(".eyebrow").first().textContent())!.trim();
  expect(leadCode).toMatch(/^LD-\d{6,}$/);

  // AC1: the same mobile, written another way, is caught before anything is created
  await page.goto("/telecaller/leads/new");
  await page.getByLabel(/Mobile number/).fill(`+91 ${mobile}`);
  await page.getByLabel(/Mobile number/).blur();
  const panel = page.getByRole("region", { name: /Lead already exists/ });
  await expect(panel).toContainText(leadCode);
  await expect(panel).toContainText("Assigned");
  await expect(panel).toContainText("No contact logged yet");
  await expect(panel.getByRole("link", { name: `Open ${leadCode}` })).toBeVisible();
  await page.getByLabel(/Product interest/).selectOption({ label: "Cyber Security" });
  await page.getByLabel(/Lead source/).selectOption("whatsapp");
  await page.getByLabel(/Enquiry subject/).fill("Weekend batch");
  await panel.getByRole("button", { name: `Add enquiry to ${leadCode}` }).click();
  await expect(panel.getByText(`Enquiry added to ${leadCode}.`)).toBeVisible();
  await page.getByLabel(/Student name/).fill(`${name} again`);
  await page.getByRole("button", { name: "Create lead" }).click();
  await expect(page.getByText("This person is already a lead", { exact: false })).toBeVisible(); // the create re-checks (409)

  // AC2 / I3: a website enquiry from the same mobile attaches, with the new-lead reply
  const web = await page.request.post("/api/v1/public/enquiries", {
    data: { division: "it", name: "Someone", email: `tel005-${stamp}@example.com`, phone: mobile, subject: "Fees please", message: "Send the fees." },
  });
  expect(web.status()).toBe(201);
  expect(await web.json()).toEqual({ id: leadId, status: "new", crm_sync_status: "pending", lead_code: leadCode });

  await panel.getByRole("link", { name: `Open ${leadCode}` }).click();
  await page.waitForURL(`**/telecaller/leads/${leadId}`);
  const activity = page.getByRole("list", { name: "Lead activity" });
  await expect(activity).toContainText("New enquiry: Weekend batch");
  await expect(activity).toContainText("WhatsApp");
  await expect(activity).toContainText("New enquiry: Fees please");
  await expect(activity).toContainText("Website form");
  // the browser logs the intended 409 of the re-checked create as a failed resource; anything else is a real error
  expect(errors.filter((e) => !e.includes("status of 409"))).toEqual([]);
});

test("the New Lead form and its duplicate panel fit a phone screen", async ({ page }) => {
  const stamp = Date.now();
  await telecaller(page, stamp);
  const mobile = `9${String(stamp).slice(-9)}`;
  const created = await page.request.post("/api/v1/telecaller/leads", {
    data: { name: `Phone Fit ${stamp}`, phone: mobile, product_id: (await (await page.request.get("/api/v1/telecaller/products?active=true&limit=100")).json()).items[0].id, source: "google" },
  });
  expect(created.status()).toBe(201);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/telecaller/leads/new");
  await page.getByLabel(/Mobile number/).fill(mobile);
  await page.getByLabel(/Mobile number/).blur();
  await expect(page.getByRole("region", { name: /Lead already exists/ })).toBeVisible();
  expect(await noSideScroll(page)).toBe(true);
  await page.setViewportSize({ width: 820, height: 1180 });
  expect(await noSideScroll(page)).toBe(true);
});
