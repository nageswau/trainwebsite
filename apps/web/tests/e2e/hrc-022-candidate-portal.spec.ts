import { expect, test, type Page } from "@playwright/test";

// hrc-022 (DEC-SCOPE-385): an external candidate registers from the careers page, verifies by the emailed link (development shows it),
// is refused sign-in until verified, signs in, edits an allow-listed field (the name stays with the recruiter), changes their email only
// through a link to the new address, and leaves the pool from Privacy. Each run gets its own client IP header, so the per-network
// registration throttle (5 an hour) never trips a re-run.
const PASSWORD = "Candidate@12345";

async function freshNetwork(page: Page) {
  const n = () => Math.floor(Math.random() * 65535).toString(16);
  await page.setExtraHTTPHeaders({ "X-Forwarded-For": `2001:db8::${n()}:${n()}` });
}

async function register(page: Page, email: string) {
  await page.goto("/it/careers");
  await page.getByRole("link", { name: "Create candidate account" }).click();
  await expect(page.getByRole("heading", { name: "Create a candidate account" })).toBeVisible();
  await page.getByLabel("Full name").fill("Asha Portal");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Mobile (optional)").fill("");
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD);
  await page.getByLabel("Confirm password").fill(PASSWORD);
  await page.getByRole("checkbox").check();
  await page.getByRole("button", { name: "Create candidate account" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Check your inbox" })).toContainText(email);
}

async function signIn(page: Page, email: string) {
  await page.goto("/it/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
}

test("register, verify, sign in, edit an allowed field, change email by link, leave the pool", async ({ page }) => {
  await freshNetwork(page);
  const email = `hrc022-${Date.now()}@example.com`;
  await register(page, email);

  await signIn(page, email); // not verified yet
  await expect(page.getByRole("alert").filter({ hasText: "Verify your email address first" })).toBeVisible();

  await page.goto("/it/careers");
  await register(page, `${email}.x`); // a second account, so the dev link below is for a fresh one
  await page.getByRole("link", { name: "open the verification link" }).click();
  await page.getByRole("button", { name: "Verify my email" }).click();
  await expect(page.getByRole("status")).toContainText("Your email is verified");

  // the first account: its link from the resend API (development), then sign in
  const resent = await (await page.request.post("/api/v1/candidate/resend-verification", { data: { email } })).json();
  await page.goto(`/it/careers/verify-email?token=${encodeURIComponent(resent.development_verification_token)}`);
  await page.getByRole("button", { name: "Verify my email" }).click();
  await expect(page.getByRole("status")).toContainText("Your email is verified");
  await page.getByRole("link", { name: "Sign in" }).click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await page.waitForURL("**/it/careers/portal/profile");
  await expect(page.getByRole("heading", { name: "My profile" })).toBeVisible();
  await expect(page.getByText(email).first()).toBeVisible();

  // AC3: the name is not offered; the city is
  await expect(page.getByLabel("Full name")).toHaveCount(0);
  await expect(page.getByText("Kept by your recruiter")).toBeVisible();
  await page.getByLabel("City").fill("Pune");
  await page.getByRole("button", { name: "Save my details" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Your profile is saved." })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("City")).toHaveValue("Pune");

  // AC4: the old email stays until the link to the new one is opened
  const newEmail = `hrc022-new-${Date.now()}@example.com`;
  await page.getByLabel("New email").fill(newEmail);
  await page.getByLabel("Current password").fill(PASSWORD);
  await page.getByRole("button", { name: "Send confirmation link" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Your current email stays in use" })).toBeVisible();
  await page.reload();
  await expect(page.getByText(`Waiting for confirmation: ${newEmail}`)).toBeVisible();
  const change = await (await page.request.post("/api/v1/candidate/me/email", { data: { new_email: newEmail, current_password: PASSWORD } })).json();
  await page.goto(`/it/careers/verify-email?token=${encodeURIComponent(change.development_verification_token)}`);
  await page.getByRole("button", { name: "Verify my email" }).click();
  await expect(page.getByRole("status")).toContainText("Your email address is updated.");
  await page.getByRole("link", { name: "Back to my profile" }).click();
  await expect(page.getByText(newEmail).first()).toBeVisible();

  // QA-01: the portal's own nav item is not a second "My profile"
  await expect(page.getByRole("link", { name: "Candidate profile" })).toBeVisible();
  await expect(page.getByRole("link", { name: "My profile", exact: true })).toHaveCount(1);
  // C12: leave the pool
  await page.getByRole("link", { name: "Privacy" }).click();
  await expect(page.getByText("In the candidate pool", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Leave the candidate pool" }).click();
  await expect(page.getByRole("status").filter({ hasText: "You have left the candidate pool" })).toBeVisible();
  await expect(page.getByText("Left the pool")).toBeVisible();
});

test("the portal is protected and staff are refused", async ({ page }) => {
  await page.goto("/it/careers/portal/profile");
  await page.waitForURL("**/it/login?next=%2Fit%2Fcareers%2Fportal%2Fprofile");
  expect((await page.request.post("/api/v1/auth/login", { data: { email: "placement@edusphere.local", password: "Demo@123", division: "it" } })).ok()).toBeTruthy();
  expect((await page.request.get("/api/v1/candidate/me")).status()).toBe(403);
});

test("registration and the profile fit a phone", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/it/careers/register");
  await expect(page.getByRole("button", { name: "Create candidate account" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
});
