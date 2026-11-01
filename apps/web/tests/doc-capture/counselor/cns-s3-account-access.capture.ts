import { test, type Page } from "@playwright/test";

import { COUNSELOR_ROOT, mailCount, mailLink, noPrefetch, password, shoot, signIn, toTop } from "../shoot";

// Counselor CRM S3 (docs/counselor-crm/documentation-plan.md): DOC-CNS-AUTH-001..006 (deactivated sign-in is S10), NAV-001.
// Runs after cns-s2: Docs Counselor A/B/C set their first passwords from the welcome emails in Mailpit.
const root = COUNSELOR_ROOT;
const AUTH = "account-access";
const NAV = "navigation";
const A = "docs.counselor.a@example.test";
const DASH = /\/overseas\/counselor\/dashboard/;
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const main = async (page: Page) => (await page.locator("main").or(page.locator("body")).first().innerText()).replace(/\s+/g, " ").slice(0, 900);

async function setFirstPassword(p: Page, email: string, value: string) {
  await p.goto(await mailLink(email));
  await p.getByLabel("New password").fill(value);
  await p.getByRole("button", { name: "Reset password" }).click();
  await p.waitForURL(/\/overseas\/login/);
}

test("Counselor CRM S3 account access and navigation", async ({ browser }) => {
  test.setTimeout(600_000);
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const p = await ctx.newPage();

  // --- AUTH-001 sign-in page (demo card masked) and a wrong password ---
  await p.goto("/overseas/login");
  await shoot(p, AUTH, "01-overseas-login.png", { root });
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
  await p.waitForURL(/\/overseas\/login/);
  await p.waitForTimeout(800);
  await say(p, "AUTH-002 set");
  await shoot(p, AUTH, "05-after-set-password-login.png", { root });
  // The same link a second time.
  await p.goto(link);
  await p.getByLabel("New password").fill(password("test") + "x");
  await p.getByRole("button", { name: "Reset password" }).click();
  await p.waitForTimeout(1200);
  await say(p, "AUTH-002 reused link");
  await shoot(p, AUTH, "06-set-password-link-used.png", { root });
  for (const who of ["docs.counselor.b@example.test", "docs.counselor.c@example.test"]) await setFirstPassword(p, who, password("test"));
  console.log("VERIFY AUTH-002 B and C passwords set");

  // --- AUTH-001 landing + NAV-001 tour ---
  await signIn(p, A, "test", DASH);
  await p.waitForTimeout(2000);
  console.log(`VERIFY AUTH-001 landing ${p.url()} :: ${await main(p)}`);
  await shoot(p, AUTH, "07-signed-in-dashboard.png", { root });
  const sidebar = p.locator("aside.sidebar");
  console.log(`VERIFY NAV-001 sidebar: ${(await sidebar.innerText()).replace(/\s+/g, " | ")}`);
  await shoot(p, NAV, "01-sidebar.png", { root, element: sidebar });
  await shoot(p, NAV, "02-topbar.png", { root, element: p.locator(".portal-topbar") });
  for (const [slug, file] of [["school-applications", "03-school-applications.png"], ["counselor-chat", "04-counselor-chat.png"]] as const) {
    await p.goto(`/overseas/counselor/${slug}`);
    await p.waitForTimeout(1500);
    console.log(`VERIFY NAV-001 ${slug}: ${await main(p)}`);
    await shoot(p, NAV, file, { root });
  }
  await p.goto("/account/management-tasks");
  await p.waitForTimeout(1500);
  console.log(`VERIFY NAV-001 management-tasks: ${p.url()} :: ${(await p.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 600)}`);
  await shoot(p, NAV, "05-management-tasks.png", { root });

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
  console.log(`VERIFY AUTH-005 page: ${(await p.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 900)}`);
  await shoot(p, AUTH, "12-my-profile.png", { root });
  await p.getByLabel("Phone").first().fill("+91 90000 10031");
  await p.getByRole("button", { name: "Save changes" }).first().click();
  await p.waitForTimeout(1200);
  await say(p, "AUTH-005 saved");
  await shoot(p, AUTH, "13-my-profile-saved.png", { root });

  // --- AUTH-006 sign out ---
  await p.goto("/overseas/counselor/dashboard");
  await p.waitForTimeout(1500);
  const footer = p.locator(".sidebar-footer");
  await footer.evaluate((el) => el.scrollIntoView({ block: "center", behavior: "instant" }));
  await shoot(p, AUTH, "14-sidebar-footer-sign-out.png", { root, element: p.locator("aside.sidebar") });
  await footer.getByRole("button", { name: "Sign out" }).click();
  await p.waitForURL((u) => !u.pathname.startsWith("/overseas/counselor"));
  await p.waitForTimeout(1200);
  console.log(`VERIFY AUTH-006 after sign out: ${p.url()}`);
  await p.goto("/overseas/counselor/dashboard");
  await p.waitForTimeout(1200);
  console.log(`VERIFY AUTH-006 protected page after sign out: ${p.url()}`);
  await shoot(p, AUTH, "15-signed-out-redirect.png", { root });

  // --- AUTH-003 forgot password ---
  await p.goto("/overseas/login");
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
  await say(p, "AUTH-003 reset (same password)");
  console.log(`VERIFY AUTH-003 after reset: ${p.url()}`);

  // --- AUTH-001 wrong portal: a counselor at the administration sign-in ---
  await p.goto("/admin/login");
  await p.fill("#login-email", A);
  await p.fill("#login-password", password("test"));
  await p.click("button:has-text('Sign in securely')");
  await p.waitForTimeout(1500);
  await say(p, "AUTH-001 wrong portal");
  await shoot(p, AUTH, "18-wrong-portal.png", { root });
});

