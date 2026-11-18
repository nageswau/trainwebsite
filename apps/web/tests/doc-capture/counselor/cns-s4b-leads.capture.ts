import { readFileSync, writeFileSync } from "node:fs";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { COUNSELOR_ROOT, noPrefetch, password, shoot, signIn, toTop } from "../shoot";

// Counselor CRM S4 (docs/counselor-crm/documentation-plan.md): DOC-CNS-HO-001, HO-002, LEAD-001..009, CONV-001, CONV-002.
// Runs after cns-s4a (Docs Telecaller password). Creates the Docs leads used by S5-S9.
const root = COUNSELOR_ROOT;
const A = "docs.counselor.a@example.test";
const TEL = "docs.telecaller@example.test";
const LEAD = (n: string) => ({ asha: { name: "Docs Lead Asha", phone: "+91 90000 10101", email: "docs.lead.asha@example.test", product: "UK", source: "instagram", priority: "hot" },
  bilal: { name: "Docs Lead Bilal", phone: "+91 90000 10102", email: "docs.lead.bilal@example.test", product: "Canada", source: "facebook", priority: "warm" },
  esha: { name: "Docs Lead Esha", phone: "+91 90000 10105", email: "docs.lead.esha@example.test", product: "Germany", source: "google", priority: "cold" },
  divya: { name: "Docs Lead Divya", phone: "+91 90000 10104", email: "docs.lead.divya@example.test", product: "UK", source: "walk_in", priority: "warm" } } as const)[n as "asha"]!;
const CHEN = { name: "Docs Lead Chen", phone: "+91 90000 10103", email: "docs.lead.chen@example.com" };
const ist = (days = 0) => new Date(Date.now() + 5.5 * 3600_000 + days * 86_400_000).toISOString().slice(0, 10);
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 1200);
// A lead-page section, found by its heading id.
const sec = (p: Page, headingId: string) => p.locator(`#${headingId}`).locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ')][1]");

async function ctxPage(browser: Browser, viewport?: { width: number; height: number }) {
  const ctx = await browser.newContext(viewport ? { viewport } : {});
  await noPrefetch(ctx);
  return ctx.newPage();
}

async function newLead(p: Page, l: ReturnType<typeof LEAD>, base: string) {
  await p.goto(`${base}/new`);
  await p.waitForTimeout(1500);
  await p.fill("#new-name", l.name);
  await p.fill("#new-phone", l.phone);
  await p.fill("#new-email", l.email);
  await p.selectOption("#new-product_id", { label: l.product });
  await p.selectOption("#new-source", l.source);
  await p.selectOption("#new-priority", l.priority);
}

const ids: Record<string, string> = {};
const leadId = (p: Page) => decodeURIComponent(new URL(p.url()).pathname.split("/").pop() ?? "");

