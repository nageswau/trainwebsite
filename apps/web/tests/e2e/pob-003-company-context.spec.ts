import { expect, test, type Page } from "@playwright/test";

// pob-003 (DEC-SCOPE-406): the seeded recruiter records a company's business context and branches (AC1), logs a call and sees "Last
// contact" move in place (AC2), and uploads + downloads a document (AC3); the page has no sideways scroll on a phone.
const RECRUITER = "placement@edusphere.local";
const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function signIn(page: Page) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/it/login");
  await page.fill("#login-email", RECRUITER);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test("a recruiter records business context, sees last contact move and keeps documents", async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page);
  const created = await page.request.post("/api/v1/recruiter/companies", {
    data: { name: `POB3 ${Date.now()} Pvt`, contact: { name: "Priya HR", mobile: "+91 98765 43210", is_primary: true } },
  });
  expect(created.status(), await created.text()).toBe(201);
  const company = (await created.json()).company;
  await page.goto(`/recruiter/companies/${company.id}`);

  // AC2 "E": no activity yet
  const details = page.getByRole("region", { name: "Details", exact: true });
  await expect(details.getByText("Last contact")).toBeVisible();

  // AC1: the business context
  const context = page.getByRole("region", { name: "Business context" });
  await context.getByRole("button", { name: "Edit business context" }).click();
  await context.getByLabel("Products and services").fill("Payroll software");
  await context.getByLabel("Departments hiring").fill("Engineering, Sales");
  await context.getByLabel("Target roles").fill("Java Developer");
  await context.getByRole("button", { name: "Add branch" }).click();
  await context.getByLabel("Branch 1 City").fill("Pune");
  await context.getByLabel("Branch 1 Country").fill("India");
  await context.getByRole("button", { name: "Save business context" }).click();
  await expect(page.getByText("Business context saved.")).toBeVisible();
  await expect(context.getByText("Engineering, Sales")).toBeVisible();
  await expect(context.getByText("Pune, India")).toBeVisible();
  await page.reload();
  await expect(page.getByRole("region", { name: "Business context" }).getByText("Java Developer")).toBeVisible();

  // AC2: logging a call moves Last contact in place
  const contacts = await (await page.request.get(`/api/v1/recruiter/companies/${company.id}/contacts`)).json();
  const call = await page.request.post("/api/v1/recruiter/calls", { data: { contact_id: contacts.items[0].id, outcome: "connected" } });
  expect(call.status()).toBe(201);
  await page.reload();
  const lastContact = page.getByRole("region", { name: "Details", exact: true }).locator("dt", { hasText: "Last contact" }).locator("xpath=following-sibling::dd[1]");
  await expect(lastContact).not.toHaveText("—");

  // AC3: upload and download a document
  const documents = page.getByRole("region", { name: "Documents", exact: true });
  await expect(documents.getByText("No documents yet.")).toBeVisible();
  await documents.getByLabel("Document type").selectOption("company_profile");
  await documents.getByLabel(/^File/).setInputFiles({ name: "profile.pdf", mimeType: "application/pdf", buffer: PDF });
  await documents.getByRole("button", { name: "Upload document" }).click();
  await expect(documents.getByText("Document uploaded.")).toBeVisible();
  const link = documents.getByRole("link", { name: "Download profile.pdf" });
  await expect(link).toBeVisible();
  const download = await page.request.get((await link.getAttribute("href"))!);
  expect(download.status()).toBe(200);
  expect(download.headers()["content-disposition"]).toContain(company.code);

  // the list sorts by last contact and shows the column
  await page.goto(`/recruiter/companies?sort=last_contacted&q=${encodeURIComponent(company.code)}`);
  await expect(page.getByRole("columnheader", { name: "Last contact" })).toBeVisible();

  await page.goto(`/recruiter/companies/${company.id}`);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("region", { name: "Documents", exact: true })).toBeVisible();
  expect(await noSideScroll(page)).toBe(true);
});
