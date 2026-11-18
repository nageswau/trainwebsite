import { readFileSync, writeFileSync } from "node:fs";

import { test, type Locator, type Page } from "@playwright/test";

import { mailCount, noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S2 (docs/recruitment-crm/documentation-plan.md): DOC-REC-ADM-001, ADM-002, ADM-003 (edit).
// Creates the Docs recruitment staff used by every later session. No money is recorded (owner R3).
const root = REC_ROOT;
const ADM = "admin";
export const PERSONAS = {
  lead: { name: "Docs Team Lead", email: "docs.rec.lead@example.test", phone: "+91 90000 30001" },
  hrm: { name: "Docs HR Manager", email: "docs.rec.hrm@example.test", phone: "+91 90000 30002" },
  a: { name: "Docs Recruiter A", email: "docs.rec.a@example.test", phone: "+91 90000 30011", employeeId: "DOCS-REC-A" },
  b: { name: "Docs Recruiter B", email: "docs.rec.b@example.test", phone: "+91 90000 30012", employeeId: "DOCS-REC-B" },
  po: { name: "Docs Placement Officer", email: "docs.rec.po@example.test", phone: "+91 90000 30021" },
  hr: { name: "Docs HR", email: "docs.rec.hr@example.test", phone: "+91 90000 30022" },
  int: { name: "Docs Interviewer", email: "docs.rec.interviewer@example.test", phone: "+91 90000 30023" },
};

const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 1500);
const ids = (): Record<string, unknown> => {
  try { return JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8")); } catch { return {}; }
};

async function createUser(p: Page, who: { name: string; email: string; phone: string }, division: string, role: string, shots?: [string, string]) {
  await p.fill("[id='Create user-full_name']", who.name);
  await p.fill("[id='Create user-email']", who.email);
  await p.fill("[id='Create user-phone']", who.phone);
  await p.selectOption("[id='Create user-division']", division);
  await p.selectOption("[id='Create user-role']", role);
  const form = p.locator("form:has([id='Create user-full_name'])");
  if (shots) await shoot(p, ADM, shots[0], { root, element: form });
  await form.getByRole("button", { name: "Create user" }).click();
  await p.waitForTimeout(1800);
  await say(p, `create ${who.name}`);
  if (shots) await shoot(p, ADM, shots[1], { root, center: p.locator('[role="status"],[role="alert"]').first() });
}

test("Recruitment CRM S2 Super Admin creates Team Lead and HR Manager", async ({ browser }) => {
  test.setTimeout(300_000);
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const s = await ctx.newPage();
  await signIn(s, "superadmin@edusphere.local", "seed", /\/admin(\/(?!login)|$)/, "/admin/login");
  await s.goto("/admin/users");
  await s.waitForTimeout(1500);
  await createUser(s, PERSONAS.lead, "global", "placement_manager", ["01-create-team-lead-filled.png", "02-create-team-lead-done.png"]);
  await createUser(s, PERSONAS.hrm, "it", "hr_manager", ["03-create-hr-manager-filled.png", "04-create-hr-manager-done.png"]);
});

test("Recruitment CRM S2 IT Admin creates recruiters and staff", async ({ browser }) => {
  test.setTimeout(600_000);
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const a = await ctx.newPage();
  await signIn(a, "itadmin@edusphere.local", "seed", /\/it\/admin\//, "/it/login");

  // --- ADM-001 Recruiter Staff ---
  await a.goto("/it/admin/recruiter-staff");
  await a.waitForTimeout(2000);
  console.log(`VERIFY ADM-001 page: ${await text(a.locator("main"))}`);
  await shoot(a, ADM, "05-recruiter-staff.png", { root });
  const form = a.locator("form").filter({ has: a.locator("#rec-name") });
  for (const [i, who] of [PERSONAS.a, PERSONAS.b].entries()) {
    await a.fill("#rec-name", who.name);
    await a.fill("#rec-email", who.email);
    await a.fill("#rec-phone", who.phone);
    await a.fill("#rec-employee-id", who.employeeId);
    await form.getByRole("combobox").fill("Docs Team");
    await a.waitForTimeout(1200);
    await a.getByRole("option", { name: /Docs Team Lead/ }).first().click();
    if (i === 0) await shoot(a, ADM, "06-create-recruiter-filled.png", { root, element: form });
    await form.getByRole("button", { name: "Create recruiter" }).click();
    await a.waitForTimeout(2000);
    await say(a, `create ${who.name}`);
    if (i === 0) await shoot(a, ADM, "07-create-recruiter-done.png", { root, element: form });
  }
  // duplicate employee ID (nothing is created)
  await a.fill("#rec-name", "Docs Recruiter Duplicate");
  await a.fill("#rec-email", "docs.rec.dup@example.test");
  await a.fill("#rec-employee-id", PERSONAS.a.employeeId);
  await form.getByRole("combobox").fill("Docs Team");
  await a.waitForTimeout(1200);
  await a.getByRole("option", { name: /Docs Team Lead/ }).first().click();
  await form.getByRole("button", { name: "Create recruiter" }).click();
  await a.waitForTimeout(2000);
  await say(a, "duplicate employee id");
  await shoot(a, ADM, "08-create-recruiter-duplicate.png", { root, element: form });
  await a.reload();
  await a.waitForTimeout(2000);
  await a.getByLabel("Search recruiters").fill("Docs Recruiter");
  await a.getByLabel("Search recruiters").press("Enter");
  await a.waitForTimeout(1500);
  const list = a.getByRole("heading", { name: "Recruiters", exact: true }).first().locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
  console.log(`VERIFY ADM-001 list: ${await text(list)}`);
  await shoot(a, ADM, "09-recruiters-list.png", { root, element: list });

  // --- ADM-003 edit a recruiter ---
  await a.getByRole("button", { name: `Edit ${PERSONAS.a.name}` }).click();
  await a.waitForTimeout(800);
  console.log(`VERIFY ADM-003 edit form: ${await text(list)}`);
  await list.getByLabel("Mobile", { exact: true }).fill("+91 90000 30019");
  await shoot(a, ADM, "10-edit-recruiter.png", { root, element: list });
  await list.getByRole("button", { name: "Save", exact: true }).click();
  await a.waitForTimeout(1500);
  await say(a, "edit recruiter A");
  await shoot(a, ADM, "10b-recruiter-saved.png", { root, element: list });

  // --- ADM-002 other recruitment users (Users) ---
  await a.goto("/it/admin/users");
  await a.waitForTimeout(2000);
  const roles = await a.locator("[id='Create user-role'] option").allInnerTexts();
  console.log(`VERIFY ADM-002 IT Admin role options: ${roles.join(" | ")}`);
  await createUser(a, PERSONAS.po, "it", "placement_officer", ["11-create-placement-officer-filled.png", "12-create-placement-officer-done.png"]);
  await createUser(a, PERSONAS.hr, "it", "hr_team");
  await createUser(a, PERSONAS.int, "it", "interviewer");
  console.log(`VERIFY welcome mail to Recruiter A: ${await mailCount(PERSONAS.a.email)}, PO: ${await mailCount(PERSONAS.po.email)}`);
  await a.fill("#admin-user-search", "docs.rec");
  await a.waitForTimeout(1500);
  const manage = a.locator(".action-card").filter({ has: a.getByRole("heading", { name: "Manage users" }) });
  console.log(`VERIFY ADM-002 directory: ${await text(manage)}`);
  await shoot(a, ADM, "13-recruitment-users.png", { root, element: manage });

  writeFileSync(process.env.DOCS_REC_FILE!, JSON.stringify({ ...ids(), personas: PERSONAS }, null, 2));
});
