import { writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";

import { expect, test, type Page } from "@playwright/test";

import { noPrefetch, SCHOOL_ROOT, shoot, signIn, toTop } from "../shoot";

// School CRM S2 (docs/school-crm/documentation-plan.md): DOC-SCH-SADM-001..005, 010, 011 + the login masking check.
// Creates the Docs schools and staff every later School CRM session relies on. Needs a freshly seeded DB.
const ADM = "admin-schools";
const opts = { root: SCHOOL_ROOT };
const card = (p: Page, name: string) => p.locator(".action-card").filter({ has: p.getByRole("heading", { name, exact: true }) });
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
// Dates in the India calendar, as the server computes tier expiry.
const istDate = (offsetDays: number) => {
  const d = new Date(Date.now() + 5.5 * 3600_000 + offsetDays * 86_400_000);
  return d.toISOString().slice(0, 10);
};

const SCHOOLS = {
  bronze: { name: "Docs Bronze School", city: "Pune", state: "Maharashtra", tier: "Bronze", coordinator: "Docs Bronze Coordinator", email: "docs.bronze.coordinator@example.test" },
  notier: { name: "Docs No-Tier School", city: "Chennai", state: "Tamil Nadu", tier: "Not set", coordinator: "Docs No-Tier Coordinator", email: "docs.notier.coordinator@example.test" },
  platinum2: { name: "Docs Platinum Two", city: "Mumbai", state: "Maharashtra", tier: "Platinum", coordinator: "Docs Platinum Two Coordinator", email: "docs.platinum2.coordinator@example.test" },
};
const STAFF = [
  { role: "Academic Team", name: "Docs Academic Team", email: "docs.at@example.test", schools: ["Sunrise Public School", "Docs Platinum Two"] },
  { role: "Career Counselor", name: "Docs Career Counselor", email: "docs.cc@example.test", schools: ["Sunrise Public School", "Docs Platinum Two"] },
  { role: "Psychometric Team", name: "Docs Psychometric Team", email: "docs.pt@example.test", schools: ["Sunrise Public School", "Docs Platinum Two"] },
  { role: "Career Counselor", name: "Docs Empty Portfolio Counselor", email: "docs.cc.empty@example.test", schools: [] as string[] },
];

async function createSchool(p: Page, s: (typeof SCHOOLS)[keyof typeof SCHOOLS], shotFilled?: string): Promise<string> {
  await p.fill("#school-name", s.name);
  await p.fill("#school-branch", "Main campus");
  await p.fill("#school-city", s.city);
  await p.fill("#school-state", s.state);
  await p.selectOption("#school-board", { label: "CBSE" });
  await p.selectOption("#school-tier", { label: s.tier });
  await p.fill("#school-partnership-date", istDate(0));
  await p.fill("#school-coordinator-name", s.coordinator);
  await p.fill("#school-coordinator-email", s.email);
  if (shotFilled) await shoot(p, ADM, shotFilled, { ...opts, element: card(p, "Create school") });
  await p.getByRole("button", { name: "Create school + seed Coordinator" }).click();
  const status = p.getByText(/School created\. School code [0-9A-F]{8}/);
  await expect(status).toBeVisible({ timeout: 20_000 });
  const code = (await status.innerText()).match(/School code ([0-9A-F]{8})/)![1];
  await say(p, `create ${s.name}`);
  return code;
}

test("School CRM S2 admin school management", async ({ browser }) => {
  test.setTimeout(420_000);
  const codes: Record<string, string> = {};

  // --- Masking check (S2.3) ---
  const anon = await browser.newPage();
  await noPrefetch(anon);
  await anon.goto("/overseas/login");
  await shoot(anon, "account-access", "01-login-page.png", opts);
  await anon.close();

  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const a = await ctx.newPage();
  await signIn(a, "overseasadmin@edusphere.local", "seed", /\/overseas\/admin\//);

  // --- SADM-001 Partner Schools list (seed only) ---
  await a.goto("/overseas/admin/schools");
  await expect(a.getByRole("heading", { name: "Partner Schools" })).toBeVisible();
  await shoot(a, ADM, "01-schools-list.png", opts);

  // --- SADM-002 Create a school ---
  codes.bronze = await createSchool(a, SCHOOLS.bronze, "03-create-school-filled.png");
  await shoot(a, ADM, "04-create-school-success.png", { ...opts, center: a.getByText(/School created\. School code/) });
  codes.notier = await createSchool(a, SCHOOLS.notier);
  codes.platinum2 = await createSchool(a, SCHOOLS.platinum2);
  // Duplicate coordinator email (the seeded Sunrise coordinator).
  await a.fill("#school-name", "Docs Duplicate Coordinator School");
  await a.fill("#school-coordinator-name", "Duplicate Coordinator");
  await a.fill("#school-coordinator-email", "school.coordinator@edusphere.local");
  await a.getByRole("button", { name: "Create school + seed Coordinator" }).click();
  await expect(a.getByText("Email already exists")).toBeVisible();
  await say(a, "create duplicate email");
  await shoot(a, ADM, "05-create-school-email-exists.png", { ...opts, center: a.getByText("Email already exists") });

  // Search the list (client-side DataTable).
  await a.reload();
  await a.getByLabel("Search records").fill("Docs");
  await toTop(a.getByRole("heading", { name: "Partner Schools" }));
  await shoot(a, ADM, "02-schools-search.png", opts);

  // --- SADM-003 Edit profile and tier (Docs Bronze School: Bronze -> Silver -> Bronze) ---
  await a.reload();
  await a.fill("#school-lookup-code", codes.bronze);
  await toTop(a.getByRole("heading", { name: "Edit school profile" }));
  await shoot(a, ADM, "06-edit-school-lookup.png", opts);
  await a.getByRole("button", { name: "Look up" }).click();
  await expect(a.locator("#edit-tier")).toBeVisible();
  await shoot(a, ADM, "07-edit-school-loaded.png", { ...opts, element: card(a, "Edit school profile") });
  await a.selectOption("#edit-tier", { label: "Silver" });
  await a.getByRole("button", { name: "Save changes" }).click();
  await expect(a.getByText(/Partnership is now Silver/)).toBeVisible();
  await say(a, "upgrade");
  await shoot(a, ADM, "08-edit-school-upgrade-saved.png", { ...opts, center: a.getByText(/Partnership is now Silver/) });
  await a.selectOption("#edit-tier", { label: "Bronze" });
  await a.getByRole("button", { name: "Save changes" }).click();
  const confirm = a.getByRole("group").filter({ hasText: "Downgrading" });
  await expect(confirm).toBeVisible();
  console.log(`VERIFY downgrade preview: ${(await confirm.innerText()).replace(/\s+/g, " ")}`);
  await shoot(a, ADM, "09-edit-school-downgrade-confirm.png", { ...opts, center: confirm });
  await a.getByRole("button", { name: "Confirm downgrade" }).click();
  await expect(a.getByText(/Partnership is now Bronze/)).toBeVisible();
  await say(a, "downgrade saved");
  await shoot(a, ADM, "10-edit-school-downgrade-saved.png", { ...opts, center: a.getByText(/Partnership is now Bronze/) });
  await a.getByRole("button", { name: "Save changes" }).click();
  await expect(a.getByText("No changes to save.")).toBeVisible();
  await shoot(a, ADM, "11-edit-school-no-changes.png", { ...opts, center: a.getByText("No changes to save.") });
  await a.reload();
  await a.fill("#school-lookup-code", "FFFFFFFF");
  await a.getByRole("button", { name: "Look up" }).click();
  await expect(a.getByText("No school found with that School ID")).toBeVisible();
  await shoot(a, ADM, "12-edit-school-not-found.png", { ...opts, center: a.getByText("No school found with that School ID") });

  // --- SADM-004 Bulk onboarding (Renewal + Expired schools, plus three rejected rows) ---
  await a.reload();
  const header = (await (await a.request.get("/api/v1/overseas-admin/schools/bulk-template")).text()).split(/\r?\n/)[0].replace(/^\uFEFF/, "");
  const cols = header.split(",");
  const row = (v: Record<string, string>) => cols.map((c) => v[c] ?? "").join(",");
  const csv = [
    header,
    row({ name: "Docs Renewal School", city: "Kochi", state: "Kerala", tier: "gold", tier_valid_until: istDate(30), coordinator_full_name: "Docs Renewal Coordinator", coordinator_email: "docs.renewal.coordinator@example.test", board: "ICSE" }),
    row({ name: "Docs Expired School", city: "Jaipur", state: "Rajasthan", tier: "gold", tier_valid_until: istDate(-1), coordinator_full_name: "Docs Expired Coordinator", coordinator_email: "docs.expired.coordinator@example.test", board: "State" }),
    row({ name: "Docs Duplicate Email School", city: "Delhi", tier: "silver", coordinator_full_name: "Docs Duplicate", coordinator_email: "docs.renewal.coordinator@example.test" }),
    row({ name: "Docs Bad Tier School", city: "Goa", tier: "diamond", coordinator_full_name: "Docs Bad Tier", coordinator_email: "docs.badtier@example.test" }),
    row({ name: "Docs Bronze School", city: "Pune", tier: "bronze", coordinator_full_name: "Docs Second Bronze", coordinator_email: "docs.bronze2@example.test" }),
  ].join("\n");
  const csvPath = path.join(os.tmpdir(), "docs-school-onboarding.csv");
  writeFileSync(csvPath, csv);
  const bulk = a.getByRole("heading", { name: "Onboard several schools (CSV)" });
  await a.getByText("Column reference").first().click();
  await toTop(bulk);
  await shoot(a, ADM, "13-bulk-onboard-panel.png", opts);
  await a.getByLabel("Filled-in schools file").setInputFiles(csvPath);
  await a.getByRole("button", { name: "Upload schools" }).click();
  await expect(a.getByRole("heading", { name: "Upload result" })).toBeVisible({ timeout: 60_000 });
  console.log(`VERIFY bulk card: ${(await card(a, "Onboard several schools (CSV)").innerText()).replace(/\s+/g, " ").slice(0, 900)}`);
  console.log(`VERIFY bulk table: ${(await a.locator("table").last().innerText()).replace(/\s+/g, " ")}`);
  await toTop(a.getByRole("heading", { name: "Upload result" }));
  await shoot(a, ADM, "14-bulk-onboard-result.png", opts);
  // File-level error: a required column is missing.
  const badPath = path.join(os.tmpdir(), "docs-school-onboarding-bad.csv");
  writeFileSync(badPath, "name,city,coordinator_full_name\nDocs Missing Column School,Agra,Someone\n");
  await a.reload();
  await a.getByLabel("Filled-in schools file").setInputFiles(badPath);
  await a.getByRole("button", { name: "Upload schools" }).click();
  await expect(a.getByText(/Missing required column/)).toBeVisible({ timeout: 30_000 });
  await say(a, "bulk file error");
  await toTop(bulk);
  await shoot(a, ADM, "15-bulk-onboard-file-error.png", opts);

  // --- SADM-005 School staff accounts ---
  await a.goto("/overseas/admin/school-staff");
  const staffHeading = a.getByRole("heading", { name: "Create Academic Team / Career Counselor / Psychometric Team account" });
  for (const [i, s] of STAFF.entries()) {
    await a.selectOption("#staff-role", { label: s.role });
    await a.fill("#staff-name", s.name);
    await a.fill("#staff-email", s.email);
    if (s.schools.length) {
      await a.getByPlaceholder("Search schools…").fill("");
      await a.selectOption("#staff-schools", s.schools.map((label) => ({ label })));
    }
    if (i === 0) {
      await toTop(staffHeading);
      await shoot(a, ADM, "17-school-staff-form.png", opts);
    }
    await a.getByRole("button", { name: "Create account" }).click();
    await expect(a.getByText(`Account created for ${s.email}`)).toBeVisible({ timeout: 20_000 });
    await say(a, `staff ${s.name}`);
    if (i === 0) await shoot(a, ADM, "18-school-staff-created.png", { ...opts, center: a.getByText(`Account created for ${s.email}`) });
  }
  await a.goto("/overseas/admin/school-staff");
  await toTop(a.getByRole("heading", { name: "Academic Team / Career Counselor / Psychometric Team", exact: true }), 140);
  await shoot(a, ADM, "16-school-staff-list.png", opts);

  // --- SADM-010 Re-send a set-password link (Users page) ---
  await a.goto("/overseas/admin/users");
  const search = a.getByLabel("Search by name, email, or role");
  await search.fill(STAFF[0].email);
  await search.press("Enter");
  const resend = a.getByRole("button", { name: `Re-send set-password link to ${STAFF[0].name}` });
  await expect(resend).toBeVisible();
  await toTop(a.getByRole("heading", { name: "Manage users" }));
  await shoot(a, ADM, "19-users-resend-link.png", opts);
  await resend.click();
  await a.waitForTimeout(1500);
  await say(a, "resend");
  await toTop(a.getByRole("heading", { name: "Manage users" }));
  await shoot(a, ADM, "20-users-resend-result.png", opts);
  await ctx.close();

  // --- SADM-011 Super Admin ---
  const sctx = await browser.newContext();
  await noPrefetch(sctx);
  const s = await sctx.newPage();
  await signIn(s, "superadmin@edusphere.local", "seed", /\/admin/);
  await s.goto("/overseas/admin/schools");
  await expect(s.getByText("Workspace not found")).toBeVisible();
  await shoot(s, ADM, "21-superadmin-workspace-not-found.png", opts);
  await s.goto("/overseas/admin/school-transfers");
  await expect(s.getByRole("heading", { name: "School Transfers" })).toBeVisible();
  await shoot(s, ADM, "22-superadmin-transfers-overseas-sidebar.png", opts);
  await sctx.close();

  const out = JSON.stringify({ codes, schools: SCHOOLS, staff: STAFF.map(({ name, email }) => ({ name, email })) });
  if (process.env.DOCS_SCHOOL_FILE) writeFileSync(process.env.DOCS_SCHOOL_FILE, out); // read by later School CRM capture specs
  console.log(`SCHOOLS ${out}`);
});
