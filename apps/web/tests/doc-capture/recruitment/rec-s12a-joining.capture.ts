import { readFileSync } from "node:fs";
import path from "node:path";

import { test, type Locator, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S12a (docs/recruitment-crm/documentation-plan.md): DOC-REC-HIRE-011..013 (+ first look at HIRE-014/015/016). Runs after
// rec-s11c. Recruiter A records the candidate's and the client's confirmation, marks Docs Candidate Kiran Joined today with a joining
// proof, and reads the placement. The invoice draft is only viewed: nothing is issued, discarded or paid (R3).
const root = REC_ROOT;
const H = "hiring";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean).slice(-4))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 3500);
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
const sec = (p: Page, h: string | RegExp) =>
  p.getByRole("heading", { name: h, exact: typeof h === "string" }).first()
    .locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
const ctrls = async (l: Locator) => JSON.stringify([...new Set((await l.locator("button, a").evaluateAll((els) => els.map((e) => (e.getAttribute("aria-label") || e.textContent || "").trim()))).filter(Boolean))]);
const fields = (l: Locator) => l.evaluate((el) => [...el.querySelectorAll("input, select, textarea")].map((e) => {
  const f = e as HTMLInputElement;
  const lab = (f.id && document.querySelector(`label[for="${CSS.escape(f.id)}"]`)?.textContent?.trim()) || f.getAttribute("aria-label") || f.closest("label")?.textContent?.trim() || f.name;
  const o = f.tagName === "SELECT" ? " [" + [...(f as unknown as HTMLSelectElement).options].map((x) => x.text).join("|") + "]" : "";
  return `${f.type} "${(lab ?? "").slice(0, 70)}"${o}`;
}));
async function step(name: string, fn: () => Promise<void>) {
  try { await fn(); } catch (e) { console.log(`STEP FAILED ${name}: ${String(e).split("\n")[0].slice(0, 300)}`); }
}
const today = () => new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10);

test("Recruitment CRM S12a joining", async ({ browser }) => {
  test.setTimeout(1_200_000);
  const ids = JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8"));
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const a = await ctx.newPage();
  a.on("dialog", (d) => { console.log(`VERIFY dialog (dismissed): ${d.message()}`); void d.dismiss(); });
  await signIn(a, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");
  const reqUrl = `/recruiter/requirements/${ids.requirements.python}`;
  let placementUrl = "";

  // ===== HIRE-012 joinings list, HIRE-013 placements list (before) =====
  await step("lists before", async () => {
    await a.goto("/recruiter/joinings");
    await settle(a, 3000);
    await shoot(a, H, "30-joinings-due.png", { root });
    await a.goto("/recruiter/placements");
    await settle(a, 3000);
    await shoot(a, H, "31-placements-pending.png", { root });
    await a.locator("main").getByRole("link", { name: "Docs Candidate Kiran" }).first().click();
    await settle(a, 3500);
    placementUrl = new URL(a.url()).pathname;
    console.log("VERIFY HIRE-013 placement url:", placementUrl);
    await shoot(a, H, "32-placement-pending.png", { root, fullPage: true });
  });

  // ===== HIRE-013 confirmations =====
  for (const [i, who, by] of [[0, "candidate", "Docs Candidate Kiran by phone"], [1, "client", "Docs Rahul Hiring Manager by email"]] as const) {
    await step(`HIRE-013 ${who}`, async () => {
      await a.goto(placementUrl);
      await settle(a, 3000);
      await a.locator("main").getByRole("button", { name: "Record confirmation" }).nth(i === 0 ? 0 : 0).click();
      await settle(a, 1500);
      const form = a.locator("main form").first();
      console.log(`VERIFY HIRE-013 ${who} fields:`, JSON.stringify(await fields(form)));
      await form.getByLabel("Confirmed by").fill(by.split(" by ")[0]);
      await form.getByLabel("Confirmed on").fill(today());
      await form.getByLabel("How").selectOption({ label: by.endsWith("phone") ? "Call" : "Email" });
      if (who === "candidate") await shoot(a, H, "33-record-confirmation.png", { root, element: form });
      await form.getByRole("button", { name: /^(Save|Record|Confirm)/ }).first().click();
      await settle(a, 2500);
      await say(a, `HIRE-013 ${who}`);
    });
  }

  // ===== HIRE-011 joined, with proof =====
  await step("HIRE-011", async () => {
    const proof = path.join(process.env.DOCS_FILES_DIR!, "docs-kiran-joining-proof.pdf");
    const g = await ctx.newPage();
    await g.setContent("<html><body style='font-family:Arial;margin:40px'><h1>Docs Acme Technologies</h1><h2>Joining confirmation</h2><p>Docs Candidate Kiran joined as Python Developer, Hyderabad. Reporting manager: Docs Rahul Hiring Manager.</p><p><i>Fictional document for the EduSphere user guide.</i></p></body></html>");
    await g.pdf({ path: proof, format: "A4" });
    await g.close();
    await a.goto(reqUrl);
    await settle(a, 3500);
    const c = sec(a, /^Candidates \(/);
    await c.getByRole("button", { name: "Offer of Docs Candidate Kiran" }).click();
    await settle(a, 1500);
    await c.getByRole("button", { name: "Update joining of Docs Candidate Kiran" }).click();
    await settle(a, 1500);
    await c.getByLabel("Joining status").selectOption({ label: "Joined" });
    await c.getByLabel("Actual joining date").fill(today());
    await c.getByLabel("Joining location").fill("Docs Acme office, Hyderabad");
    await c.getByLabel("Reporting manager").fill("Docs Rahul Hiring Manager");
    await c.getByLabel("Confirmed by (who at the company)").fill("Docs Priya HR Lead");
    await c.getByLabel("Confirmation date").fill(today());
    await shoot(a, H, "34-update-joining.png", { root, element: c });
    await c.getByRole("button", { name: "Save joining" }).click();
    await settle(a, 3000);
    await say(a, "HIRE-011 joined");
    const file = c.locator('input[type="file"]').last();
    await file.setInputFiles(proof);
    await c.getByRole("button", { name: "Upload", exact: true }).last().click();
    await settle(a, 3000);
    await say(a, "HIRE-011 proof");
    console.log("VERIFY HIRE-011 after:", await text(c));
    await shoot(a, H, "35-joined.png", { root, element: c });
  });

  // ===== placement after joining =====
  await step("placement after", async () => {
    await a.goto(placementUrl);
    await settle(a, 3500);
    console.log("VERIFY HIRE-013 placement after:", await text(a.locator("main")));
    console.log("VERIFY HIRE-013 controls:", await ctrls(a.locator("main")));
    console.log("VERIFY HIRE-013 fields:", JSON.stringify(await fields(a.locator("main"))));
    await shoot(a, H, "36-placement-joined.png", { root, fullPage: true });
    await a.goto("/recruiter/joinings");
    await settle(a, 3000);
    await a.locator("main").getByRole("button", { name: /^Joined/ }).or(a.locator("main").getByRole("link", { name: /^Joined/ })).first().click();
    await settle(a, 2500);
    console.log("VERIFY HIRE-012 joined tab:", (await text(a.locator("main"))).slice(0, 800));
    await shoot(a, H, "37-joinings-joined.png", { root });
    await a.goto("/recruiter/placements");
    await settle(a, 3000);
    console.log("VERIFY HIRE-013 placements list:", (await text(a.locator("main"))).slice(0, 800));
  });
  await ctx.close();
});
