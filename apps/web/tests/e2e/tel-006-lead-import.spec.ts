import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-006 (AC1-AC4; IM1): a telecaller manager imports a CSV for a campaign -- one new lead, one row for a person who is already a lead
// (it attaches), one bad mobile (rejected with its line). The past imports list it; a telecaller cannot open the page.
test.describe.configure({ timeout: 120_000 });

type Created = { id: string; email: string; development_welcome_token: string };

async function setUp(page: Page, stamp: number) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
  const manager: Created = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E Import Manager ${stamp}`, email: `tel006-m-${stamp}@example.local` },
  })).json();
  const caller: Created = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E Import Telecaller ${stamp}`, email: `tel006-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `IM-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
  const products = await (await page.request.get("/api/v1/telecaller/products?active=true&limit=100")).json();
  const cyber = products.items.find((p: { name: string; group: string }) => p.group === "it" && p.name === "Cyber Security");
  const campaign = await (await page.request.post("/api/v1/telecaller/campaigns", {
    data: { name: `E2E Import ${stamp}`, source: "facebook", product_id: cyber.id, start_date: "2026-09-01" },
  })).json();
  await page.request.post("/api/v1/auth/logout");
  return { manager, caller, campaign };
}

async function signIn(page: Page, user: Created, portal: string, landing: string) {
  await activateWithToken(page.request, user.development_welcome_token);
  await page.goto(portal);
  await page.fill("#login-email", user.email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test("a manager imports a campaign CSV: created, attached and rejected rows, then the history", async ({ page }) => {
  const stamp = Date.now();
  const known = `9${String(stamp).slice(-9)}`;
  const fresh = `8${String(stamp).slice(-9)}`;
  const errors: string[] = [];
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.on("pageerror", (e) => errors.push(e.message));
  const { manager, caller, campaign } = await setUp(page, stamp);
  const web = await page.request.post("/api/v1/public/enquiries", {
    data: { division: "it", name: "Known Person", email: `tel006-k-${stamp}@example.com`, phone: known, subject: "Python", message: "Send the fees." },
  });
  expect(web.status()).toBe(201);

  await signIn(page, manager, "/admin/login", "/telecaller/manager/team");
  await page.getByRole("link", { name: "Lead import" }).first().click();
  await page.waitForURL("**/telecaller/manager/imports");
  await expect(page.getByRole("heading", { name: "Lead import" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Download the template/ })).toHaveAttribute("href", "/api/v1/telecaller/imports/template");

  // the campaign is required before anything is sent
  await page.getByRole("button", { name: "Import leads" }).click();
  await expect(page.locator(".lead-import [role=alert]")).toHaveText("Choose a campaign first."); // not Next's route announcer

  await page.getByLabel("Campaign", { exact: true }).selectOption({ label: `${campaign.name} — Facebook → Cyber Security` });
  const csv = ["name,phone,email,city,priority", `Fresh Lead ${stamp},${fresh},,Pune,hot`, `Known Again,+91 ${known},,,`, "Bad Mobile,12345,,,"].join("\n");
  await page.getByLabel(/Filled-in leads file/).setInputFiles({ name: "leads.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.getByRole("button", { name: "Import leads" }).click();

  await expect(page.getByRole("heading", { name: "Import result" })).toBeFocused();
  await expect(page.getByText("1 created, 1 added to existing leads, 1 rejected. Fix the rejected rows and upload just those.")).toBeVisible();
  const result = page.locator("table.bulk-report");
  await expect(result.locator("tbody tr")).toHaveCount(3);
  await expect(result.locator("tbody tr").nth(0)).toContainText(/2\s*Created\s*LD-\d{6,}/);
  await expect(result.locator("tbody tr").nth(1)).toContainText(/3\s*Added to existing lead\s*LD-\d{6,}/);
  await expect(result.locator("tbody tr").nth(2)).toContainText(/4\s*Rejected\s*-\s*phone/);

  const history = page.locator(".action-card", { has: page.getByRole("heading", { name: "Past imports" }) });
  await expect(history.locator("tbody tr").first()).toContainText(campaign.name);
  await expect(history.locator("tbody tr").first()).toContainText("1 created, 1 added to existing leads, 1 rejected");

  await page.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(page)).toBe(true);
  expect(errors).toEqual([]);

  // a telecaller is not a manager
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, caller, "/it/login", "/telecaller/dashboard");
  await page.goto("/telecaller/manager/imports");
  await expect(page.getByText("Telecaller manager role required")).toBeVisible();
  expect((await page.request.get("/api/v1/telecaller/imports")).status()).toBe(403);
});
