import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// itc-009 (DEC-SCOPE-342; API §12IN): a telecaller manager turns on overdue follow-up escalation for the IT team, the form refuses an
// out-of-range entry, and 0 turns it off again. The settings are shared by the whole database, so the spec puts the default (0) back.

async function signIn(page: Page, email: string) {
  await page.goto("/admin/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/telecaller/manager/team");
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
const LABEL = "Escalate overdue follow-ups after (hours)";

test("a manager sets, checks and turns off the IT team's escalation hours", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = String(Date.now());
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

  await page.request.post("/api/v1/auth/login", { data: { email: "superadmin@edusphere.local", password: "Demo@123", division: "global" } });
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "telecaller_manager", division: "global", full_name: `E2E Escalation Manager ${stamp}`, email: `itc009-m-${stamp}@example.local` },
  })).json();
  await page.request.post("/api/v1/auth/logout");
  await activateWithToken(page.request, manager.development_welcome_token);

  await signIn(page, manager.email);
  await page.getByRole("link", { name: "Alert settings" }).click();
  await page.waitForURL("**/telecaller/manager/alerts");
  const it = page.getByRole("region", { name: "IT team" });
  const hours = it.getByLabel(LABEL);
  await expect(hours).toHaveValue("0");
  await expect(it.getByText(/0 turns escalation off/)).toBeVisible();

  // Out of range: the form stops it and nothing is saved.
  await hours.fill("169");
  await it.getByRole("button", { name: "Save IT thresholds" }).click();
  expect(await hours.evaluate((el: HTMLInputElement) => el.validity.valid)).toBe(false);

  await hours.fill("24");
  await it.getByRole("button", { name: "Save IT thresholds" }).click();
  await expect(it.getByText("Saved. Alerts use the new thresholds from the next check (within 15 minutes).")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("region", { name: "IT team" }).getByLabel(LABEL)).toHaveValue("24");
  await expect(page.getByRole("region", { name: "Overseas team" }).getByLabel(LABEL)).toHaveValue("0"); // the other team is untouched

  for (const width of [390, 768]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await noSideScroll(page)).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 800 });

  // 0 turns it off again (and restores the shared default).
  const again = page.getByRole("region", { name: "IT team" });
  await again.getByLabel(LABEL).fill("0");
  await again.getByRole("button", { name: "Save IT thresholds" }).click();
  await expect(again.getByText(/^Saved\./)).toBeVisible();
  const items = (await (await page.request.get("/api/v1/telecaller/settings")).json()).items;
  expect(items.map((i: { escalate_after_hours: number }) => i.escalate_after_hours)).toEqual([0, 0]);
  expect(errors).toEqual([]);
});
