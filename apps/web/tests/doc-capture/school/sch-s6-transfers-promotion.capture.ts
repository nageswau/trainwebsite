import { readFileSync, writeFileSync } from "node:fs";

import { expect, test, type Browser, type Page } from "@playwright/test";

import { noPrefetch, SCHOOL_ROOT, shoot, signIn } from "../shoot";

// School CRM S6 (docs/school-crm/documentation-plan.md): DOC-SCH-XFER-001..003, DOC-SCH-SADM-007, DOC-SCH-STU-009.
// Runs after sch-s5. Creates and activates the 2027-28 academic year itself through the Overseas Admin API
// (owner decision 2026-10-06, U3).
const XF = "transfers";
const STU = "students";
const ADM = "admin-schools";
const opts = { root: SCHOOL_ROOT };
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const main = async (page: Page) => (await page.locator("main").first().innerText()).replace(/\s+/g, " ");

async function fresh(browser: Browser) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await noPrefetch(ctx);
  return { ctx, page: await ctx.newPage() };
}

async function requestOut(p: Page, studentId: string, dest: string, reason: string, shots?: [string, string]) {
  await p.goto(`/school/coordinator/students/${studentId}`);
  await p.getByText("Request a transfer").click();
  await p.selectOption("#transfer-destination", { label: dest });
  await p.fill("#transfer-reason", reason);
  if (shots) await shoot(p, XF, shots[0], { ...opts, center: p.locator("#transfer-reason") });
  await p.getByRole("button", { name: "Request transfer" }).click();
  await expect(p.getByText(/Transfer request sent for review/)).toBeVisible();
  if (shots) {
    await p.reload();
    await shoot(p, XF, shots[1], opts);
  }
}

