import { readFileSync, writeFileSync } from "node:fs";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S5a (docs/recruitment-crm/documentation-plan.md): DOC-REC-CO-001, CO-002. Runs after rec-s4.
// The Team Lead adds the industry "Docs IT Services"; Recruiter A adds Docs Acme Technologies with its first contact (Add recruiter)
// and Docs Beta Systems (Add company). Company ids are written to DOCS_REC_FILE.
const root = REC_ROOT;
const C = "companies";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 2000);
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
async function ctxPage(browser: Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  return ctx.newPage();
}
const ids = (): Record<string, unknown> => {
  try { return JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8")); } catch { return {}; }
};

test("Recruitment CRM S5a companies", async ({ browser }) => {
  test.setTimeout(600_000);
  const l = await ctxPage(browser);
  await signIn(l, "docs.rec.lead@example.test", "test", /\/recruiter\/manager\/team/, "/admin/login");
  await l.goto("/recruiter/manager/catalogue/industries");
  await settle(l);
  await l.getByLabel(/industry name \(required\)/i).fill("Docs IT Services");
  await l.getByRole("button", { name: /^Add industry/i }).click();
  await settle(l, 1500);
  await say(l, "industry added");

  const a = await ctxPage(browser);
  await signIn(a, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");
  await a.goto("/recruiter/companies");
  await settle(a);
  await shoot(a, C, "01-companies-empty.png", { root });

  // CO-002 Add recruiter: company + first contact
  await a.getByRole("link", { name: "Add recruiter" }).first().click();
  await a.waitForURL(/companies\/new/);
  await settle(a);
  const linkedins = a.getByLabel("LinkedIn", { exact: true });
  await a.getByLabel("Contact name (required)").fill("Docs Priya HR Lead");
  await a.getByLabel("Designation").fill("Talent Acquisition Lead");
  await a.getByLabel("Role", { exact: true }).selectOption({ label: "Talent Acquisition Manager" });
  await a.getByLabel("Mobile").fill("+91 90000 31001");
  await a.getByLabel("Email").fill("docs.priya.hr@example.test");
  await a.getByLabel("Company name (required)").fill("Docs Acme Technologies");
  await a.getByLabel("Website").fill("docs-acme.example.test");
  await linkedins.nth(1).fill("linkedin.com/company/docs-acme");
  await a.getByLabel("Industry").selectOption({ label: "Docs IT Services" });
  await a.getByLabel("Company size").selectOption({ label: "201-500" });
  await a.getByLabel("City").fill("Hyderabad");
  await a.getByLabel("State").fill("Telangana");
  await a.getByLabel("Country").fill("India");
  await a.getByLabel("Lead source").selectOption({ label: "LinkedIn" });
  await a.getByLabel("Campaign").selectOption({ label: "Docs Q4 IT hiring push" });
  await a.getByLabel("Priority").selectOption({ label: "Hot" });
  await a.getByLabel("Company description").fill("Docs: product company hiring Python and React developers.");
  await shoot(a, C, "02-add-recruiter-form.png", { root, fullPage: true });
  await a.getByRole("button", { name: "Save company" }).click();
  await a.waitForURL(/companies\/[0-9a-f-]{36}/, { timeout: 30_000 });
  await settle(a, 2500);
  await say(a, "CO-002 saved");
  const acme = a.url().split("/").pop()!.split("?")[0];
  console.log(`VERIFY CO-002 company page: ${await text(a.locator("main"))}`);
  await shoot(a, C, "03-company-created.png", { root });

  // CO-002 Add company (no contact)
  await a.goto("/recruiter/companies/new");
  await settle(a);
  console.log(`VERIFY CO-002 add company heading: ${await a.locator("main h2").first().innerText()}`);
  await a.getByLabel("Company name (required)").fill("Docs Beta Systems");
  await a.getByLabel("Industry").selectOption({ label: "Docs IT Services" });
  await a.getByLabel("City").fill("Bengaluru");
  await a.getByLabel("Lead source").selectOption({ label: "Referrals" });
  await a.getByLabel("Priority").selectOption({ label: "Warm" });
  await a.getByRole("button", { name: "Save company" }).click();
  await a.waitForURL(/companies\/[0-9a-f-]{36}/, { timeout: 30_000 });
  await settle(a, 2000);
  const beta = a.url().split("/").pop()!.split("?")[0];

  // CO-001 list and filters
  await a.goto("/recruiter/companies");
  await settle(a);
  console.log(`VERIFY CO-001 list: ${await text(a.locator("main"))}`);
  await shoot(a, C, "04-companies-list.png", { root });
  await a.getByLabel("Priority").selectOption({ label: "Hot" });
  await a.getByRole("button", { name: "Search" }).click();
  await settle(a, 1500);
  await shoot(a, C, "05-companies-filter-hot.png", { root });

  // Team Lead's view of the same list
  await l.goto("/recruiter/companies");
  await settle(l);
  console.log(`VERIFY CO-001 lead list: ${await text(l.locator("main"))}`);
  await shoot(l, C, "06-companies-team-lead.png", { root });

  writeFileSync(process.env.DOCS_REC_FILE!, JSON.stringify({ ...ids(), companies: { acme, beta } }, null, 2));
});
