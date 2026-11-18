import { readFileSync, writeFileSync } from "node:fs";

import { test, type Browser, type Locator, type Page } from "@playwright/test";

import { ITC_ROOT, noPrefetch, shoot, signIn } from "../shoot";

// IT Counselor CRM S4a (docs/it-counselor-crm/documentation-plan.md): DOC-ITC-HO-001, HO-002.
// Runs after itc-s3. Docs IT Telecaller creates five Docs IT leads; four go to Counselor A, Chirag to B; the
// Telecaller Manager then changes Chirag's counselor to A. Lead ids are saved in DOCS_ITC_FILE for S4b-S9.
const root = ITC_ROOT;
const HO = "handoffs";
const TEL = "docs.itc.telecaller@example.test";
export const LEADS = {
  arjun: { name: "Docs IT Lead Arjun", phone: "+91 90000 20101", email: "docs.itlead.arjun@example.test", priority: "hot", source: "instagram", counselor: "a" },
  bhavna: { name: "Docs IT Lead Bhavna", phone: "+91 90000 20102", email: "docs.itlead.bhavna@example.test", priority: "warm", source: "google", counselor: "a" },
  chirag: { name: "Docs IT Lead Chirag", phone: "+91 90000 20103", email: "docs.itlead.chirag@example.test", priority: "cold", source: "facebook", counselor: "b" },
  deepa: { name: "Docs IT Lead Deepa", phone: "+91 90000 20104", email: "docs.itlead.deepa@example.test", priority: "warm", source: "website", counselor: "a" },
  esha: { name: "Docs IT Lead Esha", phone: "+91 90000 20105", email: "docs.itlead.esha@example.test", priority: "hot", source: "referral", counselor: "a" },
} as const;
const NAMES = { a: "Docs IT Counselor A", b: "Docs IT Counselor B" };
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const istDate = (days = 0) => new Date(Date.now() + 5.5 * 3600_000 + days * 86_400_000).toISOString().slice(0, 10);
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 1500);
const leadId = (p: Page) => decodeURIComponent(new URL(p.url()).pathname.split("/").pop() ?? "");
const store = (): Record<string, unknown> => {
  try { return JSON.parse(readFileSync(process.env.DOCS_ITC_FILE!, "utf8")); } catch { return {}; }
};

async function ctxPage(browser: Browser) {
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  return ctx.newPage();
}

test("IT Counselor CRM S4a leads and handover", async ({ browser }) => {
  test.setTimeout(900_000);
  const ids: Record<string, string> = {};
  const t = await ctxPage(browser);
  await signIn(t, TEL, "test", /\/telecaller\//, "/it/login");

  for (const [key, l] of Object.entries(LEADS)) {
    await t.goto("/telecaller/leads/new");
    await t.waitForTimeout(1500);
    await t.fill("#new-name", l.name);
    await t.fill("#new-phone", l.phone);
    await t.fill("#new-email", l.email);
    await t.selectOption("#new-product_id", { label: "Python Full Stack" });
    await t.selectOption("#new-source", l.source);
    await t.selectOption("#new-priority", l.priority);
    await t.fill("#new-city", "Hyderabad");
    await t.fill("#new-qualification", "B.Tech");
    await t.getByRole("button", { name: "Create lead" }).click();
    await t.waitForURL(/\/telecaller\/leads\/(?!new)[^/]+$/);
    await t.waitForTimeout(1500);
    ids[key] = leadId(t);
    if (key === "esha") {
      // APPT-001 (telecaller side): the lead's telecaller books counselling BEFORE the handover; afterwards the telecaller cannot book.
      await t.getByRole("button", { name: "Book counselling" }).click();
      await t.waitForTimeout(1200);
      const bf = t.locator("form", { has: t.getByLabel("Date and time (IST)") });
      console.log(`VERIFY APPT-001 booking form: ${await text(bf)}`);
      await bf.getByLabel("Appointment type").selectOption({ label: "IT course counselling" });
      await bf.getByLabel("Counselor").selectOption({ label: NAMES.a });
      await bf.getByLabel("Purpose").fill("Course fit and batch timings");
      await bf.getByLabel("Date and time (IST)").fill(`${istDate(1)}T11:00`);
      await shoot(t, "appointments", "01-telecaller-book-counselling.png", { root, center: bf });
      await bf.getByRole("button", { name: "Book appointment" }).click();
      await t.waitForTimeout(2000);
      await say(t, "APPT-001 booked");
      console.log(`VERIFY APPT-001 after booking: ${await text(t.locator("main"))}`);
    }
    await t.getByRole("button", { name: "Assign to counselor" }).click();
    await t.waitForTimeout(800);
    const form = t.locator("form", { has: t.getByLabel("Counselor") });
    const counselor = form.getByLabel("Counselor");
    if (key === "arjun") console.log(`VERIFY HO-001 counselor options: ${JSON.stringify(await counselor.locator("option").allInnerTexts())}`);
    await counselor.selectOption({ label: NAMES[l.counselor] });
    if (key === "arjun") {
      console.log(`VERIFY HO-001 form: ${await text(form)}`);
      await shoot(t, HO, "01-telecaller-assign-counselor.png", { root, center: form });
    }
    await form.getByRole("button", { name: "Hand over" }).click();
    await t.waitForTimeout(1500);
    await say(t, `HO-001 handed over ${key}`);
    if (key === "arjun") {
      console.log(`VERIFY HO-001 after: ${await text(t.locator("main"))}`);
      await shoot(t, HO, "02-telecaller-handed-over.png", { root, center: t.getByText(`Handed over to ${NAMES.a}`).first() });
    }
  }
  await t.goto("/telecaller/leads");
  await t.waitForTimeout(1500);
  await shoot(t, HO, "03-telecaller-list-after-handover.png", { root });

  // ===== HO-002: Telecaller Manager changes Chirag's counselor B -> A =====
  const m = await ctxPage(browser);
  // A Telecaller Manager is a global account, so it signs in at the administration sign-in.
  await signIn(m, "telecaller.manager@edusphere.local", "seed", /\/telecaller\//, "/admin/login");
  await m.goto(`/telecaller/manager/leads/${ids.chirag}`);
  await m.waitForTimeout(2000);
  console.log(`VERIFY HO-002 manager lead page: ${await text(m.locator("main"))}`);
  const change = m.getByRole("button", { name: "Change counselor" });
  if (await change.count()) {
    await change.first().click();
    await m.waitForTimeout(800);
    const cform = m.locator("form", { has: m.getByLabel("Counselor") });
    await cform.getByLabel("Counselor").selectOption({ label: NAMES.a });
    console.log(`VERIFY HO-002 form: ${await text(cform)}`);
    await shoot(m, HO, "04-manager-change-counselor.png", { root, center: cform });
    await cform.getByRole("button", { name: "Hand over" }).click();
    await m.waitForTimeout(1500);
    await say(m, "HO-002 changed");
    console.log(`VERIFY HO-002 after: ${await text(m.locator("main"))}`);
    await shoot(m, HO, "05-manager-counselor-changed.png", { root, center: m.getByText(`Handed over to ${NAMES.a}`).first() });
  } else console.log("VERIFY HO-002 no Change counselor button");

  writeFileSync(process.env.DOCS_ITC_FILE!, JSON.stringify({ ...store(), leads: ids }, null, 2));
  console.log(`VERIFY ids ${JSON.stringify(ids)}`);
});
