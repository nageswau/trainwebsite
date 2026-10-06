import { readFileSync } from "node:fs";

import { expect, test, type Browser, type Page } from "@playwright/test";

import { noPrefetch, SCHOOL_ROOT, shoot, signIn } from "../shoot";

// School CRM S10 (docs/school-crm/documentation-plan.md): DOC-SCH-DASH-001..004 (005..007 reuse S7-S9 shots),
// DOC-SCH-RPT-001..005, DOC-SCH-ENT-001..002, DOC-SCH-NOTIF-001..002, DOC-SCH-PAR-001, DOC-SCH-SADM-008. Runs after sch-s9.
const DASH = "dashboards";
const RPT = "reports";
const ENT = "entitlements";
const NOT = "notifications";
const PAR = "parent";
const ADM = "admin-schools";
const opts = { root: SCHOOL_ROOT };
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const main = async (page: Page) => (await page.locator("main").first().innerText()).replace(/\s+/g, " ");
const h = (p: Page, name: string | RegExp) => p.getByRole("heading", { name }).first();

async function as(browser: Browser, email: string, kind: "seed" | "test", landing: RegExp) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
  await noPrefetch(ctx);
  const page = await ctx.newPage();
  await signIn(page, email, kind, landing);
  return { ctx, page };
}

