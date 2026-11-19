import { readFileSync } from "node:fs";
import path from "node:path";

import { test, type Locator, type Page } from "@playwright/test";

import { noPrefetch, REC_ROOT, shoot, signIn } from "../shoot";

// Recruitment CRM S8b (docs/recruitment-crm/documentation-plan.md): DOC-REC-CAN-003..010 on Docs Candidate Kiran. Runs after rec-s8a.
// WhatsApp opens wa.me, which is blocked: the send is only recorded. Email goes to Mailpit. The resume PDF is generated here.
const root = REC_ROOT;
const C = "candidates";
const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean).slice(-4))}`);
};
const text = async (l: Locator) => (await l.innerText()).replace(/\s+/g, " ").slice(0, 1800);
const settle = (p: Page, ms = 2000) => p.waitForTimeout(ms);
const sec = (p: Page, heading: string) =>
  p.getByRole("heading", { name: heading, exact: true }).first()
    .locator("xpath=ancestor::*[self::section or contains(concat(' ',@class,' '),' card ') or contains(concat(' ',@class,' '),' action-card ')][1]");
const plusDays = (n: number) => new Date(Date.now() + 5.5 * 3600_000 + n * 86_400_000).toISOString().slice(0, 10);
const fieldsOf = (l: Locator) => l.evaluate((el) => [...el.querySelectorAll("input, select, textarea")].map((e) => {
  const f = e as HTMLInputElement;
  return (f.id ? document.querySelector(`label[for="${CSS.escape(f.id)}"]`)?.textContent?.trim() : "") || f.getAttribute("aria-label") || f.name;
}));
async function step(name: string, fn: () => Promise<void>) {
  try { await fn(); } catch (e) { console.log(`STEP FAILED ${name}: ${String(e).split("\n")[0].slice(0, 300)}`); }
}
async function pick(p: Page, scope: Locator, name: string | RegExp, typed: string, option: RegExp) {
  const box = scope.getByRole("combobox", { name });
  await box.click();
  await box.fill(typed);
  await settle(p, 1500);
  await p.getByRole("option", { name: option }).first().click();
  await settle(p, 500);
}

const RESUME = `<html><body style="font-family:Arial;margin:40px">
<h1>Docs Candidate Kiran</h1><p>Email: docs.cand.kiran@example.com · Mobile: +91 90000 40001 · Hyderabad, India</p>
<h2>Summary</h2><p>Python developer with 2.5 years building REST APIs with FastAPI and Django.</p>
<h2>Skills</h2><p>Python, FastAPI, Django, SQL, PostgreSQL, Docker, Git</p>
<h2>Experience</h2><p>Software Engineer, Docs Orbit Softech, Hyderabad — Jun 2023 to present. Built FastAPI services and PostgreSQL schemas.</p>
<h2>Education</h2><p>B.Tech, Computer Science, Docs Institute of Technology, 2023</p>
</body></html>`;

test("Recruitment CRM S8b candidate page", async ({ browser }) => {
  test.setTimeout(1_500_000);
  const ids = JSON.parse(readFileSync(process.env.DOCS_REC_FILE!, "utf8"));
  const files = process.env.DOCS_FILES_DIR!;
  const resume = path.join(files, "docs-kiran-resume.pdf");
  const ctx = await browser.newContext();
  await noPrefetch(ctx);
  await ctx.route(/(wa\.me|whatsapp\.com)/, (r) => r.abort());
  const gen = await ctx.newPage();
  await gen.setContent(RESUME);
  await gen.pdf({ path: resume, format: "A4" });
  await gen.close();

  const a = await ctx.newPage();
  a.on("dialog", (d) => { console.log(`VERIFY dialog: ${d.message()}`); void d.accept(); });
  await signIn(a, "docs.rec.a@example.test", "test", /\/recruiter\/dashboard/, "/it/login");
  const url = `/recruiter/candidates/${ids.candidates.kiran}`;
  const open = async () => { await a.goto(url); await settle(a, 3500); };
  await open();
  await shoot(a, C, "07-candidate-page.png", { root });

  // ===== CAN-003 edit (notice period + education) =====
  await step("CAN-003 edit", async () => {
    await a.locator("main").getByRole("button", { name: "Edit", exact: true }).first().click();
    await settle(a, 1500);
    const form = a.locator("main form").first();
    await form.getByLabel("Notice period (days)").fill("30");
    await form.getByLabel("Willing to relocate").selectOption({ label: "Yes" });
    await form.getByLabel("Hybrid", { exact: true }).check();
    await form.getByLabel("Full time", { exact: true }).check();
    await form.getByRole("button", { name: "+ Add education" }).click();
    await settle(a, 800);
    const before = await fieldsOf(form);
    console.log("VERIFY CAN-003 edit fields:", JSON.stringify(before.filter((f) => /educ|degree|qualif|institut|college|year|course|special|grade|score/i.test(f ?? ""))));
    const tryFill = async (re: RegExp, v: string) => { const f = form.getByLabel(re).first(); if (await f.count()) { if ((await f.evaluate((e) => e.tagName)) === "SELECT") await f.selectOption({ index: 1 }); else await f.fill(v); } };
    await tryFill(/^(Degree|Qualification)/i, "B.Tech");
    await tryFill(/Speciali[sz]ation|Field|Branch/i, "Computer Science");
    await tryFill(/Institution|College|University/i, "Docs Institute of Technology");
    await tryFill(/(Passing|Graduation|Completion|End) year|^Year/i, "2023");
    await shoot(a, C, "08-edit-candidate.png", { root, element: form });
    await form.getByRole("button", { name: "Save changes" }).click();
    await settle(a, 3000);
    await say(a, "CAN-003 saved");
  });

  // ===== CAN-010 source, verification, outreach, permission =====
  await step("CAN-010", async () => {
    await open();
    const so = () => sec(a, "Source and outreach");
    await so().getByRole("button", { name: "Edit source details" }).click();
    await settle(a, 1000);
    await so().getByLabel("Portal import reference").fill("LinkedIn Recruiter search, Nov 2026");
    await shoot(a, C, "09-source-details-form.png", { root, element: so() });
    await so().getByRole("button", { name: "Save source details" }).click();
    await settle(a, 2500);
    await say(a, "CAN-010 source");
    await so().getByRole("button", { name: "Verify details" }).click();
    await settle(a, 2500);
    await say(a, "CAN-010 verified");
    await so().getByRole("button", { name: "Update outreach" }).click();
    await settle(a, 1000);
    await so().getByLabel("Outreach status").selectOption({ label: "Consented" });
    await settle(a, 800);
    console.log("VERIFY CAN-010 consent form:", await text(so()));
    await so().getByLabel("How they agreed").selectOption({ label: "Phone call" });
    await so().getByLabel("Date they agreed").fill(plusDays(0));
    await so().getByLabel("Note (optional)").fill("Agreed on the call to be put forward for Python roles.");
    await shoot(a, C, "10-outreach-consented.png", { root, element: so() });
    await so().getByRole("button", { name: "Save outreach" }).click();
    await settle(a, 2500);
    await say(a, "CAN-010 outreach");
    console.log("VERIFY CAN-010 card:", await text(so()));
    await shoot(a, C, "11-source-and-outreach.png", { root, element: so() });
  });

  // ===== CAN-005 skills and tags =====
  await step("CAN-005 skills", async () => {
    const sk = () => sec(a, "Skills");
    const add = async (name: string, typed: string, level: string, months: string, primary: boolean) => {
      await sk().getByRole("button", { name: "Add skill" }).click();
      await settle(a, 1000);
      const box = sk().getByRole("combobox", { name: /Skill/ });
      if (await box.count()) await pick(a, sk(), /Skill/, typed, new RegExp(`^${name}`));
      else await sk().getByLabel("Skill (required)").fill(name);
      await sk().getByLabel("Level (required)").selectOption({ label: level });
      await sk().getByLabel("Experience (months)").fill(months);
      await sk().getByLabel("Last used (year)").fill("2026");
      if (primary) await sk().getByLabel("Primary skill").check();
      if (primary) await shoot(a, C, "12-add-skill.png", { root, element: sk() });
      await sk().getByRole("button", { name: "Add", exact: true }).click();
      await settle(a, 2500);
      await say(a, `CAN-005 skill ${name}`);
    };
    await add("Python", "Pyth", "Advanced", "30", true);
    await add("Docs FastAPI", "Docs Fast", "Intermediate", "24", false);
    await add("SQL", "SQL", "Intermediate", "30", false);
    console.log("VERIFY CAN-005 skills:", await text(sk()));
    await shoot(a, C, "13-skills.png", { root, element: sk() });
  });
  await step("CAN-005 tags", async () => {
    const tg = () => sec(a, "Tags");
    await tg().getByRole("button", { name: "Edit tags" }).click();
    await settle(a, 1000);
    await tg().getByLabel("Docs Immediate joiner").check();
    await tg().getByRole("button", { name: "Save tags" }).click();
    await settle(a, 2500);
    await say(a, "CAN-005 tags");
    await shoot(a, C, "14-tags.png", { root, element: tg() });
  });

  // ===== CAN-006 resume =====
  await step("CAN-006 resume", async () => {
    await open();
    const rs = () => sec(a, "Resume");
    await rs().getByLabel("Upload resume").setInputFiles(resume);
    await rs().getByRole("button", { name: "Upload", exact: true }).click();
    await settle(a, 6000);
    await say(a, "CAN-006 upload");
    await open();
    console.log("VERIFY CAN-006 resume card:", await text(rs()));
    await shoot(a, C, "15-resume.png", { root, element: rs() });
    await rs().getByRole("button", { name: "Review extracted details" }).click();
    await settle(a, 2500);
    console.log("VERIFY CAN-006 review:", await text(rs()));
    for (const f of await fieldsOf(rs())) console.log("VERIFY CAN-006 review field:", f);
    console.log("VERIFY CAN-006 review buttons:", JSON.stringify(await rs().locator("button").allInnerTexts()));
    await shoot(a, C, "15b-resume-review.png", { root, element: rs() });
  });

  // ===== CAN-007 documents =====
  await step("CAN-007 documents", async () => {
    const dc = () => sec(a, "Documents");
    await dc().getByLabel("Document to request").selectOption({ label: "Experience letter" });
    await dc().getByLabel("Note for the candidate (optional)").fill("Please share the experience letter from Docs Orbit Softech.");
    await dc().getByLabel("Due date (optional)").fill(plusDays(7));
    await dc().getByRole("button", { name: "Request document" }).click();
    await settle(a, 2500);
    await say(a, "CAN-007 request");
    await dc().getByLabel("Document type").selectOption({ label: "Certificate" });
    await dc().getByLabel("Title (optional)").fill("Docs Python certification");
    await dc().getByLabel("File", { exact: true }).setInputFiles(resume);
    await dc().getByRole("button", { name: "Upload document" }).click();
    await settle(a, 3000);
    await say(a, "CAN-007 upload");
    console.log("VERIFY CAN-007 card:", await text(dc()));
    await shoot(a, C, "16-documents.png", { root, element: dc() });
  });

  // ===== CAN-004 ownership =====
  await step("CAN-004 ownership", async () => {
    await open();
    const ow = () => sec(a, "Ownership");
    await ow().getByRole("button", { name: "Change ownership" }).click();
    await settle(a, 1000);
    await pick(a, ow(), "Placement officer", "Docs Placement", /Docs Placement Officer/);
    await pick(a, ow(), "Add a collaborator", "Docs Recruiter B", /Docs Recruiter B/);
    await shoot(a, C, "17-change-ownership.png", { root, element: ow() });
    await ow().getByRole("button", { name: "Save ownership" }).click();
    await settle(a, 2500);
    await say(a, "CAN-004 saved");
    console.log("VERIFY CAN-004 card:", await text(ow()));
    await shoot(a, C, "18-ownership.png", { root, element: ow() });
  });

  // ===== CAN-009 calls and messages =====
  await step("CAN-009 call", async () => {
    const cl = () => sec(a, "Calls");
    await cl().getByRole("button", { name: "Log call" }).click();
    await settle(a, 1000);
    await cl().getByLabel("Outcome (required)").selectOption({ label: "Connected" });
    await cl().getByLabel("Minutes").fill("6");
    await cl().getByLabel("Notes").fill("Interested in Python backend roles in Hyderabad. Can join in 30 days.");
    await cl().getByLabel("Next action").fill("Share the Docs Acme Python Developer JD");
    await shoot(a, C, "19-log-call.png", { root, element: cl() });
    await cl().getByRole("button", { name: "Save call" }).click();
    await settle(a, 2500);
    await say(a, "CAN-009 call");
    console.log("VERIFY CAN-009 calls:", await text(cl()));
  });
  await step("CAN-009 email", async () => {
    const ms = () => sec(a, "Messages");
    await ms().getByRole("button", { name: "Send email" }).click();
    await settle(a, 1000);
    await ms().getByLabel("Subject").fill("Python Developer role in Hyderabad");
    await ms().getByLabel("Message", { exact: true }).fill("Hi Kiran, thanks for the call. I will share the Python Developer JD shortly. Regards, Docs Recruiter A");
    await shoot(a, C, "20-send-email.png", { root, element: ms() });
    await ms().getByRole("button", { name: "Send email" }).last().click();
    await settle(a, 3000);
    await say(a, "CAN-009 email");
  });
  await step("CAN-009 whatsapp", async () => {
    const ms = () => sec(a, "Messages");
    await ms().getByRole("button", { name: "Send WhatsApp" }).click();
    await settle(a, 1000);
    await ms().getByLabel("Message", { exact: true }).fill("Hi Kiran, this is Docs Recruiter A from EduSphere. I have emailed you the role details.");
    await settle(a, 800);
    console.log("VERIFY CAN-009 whatsapp controls:", JSON.stringify(await ms().locator("a, button").allInnerTexts()));
    const popup = a.waitForEvent("popup", { timeout: 5000 }).catch(() => null);
    await ms().getByRole("link", { name: /Open WhatsApp/ }).click();
    const pg = await popup;
    if (pg) await pg.close();
    await settle(a, 1000);
    await shoot(a, C, "21-whatsapp-confirm.png", { root, element: ms() });
    await ms().getByRole("button", { name: "Yes, record as sent" }).click();
    await settle(a, 2000);
    await say(a, "CAN-009 whatsapp");
  });
  await step("CAN-009 linkedin", async () => {
    const ms = () => sec(a, "Messages");
    await ms().getByRole("button", { name: "LinkedIn message" }).click();
    await settle(a, 1000);
    await ms().getByLabel("What did you send on LinkedIn?").selectOption({ label: "Connection request" });
    await ms().getByRole("button", { name: "Log as sent" }).click();
    await settle(a, 2000);
    await say(a, "CAN-009 linkedin");
    await open();
    console.log("VERIFY CAN-009 messages:", await text(ms()));
    await shoot(a, C, "22-calls.png", { root, element: sec(a, "Calls") });
    await shoot(a, C, "23-messages.png", { root, element: ms() });
  });

  // ===== CAN-008 notes, tasks, timeline, change history =====
  await step("CAN-008 note", async () => {
    const nt = () => sec(a, "Notes");
    await nt().getByLabel("New note").fill("Strong FastAPI work. Prefers hybrid. Good fit for the Docs Acme Python Developer requirement.");
    await nt().getByRole("button", { name: "Add note" }).click();
    await settle(a, 2500);
    await say(a, "CAN-008 note");
    await shoot(a, C, "24-notes.png", { root, element: nt() });
  });
  await step("CAN-008 task", async () => {
    const tk = () => sec(a, "Tasks");
    await tk().getByRole("button", { name: "Add task" }).click();
    await settle(a, 1000);
    await tk().getByLabel("Type (required)").selectOption({ label: "Follow-up" });
    await tk().getByLabel("Title (required)").fill("Call Kiran after the JD is shared");
    await tk().getByLabel("Due date and time (IST, required)").fill(`${plusDays(2)}T11:00`);
    const asg = tk().getByRole("combobox", { name: /Assigned to/ });
    if (await asg.count()) await pick(a, tk(), /Assigned to/, "Docs Recruiter A", /Docs Recruiter A/);
    await shoot(a, C, "25-add-task.png", { root, element: tk() });
    await tk().getByRole("button", { name: "Add task" }).last().click();
    await settle(a, 2500);
    await say(a, "CAN-008 task");
    console.log("VERIFY CAN-008 tasks:", await text(tk()));
  });
  await step("CAN-008 history", async () => {
    await open();
    console.log("VERIFY CAN-003 header:", (await text(a.locator("main"))).slice(0, 700));
    await shoot(a, C, "26-profile-complete.png", { root, element: sec(a, "Profile") });
    await shoot(a, C, "27-timeline.png", { root, element: sec(a, "Timeline") });
    console.log("VERIFY CAN-008 timeline:", await text(sec(a, "Timeline")));
    await shoot(a, C, "28-change-history.png", { root, element: sec(a, "Change history") });
  });

  // ===== CAN-003 archive and restore (Meena) =====
  await step("CAN-003 archive", async () => {
    await a.goto(`/recruiter/candidates/${ids.candidates.meena}`);
    await settle(a, 3500);
    await a.locator("main").getByRole("button", { name: "Archive", exact: true }).first().click();
    await settle(a, 3000);
    await say(a, "CAN-003 archived");
    console.log("VERIFY CAN-003 archived page:", (await text(a.locator("main"))).slice(0, 400));
    await shoot(a, C, "29-archived.png", { root });
    await a.goto("/recruiter/candidates");
    await settle(a, 3000);
    await a.getByLabel("Show archived only").click();
    await settle(a, 1500);
    console.log("VERIFY CAN-003 archived checkbox:", await a.getByLabel("Show archived only").isChecked(), a.url());
    if (!a.url().includes("archiv")) await a.getByRole("button", { name: "Search" }).click();
    await settle(a, 2500);
    console.log("VERIFY CAN-003 archived list:", (await text(a.locator("main"))).slice(-500));
    await shoot(a, C, "30-archived-list.png", { root });
    await a.goto(`/recruiter/candidates/${ids.candidates.meena}`);
    await settle(a, 3500);
    const restore = a.locator("main").getByRole("button", { name: /Restore/ }).first();
    console.log("VERIFY CAN-003 restore button:", await restore.count());
    if (await restore.count()) {
      await restore.click();
      await settle(a, 3000);
      await say(a, "CAN-003 restored");
    }
  });
  await ctx.close();
});
