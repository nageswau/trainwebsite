import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// tel-017 (DEC-SCOPE-076): the IT Admin creates an IT counselor; it activates, signs in at /it/login, lands on its own workspace
// (Dashboard + Leads, C1), sees the IT lead routed to it, and is refused the overseas counselor workspace. Throwaway accounts.

async function signIn(page: Page, portal: "it" | "overseas", email: string, password: string, landing: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("IT admin creates an IT counselor, who lands on the IT workspace and sees their routed lead", async ({ page }) => {
  test.setTimeout(45_000);
  const stamp = Date.now();
  await signIn(page, "it", "itadmin@edusphere.local", "Demo@123", "/it/admin/dashboard");

  // AC1 in the UI: the IT admin's Create user form offers Counselor.
  await page.goto("/it/admin/users");
  await expect(page.getByLabel("Role").locator("option[value='counselor']")).toHaveCount(1);

  const created = await page.request.post("/api/v1/admin/users", {
    data: { role: "counselor", division: "it", full_name: `E2E IT Counselor ${stamp}`, email: `tel017-c-${stamp}@example.local` },
  });
  expect(created.status()).toBe(201);
  const counselor = await created.json();
  expect(counselor.division).toBe("it");

  // AC2: an IT lead routed to them (the existing owner_id routing; tel-018 adds the real handover).
  const enquiry = await page.request.post("/api/v1/public/enquiries", {
    data: { division: "it", name: `E2E Lead ${stamp}`, email: `tel017-l-${stamp}@example.com`, subject: "Full Stack Java", message: "Please call me back." },
  });
  expect(enquiry.status()).toBe(201);
  const routed = await page.request.patch(`/api/v1/admin/leads/${(await enquiry.json()).id}`, { data: { owner_id: counselor.id } });
  expect(routed.status()).toBe(200);

  // The IT admin's Counselors page lists the new account.
  await page.goto("/it/admin/counselors");
  await expect(page.getByText(`E2E IT Counselor ${stamp}`).first()).toBeVisible();
  await page.request.post("/api/v1/auth/logout");

  await activateWithToken(page.request, counselor.development_welcome_token);
  await signIn(page, "it", counselor.email, E2E_PASSWORD, "/it/counselor/dashboard");
  const nav = page.getByRole("navigation").filter({ has: page.getByRole("link", { name: "Leads" }) });
  await expect(nav.getByRole("link")).toHaveText(["Dashboard", "Leads"]);
  await expect(page.getByText("Leads routed to you", { exact: true })).toBeVisible();
  await expect(page.getByText(`E2E Lead ${stamp}`)).toBeVisible(); // the dashboard's recent-leads table

  await page.getByRole("link", { name: "Leads" }).click();
  await page.waitForURL("**/it/counselor/leads");
  await expect(page.getByRole("heading", { name: "My Leads" })).toBeVisible();
  await expect(page.getByText(`E2E Lead ${stamp}`)).toBeVisible();

  // AC3: the overseas counselor workspace refuses an IT counselor, and the card's way home is the IT workspace.
  await page.goto("/overseas/counselor/dashboard");
  await expect(page.getByText("Role/division mismatch")).toBeVisible();
  // C1: overseas sections don't exist in the IT workspace.
  const missing = await page.goto("/it/counselor/visa");
  expect(missing?.status()).toBe(404);
});

test("signed-out /it/counselor visits go to the IT sign-in", async ({ page }) => {
  await page.goto("/it/counselor/leads");
  await page.waitForURL("**/it/login?next=%2Fit%2Fcounselor%2Fleads");
});