test("Counselor CRM S4 leads and handoffs", async ({ browser }) => {
  test.setTimeout(900_000);

  // ===== Telecaller creates three leads and hands them to Docs Counselor A (HO-001) =====
  const t = await ctxPage(browser);
  await signIn(t, TEL, "test", /\/telecaller\//);
  for (const key of ["asha", "bilal", "esha"]) {
    const l = LEAD(key);
    await newLead(t, l, "/telecaller/leads");
    await t.getByRole("button", { name: "Create lead" }).click();
    await t.waitForURL(/\/telecaller\/leads\/(?!new)[^/]+$/);
    await t.waitForTimeout(1500);
    ids[key] = leadId(t);
    await t.getByRole("button", { name: "Assign to counselor" }).click();
    await t.waitForTimeout(800);
    const form = t.locator("form", { has: t.getByLabel("Counselor") });
    if (key === "asha") {
      console.log(`VERIFY HO-001 telecaller lead page: ${await text(t.locator("main"))}`);
      await form.getByLabel("Counselor").selectOption({ label: "Docs Counselor A" }).catch(async () => console.log(`VERIFY HO-001 options ${JSON.stringify(await form.getByLabel("Counselor").locator("option").allInnerTexts())}`));
      await shoot(t, "handoffs", "01-telecaller-assign-counselor.png", { root, center: form });
      await form.getByRole("button", { name: "Hand over" }).click();
      await t.waitForTimeout(1500);
      await say(t, "HO-001 handed over");
      console.log(`VERIFY HO-001 after: ${await text(t.locator("main"))}`);
      await shoot(t, "handoffs", "02-telecaller-handed-over.png", { root, center: t.getByText("Handed over to Docs Counselor A.") });
    } else {
      await form.getByLabel("Counselor").selectOption({ label: "Docs Counselor A" });
      await form.getByRole("button", { name: "Hand over" }).click();
      await t.waitForTimeout(1500);
      await say(t, `HO-001 handed over ${key}`);
    }
  }

  // ===== Website enquiry -> unassigned -> manager assigns -> telecaller hands over (HO-002) =====
  const w = await ctxPage(browser);
  await w.goto("/overseas/contact");
  await w.waitForTimeout(1500);
  await w.fill("#overseas-enquiry-name", CHEN.name);
  await w.fill("#overseas-enquiry-email", CHEN.email);
  await w.fill("#overseas-enquiry-phone", CHEN.phone);
  await w.fill("#overseas-enquiry-subject", "Masters in Australia");
  await w.fill("#overseas-enquiry-message", "I would like a callback about a Masters in Data Science in Australia for 2027.");
  const cform = w.locator("form", { has: w.locator("#overseas-enquiry-name") });
  await shoot(w, "handoffs", "03-website-enquiry-form.png", { root, center: cform });
  await cform.getByRole("button", { name: "Book counseling callback" }).click();
  await w.waitForTimeout(2000);
  await say(w, "HO-002 website enquiry sent");
  await shoot(w, "handoffs", "04-website-enquiry-sent.png", { root, center: cform });

  // Distribution assigns the website lead to an Overseas telecaller automatically.
  await t.goto("/telecaller/leads");
  await t.waitForTimeout(1500);
  console.log(`VERIFY HO-002 telecaller list: ${await text(t.locator("main"))}`);
  await shoot(t, "handoffs", "05-website-lead-in-telecaller-list.png", { root });
  await t.getByRole("link", { name: CHEN.name }).first().click().catch(async () => t.getByText(CHEN.name).first().click());
  await t.waitForURL(/\/telecaller\/leads\/(?!new)[^/]+$/);
  await t.waitForTimeout(1200);
  ids.chen = leadId(t);
  await t.getByRole("button", { name: "Assign to counselor" }).click();
  await t.waitForTimeout(800);
  const cf = t.locator("form", { has: t.getByLabel("Counselor") });
  await cf.getByLabel("Counselor").selectOption({ label: "Docs Counselor A" });
  await cf.getByRole("button", { name: "Hand over" }).click();
  await t.waitForTimeout(1500);
  await say(t, "HO-002 chen handed over");

  // ===== Counselor A =====
  const c = await ctxPage(browser);
  await signIn(c, A, "test", /\/overseas\/counselor\/dashboard/);

  // LEAD-002 walk-in lead (Divya), and the duplicate panel (Asha's mobile).
  await c.goto("/overseas/counselor/leads");
  await c.waitForTimeout(1500);
  await c.getByRole("link", { name: "New walk-in lead" }).or(c.getByRole("button", { name: "New walk-in lead" })).first().click();
  await c.waitForURL(/\/leads\/new/);
  await c.waitForTimeout(1500);
  console.log(`VERIFY LEAD-002 form: ${await text(c.locator("main"))}`);
  console.log(`VERIFY LEAD-002 source preset: ${await c.locator("#new-source").inputValue()}`);
  await shoot(c, "leads", "05-new-walk-in-lead-empty.png", { root });
  const d = LEAD("divya");
  await newLead(c, d, "/overseas/counselor/leads");
  await shoot(c, "leads", "06-new-walk-in-lead-filled.png", { root, element: c.locator("form").filter({ has: c.locator("#new-name") }) });
  await c.getByRole("button", { name: "Create lead" }).click();
  await c.waitForURL(/\/overseas\/counselor\/leads\/(?!new)[^/]+$/);
  await c.waitForTimeout(1500);
  ids.divya = leadId(c);
  console.log(`VERIFY LEAD-002 created: ${await text(c.locator("main"))}`);
  const a = LEAD("asha");
  await newLead(c, { ...a, name: "Docs Lead Asha Again" }, "/overseas/counselor/leads");
  await c.locator("#new-email").fill("");
  await c.getByRole("button", { name: "Create lead" }).click();
  await c.waitForTimeout(2000);
  console.log(`VERIFY LEAD-002 duplicate: ${await text(c.locator("main"))}`);
  await toTop(c.getByText("Lead already exists").first(), 120).catch(() => {});
  await shoot(c, "leads", "07-new-walk-in-lead-duplicate.png", { root });

  // LEAD-001 My leads list + filters.
  await c.goto("/overseas/counselor/leads");
  await c.waitForTimeout(1800);
  console.log(`VERIFY LEAD-001 list: ${await text(c.locator("main"))}`);
  await shoot(c, "leads", "01-my-leads.png", { root });
  await c.getByLabel("Priority").selectOption({ label: "Hot" });
  await c.waitForTimeout(1500);
  await shoot(c, "leads", "02-my-leads-filter-priority.png", { root });
  await c.goto("/overseas/counselor/leads");
  await c.waitForTimeout(1500);
  await c.getByLabel("Stage").selectOption({ label: "Lost" });
  await c.waitForTimeout(1500);
  await say(c, "LEAD-001 empty filter");
  await shoot(c, "leads", "03-my-leads-no-match.png", { root });

  // LEAD-003 Asha detail layout.
  await c.goto(`/overseas/counselor/leads/${ids.asha}`);
  await c.waitForTimeout(2000);
  console.log(`VERIFY LEAD-003 detail: ${await text(c.locator("main"))}`);
  await shoot(c, "leads", "08-lead-detail-top.png", { root });
  await shoot(c, "leads", "09-lead-detail-full.png", { root, fullPage: true });

  // CONV-001 hint before Qualified.
  const link = sec(c, "lead-link-heading");
  console.log(`VERIFY CONV-001 hint: ${await text(link)}`);
  await shoot(c, "conversion", "01-convert-hint-not-qualified.png", { root, element: link });

  // LEAD-006 move to Qualified without a next action -> refused.
  const stage = sec(c, "lead-stage-heading");
  await stage.getByRole("button", { name: "Change stage" }).click();
  console.log(`VERIFY LEAD-006 options: ${JSON.stringify(await stage.locator("select").first().locator("option").allInnerTexts())}`);
  await stage.locator("select").first().selectOption({ label: "Qualified" });
  await stage.getByRole("button", { name: "Save" }).click();
  await c.waitForTimeout(1200);
  await say(c, "LEAD-006 no next action");
  await shoot(c, "leads", "13-stage-needs-next-action.png", { root, center: stage });
  await stage.getByRole("button", { name: "Cancel" }).click().catch(() => {});

  // LEAD-005 next action: past date refused, then saved.
  const na = sec(c, "lead-next-action-heading");
  await na.getByRole("button", { name: /Set next action|Edit next action/ }).click();
  await na.getByLabel("Action", { exact: true }).fill("Send the university shortlist");
  await na.getByLabel("Due date", { exact: true }).fill(ist(-1));
  await na.getByRole("button", { name: "Save next action" }).click();
  await c.waitForTimeout(1200);
  await say(c, "LEAD-005 past date");
  await shoot(c, "leads", "10-next-action-past-date.png", { root, center: na });
  await na.getByLabel("Due date", { exact: true }).fill(ist(2));
  await na.getByRole("button", { name: "Save next action" }).click();
  await c.waitForTimeout(1200);
  await say(c, "LEAD-005 saved");
  await shoot(c, "leads", "11-next-action-saved.png", { root, center: na });

  // LEAD-006 Asha -> Qualified.
  await stage.getByRole("button", { name: "Change stage" }).click();
  await stage.locator("select").first().selectOption({ label: "Qualified" });
  await shoot(c, "leads", "12-change-stage-qualified.png", { root, center: stage });
  await stage.getByRole("button", { name: "Save" }).click();
  await c.waitForTimeout(1500);
  await say(c, "LEAD-006 qualified");
  await shoot(c, "leads", "14-stage-updated.png", { root });

  // LEAD-004 details edit.
  const det = sec(c, "lead-details-heading");
  await det.getByRole("button", { name: "Edit details" }).click();
  await det.getByLabel("Preferred contact method").selectOption({ label: "WhatsApp" });
  await det.getByLabel("Marketing consent").selectOption({ index: 1 });
  await det.getByLabel("Referred by (name)").fill("Docs Referrer");
  await shoot(c, "leads", "17-lead-details-edit.png", { root, element: det });
  await det.getByRole("button", { name: "Save details" }).click();
  await c.waitForTimeout(1200);
  await say(c, "LEAD-004 saved");
  await shoot(c, "leads", "18-lead-details-saved.png", { root, element: sec(c, "lead-details-heading") });

  // LEAD-007 qualification.
  const q = c.getByRole("heading", { name: "Qualification", exact: true }).locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ')][1]");
  await q.getByRole("button", { name: "Edit qualification" }).click();
  await c.waitForTimeout(500);
  console.log(`VERIFY LEAD-007 form: ${await text(q)}`);
  await q.getByLabel("Qualification", { exact: true }).fill("B.Tech Computer Science").catch(() => console.log("VERIFY LEAD-007 no Qualification field"));
  await q.getByLabel("Passing year").fill("2025").catch(() => {});
  await q.getByLabel("Preferred course").fill("MSc Data Science").catch(() => {});
  await q.getByLabel("Academic percentage").fill("78").catch(() => {});
  await q.getByLabel("Passport status").selectOption({ index: 3 }).catch(() => {});
  await shoot(c, "leads", "19-qualification-edit.png", { root, element: q });
  await q.getByRole("button", { name: "Save qualification" }).click();
  await c.waitForTimeout(1500);
  await say(c, "LEAD-007 saved");
  await shoot(c, "leads", "20-qualification-saved.png", { root, element: q });

  // CONV-001 convert Asha.
  await link.getByRole("button", { name: "Convert to student" }).click();
  await c.waitForTimeout(500);
  await shoot(c, "conversion", "02-convert-form.png", { root, element: link });
  await link.getByRole("button", { name: "Create student account" }).click();
  await c.waitForTimeout(2500);
  await say(c, "CONV-001 converted");
  await shoot(c, "conversion", "03-converted.png", { root, center: link });
  const ms = c.getByRole("heading", { name: "Student and milestones" }).locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ')][1]");
  console.log(`VERIFY LEAD-009 milestones: ${await text(ms)}`);
  await shoot(c, "leads", "23-student-and-milestones.png", { root, element: ms });
  console.log(`VERIFY CONV-001 stage now: ${await text(c.locator("main").locator("p,div").filter({ hasText: /^Stage:/ }).first())}`);

  // LEAD-006 Bilal: close as Not Interested with a lost reason.
  await c.goto(`/overseas/counselor/leads/${ids.bilal}`);
  await c.waitForTimeout(1800);
  const bs = sec(c, "lead-stage-heading");
  await bs.getByRole("button", { name: "Change stage" }).click();
  await bs.locator("select").first().selectOption({ label: "Not Interested" });
  await c.waitForTimeout(800);
  const reasons = await bs.getByLabel(/Lost reason/).locator("option").allInnerTexts();
  console.log(`VERIFY LEAD-006 lost reasons: ${JSON.stringify(reasons)}`);
  await bs.getByLabel(/Lost reason/).selectOption({ index: 1 });
  await bs.getByLabel(/Lost to/).fill("Another consultancy");
  await bs.getByLabel(/^Reason/).fill("Chose a local university instead.");
  await shoot(c, "leads", "15-close-not-interested.png", { root, element: bs });
  await bs.getByRole("button", { name: "Save" }).click();
  await c.waitForTimeout(1800);
  await say(c, "LEAD-006 closed");
  console.log(`VERIFY LEAD-006 closed page: ${await text(c.locator("main"))}`);
  await shoot(c, "leads", "16-closed-lead.png", { root });
  // P2: Return is still offered on the closed lead (shot only, not submitted).
  const ret = c.getByRole("button", { name: "Return to telecaller" });
  console.log(`VERIFY P2 return on closed lead visible: ${await ret.isVisible().catch(() => false)}`);
  if (await ret.isVisible().catch(() => false)) await shoot(c, "leads", "22-return-offered-on-closed-lead.png", { root, center: ret });

  // LEAD-008 return Esha.
  await c.goto(`/overseas/counselor/leads/${ids.esha}`);
  await c.waitForTimeout(1800);
  await c.getByRole("button", { name: "Return to telecaller" }).click();
  const rform = c.locator("form", { has: c.getByLabel("Reason for returning") });
  await rform.getByRole("button", { name: "Return lead" }).click();
  await c.waitForTimeout(800);
  await say(c, "LEAD-008 reason missing");
  await rform.getByLabel("Reason for returning").fill("Wants to study in Germany next year; telecaller to follow up in January.");
  await shoot(c, "leads", "21-return-to-telecaller.png", { root, center: rform });
  await rform.getByRole("button", { name: "Return lead" }).click();
  await c.waitForTimeout(1800);
  await say(c, "LEAD-008 returned");
  await shoot(c, "leads", "21b-returned.png", { root });

  // CONV-002 Divya: a walk-in student with the same email, then link and unlink.
  await c.goto("/overseas/counselor/students");
  await c.waitForTimeout(2000);
  await c.fill("#walk-in-full-name", "Docs Divya Student");
  await c.fill("#walk-in-email", d.email);
  await c.locator("form[aria-label='Add a walk-in student']").getByRole("button", { name: "Create account" }).click();
  await c.waitForTimeout(2000);
  await say(c, "setup Divya walk-in student");
  await c.goto(`/overseas/counselor/leads/${ids.divya}`);
  await c.waitForTimeout(2500);
  const dl = sec(c, "lead-link-heading");
  console.log(`VERIFY CONV-002 suggestions: ${await text(dl)}`);
  await shoot(c, "conversion", "04-link-suggestion.png", { root, element: dl });
  await dl.getByRole("button", { name: "Link Docs Divya Student" }).first().click();
  await c.waitForTimeout(500);
  await shoot(c, "conversion", "05-link-confirm.png", { root, element: dl });
  await dl.getByRole("button", { name: "Yes, link" }).click();
  await c.waitForTimeout(1800);
  await say(c, "CONV-002 linked");
  await shoot(c, "conversion", "06-linked.png", { root, element: sec(c, "lead-link-heading") });
  const dl2 = sec(c, "lead-link-heading");
  await dl2.getByRole("button", { name: "Unlink student" }).click();
  await c.waitForTimeout(500);
  await shoot(c, "conversion", "07-unlink-confirm.png", { root, element: dl2 });
  await dl2.getByRole("button", { name: "Yes, unlink" }).click();
  await c.waitForTimeout(1800);
  await say(c, "CONV-002 unlinked");
  // Search for Asha's converted student: already linked to another lead.
  const dl3 = sec(c, "lead-link-heading");
  await dl3.getByLabel("Search students").fill("Docs Lead Asha");
  await dl3.getByRole("button", { name: "Search" }).click();
  await c.waitForTimeout(1500);
  console.log(`VERIFY CONV-002 search: ${await text(dl3)}`);
  await shoot(c, "conversion", "08-search-already-linked.png", { root, element: dl3 });
  console.log(`VERIFY Divya stage after unlink: ${(await text(c.locator("main"))).slice(0, 200)}`);

  // Final list for the guide's overview.
  await c.goto("/overseas/counselor/leads");
  await c.waitForTimeout(1800);
  console.log(`VERIFY LEAD-001 final list: ${await text(c.locator("main"))}`);
  await shoot(c, "leads", "04-my-leads-after-work.png", { root });

  if (process.env.DOCS_CNS_FILE) {
    const data = JSON.parse(readFileSync(process.env.DOCS_CNS_FILE, "utf8"));
    writeFileSync(process.env.DOCS_CNS_FILE, JSON.stringify({ ...data, leads: ids }, null, 2));
  }
  console.log(`VERIFY lead ids ${JSON.stringify(ids)} password-ok ${password("test").length > 0}`);
});
