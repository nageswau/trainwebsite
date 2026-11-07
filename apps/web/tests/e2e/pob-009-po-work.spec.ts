import { expect, test, type Page } from "@playwright/test";

// pob-009: the Team Lead sets a PO's monthly target and territory and adds target companies by territory (AC2); the PO sees target vs actual,
// plans a target company, ticks it done and submits the daily report; the Team Lead reads it. Weekly = Monday-Sunday (AC3); no sideways
// scroll on a phone.
const MANAGER = "placement.manager@edusphere.local";
const PO = "placement@edusphere.local";
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function signIn(page: Page, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(email === MANAGER ? "/admin/login" : "/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test("targets, territory, target companies, the daily plan and the daily report", async ({ page }) => {
  test.setTimeout(150_000);
  const territory = `E2E Terr ${Date.now()}`;
  const company = `POB9 Target ${Date.now()} Pvt`;
  const target = String(10 + (Date.now() % 80));

  await signIn(page, PO);
  const created = await page.request.post("/api/v1/recruiter/companies", { data: { name: company, territory } });
  expect(created.status()).toBe(201);
  const me = await (await page.request.get("/api/v1/auth/me")).json();

  await signIn(page, MANAGER);
  await page.goto("/recruiter/manager/targets");
  await expect(page.getByRole("heading", { name: /Placement officer targets/ })).toBeVisible();
  await page.goto(`/recruiter/manager/targets/${me.id}`);
  await page.getByLabel("Outreach target").fill(target);
  await page.getByRole("button", { name: "Save targets" }).click();
  await expect(page.getByText(/Saved 1 target/)).toBeVisible();
  await page.getByLabel("Territory", { exact: true }).fill(territory);
  await page.getByRole("button", { name: "Save territory" }).click();
  await expect(page.getByText("Territory saved.")).toBeVisible();
  await page.getByLabel("Add every company in territory").fill(territory.toLowerCase());
  await page.getByRole("button", { name: "Add by territory" }).click();
  await expect(page.getByText("Added 1 company.")).toBeVisible();
  await expect(page.getByRole("link", { name: company })).toBeVisible();

  await signIn(page, PO);
  await page.goto("/recruiter/targets");
  const outreach = page.getByRole("row", { name: /Outreach/ });
  await expect(outreach.getByRole("cell").first()).toHaveText(target);
  await expect(page.getByRole("link", { name: company })).toBeVisible();

  await page.goto("/recruiter/daily-plan");
  await page.getByRole("button", { name: `Plan ${company}` }).click();
  const planned = page.locator("li", { hasText: company }).filter({ has: page.getByRole("checkbox") });
  await expect(planned).toBeVisible();
  await planned.getByRole("checkbox").check();
  await expect(planned.getByRole("checkbox")).toBeChecked();

  await page.goto("/recruiter/activity-reports");
  if (await page.getByRole("button", { name: "Submit to Team Lead" }).isVisible()) {
    await page.getByLabel("Notes for your Team Lead").fill("E2E: called target companies");
    await page.getByRole("button", { name: "Submit to Team Lead" }).click();
  }
  await expect(page.getByText("Submitted", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Show contacts reached" }).click();
  await expect(page.getByText(/No contact was reached|replied \(/)).toBeVisible();

  await page.goto("/recruiter/activity-reports?period=weekly&start=2026-11-05");
  await expect(page.getByRole("heading", { name: /Weekly report — Week Mon, 2 Nov 2026 – Sun, 8 Nov 2026/ })).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/recruiter/daily-plan");
  expect(await noSideScroll(page)).toBe(true);

  await signIn(page, MANAGER);
  await page.goto("/recruiter/manager/activity-reports");
  const row = page.getByRole("row", { name: new RegExp(me.full_name) });
  await expect(row.getByText("Submitted")).toBeVisible();
  await row.getByRole("link", { name: /Open/ }).click();
  await expect(page.getByText("Submitted", { exact: true })).toBeVisible();
  expect(await noSideScroll(page)).toBe(true);
});
