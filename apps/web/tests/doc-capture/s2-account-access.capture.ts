import { expect, test, type Page } from "@playwright/test";

import { password, shoot, signIn, toTop } from "./shoot";

// S2 (docs/documentation-plan.md): DOC-AUTH-001..006 and DOC-ADM-001. Creates the docs test agencies as it goes:
// Docs Pending Agency (left pending), Docs Rejected Agency, Docs Suspended Agency, Docs Second Agency (approved).
const AUTH = "account-access";
const ADM = "admin-agencies";
const run = Date.now().toString().slice(-6);
const email = (who: string) => `docs.${who}.${run}@example.test`;
const AGENCIES = {
  pending: { name: "Docs Pending Agency", master: "Priya Pending", email: email("pending") },
  rejected: { name: "Docs Rejected Agency", master: "Rahul Rejected", email: email("rejected") },
  suspended: { name: "Docs Suspended Agency", master: "Sana Suspended", email: email("suspended") },
  second: { name: "Docs Second Agency", master: "Arun Second", email: email("second") },
};

const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};

async function register(page: Page, a: { name: string; master: string; email: string }, shots = false) {
  await page.goto("/overseas/register");
  if (shots) await shoot(page, AUTH, "04-register-empty.png");
  await page.fill('input[name="full_name"]', a.master);
  await page.fill('input[name="email"]', a.email);
  await page.fill('input[name="phone"]', "+91 98450 12345");
  await page.selectOption('select[name="account_type"]', "agent");
  await page.fill('input[name="agency_name"]', a.name);
  await page.fill('input[name="password"]', password("test"));
  if (shots) await shoot(page, AUTH, "05-register-agent-filled.png");
  await page.click('button:has-text("Create account")');
  await page.waitForURL("**/overseas/agent/dashboard");
  await expect(page.getByText("Access unavailable")).toBeVisible();
}

const orgCard = (page: Page, agencyEmail: string) => page.locator(".card", { hasText: agencyEmail }).last();
// Buttons carry aria-label "<Action> <agency name>"; match it exactly ("Reject" is a substring of "Docs Rejected Agency").
const act = (page: Page, a: { name: string; email: string }, action: string) =>
  orgCard(page, a.email).getByRole("button", { name: `${action} ${a.name}`, exact: true });