test("School CRM S6 transfers and promotion", async ({ browser }) => {
  test.setTimeout(600_000);
  const school = JSON.parse(readFileSync(process.env.DOCS_SCHOOL_FILE!, "utf8"));

  const co = await fresh(browser);
  const p = co.page;
  await signIn(p, "school.coordinator@edusphere.local", "seed", /\/school\/coordinator\//);
  const students: { id: string; full_name: string; student_code: string }[] = await (await p.request.get("/api/v1/school/students")).json();
  const st = (name: string) => students.find((s) => s.full_name === name)!;

  // --- XFER-001 outgoing requests (Sunrise -> other schools) ---
  await requestOut(p, st("Docs Student Vihaan").id, "Docs Platinum Two", "Family is moving to Mumbai.", ["01-request-transfer-form.png", "02-transfer-requested.png"]);
  await requestOut(p, st("Docs Student Riya").id, "Docs Platinum Two", "Parent request.");
  await requestOut(p, st("Docs Student Omar").id, "Docs Platinum Two", "Requested by mistake.");
  await requestOut(p, st("Docs Student Ananya").id, "Docs Bronze School", "Closer to home.");
  // Duplicate pending request.
  await p.goto(`/school/coordinator/students/${st("Docs Student Vihaan").id}`);
  console.log(`VERIFY pending state on profile: ${(await main(p)).slice(0, 300)}`);

  // --- XFER-002 incoming (Docs Platinum Two asks for Sunrise's Sara) ---
  {
    const f = await fresh(browser);
    await signIn(f.page, school.schools.platinum2.email, "test", /\/school\/coordinator\//);
    await f.page.goto("/school/coordinator/transfers");
    await f.page.fill("#incoming-code", "ABC");
    await f.page.getByRole("button", { name: "Request student" }).click();
    await f.page.waitForTimeout(700);
    await say(f.page, "incoming short code");
    await f.page.fill("#incoming-code", st("Docs Student Sara").student_code);
    await f.page.fill("#incoming-reason", "Sibling already studies here.");
    await shoot(f.page, XF, "03-incoming-request-form.png", { ...opts, center: f.page.locator("#incoming-code") });
    await f.page.getByRole("button", { name: "Request student" }).click();
    const neutral = f.page.getByText(/If that Student ID belongs to a student at another school/);
    await expect(neutral).toBeVisible();
    await shoot(f.page, XF, "04-incoming-request-sent.png", { ...opts, center: neutral });
    await f.page.reload();
    console.log(`VERIFY incoming list: ${(await main(f.page)).slice(0, 400)}`);
    await f.ctx.close();
  }

  // --- XFER-003 track and cancel (Sunrise) ---
  await p.goto("/school/coordinator/transfers");
  await expect(p.getByRole("heading", { name: "Transfer requests" })).toBeVisible();
  await shoot(p, XF, "05-transfer-requests-pending.png", opts);
  await p.getByRole("button", { name: /Cancel request for Docs Student Omar/ }).click();
  const cancelled = p.getByText("Request cancelled.");
  await expect(cancelled).toBeVisible();
  await shoot(p, XF, "06-transfer-cancelled.png", { ...opts, center: cancelled });

  // --- SADM-007 admin decides ---
  {
    const f = await fresh(browser);
    const a = f.page;
    await signIn(a, "overseasadmin@edusphere.local", "seed", /\/overseas\/admin\//);
    await a.goto("/overseas/admin/school-transfers");
    await expect(a.getByRole("heading", { name: /Transfer requests/ })).toBeVisible();
    await a.waitForTimeout(1000);
    console.log(`VERIFY admin queue: ${(await main(a)).slice(0, 1500)}`);
    await shoot(a, ADM, "25-transfers-pending-queue.png", opts);
    await shoot(a, ADM, "26-transfer-warnings.png", { ...opts, center: a.getByText(/Docs Student Ananya/).first() });
    await a.getByRole("button", { name: "Approve transfer of Docs Student Vihaan to Docs Platinum Two" }).click();
    const confirm = a.getByRole("button", { name: "Confirm approval" });
    await expect(confirm).toBeVisible();
    await shoot(a, ADM, "27-transfer-approve-confirm.png", { ...opts, center: confirm });
    await confirm.click();
    const moved = a.getByText(/Moved Docs Student Vihaan to Docs Platinum Two/);
    await expect(moved).toBeVisible();
    await say(a, "approved");
    await shoot(a, ADM, "28-transfer-approved.png", { ...opts, center: moved });
    await a.getByRole("button", { name: "Reject transfer of Docs Student Riya to Docs Platinum Two" }).click();
    await a.getByLabel("Note for the requesting coordinator (optional)").fill("Please resubmit after the term ends.");
    await shoot(a, ADM, "29-transfer-reject-note.png", { ...opts, center: a.getByLabel("Note for the requesting coordinator (optional)") });
    await a.getByRole("button", { name: "Confirm rejection" }).click();
    const rejected = a.getByText(/Request rejected for Docs Student Riya/);
    await expect(rejected).toBeVisible();
    await say(a, "rejected");
    await a.selectOption("#admin-transfer-status", { label: "All" });
    await a.waitForTimeout(1000);
    console.log(`VERIFY admin all: ${(await main(a)).slice(0, 1200)}`);
    await shoot(a, ADM, "30-transfers-all.png", opts);

    // --- STU-009 setup: create and activate 2027-28 (Overseas Admin API) ---
    const years = await (await a.request.get("/api/v1/overseas-admin/academic-years")).json();
    let next = years.find((y: { label: string }) => y.label === "2027-28");
    if (!next) {
      const res = await a.request.post("/api/v1/overseas-admin/academic-years", { data: { label: "2027-28", start_date: "2027-04-01", end_date: "2028-03-31" } });
      next = await res.json();
      console.log(`VERIFY year created: ${res.status()} ${JSON.stringify(next)}`);
    }
    // Capture the promotion page before activation (only the current year exists as active).
    school.nextYearId = next.id;
    await f.ctx.close();
  }

  // Sunrise coordinator's view of the decisions and notices.
  await p.goto("/school/coordinator/transfers");
  await p.selectOption("#transfer-status", { label: "All" });
  await p.waitForTimeout(1000);
  console.log(`VERIFY CO all requests: ${(await main(p)).slice(0, 900)}`);
  await shoot(p, XF, "07-transfer-requests-all.png", opts);
  await p.goto("/school/coordinator/notifications");
  console.log(`VERIFY CO notifications: ${(await main(p)).slice(0, 500)}`);
  {
    const f = await fresh(browser);
    await signIn(f.page, school.schools.platinum2.email, "test", /\/school\/coordinator\//);
    await f.page.goto("/school/coordinator/notifications");
    console.log(`VERIFY P2 notifications: ${(await main(f.page)).slice(0, 400)}`);
    await f.page.goto(`/school/coordinator/students/${st("Docs Student Vihaan").id}`);
    console.log(`VERIFY moved student at P2: ${(await main(f.page)).slice(0, 300)}`);
    await shoot(f.page, XF, "08-transfer-history-on-profile.png", { ...opts, center: f.page.getByRole("heading", { name: "Transfer history" }) });
    await f.ctx.close();
  }
  {
    const f = await fresh(browser);
    await signIn(f.page, "school.parent@edusphere.local", "seed", /\/school\/parent\//);
    await f.page.goto("/school/parent/notifications");
    console.log(`VERIFY parent notifications: ${(await main(f.page)).slice(0, 300)}`);
    await f.ctx.close();
  }

  // --- STU-009 promotion ---
  await p.goto("/school/coordinator/promotion");
  await expect(p.getByRole("heading", { name: "Promote students" }).first()).toBeVisible();
  console.log(`VERIFY promotion before new year: ${(await main(p)).slice(0, 400)}`);
  await shoot(p, STU, "23-promotion-all-in-current-year.png", opts);
  {
    const f = await fresh(browser);
    await signIn(f.page, "overseasadmin@edusphere.local", "seed", /\/overseas\/admin\//);
    const res = await f.page.request.patch(`/api/v1/overseas-admin/academic-years/${school.nextYearId}`, { data: { status: "active" } });
    console.log(`VERIFY year activated: ${res.status()} ${await res.text()}`);
    await f.ctx.close();
  }
  await p.reload();
  await expect(p.locator("#promotion-select-all")).toBeVisible();
  console.log(`VERIFY promotion page: ${(await main(p)).slice(0, 600)}`);
  await p.check("#promotion-select-all");
  await p.selectOption(`#promo-action-${st("Docs Student Omar").id}`, "hold_back");
  await shoot(p, STU, "24-promotion-list.png", opts);
  console.log(`VERIFY hints: ${(await main(p)).match(/Grade (level is not set|12 is the highest)[^.]*\./g)}`);
  await p.getByRole("button", { name: /Review changes/ }).click();
  const confirmText = p.locator("#promotion-confirm-text");
  await expect(confirmText).toBeVisible();
  console.log(`VERIFY confirm: ${await confirmText.innerText()}`);
  await shoot(p, STU, "25-promotion-confirm.png", { ...opts, center: confirmText });
  await p.getByRole("button", { name: "Confirm promotion" }).click();
  const done = p.getByText(/Done for 2027-28/);
  await expect(done).toBeVisible({ timeout: 30_000 });
  await say(p, "promotion result");
  await shoot(p, STU, "26-promotion-result.png", { ...opts, center: done });
  console.log(`VERIFY failed rows: ${(await main(p)).match(/(Already in the active academic year|Grade level is not set[^.]*|Grade 12 is the highest grade[^.]*|This student's grade label can't be advanced[^.]*)\./g)}`);
  await p.goto(`/school/coordinator/students/${st("Docs Student Arjun").id}`);
  await shoot(p, STU, "27-grade-history.png", { ...opts, center: p.getByRole("heading", { name: "Grade history" }) });
  await co.ctx.close();

  school.transfers = { approved: "Docs Student Vihaan", rejected: "Docs Student Riya", cancelled: "Docs Student Omar", pending: ["Docs Student Ananya", "Docs Student Sara (incoming)"] };
  writeFileSync(process.env.DOCS_SCHOOL_FILE!, JSON.stringify(school));
});
