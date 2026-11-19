import { readFileSync, writeFileSync } from "node:fs";

import { test, type Locator, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S8d (docs/recruitment-crm/documentation-plan.md): DOC-REC-STU-001/002. Runs after rec-s8c.
// Docs IT Lead Arjun (IT Counselor set; enrolled in Docs FSP Batch 1) joins the placement candidate pool; Recruiter A and the
// Team Lead then see him in the Candidate Master with his Journey and training progress. Saved as candidates.arjun.
const root = REC_ROOT;
const S = "student";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean).slice(-4))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 2500);
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
const sec = (p: Page, heading: string) =>
  p.getByRole("heading", { name: heading, exact: true }).first()
    .locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
async function step(name: string, fn: () => Promise<void>) {
  try { await fn(); } catch (e) { console.log(`STEP FAILED ${name}: ${String(e).split("\n")[0].slice(0, 300)}`); }
}

test("Recruitment CRM S8d IT student joins the pool", async ({ browser }) => {
  test.setTimeout(900_000);
  const ids = JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8"));

  // ===== STU-001 Arjun joins =====
  const sctx = await browser.newContext();
  await noPrefetch(sctx);
  const s = await sctx.newPage();
  await signIn(s, "docs.itlead.arjun@example.test", "test", /\/it\/student/, "/it/login");
  await step("STU-001 join", async () => {
    await s.goto("/it/student/placement-status");
    await settle(s, 3500);
    const join = () => sec(s, "Join the placement candidate pool");
    await shoot(s, S, "01-placement-status-before.png", { root });
    await join().getByLabel("I agree to the consent text above").check();
    await shoot(s, S, "02-join-pool.png", { root, element: join() });
    await join().getByRole("button", { name: "Join the pool" }).click();
    await settle(s, 3000);
    await say(s, "STU-001 joined");
    await s.reload();
    await settle(s, 3500);
    console.log("VERIFY STU-001 after:", await text(s.locator("main")));
    console.log("VERIFY STU-001 buttons:", JSON.stringify((await s.locator("main button").allInnerTexts()).map((b) => b.trim())));
    await shoot(s, S, "03-in-the-pool.png", { root });
  });
  await sctx.close();

  // ===== STU-002 staff view (Recruiter A, then Team Lead) =====
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const a = await ctx.newPage();
  await signIn(a, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");
  await step("STU-002 recruiter", async () => {
    await a.goto("/recruiter/candidates");
    await settle(a, 3000);
    await a.getByLabel("Search candidates").fill("Arjun");
    await a.getByRole("button", { name: "Search" }).click();
    await settle(a, 2500);
    console.log("VERIFY STU-002 recruiter search:", (await text(a.locator("main"))).slice(-700));
    await shoot(a, S, "04-recruiter-search.png", { root });
  });
  await ctx.close();
  const lctx = await browser.newContext();
  await noPrefetch(lctx);
  const l = await lctx.newPage();
  await signIn(l, "docs.rec.lead@example.test", "test", /\/recruiter\/manager\/team/, "/admin/login");
  await step("STU-002 team lead", async () => {
    await l.goto("/recruiter/candidates");
    await settle(l, 3000);
    await l.getByLabel("Search candidates").fill("Arjun");
    await l.getByRole("button", { name: "Search" }).click();
    await settle(l, 2500);
    console.log("VERIFY STU-002 lead search:", (await text(l.locator("main"))).slice(-700));
    await shoot(l, S, "05-team-lead-search.png", { root });
    const link = l.locator("main").getByRole("link", { name: /Arjun/ }).first();
    await link.click();
    await settle(l, 3500);
    const id = l.url().match(/candidates\/([0-9a-f-]{36})/)?.[1];
    ids.candidates = { ...(ids.candidates ?? {}), arjun: id };
    writeFileSync(process.env.DOCS_REC_FILE!, JSON.stringify(ids, null, 2));
    console.log("VERIFY STU-002 header:", (await text(l.locator("main"))).slice(0, 1200));
    console.log("VERIFY STU-002 journey:", await text(sec(l, "Journey")));
    console.log("VERIFY STU-002 training:", await text(sec(l, "Training progress")));
    console.log("VERIFY STU-002 ownership:", await text(sec(l, "Ownership")));
    console.log("VERIFY STU-002 buttons:", JSON.stringify([...new Set((await l.locator("main button").allInnerTexts()).map((b) => b.trim()))]));
    await shoot(l, S, "06-student-candidate-page.png", { root });
    await shoot(l, S, "07-journey.png", { root, element: sec(l, "Journey") });
    await shoot(l, S, "08-training-progress.png", { root, element: sec(l, "Training progress") });
  });

  // ===== CAN-013 unassigned queue: the Team Lead assigns Arjun to Recruiter A =====
  await step("CAN-013 queue", async () => {
    await l.goto("/recruiter/manager/team");
    await settle(l, 2500);
    await l.getByRole("link", { name: "Unassigned Queue", exact: true }).first().click();
    await settle(l, 3500);
    console.log("VERIFY CAN-013 queue url:", l.url());
    console.log("VERIFY CAN-013 queue:", (await text(l.locator("main"))).slice(0, 1500));
    await shoot(l, "candidates", "42-unassigned-queue.png", { root });
    await l.goto(`/recruiter/candidates/${ids.candidates.arjun}`);
    await settle(l, 3500);
    const ow = () => sec(l, "Ownership");
    await ow().getByRole("button", { name: "Change ownership" }).click();
    await settle(l, 1000);
    const box = ow().getByRole("combobox", { name: "Primary recruiter" });
    await box.click();
    await box.fill("Docs Recruiter A");
    await settle(l, 1500);
    await l.getByRole("option", { name: /Docs Recruiter A/ }).first().click();
    await settle(l, 500);
    await shoot(l, "candidates", "43-assign-primary.png", { root, element: ow() });
    await ow().getByRole("button", { name: "Save ownership" }).click();
    await settle(l, 2500);
    await say(l, "CAN-013 assigned");
    console.log("VERIFY CAN-013 ownership:", await text(ow()));
  });
  await lctx.close();
});
