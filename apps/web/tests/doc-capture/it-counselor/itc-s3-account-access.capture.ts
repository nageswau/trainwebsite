import { test, type Page } from "@playwright/test";

import { ITC_ROOT, mailCount, mailLink, noPrefetch, password, shoot, signIn } from "../shoot";

// IT Counselor CRM S3 (docs/it-counselor-crm/documentation-plan.md): DOC-ITC-AUTH-001..005, AUTH-006 sign out (deactivated is S10), NAV-001.
// Runs after itc-s2: Docs IT Counselor A/B and Docs IT Telecaller set their first passwords from the welcome emails in Mailpit.
const root = ITC_ROOT;
const AUTH = "account-access";
const NAV = "navigation";
const A = "docs.itc.a@example.test";
const DASH = /\/it\/counselor\/dashboard/;
const LOGIN_AFTER_RESET = /\/(it\/|overseas\/|admin\/)?login/;
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const main = async (page: Page) => (await page.locator("main").or(page.locator("body")).first().innerText()).replace(/\s+/g, " ").slice(0, 900);

async function setFirstPassword(p: Page, email: string, value: string) {
  await p.goto(await mailLink(email));
  await p.getByLabel("New password").fill(value);
  await p.getByRole("button", { name: "Reset password" }).click();
  await p.waitForURL(LOGIN_AFTER_RESET);
}

test("IT Counselor CRM S3 account access and navigation", async ({ browser }) => {
  test.setTimeout(600_000);
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const p = await ctx.newPage();

  // --- AUTH-001 sign-in page (demo card masked) and a wrong password ---
  await p.goto("/it/login");
  await shoot(p, AUTH, "01-it-login.png", { root });
  await p.fill("#login-email", A);
  await p.fill("#login-password", "not-the-password");
  await p.click("button:has-text('Sign in securely')");
  await p.waitForTimeout(1500);
  await say(p, "AUTH-001 wrong password");
  await shoot(p, AUTH, "02-login-invalid-credentials.png", { root });

  // --- AUTH-002 first password from the welcome email ---
  await p.goto(await mailLink(A));
  await p.waitForTimeout(800);
  console.log(`VERIFY AUTH-002 page: ${await main(p)}`);
  await shoot(p, AUTH, "03-set-password-page.png", { root });
  await p.getByLabel("New password").fill("short");
  await p.getByRole("button", { name: "Reset password" }).click();
  await p.waitForTimeout(1000);
  await say(p, "AUTH-002 too short");
  await shoot(p, AUTH, "04-set-password-too-short.png", { root });
  const link = new URL(p.url()).pathname + new URL(p.url()).search;
  await p.getByLabel("New password").fill(password("test"));
  await p.getByRole("button", { name: "Reset password" }).click();
  await p.waitForURL(LOGIN_AFTER_RESET);
  await p.waitForTimeout(800);
  console.log(`VERIFY AUTH-002 after set: ${p.url()}`);
  await say(p, "AUTH-002 set");
  await shoot(p, AUTH, "05-after-set-password-login.png", { root });
  await p.goto(link);
  await p.getByLabel("New password").fill(password("test") + "x");
  await p.getByRole("button", { name: "Reset password" }).click();
  await p.waitForTimeout(1200);
  await say(p, "AUTH-002 reused link");
  await shoot(p, AUTH, "06-set-password-link-used.png", { root });
  for (const who of ["docs.itc.b@example.test", "docs.itc.telecaller@example.test"]) await setFirstPassword(p, who, password("test"));
  console.log("VERIFY AUTH-002 B and telecaller passwords set");

  // --- AUTH-001 landing + NAV-001 tour ---
  await signIn(p, A, "test", DASH, "/it/login");
  await p.waitForTimeout(2500);
  console.log(`VERIFY AUTH-001 landing ${p.url()} :: ${await main(p)}`);
  await shoot(p, AUTH, "07-signed-in-dashboard.png", { root });
  const sidebar = p.locator("aside.sidebar");
  console.log(`VERIFY NAV-001 sidebar: ${(await sidebar.innerText()).replace(/\s+/g, " | ")}`);
  await shoot(p, NAV, "01-sidebar.png", { root, element: sidebar });
  await shoot(p, NAV, "02-topbar.png", { root, element: p.locator(".portal-topbar") });
  await p.goto("/account/management-tasks");
  await p.waitForTimeout(1500);
  console.log(`VERIFY NAV-001 management-tasks: ${p.url()} :: ${(await p.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 600)}`);
  await shoot(p, NAV, "03-management-tasks.png", { root });

  // --- AUTH-004 change password ---
  await p.goto("/account/password");
  await p.waitForTimeout(1000);
  await shoot(p, AUTH, "08-change-password-page.png", { root });
  const changeTo = async (current: string, next: string) => {
    await p.getByLabel("Current password").fill(current);
    await p.getByLabel("New password").fill(next);
    await p.getByRole("button", { name: "Change password" }).click();
    await p.waitForTimeout(1200);
  };
  await changeTo("wrong-current-pass", password("test") + "-2");
  await say(p, "AUTH-004 wrong current");
  await shoot(p, AUTH, "09-change-password-incorrect.png", { root });
  await changeTo(password("test"), password("test"));
  await say(p, "AUTH-004 same");
  await shoot(p, AUTH, "10-change-password-same.png", { root });
  await changeTo(password("test"), password("test") + "-2");
  await say(p, "AUTH-004 changed");
  await shoot(p, AUTH, "11-change-password-success.png", { root });
  await p.goto("/account/password");
  await changeTo(password("test") + "-2", password("test"));
  await say(p, "AUTH-004 changed back");

  // --- AUTH-005 my profile ---
  await p.goto("/account/profile");
  await p.waitForTimeout(1200);
  console.log(`VERIFY AUTH-005 page: ${(await p.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 1200)}`);
  await shoot(p, AUTH, "12-my-profile.png", { root });
  await p.getByLabel("Phone").first().fill("+91 90000 20031");
  await p.getByRole("button", { name: "Save changes" }).first().click();
  await p.waitForTimeout(1200);
  await say(p, "AUTH-005 saved");
  await shoot(p, AUTH, "13-my-profile-saved.png", { root });

  // --- AUTH-006 sign out ---
  await p.goto("/it/counselor/dashboard");
  await p.waitForTimeout(1500);
  const footer = p.locator(".sidebar-footer");
  await footer.evaluate((el) => el.scrollIntoView({ block: "center", behavior: "instant" }));
  await shoot(p, AUTH, "14-sidebar-footer-sign-out.png", { root, element: p.locator("aside.sidebar") });
  await footer.getByRole("button", { name: "Sign out" }).click();
  await p.waitForURL((u) => !u.pathname.startsWith("/it/counselor"));
  await p.waitForTimeout(1200);
  console.log(`VERIFY AUTH-006 after sign out: ${p.url()}`);
  await p.goto("/it/counselor/dashboard");
  await p.waitForTimeout(1200);
  console.log(`VERIFY AUTH-006 protected page after sign out: ${p.url()}`);
  await shoot(p, AUTH, "15-signed-out-redirect.png", { root });

  // --- AUTH-003 forgot password ---
  await p.goto("/it/login");
  await p.getByRole("link", { name: "Forgot your password?" }).click();
  await p.waitForURL(/forgot-password/);
  console.log(`VERIFY AUTH-003 forgot url: ${p.url()}`);
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
  await say(p, "AUTH-003 reset (same password)");
  console.log(`VERIFY AUTH-003 after reset: ${p.url()}`);

  // --- AUTH-001 wrong portal: an IT counselor at the Overseas sign-in ---
  await p.goto("/overseas/login");
  await p.fill("#login-email", A);
  await p.fill("#login-password", password("test"));
  await p.click("button:has-text('Sign in securely')");
  await p.waitForTimeout(2000);
  await say(p, "AUTH-001 wrong portal");
  console.log(`VERIFY AUTH-001 wrong portal url: ${p.url()}`);
  await shoot(p, AUTH, "18-wrong-portal.png", { root });
});

