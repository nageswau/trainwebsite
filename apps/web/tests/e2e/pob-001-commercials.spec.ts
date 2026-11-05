import { expect, test, type Page } from "@playwright/test";

// pob-001 (DEC-SCOPE-403): the seeded recruiter sees the contract fee and terms by default (C3); after a super admin denies them
// `commercials.client.view` (a nehn-007 per-user override) the company page shows no fee or terms, no Revenue section and no
// Receivables menu item, and the receivables page says why (AC1). The override is cleared afterwards. Run with --workers=1.
const RECRUITER = "placement@edusphere.local";
const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

async function signIn(page: Page, email: string, portal: "it" | "admin") {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function setOverrides(page: Page, userId: string, overrides: object[]) {
  await signIn(page, "superadmin@edusphere.local", "admin");
  const response = await page.request.put(`/api/v1/admin/users/${userId}/permissions`, { data: { overrides } });
  expect(response.status(), await response.text()).toBe(200);
}

test("a recruiter without commercials.client.view sees no fee, terms, revenue or receivables", async ({ page }) => {
  test.setTimeout(120_000);
  await signIn(page, RECRUITER, "it");
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  const created = await page.request.post("/api/v1/recruiter/companies", { data: { name: `POB1 ${Date.now()} Pvt` } });
  expect(created.status()).toBe(201);
  const company = (await created.json()).company;
  const contract = await page.request.post(`/api/v1/recruiter/companies/${company.id}/contracts`, {
    data: { agreement_type: "Permanent hiring", fee_basis: "fixed", fee_value: "50000", payment_terms: "30 days from joining" },
  });
  expect(contract.status()).toBe(201);

  await page.goto(`/recruiter/companies/${company.id}`);
  const card = page.locator("#company-contract");
  await expect(card.getByText("Recruitment fee")).toBeVisible(); // C3: today's recruiters keep the terms
  await expect(card.getByText("30 days from joining")).toBeVisible();
  await expect(page.getByRole("link", { name: "Receivables" }).first()).toBeVisible();

  try {
    await setOverrides(page, me.id, [{ permission: "commercials.client.view", effect: "deny", reason: "pob-001 e2e" }]);
    await signIn(page, RECRUITER, "it");
    await page.goto(`/recruiter/companies/${company.id}`);
    await expect(card.getByText("Permanent hiring")).toBeVisible();
    await expect(card.getByText("Recruitment fee")).toHaveCount(0);
    await expect(card.getByText("30 days from joining")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Revenue" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Receivables" })).toHaveCount(0);
    await card.getByRole("button", { name: "Edit contract" }).click();
    await expect(card.getByLabel("Fee basis")).toHaveCount(0);
    await card.getByRole("button", { name: "Cancel" }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await noSideScroll(page)).toBe(true);
    await page.goto("/recruiter/receivables");
    await expect(page.getByText("Your role cannot view client commercials")).toBeVisible();
  } finally {
    await setOverrides(page, me.id, []);
  }
});
