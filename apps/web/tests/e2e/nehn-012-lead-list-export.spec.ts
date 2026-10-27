import { readFile } from "node:fs/promises";

import { expect, test, type Page } from "@playwright/test";

// nehn-012 (DEC-SCOPE-298): the admin narrows the lead list to today's (India time) enquiries and downloads exactly those as Excel;
// the filters live in the URL; a reversed range is explained, not sent; a telecaller manager may download the team's list, a
// telecaller may not. The shared stack DB also holds backend-test rows, so the admin checks narrow to this run's leads by a stamp.
test.describe.configure({ timeout: 90_000 });

const PASSWORD = "Demo@123";
const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());

async function signIn(page: Page, loginPath: string, email: string) {
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test("an admin filters today's enquiries and downloads exactly those as Excel", async ({ page }) => {
  const stamp = `n12${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  for (const i of [1, 2]) {
    const mobile = `9${String(Date.now() + i).slice(-9)}`;
    const created = await page.request.post("/api/v1/public/enquiries", {
      data: { division: "it", name: `Export ${i} ${stamp}`, email: `${stamp}-${i}@example.com`, phone: mobile, subject: "Cyber Security", message: "Please call me about the course." },
    });
    expect(created.status()).toBe(201);
  }

  await signIn(page, "/it/login", "itadmin@edusphere.local");
  await page.goto(`/it/admin/leads?q=${stamp}`);
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Manage leads" }) });
  await expect(panel.getByRole("rowheader")).toHaveCount(2);
  await panel.getByLabel("Created from").fill(today());
  await expect(page).toHaveURL(new RegExp(`created_from=${today()}`));
  await panel.getByLabel("Created to").fill(today());
  await expect(page).toHaveURL(new RegExp(`created_to=${today()}`));
  await expect(panel.getByRole("rowheader")).toHaveCount(2);
  await page.reload(); // the range lives in the URL
  await expect(panel.getByLabel("Created from")).toHaveValue(today());
  await expect(panel.getByText("All 2 matching leads, with contact details. Downloads are recorded.")).toBeVisible();

  const pending = page.waitForEvent("download");
  await panel.getByRole("button", { name: "Download Excel" }).click();
  const file = await pending;
  await expect(panel.getByText("Report downloaded.")).toBeVisible();
  expect(file.suggestedFilename()).toBe(`leads-${today()}.xlsx`);
  const body = await readFile((await file.path())!);
  expect(body.subarray(0, 2).toString()).toBe("PK"); // a zip package, not an error page saved as a file

  // a range that starts tomorrow matches nothing; a reversed one is explained and never sent
  const tomorrow = new Date(Date.now() + 86_400_000).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
  await page.goto(`/it/admin/leads?q=${stamp}&created_from=${tomorrow}`);
  await expect(panel.getByText("No leads match these filters.")).toBeVisible();
  await expect(panel.getByRole("button", { name: "Download Excel" })).toHaveCount(0);
  await page.goto(`/it/admin/leads?q=${stamp}&created_from=${tomorrow}&created_to=${today()}`);
  await expect(panel.getByText("Choose a start date on or before the end date.")).toBeVisible();

  for (const width of [320, 375, 768]) {
    await page.goto(`/it/admin/leads?q=${stamp}`);
    await page.setViewportSize({ width, height: 800 });
    await expect(panel.getByRole("button", { name: "Download Excel" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `overflow at ${width}px`).toBe(true);
  }
});

test("a telecaller manager may download the team's lead list; a telecaller may not", async ({ page }) => {
  await signIn(page, "/admin/login", "telecaller.manager@edusphere.local");
  const managerExport = await page.request.get(`/api/v1/telecaller/leads.xlsx?created_to=${today()}`);
  expect([managerExport.status(), managerExport.headers()["content-type"]]).toEqual([200, XLSX]);
  await page.goto("/telecaller/manager/leads");
  await page.getByLabel("Created to").fill(today());
  await expect(page).toHaveURL(new RegExp(`created_to=${today()}`));
  const anyLead = await page.getByRole("table").isVisible().catch(() => false);
  if (anyLead) await expect(page.getByRole("button", { name: "Download Excel" })).toBeVisible();

  await page.context().clearCookies();
  await signIn(page, "/it/login", "telecaller.it@edusphere.local");
  await page.goto("/telecaller/leads");
  await expect(page.getByLabel("Created from")).toBeVisible();
  await expect(page.getByRole("button", { name: "Download Excel" })).toHaveCount(0);
  expect((await page.request.get("/api/v1/telecaller/leads.xlsx")).status()).toBe(403);
});
