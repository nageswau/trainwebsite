import { test, type Page } from "@playwright/test";

import { mailCount, mailLink, noPrefetch, password, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S3 (docs/recruitment-crm/documentation-plan.md): DOC-REC-AUTH-001..005 (deactivated account is S16), NAV-001..003,
// DASH-003..005. Runs after rec-s2: every Docs recruitment persona sets a first password from the welcome email in Mailpit.
const root = REC_ROOT;
const AUTH = "account-access";
const NAV = "navigation";
const DASH = "dashboard";
const A = "docs.rec.a@example.test";
const LEAD = "docs.rec.lead@example.test";
const LOGIN_AFTER_RESET = /\/(it\/|overseas\/|admin\/)?login/;
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const main = async (page: Page) => (await page.locator("main").or(page.locator("body")).first().innerText()).replace(/\s+/g, " ").slice(0, 1200);

async function setFirstPassword(p: Page, email: string) {
  await p.goto(await mailLink(email));
  await p.getByLabel("New password").fill(password("test"));
  await p.getByRole("button", { name: "Reset password" }).click();
  await p.waitForURL(LOGIN_AFTER_RESET);
}

test("Recruitment CRM S3 account access", async ({ browser }) => {
  test.setTimeout(600_000);
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const p = await ctx.newPage();

  // --- AUTH-001 the IT sign-in page and a wrong password ---
  await p.goto("/it/login");
  await shoot(p, AUTH, "01-it-login.png", { root });
  await p.fill("#login-email", A);
  await p.fill("#login-password", "not-the-password");
  await p.click("button:has-text('Sign in securely')");
  await p.waitForTimeout(1500);
  await say(p, "AUTH-001 wrong password");
  await shoot(p, AUTH, "02-login-invalid-credentials.png", { root });

  // --- AUTH-002 first password (Recruiter A), then everyone else ---
  await p.goto(await mailLink(A));
  await p.waitForTimeout(800);
  console.log(`VERIFY AUTH-002 page: ${await main(p)}`);
  await shoot(p, AUTH, "03-set-password-page.png", { root });
  await p.getByLabel("New password").fill("short");
  await p.getByRole("button", { name: "Reset password" }).click();
  await p.waitForTimeout(1000);
  await say(p, "AUTH-002 too short");
  await shoot(p, AUTH, "04-set-password-too-short.png", { root });
  await p.getByLabel("New password").fill(password("test"));
  await p.getByRole("button", { name: "Reset password" }).click();
  await p.waitForURL(LOGIN_AFTER_RESET);
  await p.waitForTimeout(800);
  console.log(`VERIFY AUTH-002 after set: ${p.url()}`);
  await say(p, "AUTH-002 set");
  await shoot(p, AUTH, "05-after-set-password-login.png", { root });
  for (const who of ["docs.rec.b", "docs.rec.po", "docs.rec.hr", "docs.rec.hrm", "docs.rec.interviewer"]) await setFirstPassword(p, `${who}@example.test`);
  // the Team Lead's link opens the administration reset page
  await p.goto(await mailLink(LEAD));
  console.log(`VERIFY AUTH-002 Team Lead link path: ${new URL(p.url()).pathname}`);
  await p.getByLabel("New password").fill(password("test"));
  await p.getByRole("button", { name: "Reset password" }).click();
  await p.waitForURL(LOGIN_AFTER_RESET);
  console.log(`VERIFY AUTH-002 Team Lead lands on: ${p.url()}`);

  // --- AUTH-001 Team Lead at /admin/login; a recruiter at the wrong portal ---
  await p.goto("/admin/login");
  await p.waitForTimeout(800);
  await shoot(p, AUTH, "06-admin-login.png", { root });
  await p.fill("#login-email", A);
  await p.fill("#login-password", password("test"));
  await p.click("button:has-text('Sign in securely')");
  await p.waitForTimeout(2000);
  await say(p, "AUTH-001 wrong portal");
  await shoot(p, AUTH, "07-wrong-portal.png", { root });

  const lctx = await browser.newContext();
  await noPrefetch(lctx);
  const l = await lctx.newPage();
  await signIn(l, LEAD, "test", /\/recruiter\/manager\/team/, "/admin/login");
  await l.waitForTimeout(2500);
  console.log(`VERIFY AUTH-001 Team Lead landing ${l.url()} :: ${await main(l)}`);
  await shoot(l, AUTH, "08-team-lead-landing.png", { root });

  // --- Recruiter A signs in; AUTH-004 recruiter profile and change password ---
  await signIn(p, A, "test", /\/recruiter\/dashboard/, "/it/login");
  await p.waitForTimeout(2500);
  console.log(`VERIFY AUTH-001 recruiter landing ${p.url()}`);
  await shoot(p, AUTH, "09-recruiter-landing.png", { root });
  await p.goto("/recruiter/profile");
  await p.waitForTimeout(2000);
  console.log(`VERIFY AUTH-004 profile: ${await main(p)}`);
  await shoot(p, AUTH, "10-recruiter-profile.png", { root });
  const save = p.getByRole("button", { name: "Save mobile" });
  const mob = p.locator("form").filter({ has: save }).locator("input").first();
  await mob.fill("+91 90000 30011");
  await save.click();
  await p.waitForTimeout(1500);
  await say(p, "AUTH-004 save mobile");
  await shoot(p, AUTH, "11-recruiter-profile-saved.png", { root });
  await p.goto("/account/password");
  await p.waitForTimeout(1000);
  await shoot(p, AUTH, "12-change-password.png", { root });
  const changeTo = async (current: string, next: string) => {
    await p.getByLabel("Current password").fill(current);
    await p.getByLabel("New password").fill(next);
    await p.getByRole("button", { name: "Change password" }).click();
    await p.waitForTimeout(1200);
  };
  await changeTo("wrong-current-pass", password("test") + "-2");
  await say(p, "AUTH-004 wrong current");
  await changeTo(password("test"), password("test") + "-2");
  await say(p, "AUTH-004 changed");
  await shoot(p, AUTH, "13-change-password-success.png", { root });
  await p.goto("/account/password");
  await changeTo(password("test") + "-2", password("test"));
  await say(p, "AUTH-004 changed back");

  // --- AUTH-005 sign out ---
  await p.goto("/recruiter/dashboard");
  await p.waitForTimeout(2000);
  const footer = p.locator(".sidebar-footer");
  await footer.evaluate((el) => el.scrollIntoView({ block: "center", behavior: "instant" }));
  await shoot(p, AUTH, "14-sidebar-footer-sign-out.png", { root, element: p.locator("aside.sidebar") });
  await footer.getByRole("button", { name: "Sign out" }).click();
  await p.waitForURL((u) => !u.pathname.startsWith("/recruiter"));
  await p.goto("/recruiter/dashboard");
  await p.waitForTimeout(1500);
  console.log(`VERIFY AUTH-005 protected page after sign out: ${p.url()}`);
  await shoot(p, AUTH, "15-signed-out-redirect.png", { root });

  // --- AUTH-003 forgot password ---
  await p.goto("/it/login");
  await p.getByRole("link", { name: "Forgot your password?" }).click();
  await p.waitForURL(/forgot-password/);
  await shoot(p, AUTH, "16-forgot-password.png", { root });
  const before = await mailCount(A);
  await p.getByLabel("Email").fill(A);
  await p.getByRole("button", { name: "Send reset instructions" }).click();
  await p.waitForTimeout(1500);
  await say(p, "AUTH-003 sent");
  await shoot(p, AUTH, "17-forgot-password-sent.png", { root });
  await p.goto(await mailLink(A, before));
  await p.getByLabel("New password").fill(password("test"));
  await p.getByRole("button", { name: "Reset password" }).click();
  await p.waitForTimeout(1500);
  await say(p, "AUTH-003 reset");
  console.log(`VERIFY AUTH-003 after reset: ${p.url()}`);
});

// NAV-001..003, DASH-003..005: read only, rerunnable (-g "navigation").
test("Recruitment CRM S3 navigation", async ({ browser }) => {
  test.setTimeout(600_000);
  const tour = async (email: string, kind: "test", landing: RegExp, portal: string, prefix: string, dashShot?: string) => {
    const ctx = await browser.newContext();
    await noPrefetch(ctx);
    const p = await ctx.newPage();
    await signIn(p, email, kind, landing, portal);
    await p.waitForTimeout(2500);
    const sidebar = p.locator("aside.sidebar");
    console.log(`VERIFY ${prefix} landing ${p.url()} sidebar: ${(await sidebar.innerText()).replace(/\s+/g, " | ")}`);
    await shoot(p, NAV, `${prefix}-sidebar.png`, { root, element: sidebar });
    if (dashShot) {
      console.log(`VERIFY ${prefix} dashboard: ${await main(p)}`);
      await shoot(p, DASH, dashShot, { root });
    }
    const items = await sidebar.locator("nav a").evaluateAll((as) => as.map((a) => [a.textContent?.trim() ?? "", (a as HTMLAnchorElement).getAttribute("href") ?? ""]));
    for (const [label, href] of items) {
      await p.goto(href);
      await p.waitForTimeout(1500);
      const h = await p.locator("main h1, main h2").first().innerText({ timeout: 3000 }).catch(() => "(no heading)");
      console.log(`VERIFY ${prefix} heading ${label} -> ${href} -> ${p.url().replace(/^https?:\/\/[^/]+/, "")} -> ${h.replace(/\s+/g, " ")}`);
    }
    await ctx.close();
  };
  await tour(A, "test", /\/recruiter\/dashboard/, "/it/login", "01-recruiter");
  await tour(LEAD, "test", /\/recruiter\/manager\/team/, "/admin/login", "02-team-lead");
  await tour("docs.rec.hr@example.test", "test", /\/it\/hr\/dashboard/, "/it/login", "03-hr", "01-hr-dashboard.png");
  await tour("docs.rec.hrm@example.test", "test", /\/it\/hr-manager\/dashboard/, "/it/login", "04-hr-manager", "02-hr-manager-dashboard.png");
  await tour("docs.rec.po@example.test", "test", /\/it\/placement-officer\/dashboard/, "/it/login", "05-placement-officer", "03-placement-officer-dashboard.png");
  await tour("docs.rec.interviewer@example.test", "test", /\/it\/interviewer\/dashboard/, "/it/login", "06-interviewer", "04-interviewer-dashboard.png");
});
