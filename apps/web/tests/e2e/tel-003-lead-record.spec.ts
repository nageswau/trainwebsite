import { expect, test, type Page } from "@playwright/test";

// tel-003 (AC1-AC3): a website enquiry gets an LD- Lead ID; the IT Admin finds it by that ID, filters by source (in the URL, so a
// refresh keeps it), sees the empty-filter message, and nothing overflows at 320 / 375 px. A source outside the list is refused.
test.describe.configure({ timeout: 90_000 });

async function signInItAdmin(page: Page) {
  await page.goto("/it/login");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/it/admin/dashboard");
}

async function noOverflow(page: Page) {
  for (const width of [320, 375]) {
    await page.setViewportSize({ width, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), `overflow at ${width}px`).toBe(true);
  }
  await page.setViewportSize({ width: 1280, height: 800 });
}

test("a website enquiry gets a Lead ID the admin can search and filter by", async ({ page }) => {
  const stamp = `${Date.now()}${Math.floor(Math.random() * 1e4)}`;
  const email = `tel003-${stamp}@example.com`;
  const name = `Lead Record ${stamp}`;
  const mobile = `9${String(stamp).slice(-9)}`; // tel-005 (T12): a known mobile would attach to its existing lead
  const created = await page.request.post("/api/v1/public/enquiries", {
    data: { division: "it", name, email, phone: `0${mobile.slice(0, 5)} ${mobile.slice(5)}`, subject: "Cyber Security", message: "Please call me about the course." },
  });
  expect(created.status()).toBe(201);
  const { lead_code: leadCode } = await created.json();
  expect(leadCode).toMatch(/^LD-\d{6,}$/);

  await signInItAdmin(page);
  await page.goto("/it/admin/leads");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Manage leads" }) });
  await panel.getByLabel("Search leads").fill(leadCode);
  await panel.getByRole("button", { name: "Search" }).click();
  await expect(page).toHaveURL(new RegExp(`q=${leadCode}`));
  await expect(panel.getByRole("rowheader")).toHaveText([name]);
  const row = panel.locator("tr", { has: page.getByRole("rowheader", { name, exact: true }) });
  for (const text of [leadCode, "Website", "Unassigned", "Warm", "Cyber Security"]) await expect(row).toContainText(text);

  await panel.getByLabel("Source").selectOption("google");
  await expect(panel.getByText("No leads match these filters.")).toBeVisible();
  await page.reload(); // the filter and search live in the URL
  await expect(panel.getByLabel("Source")).toHaveValue("google");
  await expect(panel.getByText("No leads match these filters.")).toBeVisible();
  await panel.getByLabel("Source").selectOption("website");
  await expect(panel.getByRole("rowheader")).toHaveText([name]);
  await noOverflow(page);
});

test("a source outside the §2 list is refused", async ({ request }) => {
  const response = await request.post("/api/v1/public/enquiries", {
    data: { division: "it", name: "Bad Source", email: `bad-${Date.now()}@example.com`, subject: "Python", message: "Hello there", source: "tiktok" },
  });
  expect(response.status()).toBe(422);
});
