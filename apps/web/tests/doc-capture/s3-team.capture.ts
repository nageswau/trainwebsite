import { writeFileSync } from "node:fs";

import { expect, test, type Browser, type Page } from "@playwright/test";

import { mailCount, mailLink, password, shoot, signIn, toTop } from "./shoot";

// S3 (docs/documentation-plan.md): DOC-TEAM-001..005, DOC-ADM-008, and the deactivated-member case of DOC-AUTH-003.
// Works in the seeded agency "EduSphere Partner Agency" (Master agent@edusphere.local) and creates the docs staff:
// Asha Staff (no permissions), Bala Verifier (Verify documents), Chitra Reports (View reports),
// Dev Deactivated (deactivated), Esha Pending (never sets a password).
const TEAM = "team";
const AUTH = "account-access";
const ADM = "admin-agencies";
const run = Date.now().toString().slice(-6);
const staff = (key: string, name: string) => ({ name, email: `docs.${key}.${run}@example.test` });
const S = {
  a: staff("asha", "Asha Staff"),
  b: staff("bala", "Bala Verifier"),
  c: staff("chitra", "Chitra Reports"),
  d: staff("dev", "Dev Deactivated"),
  e: staff("esha", "Esha Pending"),
};
const MASTER2 = staff("meera", "Meera Master");

const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const row = (page: Page, email: string) => page.locator("li.card", { hasText: email });

async function addStaff(page: Page, who: { name: string; email: string }, shots = false) {
  const form = page.getByRole("form", { name: "Add a staff member" });
  await form.getByLabel("Full name").fill(who.name);
  await form.getByLabel("Email").fill(who.email);
  await form.getByLabel("Phone (optional)").fill("+91 90000 11111");
  if (shots) {
    await toTop(form);
    await shoot(page, TEAM, "07-add-staff-form.png");
  }
  await form.getByRole("button", { name: "Add staff" }).click();
  await expect(page.getByText(`created. A set-password link was emailed to ${who.email}.`)).toBeVisible();
}

async function activate(browser: Browser, email: string, after = 0) {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(await mailLink(email, after));
  await page.fill('input[type="password"]', password("test"));
  await page.click("button:has-text('Reset password')");
  await page.waitForURL("**/overseas/login**");
  await ctx.close();
}

