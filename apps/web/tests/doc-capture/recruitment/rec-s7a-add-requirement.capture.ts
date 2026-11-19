import { readFileSync, writeFileSync } from "node:fs";

import { test, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S7a (docs/recruitment-crm/documentation-plan.md): DOC-REC-REQ-001/002. Runs after rec-s6b.
// Recruiter A adds "Docs Python Developer" for Docs Acme Technologies; its id is saved in rec-ids.json (requirements.python).
const root = REC_ROOT;
const R = "requirements";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean).slice(-4))}`);
};
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
const plusDays = (n: number) => new Date(Date.now() + 5.5 * 3600_000 + n * 86_400_000).toISOString().slice(0, 10);

test("Recruitment CRM S7a add a requirement", async ({ browser }) => {
  test.setTimeout(600_000);
  const ids = JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8"));
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const a = await ctx.newPage();
  await signIn(a, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");

  // ===== REQ-001 empty list =====
  await a.goto("/recruiter/requirements");
  await settle(a, 3000);
  await shoot(a, R, "01-requirements-empty.png", { root });

  // ===== REQ-002 add =====
  await a.getByRole("link", { name: "Add job requirement" }).or(a.getByRole("button", { name: "Add job requirement" })).first().click();
  await settle(a, 3000);
  const co = a.getByRole("combobox", { name: /Company \(required\)/ });
  await co.click();
  await co.fill("Docs Acme");
  await settle(a, 1500);
  await a.getByRole("option", { name: /Docs Acme Technologies/ }).first().click();
  await settle(a, 1500);
  await a.getByLabel("Requisition reference").fill("ACME-ENG-2026-14");
  await a.getByLabel("Lead source").selectOption({ label: "Existing clients" });
  await a.getByLabel("Job title (required)").fill("Docs Python Developer");
  await a.getByLabel("Department").fill("Engineering");
  await a.getByLabel("Job category").selectOption({ label: "IT" });
  await a.getByLabel("Number of vacancies").fill("2");
  await a.getByLabel("Qualification").fill("B.Tech / MCA");
  await a.getByLabel("Experience from (years)").fill("1");
  await a.getByLabel("Experience to (years)").fill("3");
  await a.getByLabel("Employment type").selectOption({ label: "Full time" });
  await a.getByLabel("Shift").selectOption({ label: "Day" });
  await a.getByLabel("Country").fill("India");
  await a.getByLabel("State").fill("Telangana");
  await a.getByLabel("City").fill("Hyderabad");
  await a.getByLabel("Work mode").selectOption({ label: "Hybrid" });
  await a.getByLabel("Relocation required").selectOption({ label: "No" });
  await a.getByLabel("Salary from").fill("600000");
  await a.getByLabel("Salary to").fill("900000");
  await a.getByLabel("Pay period").selectOption({ label: "A year" });
  await a.getByLabel("Benefits").fill("Health insurance\nHybrid allowance");
  // Hiring manager searches EduSphere users (not company contacts): logged, left empty
  const hm = a.getByRole("combobox", { name: "Hiring manager" });
  await hm.click();
  await hm.fill("Docs");
  await settle(a, 1500);
  console.log("VERIFY REQ-002 hiring manager options:", JSON.stringify(await a.locator("#requirement-new-hiring_manager_user_id-list li").allInnerTexts()));
  await hm.fill("");
  await a.keyboard.press("Escape");
  await a.getByLabel("Joining requirement").fill("Within 30 days");
  await a.getByLabel("Application deadline").fill(plusDays(30));
  await a.getByLabel("Priority").selectOption({ label: "High" });
  await a.getByLabel("Interview rounds").fill("Technical round\nHR round");
  await a.getByLabel("Screening steps").fill("Resume check\nPhone screen");
  const dm = await a.getByLabel("Decision-maker").locator("option").allInnerTexts();
  console.log("VERIFY REQ-002 decision-makers:", JSON.stringify(dm));
  if (dm.some((o) => o.startsWith("Docs Rahul"))) await a.getByLabel("Decision-maker").selectOption({ label: dm.find((o) => o.startsWith("Docs Rahul"))! });
  await a.getByLabel("Expected turnaround (days)").fill("30");
  await a.getByLabel("Required skills").fill("Python, Docs FastAPI");
  await a.getByLabel("Preferred skills").fill("SQL");
  await a.getByLabel("Job description").fill("Build and maintain REST APIs in Python for Docs Acme's hiring platform. Work with SQL databases and write tests.");
  await shoot(a, R, "02-add-requirement-form.png", { root, fullPage: true });
  await a.getByRole("button", { name: "Save requirement" }).click();
  await settle(a, 4000);
  await say(a, "REQ-002 saved");
  console.log("VERIFY REQ-002 url:", a.url());
  const id = a.url().match(/requirements\/([0-9a-f-]{36})/)?.[1];
  ids.requirements = { ...(ids.requirements ?? {}), python: id };
  writeFileSync(process.env.DOCS_REC_FILE!, JSON.stringify(ids, null, 2));
  await shoot(a, R, "03-requirement-page.png", { root });
  await shoot(a, R, "04-requirement-page-full.png", { root, fullPage: true });
  const info = await a.evaluate(() => ({
    heads: [...document.querySelectorAll("main h2, main h3, main h4, main summary")].map((h) => `${h.tagName}:${h.textContent?.trim()}`),
    buttons: [...new Set([...document.querySelectorAll("main button, main a.btn")].map((b) => b.textContent?.trim().slice(0, 60)))],
    text: (document.querySelector("main") as HTMLElement).innerText.replace(/\s+/g, " ").slice(0, 6000),
  }));
  console.log("VERIFY REQ-003 page:", JSON.stringify(info, null, 1));

  // ===== REQ-001 list with the requirement =====
  await a.goto("/recruiter/requirements");
  await settle(a, 3000);
  await shoot(a, R, "05-requirements-list.png", { root });
  await ctx.close();
});