test("School CRM S10 dashboards, reports, entitlements, notifications, parent, analytics", async ({ browser }) => {
  test.setTimeout(900_000);
  const school = JSON.parse(readFileSync(process.env.DOCS_SCHOOL_FILE!, "utf8"));

  // ===== Coordinator: DASH-001, RPT-001..005, ENT-001, NOTIF-001 =====
  {
    const { ctx, page: p } = await as(browser, "school.coordinator@edusphere.local", "seed", /\/school\/coordinator\//);
    await expect(h(p, "School at a glance")).toBeVisible();
    console.log(`VERIFY CO dashboard: ${(await main(p)).slice(0, 1400)}`);
    await shoot(p, DASH, "01-coordinator-kpis.png", opts);
    await shoot(p, DASH, "02-coordinator-lower-cards.png", { ...opts, center: h(p, "Upcoming activities") });

    await p.goto("/school/coordinator/reports");
    await expect(h(p, "Download reports")).toBeVisible();
    const dl = p.waitForEvent("download");
    await p.getByRole("button", { name: "Download school report (PDF)" }).click();
    console.log(`VERIFY school report file: ${(await dl).suggestedFilename()}`);
    await expect(p.getByText("Report downloaded.")).toBeVisible();
    await shoot(p, RPT, "01-school-report-downloaded.png", opts);
    console.log(`VERIFY reports page: ${(await main(p)).slice(0, 1500)}`);
    await shoot(p, RPT, "02-summary-tiles-and-grades.png", { ...opts, center: h(p, "Students by grade") });
    await shoot(p, RPT, "03-service-delivery-and-activities.png", { ...opts, center: h(p, "Activities & attendance") });
    await shoot(p, RPT, "04-grade-wise-comparison.png", { ...opts, center: h(p, "Grade-wise comparison") });
    await p.fill("#at_risk_below", "40");
    await p.fill("#top_from", "85");
    await p.getByRole("button", { name: "Update thresholds" }).click();
    await p.waitForLoadState("networkidle");
    console.log(`VERIFY student development: ${(await p.locator("section, .card").filter({ has: h(p, "Student development") }).last().innerText()).replace(/\s+/g, " ").slice(0, 900)}`);
    await shoot(p, RPT, "05-student-development.png", { ...opts, center: h(p, "Student development") });
    await shoot(p, RPT, "06-at-risk-and-top-performers.png", { ...opts, center: p.getByText(/At-risk students \(/).first() });
    await p.goto("/school/coordinator/reports?at_risk_below=150&top_from=85");
    console.log(`VERIFY bad threshold: ${(await main(p)).match(/Thresholds must[^.]*\.[^.]*\.|At-risk must[^.]*\.[^.]*\./)}`);
    await shoot(p, RPT, "07-threshold-error.png", { ...opts, center: p.locator("#at_risk_below") });
    await p.goto("/school/coordinator/reports");
    await shoot(p, RPT, "08-scorecards-grid.png", { ...opts, center: h(p, "Student progress scorecards") });
    await p.selectOption("#scorecard-grade", { index: 2 });
    await p.locator("form").filter({ has: p.locator("#scorecard-grade") }).getByRole("button", { name: "Show" }).click();
    await p.waitForLoadState("networkidle");
    console.log(`VERIFY scorecard filter url: ${p.url()}`);
    await shoot(p, RPT, "09-scorecards-grade-filter.png", { ...opts, center: h(p, "Student progress scorecards") });

    await p.goto("/school/coordinator/entitlements");
    console.log(`VERIFY CO entitlements: ${(await main(p)).slice(0, 900)}`);
    await shoot(p, ENT, "01-entitlements-platinum.png", opts);

    await p.goto("/school/coordinator/notifications");
    console.log(`VERIFY CO notifications: ${(await main(p)).slice(0, 600)}`);
    await shoot(p, NOT, "01-coordinator-notifications.png", opts);
    const before = await p.getByText("new", { exact: true }).count();
    await p.getByRole("link", { name: "Open" }).first().click().catch(async () => p.getByRole("button", { name: "Open" }).first().click());
    await p.waitForLoadState("networkidle");
    console.log(`VERIFY open went to: ${new URL(p.url()).pathname}`);
    await p.goto("/school/coordinator/notifications");
    console.log(`VERIFY CO unread before=${before} after=${await p.getByText("new", { exact: true }).count()}`);
    await ctx.close();
  }

  // ===== Other schools: entitlements + tier notices =====
  for (const [email, file, label] of [
    [school.schools.bronze.email, "02-entitlements-bronze.png", "bronze"],
    [school.schools.notier.email, "03-entitlements-no-tier.png", "notier"],
    ["docs.expired.coordinator@example.test", "04-entitlements-expired.png", "expired"],
  ] as const) {
    const { ctx, page: p } = await as(browser, email, "test", /\/school\/coordinator\//);
    await p.goto("/school/coordinator/entitlements");
    console.log(`VERIFY entitlements ${label}: ${(await main(p)).slice(0, 500)}`);
    await shoot(p, ENT, file, opts);
    if (label === "bronze") {
      await p.goto("/school/coordinator/notifications");
      console.log(`VERIFY bronze notifications: ${(await main(p)).slice(0, 600)}`);
      await shoot(p, NOT, "02-tier-change-notices.png", opts);
    }
    await ctx.close();
  }

  // ===== Principal: DASH-002 (+ Timeline navigation), reports, entitlements =====
  {
    const { ctx, page: p } = await as(browser, "school.principal@edusphere.local", "seed", /\/school\/principal\//);
    console.log(`VERIFY PR dashboard: ${(await main(p)).slice(0, 300)}`);
    await shoot(p, DASH, "03-principal-dashboard.png", opts);
    await shoot(p, DASH, "04-principal-roster.png", { ...opts, center: h(p, "Your school") });
    await p.getByRole("row", { name: /Aarav Mehta/ }).getByRole("link", { name: "Timeline" }).click();
    await p.waitForURL(/\/school\/principal\/students\//);
    console.log(`VERIFY PR timeline nav: ${new URL(p.url()).pathname}`);
    await p.goto("/school/principal/reports");
    await shoot(p, RPT, "10-principal-reports.png", opts);
    await p.goto("/school/principal/entitlements");
    await shoot(p, ENT, "05-entitlements-principal.png", opts);
    await p.goto("/school/principal/notifications");
    console.log(`VERIFY PR notifications: ${(await main(p)).slice(0, 300)}`);
    await ctx.close();
  }

  // ===== Teacher: DASH-003 (+ View navigation) =====
  {
    const { ctx, page: p } = await as(browser, "docs.teacher.a@example.test", "test", /\/school\/teacher\//);
    console.log(`VERIFY TE dashboard: ${(await main(p)).slice(0, 400)}`);
    await shoot(p, DASH, "05-teacher-dashboard.png", opts);
    await p.getByRole("row", { name: /Docs Student Arjun/ }).getByRole("link", { name: "View" }).click();
    await p.waitForURL(/\/school\/teacher\/students\//);
    console.log(`VERIFY TE view nav: ${new URL(p.url()).pathname}`);
    await ctx.close();
  }

  // ===== Parent: DASH-004, PAR-001, NOTIF-002 =====
  {
    const { ctx, page: p } = await as(browser, "school.parent@edusphere.local", "seed", /\/school\/parent\//);
    await expect(h(p, "My children")).toBeVisible();
    console.log(`VERIFY PA dashboard: ${(await main(p)).slice(0, 1500)}`);
    await shoot(p, DASH, "06-parent-children.png", opts);
    await shoot(p, DASH, "07-parent-multi-school.png", { ...opts, center: p.getByText("Docs Platinum Two").first() });
    await shoot(p, DASH, "08-parent-upcoming-and-notifications.png", { ...opts, center: h(p, "Important notifications") });
    const kids: { id: string; full_name: string }[] = await (await p.request.get("/api/v1/school/students")).json();
    const kid = (n: string) => kids.find((k) => k.full_name === n)!.id;
    await p.goto(`/school/parent/children/${kid("Aarav Mehta")}`);
    console.log(`VERIFY PA child page headings: ${JSON.stringify(await p.locator("main h2, main h3").allInnerTexts())}`);
    await shoot(p, PAR, "01-child-overview.png", opts);
    await shoot(p, PAR, "02-child-guidance-and-psychometric.png", { ...opts, center: h(p, "Psychometric assessment") });
    await shoot(p, PAR, "03-child-results-and-activities.png", { ...opts, center: h(p, "Academic results") });
    await p.goto(`/school/parent/children/${kid("Isha Mehta")}`);
    await shoot(p, PAR, "04-child-funding-support.png", { ...opts, center: h(p, /Funding support/) });
    await p.goto(`/school/parent/children/${kid("Docs Student Vihaan")}`);
    console.log(`VERIFY Vihaan page: ${(await main(p)).slice(0, 400)}`);
    await shoot(p, PAR, "05-child-transfer-history.png", { ...opts, center: h(p, /Transfer history/) });
    await p.getByRole("link", { name: "Open 360° view" }).click();
    await p.waitForURL(/\/360/);
    await shoot(p, PAR, "06-child-360.png", opts);
    // NOTIF-002 + U8
    await p.goto("/school/parent/notifications");
    console.log(`VERIFY PA notifications: ${(await main(p)).slice(0, 900)}`);
    await shoot(p, NOT, "03-parent-notifications.png", opts);
    const newBefore = await p.getByText("new", { exact: true }).count();
    await p.getByRole("link", { name: "Open" }).first().click();
    await p.waitForLoadState("networkidle");
    console.log(`VERIFY PA open went to: ${new URL(p.url()).pathname}`);
    await p.goto("/school/parent/notifications");
    console.log(`VERIFY U8 parent new badges before=${newBefore} after=${await p.getByText("new", { exact: true }).count()}`);
    await ctx.close();
  }

  // ===== SADM-008 School Analytics =====
  {
    const { ctx, page: p } = await as(browser, "overseasadmin@edusphere.local", "seed", /\/overseas\/admin\//);
    await p.goto("/overseas/admin/school-analytics");
    await expect(h(p, "All partner schools")).toBeVisible();
    console.log(`VERIFY analytics: ${(await main(p)).slice(0, 1600)}`);
    await shoot(p, ADM, "37-analytics-kpis.png", opts);
    await shoot(p, ADM, "38-analytics-utilization.png", { ...opts, center: h(p, "Service utilization by school") });
    await p.fill("#school-search", "Docs");
    await p.getByRole("button", { name: "Search" }).click();
    await p.waitForLoadState("networkidle");
    await shoot(p, ADM, "39-analytics-search.png", { ...opts, center: h(p, "Service utilization by school") });
    await ctx.close();
  }
  {
    const { ctx, page: p } = await as(browser, "superadmin@edusphere.local", "seed", /\/admin/);
    await p.goto("/overseas/admin/school-analytics");
    await shoot(p, ADM, "40-analytics-super-admin.png", opts);
    await ctx.close();
  }
});
