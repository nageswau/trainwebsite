import { writeFileSync } from "node:fs";

import { test, type Page } from "@playwright/test";

import { COUNSELOR_ROOT, mailCount, noPrefetch, shoot, signIn, toTop } from "../shoot";

// Counselor CRM S2 (docs/counselor-crm/documentation-plan.md): DOC-CNS-ADM-001, ADM-002 (create/edit/re-send),
// CFG-001, CFG-002 (rules; Run now is S9), CFG-003. Creates the Docs personas used by every later session.
const root = COUNSELOR_ROOT;
const ADM = "admin";
const CFG = "config";
export const PERSONAS = {
  a: { name: "Docs Counselor A", email: "docs.counselor.a@example.test", phone: "+91 90000 10001" },
  b: { name: "Docs Counselor B", email: "docs.counselor.b@example.test", phone: "+91 90000 10002" },
  c: { name: "Docs Counselor C", email: "docs.counselor.c@example.test", phone: "+91 90000 10003" },
  tel: { name: "Docs Telecaller", email: "docs.telecaller@example.test", phone: "+91 90000 10011", employeeId: "DOCS-TEL-1" },
};
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};

async function createUser(p: Page, who: { name: string; email: string; phone: string }) {
  await p.fill("[id='Create user-full_name']", who.name);
  await p.fill("[id='Create user-email']", who.email);
  await p.fill("[id='Create user-phone']", who.phone);
  await p.selectOption("[id='Create user-role']", "counselor");
}

