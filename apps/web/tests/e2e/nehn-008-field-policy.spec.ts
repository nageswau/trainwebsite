import { readFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// nehn-008 (DEC-SCOPE-300): a report's financial columns follow `field.financial.view` on the screen and in the download alike. The
// matrix lists the new permission; a partnership manager sees the commission columns (seed); a per-user deny removes them from the
// screen and the CSV on the next load; the page still fits a phone. Throwaway accounts via the admin API.

async function signIn(page: Page, loginPath: string, email: string, password: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function send(page: Page, method: "post" | "put", url: string, data: unknown) {
  const response = await page.request[method](url, { data });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

async function csvHeader(page: Page): Promise<string> {
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download CSV" }).click()]);
  const text = readFileSync((await download.path())!, "utf8");
  return text.replace(/^﻿/, "").split(/\r?\n/)[0];
}

test("financial columns follow field.financial.view on the screen and in the CSV", async ({ page, browser }) => {
  test.setTimeout(180_000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  const stamp = Date.now();

  // Super admin: the matrix lists the new permission, held by Partnership Head.
  await signIn(page, "/admin/login", "superadmin@edusphere.local", "Demo@123");
  await page.goto("/admin/permissions");
  await page.getByLabel("Role", { exact: true }).selectOption({ label: "Partnership Head" });
  await expect(page.getByRole("checkbox", { name: "Financial columns: View" })).toBeChecked();
  await page.getByLabel("Role", { exact: true }).selectOption({ label: "IT Administrator" });
  await expect(page.getByRole("checkbox", { name: "Financial columns: View" })).not.toBeChecked();

  const head = await send(page, "post", "/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E N8 Head ${stamp}`, email: `n008-h-${stamp}@example.local` });
  const manager = await send(page, "post", "/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E N8 Manager ${stamp}`, email: `n008-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `N8-${stamp}`, reporting_head_user_id: head.id },
  });
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await send(page, "post", "/api/v1/partnership/universities", { name: `E2E N8 Partner ${stamp}`, country_id: countries.items[0].id, city: "London" });
  await send(page, "post", `/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: manager.id });
  await send(page, "post", `/api/v1/partnership/universities/${university.id}/stage`, { to_stage: "partner_activated", from_stage: "target_university" }); // ranked
  await activateWithToken(page.request, manager.development_welcome_token);

  // The manager (seeded grant) sees the commission columns on screen and in the file.
  const managerContext = await browser.newContext({ baseURL: test.info().project.use.baseURL, acceptDownloads: true });
  const mine = await managerContext.newPage();
  mine.on("pageerror", (e) => errors.push(e.message));
  try {
    await signIn(mine, "/overseas/login", manager.email, E2E_PASSWORD);
    await mine.goto("/partnership/reports?report=performance");
    await expect(mine.getByRole("heading", { name: "University Performance Report" })).toBeVisible();
    await expect(mine.getByRole("columnheader", { name: "Commission expected" })).toBeVisible();
    expect(await csvHeader(mine)).toContain("Commission expected");

    // A per-user deny (nehn-007) removes them from both on the next load.
    await send(page, "put", `/api/v1/admin/users/${manager.id}/permissions`, {
      overrides: [{ permission: "field.financial.view", effect: "deny", reason: "nehn-008 e2e" }],
    });
    await mine.reload();
    await expect(mine.getByRole("heading", { name: "University Performance Report" })).toBeVisible();
    await expect(mine.getByRole("columnheader", { name: "University" })).toBeVisible();
    await expect(mine.getByRole("columnheader", { name: /Commission/ })).toHaveCount(0);
    const header = await csvHeader(mine);
    expect(header).toContain("University");
    expect(header).not.toContain("Commission");

    // Phone width: no horizontal page scroll.
    await mine.setViewportSize({ width: 375, height: 800 });
    await mine.reload();
    await expect(mine.getByRole("heading", { name: "University Performance Report" })).toBeVisible();
    expect(await mine.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  } finally {
    await send(page, "put", `/api/v1/admin/users/${manager.id}/permissions`, { overrides: [] });
    await managerContext.close();
  }
  expect(errors).toEqual([]);
});
