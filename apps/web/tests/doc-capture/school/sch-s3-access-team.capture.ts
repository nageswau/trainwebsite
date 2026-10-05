import { readFileSync, writeFileSync } from "node:fs";

import { expect, test, type Browser, type Page } from "@playwright/test";

import { inviteLink, mailLink, noPrefetch, password, SCHOOL_ROOT, shoot, signIn } from "../shoot";

// School CRM S3 (docs/school-crm/documentation-plan.md): DOC-SCH-AUTH-001..009, DOC-SCH-TEAM-001..003.
// Runs after sch-s2-admin on the same DB; reads/extends DOCS_SCHOOL_FILE.
const ACC = "account-access";
const TEAM = "team";
const opts = { root: SCHOOL_ROOT };
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const main = async (page: Page) => {
  const scope = (await page.locator("main").count()) ? page.locator("main").first() : page.locator("body");
  return (await scope.innerText()).replace(/\s+/g, " ").slice(0, 400);
};

const INVITES = [
  { role: "Teacher", name: "Docs Teacher A", email: "docs.teacher.a@example.test", accept: true },
  { role: "Teacher", name: "Docs Teacher B", email: "docs.teacher.b@example.test", accept: true },
  { role: "Principal", name: "Docs Principal", email: "docs.principal@example.test", accept: false },
  { role: "Parent", name: "Docs Parent", email: "docs.parent@example.test", accept: false },
];

async function fresh(browser: Browser, viewport = { width: 1440, height: 900 }) {
  const ctx = await browser.newContext({ viewport });
  await noPrefetch(ctx);
  return { ctx, page: await ctx.newPage() };
}

async function login(page: Page, email: string, pw: string) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", pw);
  await page.click("button:has-text('Sign in securely')");
}

// Opens a welcome (set-password) link from Mailpit and sets DOCS_TEST_PASSWORD.
async function setFirstPassword(page: Page, email: string, shots?: { form: string }) {
  await page.goto(await mailLink(email));
  await page.fill("#reset-new-password", password("test"));
  if (shots) await shoot(page, ACC, shots.form, opts);
  await page.getByRole("button", { name: "Reset password" }).click();
  await page.waitForURL(/\/overseas\/login/);
}