// NAV-001 at 390 px (P18). Read-only, rerunnable on its own: -g "mobile".
test("Counselor CRM S3 mobile navigation", async ({ browser }) => {
  // --- NAV-001 mobile (390 px): menu without Sign out (P18) ---
  const m = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await noPrefetch(m);
  const mp = await m.newPage();
  await signIn(mp, A, "test", DASH);
  await mp.waitForTimeout(1500);
  await shoot(mp, NAV, "06-mobile-dashboard.png", { root });
  await mp.getByRole("button", { name: "Open menu" }).click();
  await mp.waitForTimeout(600);
  const panel = mp.locator("#portal-mobile-nav-panel");
  console.log(`VERIFY NAV-001 mobile menu: ${(await panel.innerText()).replace(/\s+/g, " | ")}`);
  await shoot(mp, NAV, "07-mobile-menu-open.png", { root });
  // The panel scrolls on its own; show its last items (no Sign out).
  await panel.evaluate((el) => {
    let n: HTMLElement | null = el as HTMLElement;
    while (n && n.scrollHeight <= n.clientHeight) n = n.parentElement;
    (n ?? document.scrollingElement!).scrollTop = 1e6;
  });
  await mp.waitForTimeout(400);
  await shoot(mp, NAV, "08-mobile-menu-end.png", { root });
  // Workaround check: My profile uses the public site header, which has its own Logout.
  await mp.goto("/account/profile");
  await mp.waitForTimeout(1200);
  const header = (await mp.locator("header").first().innerText().catch(() => "")).replace(/\s+/g, " ");
  console.log(`VERIFY NAV-001 mobile profile header: ${header}`);
  await mp.getByRole("button", { name: /menu/i }).first().click().catch(() => console.log("VERIFY no public menu button"));
  await mp.waitForTimeout(600);
  const logout = mp.getByRole("button", { name: "Logout" }).or(mp.getByRole("link", { name: "Logout" })).first();
  console.log(`VERIFY NAV-001 mobile public Logout visible: ${await logout.isVisible().catch(() => false)}`);
  await shoot(mp, NAV, "09-mobile-profile-public-menu.png", { root });
});

// NAV-001: each sidebar item's page heading (read-only, -g "headings").
test("Counselor CRM S3 sidebar headings", async ({ browser }) => {
  test.setTimeout(300_000);
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const p = await ctx.newPage();
  await signIn(p, A, "test", DASH);
  const items = await p.locator("aside.sidebar nav a").evaluateAll((as) => as.map((a) => [a.textContent?.trim() ?? "", (a as HTMLAnchorElement).getAttribute("href") ?? ""]));
  for (const [label, href] of items) {
    await p.goto(href);
    await p.waitForTimeout(1200);
    const h1 = await p.locator("main h1, main h2").first().innerText({ timeout: 3000 }).catch(() => "(no heading)");
    console.log(`VERIFY heading ${label} -> ${href} -> ${h1.replace(/\s+/g, " ")}`);
  }
});
