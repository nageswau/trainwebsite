import { readFileSync, writeFileSync } from "node:fs";

import { expect, test, type Page } from "@playwright/test";

import { ITC_ROOT, mailCount, noPrefetch, shoot, signIn } from "../shoot";

// IT Counselor CRM S2 (docs/it-counselor-crm/documentation-plan.md): DOC-ITC-ADM-001, ADM-002 (create / edit / re-send).
// Creates the Docs personas, a Docs programme and a Docs batch used by every later session. No payments are made (owner I3).
const root = ITC_ROOT;
const ADM = "admin";
export const PERSONAS = {
  a: { name: "Docs IT Counselor A", email: "docs.itc.a@example.test", phone: "+91 90000 20001" },
  b: { name: "Docs IT Counselor B", email: "docs.itc.b@example.test", phone: "+91 90000 20002" },
  tel: { name: "Docs IT Telecaller", email: "docs.itc.telecaller@example.test", phone: "+91 90000 20011", employeeId: "DOCS-ITC-TEL-1" },
};
export const PROGRAM = { title: "Docs Full Stack Python", slug: "docs-full-stack-python" };
export const BATCH = { name: "Docs FSP Batch 1" };

const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const iso = (days: number) => new Date(Date.now() + days * 86_400_000).toISOString().slice(0, 10);
const ids = (): Record<string, unknown> => {
  try { return JSON.parse(readFileSync(process.env.DOCS_ITC_FILE!, "utf8")); } catch { return {}; }
};

async function createCounselor(p: Page, who: { name: string; email: string; phone: string }, n: number) {
  await p.fill("[id='Create user-full_name']", who.name);
  await p.fill("[id='Create user-email']", who.email);
  await p.fill("[id='Create user-phone']", who.phone);
  await p.selectOption("[id='Create user-division']", "it");
  await p.selectOption("[id='Create user-role']", "counselor");
  const form = p.locator("form:has([id='Create user-full_name'])");
  if (n === 1) await shoot(p, ADM, "02-create-counselor-filled.png", { root, element: form });
  await form.getByRole("button", { name: "Create user" }).click();
  await p.waitForTimeout(1500);
  await say(p, `create ${who.name}`);
  if (n === 1) await shoot(p, ADM, "03-create-counselor-done.png", { root, center: p.locator('[role="status"],[role="alert"]').first() });
}

