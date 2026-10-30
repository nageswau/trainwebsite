import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { COUNSELOR_ROOT, noPrefetch, password, shoot, signIn } from "../shoot";

// Counselor CRM S10 (docs/counselor-crm/documentation-plan.md): DOC-CNS-STU-008, STU-009, CFG-004, plus the deactivate steps of
// ADM-002 and the deactivated sign-in of AUTH-006. Runs last: it archives the enrolled walk-in student and deactivates Docs Counselor C.
const root = COUNSELOR_ROOT;
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 2000);
async function page(browser: Browser, viewport?: { width: number; height: number }) {
  const ctx = await browser.newContext(viewport ? { viewport } : {});
  await noPrefetch(ctx);
  return ctx.newPage();
}
async function open360(c: Page, search: string) {
  await c.goto("/overseas/counselor/students");
  await c.waitForTimeout(2500);
  const my = c.locator(".action-card").filter({ has: c.locator("#my-students-source") }).last();
  await c.fill("#my-students-q", search);
  await my.getByRole("button", { name: "Search" }).click();
  await c.waitForTimeout(1500);
  await my.getByRole("link", { name: "Open" }).first().click();
  await c.waitForURL(/\/students\/[^/?]+/);
  return c.url().split("?")[0];
}

test("Counselor CRM S10 lifecycle", async ({ browser }) => {
  test.setTimeout(900_000);

  // ===== STU-009 consent: the self-registered student agrees on their dashboard =====
  const st = await page(browser);
  await signIn(st, "docs.self.student@example.com", "test", /\/overseas\/student\//);
  await st.waitForTimeout(2500);
  const consent = st.locator("form[aria-labelledby='consent-heading']");
  console.log(`VERIFY STU-009 student consent card: ${await text(consent)}`);
  await shoot(st, "students", "24-student-consent-card.png", { root, element: consent });
  const boxes = consent.locator("input[type=checkbox]");
  for (let i = 0; i < (await boxes.count()); i++) await boxes.nth(i).check();
  await consent.getByRole("button", { name: "Save consent" }).click();
  await st.waitForTimeout(2000);
  await say(st, "STU-009 consent saved");

  // ===== Counselor A: consent on the 360, archive (STU-008) =====
  const c = await page(browser);
  await signIn(c, "docs.counselor.a@example.test", "test", /\/overseas\/counselor\/dashboard/);
  const self = await open360(c, "Docs Self-registered");
  await c.waitForTimeout(2000);
  const card = c.locator("section, .card").filter({ has: c.getByRole("heading", { name: "Consent" }) }).last();
  console.log(`VERIFY STU-009 counselor view: ${await text(card)}`);
  await shoot(c, "students", "25-consent-given.png", { root, element: card });
  const asha = await open360(c, "Asha");
  await c.waitForTimeout(2000);
  await shoot(c, "students", "26-consent-not-given.png", { root, element: c.locator("section, .card").filter({ has: c.getByRole("heading", { name: "Consent" }) }).last() });
  // Archive refused while an application is open (Asha).
  await c.getByRole("button", { name: "Archive student" }).first().click();
  await c.getByLabel("Reason").fill("Testing the archive rule.");
  await c.locator("form").filter({ has: c.getByLabel("Reason") }).getByRole("button", { name: "Archive student" }).click();
  await c.waitForTimeout(1500);
  await say(c, "STU-008 refused (open application)");
  await shoot(c, "students", "27-archive-refused-open-application.png", { root, element: c.locator("form").filter({ has: c.getByLabel("Reason") }) });
  // Archive the enrolled walk-in student.
  const walkin = await open360(c, "Docs Walk-in Student");
  await c.waitForTimeout(2000);
  await c.getByRole("button", { name: "Archive student" }).first().click();
  const af = c.locator("form").filter({ has: c.getByLabel("Reason") });
  console.log(`VERIFY STU-008 form: ${await text(af)}`);
  await af.getByLabel("Reason").fill("Enrolled and arrived at Docs University; counselling complete.");
  await shoot(c, "students", "28-archive-student-form.png", { root, element: af });
  await af.getByRole("button", { name: "Archive student" }).click();
  await c.waitForTimeout(2000);
  await say(c, "STU-008 archived");
  console.log(`VERIFY STU-008 archived 360: ${await text(c.locator("main"))}`);
  await shoot(c, "students", "29-archived-banner.png", { root });
  // P16 check: what is still offered on an archived student.
  await c.goto(`${walkin}?tab=documents`);
  await c.waitForTimeout(2000);
  const docsText = await text(c.locator("main"));
  console.log(`VERIFY P16 archived documents tab: request form=${docsText.includes("Request a document")} upload=${docsText.includes("Upload a document")}`);
  await c.goto("/overseas/counselor/archived-students");
  await c.waitForTimeout(2000);
  console.log(`VERIFY STU-008 archived list: ${await text(c.locator("main"))}`);
  await shoot(c, "students", "30-archived-students-list.png", { root });

  // ===== CFG-004 restore (Overseas Admin) and the Super Admin refusal =====
  const sa = await page(browser);
  await signIn(sa, "superadmin@edusphere.local", "seed", /\/admin(\/(?!login)|$)/, "/admin/login");
  await sa.goto("/overseas/admin/archived-students");
  await sa.waitForTimeout(2500);
  console.log(`VERIFY CFG-004 SA: ${await text(sa.locator("main").or(sa.locator("body")).first())}`);
  await shoot(sa, "config", "15-super-admin-archived-refused.png", { root });
  const a = await page(browser);
  await signIn(a, "overseasadmin@edusphere.local", "seed", /\/overseas\/admin\//);
  await a.goto("/overseas/admin/archived-students");
  await a.waitForTimeout(2500);
  console.log(`VERIFY CFG-004 OA list: ${await text(a.locator("main"))}`);
  await shoot(a, "config", "13-archived-students-admin.png", { root });
  await a.getByRole("link", { name: "Docs Walk-in Student" }).first().click();
  await a.waitForURL(/\/students\/[^/?]+/);
  await a.waitForTimeout(2500);
  await a.getByRole("button", { name: "Restore student" }).click();
  await a.waitForTimeout(2000);
  await say(a, "CFG-004 restored");
  await shoot(a, "config", "14-student-restored.png", { root });
  await c.goto(`${walkin}?tab=history`);
  await c.waitForTimeout(2000);
  console.log(`VERIFY STU-008 history: ${(await text(c.locator("main"))).slice(0, 600)}`);
  await shoot(c, "students", "31-history-archived-restored.png", { root });

  // ===== ADM-002 deactivate Docs Counselor C; AUTH-006 deactivated sign-in; reactivate =====
  await a.goto("/overseas/admin/users");
  await a.waitForTimeout(2500);
  await a.locator("#admin-user-search").fill("docs.counselor.c");
  await a.waitForTimeout(1500);
  const row = a.locator("tr").filter({ hasText: "docs.counselor.c@example.test" }).filter({ has: a.getByRole("button", { name: /Deactivate|Reactivate/ }) }).first();
  await row.getByRole("button", { name: "Deactivate" }).click();
  await a.waitForTimeout(1500);
  const confirm = row.getByRole("button", { name: "Confirm deactivate" });
  console.log(`VERIFY ADM-002 confirm step shown: ${await confirm.isVisible().catch(() => false)}`);
  if (await confirm.isVisible().catch(() => false)) {
    await shoot(a, "admin", "18-deactivate-confirm.png", { root, center: row });
    await confirm.click();
    await a.waitForTimeout(2000);
  }
  await say(a, "ADM-002 deactivated");
  await shoot(a, "admin", "19-deactivated.png", { root, center: row });
  const l = await page(browser);
  await l.goto("/overseas/login");
  await l.fill("#login-email", "docs.counselor.c@example.test");
  await l.fill("#login-password", password("test"));
  await l.click("button:has-text('Sign in securely')");
  await l.waitForTimeout(2000);
  await say(l, "AUTH-006 deactivated sign-in");
  await shoot(l, "account-access", "19-deactivated-sign-in.png", { root });
  await row.getByRole("button", { name: "Reactivate" }).click();
  await a.waitForTimeout(800);
  await row.getByRole("button", { name: /Confirm|Reactivate/ }).first().click().catch(() => {});
  await a.waitForTimeout(2000);
  await say(a, "ADM-002 reactivated");
  await shoot(a, "admin", "20-reactivated.png", { root, center: row });
});
