import { readFileSync, writeFileSync } from "node:fs";

import { test, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S8a (docs/recruitment-crm/documentation-plan.md): DOC-REC-CAN-001/002. Runs after rec-s7b.
// Recruiter A adds Docs Candidate Kiran and Docs Candidate Meena by hand and tries Kiran's mobile again (duplicate check).
// Their ids are saved in rec-ids.json (candidates.kiran / candidates.meena).
const root = REC_ROOT;
const C = "candidates";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean).slice(-4))}`);
};
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
const main = async (p: Page) => (await p.locator("main").innerText()).replace(/\s+/g, " ");

async function fill(a: Page, c: { name: string; mobile: string; email: string; city: string; role: string; months: string; company: string }) {
  await a.getByLabel("Name *").fill(c.name);
  await a.getByLabel("Mobile").fill(c.mobile);
  await a.getByLabel("Email").fill(c.email);
  await a.getByLabel("Source *").selectOption({ label: "LinkedIn" });
  await a.getByLabel("Source detail").fill("Docs Q4 IT hiring push");
  await a.getByLabel("Basis for holding the details *").selectOption({ label: "They agreed to be in the candidate pool" });
  await a.getByLabel("City").fill(c.city);
  await a.getByLabel("State").fill("Telangana");
  await a.getByLabel("Country").fill("India");
  await a.getByLabel("Preferred contact").selectOption({ label: "WhatsApp" });
  await a.getByLabel("Total experience (months)").fill(c.months);
  await a.getByLabel("Current company").fill(c.company);
  await a.getByLabel("Preferred roles").fill(c.role);
  await a.getByLabel("Preferred locations").fill("Hyderabad, Bengaluru");
  await a.getByLabel("Expected salary", { exact: true }).fill("800000");
}

test("Recruitment CRM S8a add candidates", async ({ browser }) => {
  test.setTimeout(600_000);
  const ids = JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8"));
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const a = await ctx.newPage();
  await signIn(a, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");

  // ===== CAN-001 empty =====
  await a.goto("/recruiter/candidates");
  await settle(a, 3000);
  await shoot(a, C, "01-candidates-empty.png", { root });

  // ===== CAN-002 add Kiran =====
  await a.goto("/recruiter/candidates/new");
  await settle(a, 3000);
  await fill(a, { name: "Docs Candidate Kiran", mobile: "9000040001", email: "docs.cand.kiran@example.com", city: "Hyderabad", role: "Python Developer, Backend Developer", months: "30", company: "Docs Orbit Softech" });
  await shoot(a, C, "02-add-candidate-form.png", { root, fullPage: true });
  await a.getByRole("button", { name: "Add candidate", exact: true }).click();
  await settle(a, 4000);
  await say(a, "CAN-002 kiran");
  console.log("VERIFY CAN-002 kiran url:", a.url());
  const kiran = a.url().match(/candidates\/([0-9a-f-]{36})/)?.[1];
  await shoot(a, C, "03-candidate-created.png", { root });

  // duplicate: Meena typed with Kiran's mobile first
  await a.goto("/recruiter/candidates/new");
  await settle(a, 3000);
  await fill(a, { name: "Docs Candidate Meena", mobile: "9000040001", email: "docs.cand.meena@example.com", city: "Hyderabad", role: "Data Analyst", months: "18", company: "Docs Lumen Analytics" });
  await a.getByRole("button", { name: "Add candidate", exact: true }).click();
  await settle(a, 3000);
  await say(a, "CAN-002 duplicate");
  console.log("VERIFY CAN-002 duplicate page:", (await main(a)).slice(0, 900));
  await shoot(a, C, "04-duplicate-blocked.png", { root });

  // fix the mobile and save Meena
  await a.getByLabel("Mobile").fill("9000040002");
  await a.getByRole("button", { name: "Add candidate", exact: true }).click();
  await settle(a, 4000);
  await say(a, "CAN-002 meena");
  const meena = a.url().match(/candidates\/([0-9a-f-]{36})/)?.[1];
  console.log("VERIFY CAN-002 meena url:", a.url());

  ids.candidates = { ...(ids.candidates ?? {}), kiran, meena };
  writeFileSync(process.env.DOCS_REC_FILE!, JSON.stringify(ids, null, 2));

  // ===== candidate page dump (drives S8b) =====
  await a.goto(`/recruiter/candidates/${kiran}`);
  await settle(a, 3500);
  const info = await a.evaluate(() => ({
    heads: [...document.querySelectorAll("main h2, main h3, main h4, main summary")].map((h) => `${h.tagName}:${h.textContent?.trim()}`),
    buttons: [...new Set([...document.querySelectorAll("main button")].map((b) => b.textContent?.trim().slice(0, 60)))],
    fields: [...document.querySelectorAll("main input, main select, main textarea")].map((e) => {
      const el = e as HTMLInputElement;
      const lab = el.id ? document.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.textContent?.trim() : "";
      return `${el.tagName.toLowerCase()}:${el.type} "${lab || el.getAttribute("aria-label") || el.name}"`;
    }),
    text: (document.querySelector("main") as HTMLElement).innerText.replace(/\s+/g, " ").slice(0, 7000),
  }));
  console.log("VERIFY CAN-003 page:", JSON.stringify(info, null, 1));
  await shoot(a, C, "05-candidate-page-full.png", { root, fullPage: true });

  // ===== CAN-001 list =====
  await a.goto("/recruiter/candidates");
  await settle(a, 3000);
  console.log("VERIFY CAN-001 list:", (await main(a)).slice(0, 1200));
  await shoot(a, C, "06-candidates-list.png", { root });
  await ctx.close();
});
