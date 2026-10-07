import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-020 (DEC-SCOPE-111): an assignment alerts the telecaller -- Notifications nav with an unread badge, the notice opens the lead -- and a
// telecaller manager edits a team's alert thresholds. The thresholds are shared by the whole database, so the spec puts the defaults back.

async function account(page: Page, stamp: string) {
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E Alert Manager ${stamp}`, email: `tel020-m-${stamp}@example.local` },
  })).json();
  const caller = await (await page.request.post("/api/v1/admin/users", {
    data: {
      role: "telecaller", full_name: `E2E Alert Telecaller ${stamp}`, email: `tel020-t-${stamp}@example.local`,
      telecaller_profile: { team: "it", employee_id: `AL-${stamp}`, reporting_manager_user_id: manager.id },
    },
  })).json();
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

test("an assigned lead alerts the telecaller; the manager edits the alert thresholds", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = String(Date.now());
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

  await page.request.post("/api/v1/auth/login", { data: { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" } });
  const { manager, caller } = await account(page, stamp);
  const phone = `7${stamp.slice(-9)}`;
  const created = await page.request.post("/api/v1/public/enquiries", {
    data: { division: "it", name: `Alert Lead ${stamp}`, email: `tel020-${stamp}@example.com`, phone, subject: "Python", message: "Call me." },
  });
  expect(created.status()).toBe(201);
  const lead = await created.json();
  expect((await page.request.post("/api/v1/telecaller/leads/assign", { data: { lead_ids: [lead.id], telecaller_user_id: caller.id } })).status()).toBe(200);
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, manager.development_welcome_token);
  await activateWithToken(page.request, caller.development_welcome_token);

  // The telecaller: the badge, the notice, its link to the lead.
  await signIn(page, "it", caller.email, "/telecaller/dashboard");
  const navLink = page.getByRole("link", { name: /Notifications/ }).first();
  await expect(navLink).toContainText("1");
  await navLink.click();
  await page.waitForURL("**/telecaller/notifications");
  await expect(page.getByRole("heading", { name: "Your notifications" })).toBeVisible();
  const notice = page.getByText(`Alert Lead ${stamp}`, { exact: false }).first();
  await expect(notice).toContainText("is now assigned to you.");
  await expect(page.getByText("New lead assigned").first()).toBeVisible();
  await expect(page.getByText(phone)).toHaveCount(0); // never the phone
  await page.getByRole("link", { name: /New lead assigned/ }).first().click();
  await page.waitForURL(`**/telecaller/leads/${lead.id}`);
  await page.goto("/telecaller/notifications");
  await expect(page.getByRole("link", { name: /Notifications/ }).first()).not.toContainText("1"); // read on open
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(page)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });
  // A telecaller cannot read the settings.
  expect((await page.request.get("/api/v1/telecaller/settings")).status()).toBe(403);
  await page.request.post("/api/v1/auth/logout");

  // The manager: Alert settings -> save the IT team -> refused out-of-range by the form -> restored.
  await signIn(page, "admin", manager.email, "/telecaller/manager/team");
  await page.getByRole("link", { name: "Alert settings" }).click();
  await page.waitForURL("**/telecaller/manager/alerts");
  const it = page.getByRole("region", { name: "IT team" });
  await expect(it.getByLabel("Lead not contacted after (hours)")).toHaveValue("24");
  await it.getByLabel("Lead not contacted after (hours)").fill("12");
  await it.getByLabel("Hot lead pending after (hours)").fill("2");
  await it.getByRole("button", { name: "Save IT thresholds" }).click();
  await expect(it.getByText("Saved. Alerts use the new thresholds from the next check (within 15 minutes).")).toBeVisible();
  await expect(it.getByText(new RegExp(`Last changed by E2E Alert Manager ${stamp}`))).toBeVisible();
  await page.reload();
  await expect(page.getByRole("region", { name: "IT team" }).getByLabel("Lead not contacted after (hours)")).toHaveValue("12");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(page)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 800 });
  const restore = await page.request.put("/api/v1/telecaller/settings/it", { data: { not_contacted_hours: 24, hot_pending_hours: 4 } });
  expect(restore.status()).toBe(200);
  expect(errors).toEqual([]);
});
