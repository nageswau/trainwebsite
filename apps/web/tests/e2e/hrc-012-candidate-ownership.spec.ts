import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// hrc-012 (DEC-SCOPE-382): a recruiter who adds a candidate owns it (O7) and finds it under My candidates; they hand it to another
// recruiter from the Ownership card (O2/O5), after which they can no longer change it and the new owner sees it as theirs. A placement
// manager sets a placement officer, and the officer's dashboard counts it (O3). The Ownership card fits a phone.

async function signIn(page: Page, loginPath: string, email: string, password = E2E_PASSWORD) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function post(page: Page, url: string, data: unknown) {
  const response = await page.request.post(url, { data });
  expect(response.ok(), await response.text()).toBe(true);
  return response.json();
}

async function setUp(page: Page, stamp: number) {
  await signIn(page, "/admin/login", "superadmin@edusphere.local", "Demo@123");
  const manager = await post(page, "/api/v1/admin/users", { role: "placement_manager", division: "global", full_name: `E2E H12 Manager ${stamp}`, email: `hrc012-m-${stamp}@example.local` });
  const recruiter = (suffix: string, name: string) => post(page, "/api/v1/admin/users", {
    role: "placement_team", full_name: `${name} ${stamp}`, email: `hrc012-${suffix}-${stamp}@example.local`,
    recruiter_profile: { employee_id: `H12-${stamp}-${suffix}`, reporting_manager_user_id: manager.id },
  });
  const adder = await recruiter("a", "E2E Adder");
  const taker = await recruiter("b", "E2E Taker");
  const officer = await post(page, "/api/v1/admin/users", { role: "placement_officer", division: "it", full_name: `E2E Officer ${stamp}`, email: `hrc012-o-${stamp}@example.local` });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [manager, adder, taker, officer]) await activateWithToken(page.request, user.development_welcome_token);
  return { manager, adder, taker, officer };
}

async function addCandidate(page: Page, name: string, stamp: number) {
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  return post(page, "/api/v1/recruiter/candidates", { name, email: `hrc012-c-${stamp}@example.com`, source_id: sources.items[0].id });
}

test("a recruiter owns what they add, hands it over, and a manager names a placement officer", async ({ page }) => {
  const stamp = Date.now();
  const { manager, adder, taker, officer } = await setUp(page, stamp);
  const name = `E2E Owned ${stamp}`;
  const adderName = `E2E Adder ${stamp}`;
  const takerName = `E2E Taker ${stamp}`;

  await signIn(page, "/it/login", adder.email);
  const candidate = await addCandidate(page, name, stamp);
  await page.goto(`/recruiter/candidates?owner=me&q=${encodeURIComponent(name)}`);
  await expect(page.getByLabel("Owner")).toHaveValue("me");
  await expect(page.getByRole("row", { name: new RegExp(name) })).toContainText(adderName);

  await page.getByRole("link", { name }).click();
  const card = page.getByRole("region", { name: "Ownership" });
  await expect(card).toContainText(adderName);
  await card.getByRole("button", { name: "Change ownership" }).click();
  const group = card.getByRole("group", { name: "Change ownership" });
  await group.getByRole("combobox", { name: "Primary recruiter" }).fill(takerName);
  await page.getByRole("option", { name: new RegExp(takerName) }).click();
  await group.getByRole("button", { name: "Save ownership" }).click();
  await expect(card.getByRole("status")).toHaveText("Ownership updated.");
  await expect(card).toContainText(takerName);
  await expect(card.getByRole("button", { name: "Change ownership" })).toHaveCount(0); // no longer the owner

  await signIn(page, "/it/login", taker.email);
  await page.goto(`/recruiter/candidates?owner=me&q=${encodeURIComponent(name)}`);
  await expect(page.getByRole("link", { name })).toBeVisible();

  await signIn(page, "/admin/login", manager.email);
  await page.goto(`/recruiter/candidates/${candidate.id}`);
  const managerCard = page.getByRole("region", { name: "Ownership" });
  await managerCard.getByRole("button", { name: "Change ownership" }).click();
  await managerCard.getByRole("combobox", { name: "Placement officer" }).fill(`E2E Officer ${stamp}`);
  await page.getByRole("option", { name: new RegExp(`E2E Officer ${stamp}`) }).click();
  await managerCard.getByRole("button", { name: "Save ownership" }).click();
  await expect(managerCard.getByRole("status")).toHaveText("Ownership updated.");
  await expect(managerCard).toContainText(`E2E Officer ${stamp}`);

  await signIn(page, "/it/login", officer.email);
  await page.goto("/it/placement-officer/dashboard");
  await expect(page.getByText("Your candidates")).toBeVisible();
});

test("the Ownership card fits a phone", async ({ page }) => {
  const stamp = Date.now();
  const { adder } = await setUp(page, stamp);
  await signIn(page, "/it/login", adder.email);
  const candidate = await addCandidate(page, `E2E Phone ${stamp}`, stamp);
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto(`/recruiter/candidates/${candidate.id}`);
  const card = page.getByRole("region", { name: "Ownership" });
  await card.getByRole("button", { name: "Change ownership" }).click();
  await expect(card.getByRole("button", { name: "Save ownership" })).toBeInViewport();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