test("School CRM S3 account access and team", async ({ browser }) => {
  test.setTimeout(600_000);
  const school = JSON.parse(readFileSync(process.env.DOCS_SCHOOL_FILE!, "utf8"));

  // --- AUTH-001 sign-in errors ---
  {
    const { ctx, page } = await fresh(browser);
    await login(page, "school.teacher@edusphere.local", "not-the-password");
    await expect(page.getByText("Invalid credentials")).toBeVisible();
    await shoot(page, ACC, "02-login-invalid-credentials.png", opts);
    await page.goto("/it/login");
    await page.fill("#login-email", "school.coordinator@edusphere.local");
    await page.fill("#login-password", password());
    await page.click("button:has-text('Sign in securely')");
    await expect(page.getByText(/Use the correct EduSphere portal/)).toBeVisible();
    await say(page, "wrong portal");
    await shoot(page, ACC, "03-login-wrong-portal.png", opts);
    await ctx.close();
  }

  // --- AUTH-003 first password from a welcome link (Docs Platinum Two Coordinator), then every other S2 account ---
  {
    const { ctx, page } = await fresh(browser);
    await setFirstPassword(page, school.schools.platinum2.email, { form: "04-set-password-form.png" });
    await login(page, school.schools.platinum2.email, password("test"));
    await page.waitForURL(/\/school\/coordinator\/dashboard/);
    await shoot(page, ACC, "05-first-sign-in-coordinator-dashboard.png", opts);
    await ctx.close();
    const others = [school.schools.bronze.email, school.schools.notier.email, "docs.renewal.coordinator@example.test", "docs.expired.coordinator@example.test", ...school.staff.map((s: { email: string }) => s.email)];
    for (const email of others) {
      const f = await fresh(browser);
      await setFirstPassword(f.page, email);
      await f.ctx.close();
    }
    const bad = await fresh(browser);
    await bad.page.goto("/overseas/reset-password?token=not-a-real-token");
    await bad.page.fill("#reset-new-password", password("test"));
    await bad.page.getByRole("button", { name: "Reset password" }).click();
    await expect(bad.page.getByText("Reset token is invalid or expired")).toBeVisible();
    await say(bad.page, "invalid link");
    await shoot(bad.page, ACC, "06-set-password-invalid-link.png", opts);
    await bad.page.goto("/overseas/reset-password");
    console.log(`VERIFY missing token: ${await main(bad.page)}`);
    await shoot(bad.page, ACC, "07-reset-link-missing-token.png", opts);
    await bad.ctx.close();
  }

  // --- TEAM-001/002 invite (Sunrise Coordinator) ---
  const co = await fresh(browser);
  await signIn(co.page, "school.coordinator@edusphere.local", "seed", /\/school\/coordinator\//);
  await co.page.goto("/school/coordinator/team");
  await expect(co.page.getByLabel("Full name")).toBeVisible();
  await shoot(co.page, TEAM, "01-team-list.png", opts);
  for (const [i, inv] of INVITES.entries()) {
    await co.page.selectOption("#invite-role", { label: inv.role });
    await co.page.fill("#invite-name", inv.name);
    await co.page.fill("#invite-email", inv.email);
    if (i === 0) await shoot(co.page, TEAM, "02-invite-form-filled.png", { ...opts, center: co.page.locator("#invite-email") });
    await co.page.getByRole("button", { name: "Send invite" }).click();
    const sent = co.page.getByText(`Invite sent to ${inv.email}`);
    await expect(sent).toBeVisible({ timeout: 20_000 });
    await say(co.page, `invite ${inv.name}`);
    if (i === 0) await shoot(co.page, TEAM, "03-invite-sent.png", { ...opts, center: sent });
  }
  await co.page.selectOption("#invite-role", { label: "Teacher" });
  await co.page.fill("#invite-name", "Existing Teacher");
  await co.page.fill("#invite-email", "school.teacher@edusphere.local");
  await co.page.getByRole("button", { name: "Send invite" }).click();
  await expect(co.page.getByText("Email already exists")).toBeVisible();
  await shoot(co.page, TEAM, "04-invite-email-exists.png", { ...opts, center: co.page.getByText("Email already exists") });

  // --- AUTH-002 accept invitations ---
  const linkA = await inviteLink(INVITES[0].email);
  {
    const { ctx, page } = await fresh(browser);
    await page.goto(linkA);
    await page.fill("#invite-password", password("test"));
    await shoot(page, ACC, "08-invite-accept-form.png", opts);
    await page.getByRole("button", { name: "Accept and set up login" }).click();
    await page.waitForURL(/\/school\/teacher\/dashboard/);
    await shoot(page, ACC, "09-invite-accepted-teacher-dashboard.png", opts);
    await ctx.close();
  }
  {
    const { ctx, page } = await fresh(browser);
    await page.goto(await inviteLink(INVITES[1].email));
    await page.fill("#invite-password", password("test"));
    await page.getByRole("button", { name: "Accept and set up login" }).click();
    await page.waitForURL(/\/school\/teacher\/dashboard/);
    await ctx.close();
  }
  {
    const { ctx, page } = await fresh(browser);
    await page.goto(linkA);
    await page.fill("#invite-password", password("test"));
    await page.getByRole("button", { name: "Accept and set up login" }).click();
    await expect(page.getByText(/already been used, expired, or was revoked/)).toBeVisible();
    await say(page, "used invite");
    await shoot(page, ACC, "10-invite-already-used.png", opts);
    await ctx.close();
  }

  // --- TEAM-002/003 team after acceptance; deactivate Teacher B ---
  await co.page.goto("/school/coordinator/team");
  await expect(co.page.getByRole("cell", { name: "Docs Teacher A" })).toBeVisible();
  await shoot(co.page, TEAM, "05-team-and-pending-invites.png", { ...opts, element: co.page.locator("main") });
  console.log(`VERIFY team: ${await main(co.page)}`);
  await co.page.getByRole("row", { name: /Docs Teacher B/ }).getByRole("button", { name: "Deactivate" }).click();
  const deact = co.page.getByText("Docs Teacher B deactivated.");
  await expect(deact).toBeVisible();
  await shoot(co.page, TEAM, "06-teacher-deactivated.png", { ...opts, center: deact });

  // --- AUTH-008 access unavailable ---
  {
    const { ctx, page } = await fresh(browser);
    await login(page, INVITES[1].email, password("test"));
    await expect(page.getByText("Invalid credentials")).toBeVisible();
    await shoot(page, ACC, "11-login-deactivated.png", opts);
    await page.goto("/school/parent/dashboard");
    console.log(`VERIFY signed out: ${await main(page).catch(async () => (await page.locator("body").innerText()).slice(0, 300))}`);
    await shoot(page, ACC, "12-access-signed-out.png", opts);
    await ctx.close();
  }
  {
    const { ctx, page } = await fresh(browser);
    await signIn(page, INVITES[0].email, "test", /\/school\/teacher\//);
    await page.goto("/school/principal/reports");
    console.log(`VERIFY wrong role: ${(await page.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 300)}`);
    await shoot(page, ACC, "13-access-wrong-role.png", opts);
    await ctx.close();
  }
  const students = await (await co.page.request.get("/api/v1/school/students")).json();
  {
    const { ctx, page } = await fresh(browser);
    await signIn(page, school.schools.platinum2.email, "test", /\/school\/coordinator\//);
    await page.goto(`/school/coordinator/students/${students[0].id}`);
    console.log(`VERIFY other school: ${(await page.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 300)}`);
    await shoot(page, ACC, "14-access-other-school-student.png", opts);
    await ctx.close();
  }

  // --- AUTH-004 forgot / reset password (Docs Teacher A) ---
  {
    const { ctx, page } = await fresh(browser);
    const before = await (await fetch(`${process.env.DOCS_MAILPIT_URL}/api/v1/messages`)).json();
    await page.goto("/overseas/forgot-password");
    await page.fill("#forgot-email", INVITES[0].email);
    await shoot(page, ACC, "15-forgot-password-form.png", opts);
    await page.getByRole("button", { name: "Send reset instructions" }).click();
    await expect(page.getByText(/If an account exists for that email/)).toBeVisible();
    await say(page, "forgot sent");
    await shoot(page, ACC, "16-forgot-password-sent.png", opts);
    await page.waitForTimeout(3000);
    const after = await (await fetch(`${process.env.DOCS_MAILPIT_URL}/api/v1/messages`)).json();
    console.log(`VERIFY U2 reset email in Mailpit: before=${before.total} after=${after.total} newest="${after.messages?.[0]?.Subject}" to=${after.messages?.[0]?.To?.[0]?.Address}`);
    const dev = await page.getByRole("link", { name: "reset link" }).getAttribute("href");
    await page.goto(new URL(dev!, page.url()).pathname + new URL(dev!, page.url()).search);
    await page.fill("#reset-new-password", password("test"));
    await shoot(page, ACC, "17-reset-password-form.png", opts);
    await page.getByRole("button", { name: "Reset password" }).click();
    await page.waitForURL(/\/overseas\/login/);
    await ctx.close();
  }

  // --- AUTH-005 change password, AUTH-006 profile, AUTH-007 session, AUTH-009 sidebar (Docs Teacher A) ---
  {
    const { ctx, page } = await fresh(browser);
    await signIn(page, INVITES[0].email, "test", /\/school\/teacher\//);
    await page.goto("/account/password");
    await page.fill("#change-current-password", "wrong-current-password");
    await page.fill("#change-new-password", password("test") + "2");
    await shoot(page, ACC, "18-change-password-form.png", opts);
    await page.click("#change-password-submit");
    await expect(page.locator("#change-password-error")).toBeVisible();
    await say(page, "wrong current");
    await shoot(page, ACC, "19-change-password-wrong-current.png", opts);
    await page.fill("#change-current-password", password("test"));
    await page.fill("#change-new-password", password("test") + "2");
    await page.click("#change-password-submit");
    await expect(page.getByText("Your password was changed.")).toBeVisible();
    await shoot(page, ACC, "20-change-password-success.png", opts);
    // Put the known test password back for later sessions.
    await page.fill("#change-current-password", password("test") + "2");
    await page.fill("#change-new-password", password("test"));
    await page.click("#change-password-submit");
    await expect(page.getByText("Your password was changed.")).toBeVisible();

    await page.goto("/account/profile");
    await page.fill("#profile-phone", "+91 98200 12345");
    await page.click("#profile-submit");
    await expect(page.getByText("Your profile was updated.")).toBeVisible();
    await shoot(page, ACC, "21-profile-saved.png", opts);
    await page.reload();
    await page.check("#notify-whatsapp");
    await page.getByRole("button", { name: "Save notification settings" }).click();
    const saved = page.getByText("Notification settings saved.");
    await expect(saved).toBeVisible();
    await shoot(page, ACC, "22-notification-settings-saved.png", { ...opts, center: saved });

    // Session expiry: the 60-minute access cookie is gone; the web app never uses the refresh cookie.
    await ctx.clearCookies({ name: "edusphere_access" });
    await page.goto("/school/teacher/dashboard");
    console.log(`VERIFY expired session: ${(await page.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 300)}`);
    await shoot(page, ACC, "23-session-expired.png", opts);

    await signIn(page, INVITES[0].email, "test", /\/school\/teacher\//);
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.waitForURL((u) => u.pathname === "/");
    console.log(`VERIFY sign out lands on: ${new URL(page.url()).pathname}`);
    await ctx.close();
  }
  {
    const { ctx, page } = await fresh(browser, { width: 390, height: 844 });
    await signIn(page, "school.coordinator@edusphere.local", "seed", /\/school\/coordinator\//);
    await page.getByRole("button", { name: "Open menu" }).click();
    await page.waitForTimeout(500);
    await shoot(page, ACC, "25-mobile-menu-coordinator.png", opts);
    await ctx.close();
  }
  await co.ctx.close();

  school.invites = INVITES.map(({ name, email, role, accept }) => ({ name, email, role, accepted: accept }));
  school.deactivated = [INVITES[1].email];
  writeFileSync(process.env.DOCS_SCHOOL_FILE!, JSON.stringify(school));
});