test("S2 account access and agency approvals", async ({ browser }) => {
  test.setTimeout(240_000);

  // --- DOC-AUTH-002 sign in (errors) ---
  let ctx = await browser.newContext();
  let page = await ctx.newPage();
  await page.goto("/overseas/login");
  await shoot(page, AUTH, "01-login-page.png");
  await page.fill("#login-email", "agent@edusphere.local");
  await page.fill("#login-password", "not-the-right-password");
  await page.click("button:has-text('Sign in securely')");
  await expect(page.getByText("Invalid credentials")).toBeVisible();
  await shoot(page, AUTH, "02-login-invalid-credentials.png");
  await page.fill("#login-email", "itadmin@edusphere.local");
  await page.fill("#login-password", password());
  await page.click("button:has-text('Sign in securely')");
  await expect(page.getByText("Use the correct EduSphere portal")).toBeVisible();
  await shoot(page, AUTH, "03-login-wrong-portal.png");

  // --- DOC-AUTH-001 register; DOC-AUTH-003 pending card ---
  await register(page, AGENCIES.pending, true);
  await shoot(page, AUTH, "07-access-unavailable-pending.png");
  // U2: can a pending agent open Change password?
  await page.goto("/account/password");
  console.log(`VERIFY U2 pending agent /account/password heading: ${await page.locator("h1").first().innerText()}`);
  await ctx.close();

  ctx = await browser.newContext();
  page = await ctx.newPage();
  await page.goto("/overseas/register");
  await page.fill('input[name="full_name"]', "Docs Duplicate");
  await page.fill('input[name="email"]', "agent@edusphere.local");
  await page.selectOption('select[name="account_type"]', "agent");
  await page.fill('input[name="password"]', password("test"));
  await page.click('button:has-text("Create account")');
  await expect(page.getByText("Email already exists")).toBeVisible();
  await shoot(page, AUTH, "06-register-duplicate-email.png");
  for (const a of [AGENCIES.rejected, AGENCIES.suspended, AGENCIES.second]) {
    await ctx.close();
    ctx = await browser.newContext();
    page = await ctx.newPage();
    await register(page, a);
  }
  await ctx.close();

  // --- DOC-ADM-001 approvals as Overseas Admin ---
  ctx = await browser.newContext();
  page = await ctx.newPage();
  await signIn(page, "overseasadmin@edusphere.local");
  await page.goto("/overseas/admin/agents");
  await expect(orgCard(page, AGENCIES.second.email)).toBeVisible();
  await toTop(page.getByRole("heading", { name: "Agent Approvals" }));
  await shoot(page, ADM, "01-agent-approvals-pending.png");
  await page.getByLabel("Search agencies").fill("Docs Second");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(orgCard(page, AGENCIES.second.email)).toBeVisible();
  await toTop(page.getByRole("heading", { name: "Agent Approvals" }));
  await shoot(page, ADM, "02-agent-approvals-search.png");
  await page.getByLabel("Search agencies").fill("");
  await page.getByRole("button", { name: "Search", exact: true }).click();

  await act(page, AGENCIES.rejected, "Reject").click();
  await say(page, "ADM-001 reject");
  await page.getByRole("button", { name: "Pending", exact: true }).click();
  await act(page, AGENCIES.suspended, "Approve").click();
  await say(page, "ADM-001 approve");
  await page.getByRole("button", { name: "Pending", exact: true }).click();
  await act(page, AGENCIES.second, "Approve").click();
  await expect(page.getByText(`${AGENCIES.second.name} approved.`)).toBeVisible();
  await toTop(page.getByRole("heading", { name: "Agent Approvals" }));
  await shoot(page, ADM, "03-agent-approvals-approved.png");
  await act(page, AGENCIES.suspended, "Suspend").click();
  await toTop(orgCard(page, AGENCIES.suspended.email));
  await shoot(page, ADM, "04-agent-approvals-suspend-confirm.png");
  await page.getByRole("button", { name: "Confirm suspend" }).click();
  await say(page, "ADM-001 suspend");
  await toTop(page.getByRole("heading", { name: "Agent Approvals" }));
  await shoot(page, ADM, "05-agent-approvals-suspended.png");
  await page.getByRole("button", { name: "Rejected", exact: true }).click();
  await expect(orgCard(page, AGENCIES.rejected.email)).toBeVisible();
  await toTop(page.getByRole("heading", { name: "Agent Approvals" }));
  await shoot(page, ADM, "06-agent-approvals-rejected.png");
  await ctx.close();

  // --- DOC-AUTH-003 suspended / rejected cards ---
  ctx = await browser.newContext();
  page = await ctx.newPage();
  await signIn(page, AGENCIES.suspended.email, "test");
  await expect(page.getByText("Your agency's account is suspended")).toBeVisible();
  await shoot(page, AUTH, "08-access-unavailable-suspended.png");
  await ctx.close();
  ctx = await browser.newContext();
  page = await ctx.newPage();
  await signIn(page, AGENCIES.rejected.email, "test");
  console.log(`VERIFY rejected agency card: ${(await page.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 160)}`);
  await ctx.close();

  // --- DOC-AUTH-004 forgot / reset (Docs Second Agency Master) ---
  ctx = await browser.newContext();
  page = await ctx.newPage();
  await page.goto("/overseas/login");
  await page.getByRole("link", { name: "Forgot your password?" }).click();
  await page.waitForURL("**/overseas/forgot-password");
  await page.fill('input[type="email"]', AGENCIES.second.email);
  await shoot(page, AUTH, "09-forgot-password.png");
  await page.click("button:has-text('Send reset instructions')");
  await expect(page.getByText("If an account exists for that email")).toBeVisible();
  await shoot(page, AUTH, "10-forgot-password-sent.png");
  const devLink = page.getByRole("link", { name: /reset link/i });
  await devLink.click();
  await page.waitForURL(/reset-password\?token=/);
  await page.fill('input[type="password"]', password("test"));
  await shoot(page, AUTH, "11-reset-password-form.png");
  await page.click("button:has-text('Reset password')");
  await page.waitForURL("**/overseas/login**");
  console.log(`VERIFY reset success landed on ${new URL(page.url()).pathname}`);
  await page.goto("/overseas/reset-password?token=expired-or-invalid");
  await page.fill('input[type="password"]', password("test"));
  await page.click("button:has-text('Reset password')");
  await expect(page.getByText("Reset token is invalid or expired")).toBeVisible();
  await shoot(page, AUTH, "12-reset-password-invalid.png");
  await ctx.close();

  // --- DOC-AUTH-002 signed in + sign out; DOC-AUTH-005 change password; DOC-AUTH-006 profile ---
  ctx = await browser.newContext();
  page = await ctx.newPage();
  await signIn(page, AGENCIES.second.email, "test");
  await expect(page.getByText("Whole agency")).toBeVisible();
  await shoot(page, AUTH, "13-signed-in-sidebar.png");
  await page.getByRole("link", { name: "Change password" }).first().click();
  await page.waitForURL("**/account/password");
  await shoot(page, AUTH, "14-change-password.png");
  const pw = page.locator('input[type="password"]');
  await pw.nth(0).fill("not-the-current-password");
  await pw.nth(1).fill(`${password("test")}-new`);
  await page.getByRole("button", { name: "Change password" }).click();
  await expect(page.getByText("Incorrect current password")).toBeVisible();
  await shoot(page, AUTH, "15-change-password-wrong-current.png");
  await pw.nth(0).fill(password("test"));
  await pw.nth(1).fill(`${password("test")}-new`);
  await page.getByRole("button", { name: "Change password" }).click();
  await expect(page.getByText("Your password was changed.")).toBeVisible();
  await shoot(page, AUTH, "16-change-password-success.png");
  // Put the test password back so later sessions can sign in.
  await page.reload();
  await pw.nth(0).fill(`${password("test")}-new`);
  await pw.nth(1).fill(password("test"));
  await page.getByRole("button", { name: "Change password" }).click();
  await expect(page.getByText("Your password was changed.")).toBeVisible();

  await page.goto("/account/profile");
  await shoot(page, AUTH, "17-my-profile.png", { fullPage: true });
  await page.fill("#profile-full-name", "A");
  await page.getByRole("button", { name: "Save changes" }).click();
  await say(page, "AUTH-006 short name");
  await shoot(page, AUTH, "18-my-profile-validation.png");
  await page.goto("/overseas/agent/dashboard");
  await page.getByRole("button", { name: "Sign out" }).first().click();
  await page.waitForURL((u) => !u.pathname.startsWith("/overseas/agent"));
  console.log(`VERIFY sign out landed on ${new URL(page.url()).pathname}`);
  await ctx.close();

  console.log(`AGENCIES ${JSON.stringify(Object.fromEntries(Object.entries(AGENCIES).map(([k, v]) => [k, v.email])))}`);
});
