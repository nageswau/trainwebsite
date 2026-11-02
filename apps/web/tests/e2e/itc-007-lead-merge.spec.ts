import { expect, test, type Page } from "@playwright/test";

// itc-007 (DEC-SCOPE-339): merge a duplicate lead. super_admin (a manager on /telecaller, every lead in scope, so tel-007's distribution
// never moves the leads out of view) opens one of two fresh website leads, compares the other by Lead ID, keeps the duplicate's name and
// merges: the duplicate's enquiry shows on this lead's activity with "Merged from", and the duplicate's page is read only.
test.describe.configure({ timeout: 120_000 });

async function signInAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function websiteLead(page: Page, stamp: number, n: number, name: string) {
  const mobile = `9${String(stamp + n).slice(-9)}`;
  const created = await page.request.post("/api/v1/public/enquiries", {
    data: { division: "it", name, email: `itc007-${n}-${stamp}@example.com`, phone: mobile, subject: `Merge ${n}`, message: `Enquiry ${n}` },
  });
  expect(created.status()).toBe(201);
  const id = (await created.json()).id as string;
  const detail = await (await page.request.get(`/api/v1/telecaller/leads/${id}`)).json();
  return { id, code: detail.lead_code as string };
}

test("a manager merges a duplicate lead into the lead that stays", async ({ page }) => {
  const stamp = Date.now();
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));
  await signInAdmin(page);
  const survivor = await websiteLead(page, stamp, 1, `Merge Keep ${stamp}`);
  const victim = await websiteLead(page, stamp, 2, `Merge Dup ${stamp}`);

  await page.goto(`/telecaller/manager/leads/${survivor.id}`);
  await page.getByRole("button", { name: `Merge a duplicate into ${survivor.code}` }).click();
  await page.getByLabel("Lead ID of the duplicate").fill(victim.code.toLowerCase());
  await page.getByRole("button", { name: "Compare" }).click();
  const table = page.getByRole("table", { name: "Compare the two leads" });
  await expect(table).toBeVisible();
  await expect(table.getByRole("row", { name: /Student name/ })).toContainText(`Merge Dup ${stamp}`);
  await page.getByRole("radio", { name: `Keep Merge Dup ${stamp} for Student name` }).check();
  await page.getByLabel("Reason (optional)").fill("Same person");
  await page.getByRole("button", { name: "Merge into this lead" }).click();

  await expect(page.getByText(`${victim.code} was merged into this lead.`)).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: `Merge Dup ${stamp}` })).toBeVisible(); // the picked name, re-read
  const activity = page.getByRole("list", { name: "Lead activity" });
  await expect(activity.getByText(`Merged from ${victim.code}`)).toBeVisible();
  await expect(activity.getByText(`New enquiry: Merge 2`)).toBeVisible();

  await page.goto(`/telecaller/manager/leads/${victim.id}`);
  await expect(page.getByText(`This lead was merged into ${survivor.code}. You can view it but not change it.`)).toBeVisible();
  await expect(page.getByRole("button", { name: /Change stage/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Merge a duplicate/ })).toHaveCount(0);
  expect(consoleErrors).toEqual([]);
});

test("an unknown Lead ID is refused in place, and the form fits a phone", async ({ page }) => {
  const stamp = Date.now();
  await page.setViewportSize({ width: 375, height: 800 });
  await signInAdmin(page);
  const survivor = await websiteLead(page, stamp, 3, `Merge Alone ${stamp}`);
  await page.goto(`/telecaller/manager/leads/${survivor.id}`);
  await page.getByRole("button", { name: `Merge a duplicate into ${survivor.code}` }).click();
  await page.getByLabel("Lead ID of the duplicate").fill("LD-999999999");
  await page.getByRole("button", { name: "Compare" }).click();
  await expect(page.locator(".form-error", { hasText: "Lead not found" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Compare the two leads" })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});
