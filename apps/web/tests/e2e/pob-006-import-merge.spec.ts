import { expect, test, type Page } from "@playwright/test";

// pob-006 (DEC-SCOPE-418): the seeded placement manager imports a file with a good and a bad row and sees the report (AC1), checks the same file again and nothing is new
// (AC2), merges a duplicate company and then a duplicate contact into the records that stay (AC3); a plain recruiter gets neither; no sideways scroll on a phone.
const MANAGER = "placement.manager@edusphere.local";
const RECRUITER = "placement@edusphere.local";
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function signIn(page: Page, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(email === MANAGER ? "/admin/login" : "/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test("a manager imports companies, and a re-check of the same file finds nothing new", async ({ page }) => {
  test.setTimeout(120_000);
  const tag = Date.now();
  const file = {
    name: `pob6-${tag}.csv`, mimeType: "text/csv",
    buffer: Buffer.from(`company_name,priority,contact_name,contact_email\nPOB6 Import ${tag} Pvt,hot,Asha ${tag},asha${tag}@example.com\nPOB6 Bad ${tag} Pvt,urgent,,\n`),
  };
  await signIn(page, MANAGER);
  await page.goto("/recruiter/companies");
  await page.getByRole("link", { name: "Import companies" }).click();
  await page.waitForURL("**/recruiter/companies/import");

  await page.setInputFiles("#company-import-file", file);
  await page.getByRole("button", { name: "Check file" }).click();
  await expect(page.getByRole("heading", { name: "3. Check the rows" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Rows in this file" }).getByText("priority:", { exact: false })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(page)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });

  await page.getByRole("button", { name: "Import 1 new row" }).click();
  await expect(page.getByRole("heading", { name: "Import result" })).toBeVisible({ timeout: 30_000 });
  await expect(page.locator(".form-warning").filter({ hasText: "1 company and 1 contact added, 0 rows already here, 1 error" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Past imports" }).getByText(file.name)).toBeVisible();

  await page.setInputFiles("#company-import-file", file);
  await page.getByRole("button", { name: "Check file" }).click();
  await expect(page.getByText("Nothing new to add")).toBeVisible();
});

test("a manager merges a duplicate company, then a duplicate contact", async ({ page }) => {
  test.setTimeout(120_000);
  const tag = Date.now();
  await signIn(page, RECRUITER);
  const create = async (name: string, data: Record<string, unknown>) => {
    const response = await page.request.post("/api/v1/recruiter/companies", { data: { name, ...data } });
    expect(response.status(), await response.text()).toBe(201);
    return (await response.json()).company as { id: string; code: string };
  };
  const stays = await create(`POB6 Stays ${tag} Pvt`, { city: "Pune", contact: { name: "Stay Person", is_primary: true } });
  const dup = await create(`POB6 Dup ${tag} Pvt`, { city: "Goa", contact: { name: "Dup Person", email: `dup${tag}@example.com`, is_primary: true } });

  // A plain recruiter holds neither grant: no link, and the page says so.
  await page.goto(`/recruiter/companies/${stays.id}`);
  await expect(page.getByRole("heading", { name: `POB6 Stays ${tag} Pvt` })).toBeVisible();
  await expect(page.getByRole("link", { name: "Merge a duplicate" })).toHaveCount(0);
  await page.goto(`/recruiter/companies/${stays.id}/merge`);
  await expect(page.getByText("Your role cannot merge duplicates")).toBeVisible();

  await signIn(page, MANAGER);
  page.on("dialog", (dialog) => dialog.accept());
  await page.goto(`/recruiter/companies/${stays.id}`);
  await page.getByRole("link", { name: "Merge a duplicate", exact: true }).first().click();
  await page.waitForURL(/\/merge$/);
  await page.fill("#merge-code", dup.code);
  await page.getByRole("button", { name: "Compare" }).click();
  await page.getByRole("radio", { name: "Keep Goa for City" }).check();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(page)).toBe(true);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.getByLabel("Reason (optional)").fill("Entered twice");
  await page.getByRole("button", { name: `Merge ${dup.code}` }).click();
  await page.waitForURL(/merged=/);
  await expect(page.getByText(`Merged ${dup.code} into this record.`)).toBeVisible();
  const contacts = page.getByRole("region", { name: "Contacts", exact: true });
  await expect(contacts.getByRole("button", { name: "Activity Dup Person" })).toBeVisible();

  // The duplicate says where it went and offers nothing.
  await page.goto(`/recruiter/companies/${dup.id}`);
  await expect(page.getByText("Merged into")).toBeVisible();
  await expect(page.getByRole("button", { name: "Restore" })).toHaveCount(0);

  await page.goto(`/recruiter/companies/${stays.id}`);
  await page.getByRole("region", { name: "Contacts", exact: true }).getByRole("link", { name: "Merge a duplicate into Stay Person" }).click();
  await page.waitForURL(/contacts\/.+\/merge$/);
  await page.getByLabel("Duplicate contact").selectOption({ label: `Dup Person (dup${tag}@example.com)` });
  await page.getByRole("button", { name: "Merge contact" }).click();
  await page.waitForURL(/merged=contact/);
  const after = page.getByRole("region", { name: "Contacts", exact: true });
  await expect(after.getByText(`dup${tag}@example.com`)).toBeVisible();
  await expect(after.getByRole("button", { name: "Activity Dup Person" })).toHaveCount(0);
});
