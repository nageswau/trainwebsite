import { test, type Page } from "@playwright/test";

import { noPrefetch, signIn } from "../shoot";

// Counselor CRM S7 prep (set-up, not documented): the Overseas Admin adds Docs University (United Kingdom, agent-Master
// commission 10 %), publishes it, and adds Docs MSc Data Science (PG, course commission 12 %) and Docs MBA (PG). Owner D5:
// fictional commission values on Docs records only.
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
const dump = async (p: Page, what: string) => {
  const t = (await p.locator("main").innerText()).replace(/\s+/g, " ").slice(0, 2500);
  const controls = await p.locator("main button, main a.btn, main input, main select").evaluateAll((els) => els.map((e) => `${e.tagName}#${e.id}[${(e as HTMLInputElement).type ?? ""}] ${(e.getAttribute("aria-label") ?? e.textContent ?? "").trim().slice(0, 50)}`));
  console.log(`VERIFY ${what} :: ${t}\nCONTROLS ${JSON.stringify(controls)}`);
};

test("Counselor CRM S7a Docs University set-up", async ({ browser }) => {
  test.setTimeout(600_000);
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  const a = await ctx.newPage();
  await signIn(a, "overseasadmin@edusphere.local", "seed", /\/overseas\/admin\//);
  await a.goto("/partnership/universities/new");
  await a.waitForTimeout(2000);
  await a.fill("#uni-name", "Docs University");
  await a.fill("#uni-country", "United Kingdom");
  await a.waitForTimeout(1000);
  await a.getByRole("option", { name: /United Kingdom/ }).first().click().catch(() => console.log("VERIFY country option missing"));
  await a.fill("#uni-city", "Docs City");
  await a.getByLabel("PG").check().catch(() => {});
  await a.getByLabel("Percentage").check().catch(() => {});
  await a.fill("#agent-commission-percent", "10");
  await a.fill("#agent-commission-note", "Docs test value");
  await a.fill("#uni-overview", "Docs University is a fictional university used only for EduSphere documentation screenshots.");
  await a.getByRole("button", { name: "Add university" }).click();
  await a.waitForTimeout(3000);
  await say(a, "university created");
  console.log(`VERIFY url after create ${a.url()}`);
  const uniUrl = a.url();
  a.once("dialog", (d) => d.accept());
  await a.getByRole("button", { name: "Publish to catalogue" }).click();
  await a.waitForTimeout(2000);
  await say(a, "published");
  for (const [title, commission] of [["Docs MSc Data Science", "12"], ["Docs MBA", ""]] as const) {
    await a.click("#courses-add");
    await a.waitForTimeout(1000);
    const f = a.locator("form").filter({ has: a.locator("[id^='course-new-'][id$='-title']") }).first();
    await f.locator("[id$='-title']").fill(title);
    await f.locator("[id$='-level']").selectOption("PG");
    await f.locator("[id$='-category']").fill(title.includes("MBA") ? "Business & management" : "Data & analytics");
    await f.locator("[id$='-duration']").fill("1 year");
    await f.locator("[id$='-tuition_amount']").fill(title.includes("MBA") ? "30000" : "26000");
    await f.locator("[id$='-tuition_currency']").selectOption("GBP");
    await f.getByLabel("Sep").check().catch(() => {});
    if (commission) {
      await f.getByLabel("Percentage").check().catch(() => {});
      await f.locator("[id$='-agent-commission-percent']").fill(commission);
      await f.locator("[id$='-agent-commission-note']").fill("Docs test value");
    }
    await f.getByRole("button", { name: "Save course" }).click();
    await a.waitForTimeout(2000);
    await say(a, `course ${title}`);
  }
  await a.reload();
  await a.waitForTimeout(2000);
  const courses = (await a.locator("main").innerText()).replace(/\s+/g, " ");
  console.log(`VERIFY courses: ${courses.slice(courses.indexOf("Courses & programmes"), courses.indexOf("Courses & programmes") + 700)}`);
  console.log(`VERIFY uniUrl ${uniUrl}`);
});