// NAV-001 at 390 px. Read-only, rerunnable on its own: -g "mobile".
test("IT Counselor CRM S3 mobile navigation", async ({ browser }) => {
  const m = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await noPrefetch(m);
  const mp = await m.newPage();
  await signIn(mp, A, "test", DASH, "/it/login");
  await mp.waitForTimeout(1500);
  await shoot(mp, NAV, "04-mobile-dashboard.png", { root });
  await mp.getByRole("button", { name: "Open menu" }).click();
  await mp.waitForTimeout(600);
  const panel = mp.locator("#portal-mobile-nav-panel");
  console.log(`VERIFY NAV-001 mobile menu: ${(await panel.innerText()).replace(/\s+/g, " | ")}`);
  await shoot(mp, NAV, "05-mobile-menu-open.png", { root });
});

// NAV-001: each sidebar item's page heading (read-only, -g "headings"), plus Timetable and Notifications shots.
test("IT Counselor CRM S3 sidebar headings", async ({ browser }) => {
  test.setTimeout(300_000);
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const p = await ctx.newPage();
  await signIn(p, A, "test", DASH, "/it/login");
  const items = await p.locator("aside.sidebar nav a").evaluateAll((as) => as.map((a) => [a.textContent?.trim() ?? "", (a as HTMLAnchorElement).getAttribute("href") ?? ""]));
  for (const [label, href] of items) {
    await p.goto(href);
    await p.waitForTimeout(1500);
    const h1 = await p.locator("main h1, main h2").first().innerText({ timeout: 3000 }).catch(() => "(no heading)");
    console.log(`VERIFY heading ${label} -> ${href} -> ${h1.replace(/\s+/g, " ")}`);
  }
});