test("S3 team and staff", async ({ browser }) => {
  test.setTimeout(300_000);
  const mctx = await browser.newContext();
  const m = await mctx.newPage();
  await signIn(m, "agent@edusphere.local");
  await m.goto("/overseas/agent/team");
  await expect(m.getByText("No staff yet. Add your first staff member below.")).toBeVisible();

  // --- DOC-TEAM-001 Masters ---
  await shoot(m, TEAM, "01-team-page.png");
  const invite = m.getByRole("form", { name: "Invite a Master" });
  await invite.getByLabel("Full name").fill(MASTER2.name);
  await invite.getByLabel("Email").fill(MASTER2.email);
  await toTop(m.getByRole("heading", { name: /Team — / }));
  await shoot(m, TEAM, "02-invite-master-form.png");
  await invite.getByRole("button", { name: "Send invite" }).click();
  await expect(m.getByText("Invite sent.")).toBeVisible();
  await toTop(m.getByRole("heading", { name: /Team — / }));
  await shoot(m, TEAM, "03-invite-master-sent.png");
  await say(m, "TEAM-001 after invite (limit text?)");
  console.log(`VERIFY TEAM-001 limit text visible: ${await m.getByText("Limit reached").isVisible()}`);
  const deact = m.getByRole("button", { name: `Deactivate ${MASTER2.name}` });
  if (await deact.isVisible()) {
    await deact.click();
    await shoot(m, TEAM, "04-deactivate-master-confirm.png");
    await m.getByRole("group", { name: `Confirm deactivating ${MASTER2.name}` }).getByRole("button", { name: "Cancel" }).click();
  } else console.log("VERIFY TEAM-001 no Deactivate button for an invite-pending Master");

  // --- DOC-TEAM-002 create staff ---
  await addStaff(m, S.a, true);
  await toTop(m.getByRole("heading", { name: "Staff", exact: true }));
  await shoot(m, TEAM, "08-add-staff-success.png");
  for (const who of [S.b, S.c, S.d, S.e]) await addStaff(m, who);
  for (const who of [S.a, S.b, S.c, S.d]) await activate(browser, who.email);
  await m.reload();

  // --- DOC-TEAM-004 permissions ---
  await row(m, S.b.email).getByRole("button", { name: `Permissions for ${S.b.name}` }).click();
  const perm = m.getByRole("form", { name: `Permissions for ${S.b.name}` });
  await perm.getByLabel("Verify documents").check();
  await toTop(row(m, S.b.email));
  await shoot(m, TEAM, "09-permissions-form.png");
  await perm.getByRole("button", { name: "Save" }).click();
  await expect(m.getByText(/EDU-S\d+ permissions saved\./)).toBeVisible();
  await toTop(row(m, S.b.email));
  await shoot(m, TEAM, "10-permissions-saved.png");
  await row(m, S.c.email).getByRole("button", { name: `Permissions for ${S.c.name}` }).click();
  await m.getByRole("form", { name: `Permissions for ${S.c.name}` }).getByLabel("View reports").check();
  await m.getByRole("form", { name: `Permissions for ${S.c.name}` }).getByRole("button", { name: "Save" }).click();
  await expect(m.getByText("permissions saved")).toBeVisible();

  // --- DOC-TEAM-003 edit / reset / deactivate / reactivate ---
  await row(m, S.a.email).getByRole("button", { name: `Edit ${S.a.name}` }).click();
  const edit = m.getByRole("form", { name: `Edit ${S.a.name}` });
  await edit.getByLabel(/Phone/).fill("+91 90000 22222");
  await toTop(row(m, S.a.email));
  await shoot(m, TEAM, "11-edit-staff.png");
  await edit.getByRole("button", { name: "Save" }).click();
  await expect(m.getByText(/EDU-S\d+ updated\./)).toBeVisible();

  await row(m, S.c.email).getByRole("button", { name: `Reset ${S.c.name}` }).click();
  await toTop(row(m, S.c.email));
  await shoot(m, TEAM, "12-reset-confirm.png");
  const before = await mailCount(S.c.email);
  await row(m, S.c.email).getByRole("button", { name: "Confirm reset" }).click();
  await expect(m.getByText(`A new set-password link was emailed to ${S.c.name}.`)).toBeVisible();
  await activate(browser, S.c.email, before); // Chitra sets a password again from the new link

  await row(m, S.d.email).getByRole("button", { name: `Deactivate ${S.d.name}` }).click();
  await toTop(row(m, S.d.email));
  await shoot(m, TEAM, "13-deactivate-staff-confirm.png");
  await row(m, S.d.email).getByRole("button", { name: "Confirm deactivate" }).click();
  await expect(row(m, S.d.email).getByRole("button", { name: `Reactivate ${S.d.name}` })).toBeVisible();
  await expect(m.getByText(/deactivated\. They have been signed out\./)).toBeVisible();
  await toTop(row(m, S.d.email));
  await shoot(m, TEAM, "14-staff-deactivated.png");
  await row(m, S.d.email).getByRole("button", { name: `Reactivate ${S.d.name}` }).click();
  await expect(m.getByText(/reactivated\./)).toBeVisible();
  await row(m, S.d.email).getByRole("button", { name: `Deactivate ${S.d.name}` }).click();
  await row(m, S.d.email).getByRole("button", { name: "Confirm deactivate" }).click();
  await expect(row(m, S.d.email).getByRole("button", { name: `Reactivate ${S.d.name}` })).toBeVisible();
  await toTop(m.getByRole("heading", { name: "Staff", exact: true }));
  await shoot(m, TEAM, "15-staff-list.png");

  // --- Staff views (sidebar, refusal) and some activity for DOC-TEAM-005 ---
  let ctx = await browser.newContext();
  let p = await ctx.newPage();
  await signIn(p, S.a.email, "test");
  await expect(p.getByText("Your assigned students")).toBeVisible();
  await shoot(p, TEAM, "16-staff-sidebar-default.png");
  await p.goto("/overseas/agent/students?new=1");
  await p.getByLabel(/^Full name/).fill("Kiran Kumar");
  await p.getByRole("button", { name: "Save student" }).click();
  await expect(p.getByText("Kiran Kumar added.")).toBeVisible();
  await p.goto("/overseas/agent/team");
  await expect(p.getByText("Only an agency Master can open this page")).toBeVisible();
  await shoot(p, TEAM, "17-staff-team-refused.png");
  await ctx.close();

  ctx = await browser.newContext();
  p = await ctx.newPage();
  await signIn(p, S.c.email, "test");
  await expect(p.getByRole("link", { name: "Reports" })).toBeVisible();
  await shoot(p, TEAM, "18-staff-sidebar-with-reports.png");
  await ctx.close();

  // --- DOC-TEAM-005 activity ---
  await m.reload();
  await row(m, S.a.email).getByRole("button", { name: `Activity of ${S.a.name}` }).click();
  await expect(row(m, S.a.email).getByText("Created a student record")).toBeVisible();
  await toTop(row(m, S.a.email));
  await shoot(m, TEAM, "19-staff-activity.png");
  await row(m, S.b.email).getByRole("button", { name: `Activity of ${S.b.name}` }).click();
  await expect(row(m, S.b.email).getByText("No activity yet.")).toBeVisible();
  await toTop(row(m, S.b.email));
  await shoot(m, TEAM, "20-staff-activity-empty.png");
  await mctx.close();

  // --- DOC-AUTH-003 deactivated member (U3) ---
  ctx = await browser.newContext();
  p = await ctx.newPage();
  await p.goto("/overseas/login");
  await p.fill("#login-email", S.d.email);
  await p.fill("#login-password", password("test"));
  await p.click("button:has-text('Sign in securely')");
  await p.waitForTimeout(2500);
  console.log(`VERIFY U3 deactivated staff sign-in -> ${new URL(p.url()).pathname}: ${(await p.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 200)}`);
  await shoot(p, AUTH, "19-deactivated-staff-sign-in.png");
  await ctx.close();

  // --- DOC-ADM-008 re-send a set-password link (Overseas Admin > Users) ---
  ctx = await browser.newContext();
  p = await ctx.newPage();
  await signIn(p, "overseasadmin@edusphere.local");
  await p.goto("/overseas/admin/users");
  const search = p.getByLabel("Search by name, email, or role");
  await search.fill(S.e.email);
  await search.press("Enter");
  const resend = p.getByRole("button", { name: `Re-send set-password link to ${S.e.name}` });
  await expect(resend).toBeVisible();
  await toTop(p.getByRole("heading", { name: "Manage users" }));
  await shoot(p, ADM, "07-users-resend-link.png");
  await resend.click();
  await p.waitForTimeout(1500);
  await say(p, "ADM-008 resend");
  await toTop(p.getByRole("heading", { name: "Manage users" }));
  await shoot(p, ADM, "08-users-resend-result.png");
  await ctx.close();

  const emails = JSON.stringify(Object.fromEntries(Object.entries(S).map(([k, v]) => [k, v.email])));
  if (process.env.DOCS_STAFF_FILE) writeFileSync(process.env.DOCS_STAFF_FILE, emails); // read by later capture specs
  console.log(`STAFF ${emails}`);
});
