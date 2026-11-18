import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { ITC_ROOT, noPrefetch, password, shoot, signIn } from "../shoot";

// IT Counselor CRM S10 (docs/it-counselor-crm/documentation-plan.md): DOC-ITC-HO-003 (what the student sees), AUTH-006 (deactivated
// account), ADM-002 (deactivate / reactivate). Runs after itc-s9b. Owner I3: the student's fee page is captured, nothing is paid.
const root = ITC_ROOT;
const B = "docs.itc.b@example.test";
const ARJUN = "docs.itlead.arjun@example.test";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 2000);
async function ctxPage(browser: Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  return ctx.newPage();
}
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);

test("IT Counselor CRM S10 student view and lifecycle", async ({ browser }) => {
  test.setTimeout(900_000);

  // ===== HO-003: Docs IT Lead Arjun's own portal =====
  const s = await ctxPage(browser);
  await signIn(s, ARJUN, "test", /\/it\/student\//, "/it/login");
  for (const [section, file] of [
    ["dashboard", "20-student-dashboard.png"],
    ["profile", "21-student-profile.png"],
    ["updates", "22-student-updates.png"],
    ["fees", "23-student-fees.png"],
    ["notifications", "24-student-notifications.png"],
    ["timetable", "25-student-timetable.png"],
  ] as const) {
    await s.goto(`/it/student/${section}`);
    await settle(s, 2500);
    console.log(`VERIFY HO-003 ${section}: ${await text(s.locator("main"))}`);
    await shoot(s, "handoffs", file, { root, fullPage: section === "profile" || section === "fees" });
  }

  // ===== Counselor B has an open session =====
  const b = await ctxPage(browser);
  await signIn(b, B, "test", /\/it\/counselor\/dashboard/, "/it/login");

  // ===== ADM-002: IT Admin deactivates Docs IT Counselor B =====
  const a = await ctxPage(browser);
  await signIn(a, "itadmin@edusphere.local", "seed", /\/it\/admin\//, "/it/login");
  await a.goto("/it/admin/users");
  await settle(a, 2500);
  const manage = a.locator(".action-card").filter({ has: a.getByRole("heading", { name: /Manage users|Directory/ }) }).first();
  await manage.getByLabel("Search by name, email, role, or Student ID").fill("Docs IT Counselor B");
  await settle(a, 1500);
  const row = manage.locator("tr", { hasText: "Docs IT Counselor B" }).first();
  await row.getByRole("button", { name: "Deactivate" }).click();
  await settle(a, 2000);
  await say(a, "ADM-002 deactivate first click");
  const confirm = row.getByRole("button", { name: "Confirm deactivate" });
  if (await confirm.count()) {
    await shoot(a, "admin", "62-deactivate-confirm.png", { root, element: row });
    await confirm.click();
    await settle(a, 2000);
    await say(a, "ADM-002 deactivate confirmed");
  }
  console.log(`VERIFY ADM-002 row after deactivate: ${await text(row)}`);
  await shoot(a, "admin", "63-deactivated.png", { root, element: row });

  // AUTH-006: B's open session, then a new sign-in
  await b.goto("/it/counselor/students");
  await settle(b, 2500);
  console.log(`VERIFY AUTH-006 open session url ${b.url()}: ${await text(b.locator("body"))}`);
  await shoot(b, "account-access", "30-deactivated-session.png", { root });
  const n = await ctxPage(browser);
  await n.goto("/it/login");
  await n.getByLabel("Email").fill(B);
  await n.getByLabel("Password").fill(password("test"));
  await n.getByRole("button", { name: /Sign in/ }).click();
  await settle(n, 3000);
  await say(n, "AUTH-006 deactivated sign-in");
  await shoot(n, "account-access", "31-deactivated-sign-in.png", { root });

  // Student list shows the inactive counselor
  await a.goto("/it/admin/students");
  await settle(a, 2500);
  console.log(`VERIFY ADM-002 students after deactivate: ${await text(a.locator("main .workspace").first())}`);

  // ===== ADM-002: reactivate =====
  await a.goto("/it/admin/users");
  await settle(a, 2500);
  await manage.getByLabel("Search by name, email, role, or Student ID").fill("Docs IT Counselor B");
  await settle(a, 1500);
  await row.getByRole("button", { name: "Reactivate" }).click();
  await settle(a, 2500);
  await say(a, "ADM-002 reactivated");
  await shoot(a, "admin", "64-reactivated.png", { root, element: row });
  await signIn(n, B, "test", /\/it\/counselor\/dashboard/, "/it/login");
  console.log(`VERIFY AUTH-006 B signs in again: ${n.url()}`);
});