test("IT Counselor CRM S2 admin set-up", async ({ browser }) => {
  test.setTimeout(600_000);
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const a = await ctx.newPage();
  await signIn(a, "itadmin@edusphere.local", "seed", /\/it\/admin\//, "/it/login");

  // --- DOC-ITC-ADM-001 create IT counselors (Counselors page) ---
  await a.goto("/it/admin/counselors");
  await a.waitForTimeout(1500);
  await shoot(a, ADM, "01-counselors-page.png", { root });
  const mailsBefore = await mailCount(PERSONAS.a.email);
  await createCounselor(a, PERSONAS.a, 1);
  await createCounselor(a, PERSONAS.b, 2);
  // duplicate email (nothing is created)
  await createCounselor(a, { ...PERSONAS.a, name: "Docs IT Counselor A again" }, 2);
  await shoot(a, ADM, "08-create-counselor-duplicate-email.png", { root, center: a.locator('[role="alert"],[role="status"]').first() });
  await a.reload();
  await a.waitForTimeout(1500);
  const directory = a.locator(".action-card").filter({ has: a.getByRole("heading", { name: "Directory" }) });
  await shoot(a, ADM, "04-counselors-awaiting-setup.png", { root, element: directory });
  console.log(`VERIFY welcome mail to A arrived: ${(await mailCount(PERSONAS.a.email)) > mailsBefore}`);

  // --- DOC-ITC-ADM-002 edit details and re-send link (Users page) ---
  await a.goto("/it/admin/users");
  await a.waitForTimeout(1500);
  await a.fill("#admin-user-search", "Docs IT Counselor");
  await a.waitForTimeout(800);
  const manage = a.locator(".action-card").filter({ has: a.getByRole("heading", { name: "Manage users" }) });
  const rowA = manage.getByRole("row").filter({ hasText: PERSONAS.a.email });
  await shoot(a, ADM, "05-users-search.png", { root, element: manage });
  await rowA.getByRole("button", { name: "Edit details" }).click();
  const edit = rowA.locator("form");
  await edit.locator("input[name='education']").fill("MBA");
  await shoot(a, ADM, "06-edit-details.png", { root, element: manage });
  await edit.getByRole("button", { name: "Save details" }).click();
  await a.waitForTimeout(1200);
  await say(a, "edit A");
  const before = await mailCount(PERSONAS.b.email);
  await a.getByRole("button", { name: `Re-send set-password link to ${PERSONAS.b.name}` }).click();
  await a.waitForTimeout(1500);
  await say(a, "resend B");
  await shoot(a, ADM, "07-resend-link.png", { root, element: manage });
  console.log(`VERIFY resend mail to B arrived: ${(await mailCount(PERSONAS.b.email)) > before}`);

  // --- Set-up only (no doc page): IT telecaller, programme, batch ---
  await a.goto("/it/admin/telecallers");
  await a.waitForTimeout(1500);
  await a.fill("#tel-name", PERSONAS.tel.name);
  await a.fill("#tel-email", PERSONAS.tel.email);
  await a.fill("#tel-phone", PERSONAS.tel.phone);
  await a.fill("#tel-employee-id", PERSONAS.tel.employeeId);
  await a.fill("#tel-manager", "Lakshmi");
  await a.getByRole("option").filter({ hasText: "Lakshmi" }).first().click();
  await a.getByRole("button", { name: "Create telecaller" }).click();
  await a.waitForTimeout(1500);
  await say(a, "create telecaller");

  await a.goto("/it/admin/programs");
  await a.waitForTimeout(1500);
  await a.fill("[id='Create program-slug']", PROGRAM.slug);
  await a.fill("[id='Create program-category']", "Software Development");
  await a.fill("[id='Create program-title']", PROGRAM.title);
  await a.fill("[id='Create program-summary']", "Docs test programme for the IT Counselor guide.");
  await a.fill("[id='Create program-duration']", "12 weeks");
  await a.fill("[id='Create program-fees']", "45000");
  await a.fill("[id='Create program-eligibility']", "Any graduate");
  await a.fill("[id='Create program-curriculum']", "Python, Django, React");
  await a.getByRole("button", { name: "Create program" }).click();
  await a.waitForTimeout(1500);
  await say(a, "create programme");

  await a.goto("/it/admin/batches");
  await a.waitForTimeout(1500);
  await a.selectOption("#batch-program", { label: PROGRAM.title });
  const trainers = await a.locator("#batch-trainer option").count();
  if (trainers > 1) await a.selectOption("#batch-trainer", { index: 1 });
  await a.fill("#batch-name", BATCH.name);
  await a.fill("#batch-start", iso(7));
  await a.fill("#batch-end", iso(91));
  await a.fill("#batch-schedule", "Mon-Fri 18:00-20:00");
  await a.fill("#batch-capacity", "20");
  await a.selectOption("#batch-mode", "Online");
  await a.getByRole("button", { name: "Create batch" }).click();
  await a.waitForTimeout(1500);
  await say(a, "create batch");
  await expect(a.getByText(BATCH.name).first()).toBeVisible();

  writeFileSync(process.env.DOCS_ITC_FILE!, JSON.stringify({ ...ids(), personas: PERSONAS, program: PROGRAM, batch: BATCH }, null, 2));
});

// Super Admin: create-user form for an IT counselor. Nothing is saved, so it can be rerun on its own (-g "Super Admin").
test("IT Counselor CRM S2 Super Admin create-user", async ({ browser }) => {
  const sctx = await browser.newContext();
  await noPrefetch(sctx);
  const s = await sctx.newPage();
  await signIn(s, "superadmin@edusphere.local", "seed", /\/admin(\/(?!login)|$)/, "/admin/login");
  await s.goto("/admin/users");
  await s.waitForTimeout(1500);
  const division = s.locator("[id='Create user-division']");
  console.log(`VERIFY SA division default: ${await division.inputValue()} options ${JSON.stringify(await division.locator("option").allInnerTexts())}`);
  await s.selectOption("[id='Create user-role']", "counselor").catch(() => console.log("VERIFY SA role: counselor not selectable"));
  await shoot(s, ADM, "09-super-admin-create-user.png", { root, element: s.locator("form", { has: division }) });
});