test("Counselor CRM S2 admin set-up", async ({ browser }) => {
  test.setTimeout(600_000);
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const a = await ctx.newPage();
  await signIn(a, "overseasadmin@edusphere.local", "seed", /\/overseas\/admin\//);

  // --- DOC-CNS-ADM-001 create counselors (Counselors page) ---
  await a.goto("/overseas/admin/counselors");
  await a.waitForTimeout(1200);
  await shoot(a, ADM, "01-counselors-page.png", { root });
  const form = a.locator("form", { has: a.locator("[id='Create user-email']") });
  await createUser(a, PERSONAS.a);
  await shoot(a, ADM, "02-create-counselor-filled.png", { root, element: form });
  const before = await mailCount(PERSONAS.a.email);
  await form.getByRole("button", { name: "Create user" }).click();
  await a.waitForTimeout(1500);
  await say(a, "ADM-001 created A");
  await shoot(a, ADM, "03-create-counselor-success.png", { root, center: form });
  console.log(`VERIFY ADM-001 welcome mail A: ${(await mailCount(PERSONAS.a.email)) > before}`);
  for (const who of [PERSONAS.b, PERSONAS.c]) {
    await a.goto("/overseas/admin/counselors");
    await a.waitForTimeout(1000);
    await createUser(a, who);
    await form.getByRole("button", { name: "Create user" }).click();
    await a.waitForTimeout(1500);
    await say(a, `ADM-001 created ${who.name}`);
  }
  // Duplicate email.
  await a.goto("/overseas/admin/counselors");
  await a.waitForTimeout(1000);
  await createUser(a, { ...PERSONAS.a, name: "Docs Counselor Duplicate" });
  await form.getByRole("button", { name: "Create user" }).click();
  await a.waitForTimeout(1500);
  await say(a, "ADM-001 duplicate");
  await shoot(a, ADM, "04-create-counselor-duplicate-email.png", { root, center: form });
  await a.goto("/overseas/admin/counselors");
  await a.waitForTimeout(1200);
  await shoot(a, ADM, "05-counselors-list-awaiting-setup.png", { root });

  // --- DOC-CNS-ADM-002 manage users (Users page) ---
  await a.goto("/overseas/admin/users");
  await a.waitForTimeout(1500);
  await a.selectOption("#admin-user-setup", "pending_setup");
  await a.waitForTimeout(1000);
  await toTop(a.locator("#admin-user-search"), 160);
  await shoot(a, ADM, "06-manage-users-awaiting-setup.png", { root });
  const rowB = a.locator("tr", { hasText: PERSONAS.b.email }).filter({ has: a.getByRole("button", { name: "Edit details" }) });
  const wrap = await rowB.evaluate((tr) => { const t = tr.closest("table")!; const s = t.parentElement!; return { table: t.scrollWidth, box: s.clientWidth }; });
  console.log(`VERIFY ADM-002 table width ${wrap.table} in ${wrap.box}`);
  await rowB.getByRole("button", { name: "Edit details" }).click();
  await a.waitForTimeout(600);
  const phone = a.locator("[id^='directory-phone-']").first();
  await phone.fill("+91 90000 10022");
  await shoot(a, ADM, "07-edit-details.png", { root, center: phone });
  await a.getByRole("button", { name: "Save details" }).click();
  await a.waitForTimeout(1200);
  await say(a, "ADM-002 edit saved");
  await shoot(a, ADM, "08-edit-details-saved.png", { root, center: rowB });
  await rowB.getByRole("button", { name: /^Re-send set-password link to/ }).click();
  await a.waitForTimeout(1500);
  await say(a, "ADM-002 resend");
  await shoot(a, ADM, "09-resend-link.png", { root, center: rowB });
  await rowB.getByRole("button", { name: /^Re-send set-password link to/ }).click();
  await a.waitForTimeout(1500);
  await say(a, "ADM-002 resend again");
  await shoot(a, ADM, "10-resend-link-too-soon.png", { root, center: rowB });

  // --- Setup only: Docs Telecaller (HO-001 in S4) ---
  await a.goto("/overseas/admin/telecallers");
  await a.waitForTimeout(1200);
  await a.fill("#tel-name", PERSONAS.tel.name);
  await a.fill("#tel-email", PERSONAS.tel.email);
  await a.fill("#tel-phone", PERSONAS.tel.phone);
  await a.fill("#tel-employee-id", PERSONAS.tel.employeeId);
  await a.fill("#tel-manager", "Lakshmi");
  await a.waitForTimeout(1200);
  await a.getByRole("option", { name: /Lakshmi/ }).first().click().catch(() => console.log("VERIFY tel manager: no option"));
  await a.getByRole("button", { name: "Create telecaller" }).click();
  await a.waitForTimeout(1500);
  await say(a, "setup telecaller");

  // --- DOC-CNS-CFG-001 checklist template ---
  await a.goto("/overseas/admin/checklists");
  await a.waitForTimeout(1200);
  await shoot(a, CFG, "01-checklists-empty.png", { root });
  await a.click("#checklist-new-open");
  await a.fill("#checklist-new-name", "Docs UK admission checklist");
  await a.selectOption("#checklist-new-kind", "admission");
  await a.fill("#checklist-new-country", "United Kingdom");
  await a.waitForTimeout(800);
  await a.getByRole("option", { name: "United Kingdom" }).first().click().catch(() => console.log("VERIFY CFG-001 country: free text"));
  await a.getByLabel("Block until complete").check();
  const items: [string, string][] = [["Passport", "identity"], ["Transcripts", "standard"], ["English test", "standard"], ["SOP", "standard"]];
  for (let i = 0; i < items.length; i++) {
    if (i > 0) await a.click("#checklist-new-add");
    await a.selectOption(`#checklist-new-item-${i + 1}-type`, items[i][0]);
    await a.selectOption(`#checklist-new-item-${i + 1}-sensitivity`, items[i][1]);
  }
  const editor = a.locator("form", { has: a.locator("#checklist-new-name") });
  await shoot(a, CFG, "02-checklist-editor-filled.png", { root, element: editor });
  await editor.getByRole("button", { name: "Create template" }).click();
  await a.waitForTimeout(1500);
  await say(a, "CFG-001 created");
  await a.goto("/overseas/admin/checklists");
  await a.waitForTimeout(1200);
  await shoot(a, CFG, "03-checklists-list.png", { root });

  // --- DOC-CNS-CFG-002 reminder rules (view, save, range error; value restored) ---
  await a.goto("/overseas/admin/reminder-rules");
  await a.waitForTimeout(1500);
  await shoot(a, CFG, "04-reminder-rules.png", { root });
  const offset = a.locator("#rule-no_response-offset");
  const card = a.locator("form", { has: offset });
  const original = await offset.inputValue();
  console.log(`VERIFY CFG-002 no_response default: ${original}`);
  await offset.fill("99");
  await card.getByRole("button", { name: "Save" }).click();
  await a.waitForTimeout(1000);
  await say(a, "CFG-002 out of range");
  await shoot(a, CFG, "05-reminder-rule-range-error.png", { root, center: card });
  await offset.fill(original);
  await card.getByRole("button", { name: "Save" }).click();
  await a.waitForTimeout(1000);
  await say(a, "CFG-002 saved");
  await shoot(a, CFG, "06-reminder-rule-saved.png", { root, center: card });
  await toTop(a.getByRole("heading", { name: "Recent reminders" }));
  await shoot(a, CFG, "07-recent-reminders-empty.png", { root });

  // --- DOC-CNS-CFG-003 message templates ---
  await a.goto("/overseas/admin/message-templates");
  await a.waitForTimeout(1200);
  await a.selectOption("#rtpl-new-channel", "whatsapp");
  await a.fill("#rtpl-new-name", "Docs offer update");
  await a.fill("#rtpl-new-body", "Hi {name}, good news: {university} has made you an offer for {course} ({intake}). Please reply by {offer_deadline}. — {counselor}");
  const tform = a.locator("form", { has: a.locator("#rtpl-new-name") });
  await shoot(a, CFG, "08-message-template-filled.png", { root, element: tform });
  await tform.getByRole("button", { name: "Create template" }).click();
  await a.waitForTimeout(1500);
  await say(a, "CFG-003 created");
  await shoot(a, CFG, "09-message-templates-list.png", { root });

  if (process.env.DOCS_CNS_FILE) writeFileSync(process.env.DOCS_CNS_FILE, JSON.stringify({ personas: PERSONAS }, null, 2));
});

// Super Admin: create-user Division default (P4). Nothing is saved, so it can be rerun on its own (-g "Super Admin").
test("Counselor CRM S2 Super Admin create-user default", async ({ browser }) => {
  const sctx = await browser.newContext();
  await noPrefetch(sctx);
  const s = await sctx.newPage();
  await signIn(s, "superadmin@edusphere.local", "seed", /\/admin(\/(?!login)|$)/, "/admin/login");
  await s.goto("/admin/users");
  await s.waitForTimeout(1500);
  const division = s.locator("[id='Create user-division']");
  console.log(`VERIFY SA division default: ${await division.inputValue()} options ${JSON.stringify(await division.locator("option").allInnerTexts())}`);
  await s.selectOption("[id='Create user-role']", "counselor").catch(() => console.log("VERIFY SA role: counselor not selectable"));
  await shoot(s, ADM, "11-super-admin-create-user-division.png", { root, element: s.locator("form", { has: division }) });

});

// Read-only views after set-up (safe to rerun on its own: -g "views").
test("Counselor CRM S2 views", async ({ browser }) => {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const a = await ctx.newPage();
  await signIn(a, "overseasadmin@edusphere.local", "seed", /\/overseas\/admin\//);
  await a.goto("/overseas/admin/message-templates");
  await a.waitForTimeout(1500);
  await toTop(a.getByRole("heading", { name: "Templates", exact: true }));
  await shoot(a, CFG, "10-message-templates-list-item.png", { root });
});
