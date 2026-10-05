import { readFileSync } from "node:fs";

import { expect, test, type Locator, type Page } from "@playwright/test";

import { password, shoot, signIn, toTop } from "./shoot";

// S4 (docs/documentation-plan.md): DOC-STU-001..009 and DOC-UNI-001, in the seeded agency "EduSphere Partner Agency".
// Runs after s3-team (needs staff Asha Staff = EDU-S001). Students documented as steps are created through the UI;
// paging filler students are created through the same API the page uses, in the Master's own session.
const STU = "students";
const UNI = "universities";
const FILLER = [
  "Aarav Mehta", "Diya Nair", "Ishaan Gupta", "Kavya Reddy", "Rohan Das", "Saanvi Iyer", "Vihaan Joshi", "Anika Rao",
  "Arjun Pillai", "Meera Kapoor", "Nikhil Verma", "Pooja Menon", "Rahul Bose", "Sneha Kulkarni", "Tanvi Shah",
  "Varun Chopra", "Zara Khan", "Aditya Sen", "Ira Banerjee", "Kabir Malhotra",
];
const staffEmail = (key: string) => {
  const file = process.env.DOCS_STAFF_FILE;
  if (file) return JSON.parse(readFileSync(file, "utf8"))[key] as string;
  throw new Error("Set DOCS_STAFF_FILE (written by the s3 run)");
};

const say = async (page: Page, what: string) => {
  const alerts = await page.locator('[role="alert"],[role="status"]').allInnerTexts();
  console.log(`VERIFY ${what}: ${JSON.stringify(alerts.map((a) => a.trim()).filter(Boolean))}`);
};
// Student cards: each button's accessible name is "<Action> <student name>"; the card heading is the name.
const btn = (page: Page, action: string, name: string) => page.getByRole("button", { name: `${action} ${name}`, exact: true });
const cardHeading = (page: Page, name: string) => page.getByRole("heading", { name, exact: true, level: 4 });
async function selectByText(select: Locator, text: string) {
  const value = await select.locator("option", { hasText: text }).first().getAttribute("value");
  await select.selectOption(value ?? "");
}

test("S4 students and universities", async ({ browser }) => {
  test.setTimeout(300_000);
  const ctx = await browser.newContext();
  const m = await ctx.newPage();
  m.on("dialog", (d) => d.accept());
  await signIn(m, "agent@edusphere.local");

  // --- DOC-UNI-001 agency universities (needed later on the shortlist) ---
  await m.goto("/overseas/agent/universities");
  await expect(m.getByText("Your agency hasn't added any universities yet.")).toBeVisible();
  await shoot(m, UNI, "01-universities-empty.png");
  await m.getByRole("button", { name: "Add university" }).click();
  await m.getByRole("button", { name: "Save university" }).click();
  await expect(m.getByText("Name is required.")).toBeVisible();
  await shoot(m, UNI, "02-university-validation.png");
  await m.getByLabel("Name (required)").fill("Northbridge University");
  await m.getByLabel("Country (required)").fill("United Kingdom");
  await m.getByLabel("City").fill("Leeds");
  await m.getByLabel("Entry requirements").fill("IELTS 6.5 overall (no band below 6.0)\nBachelor's degree with 60% or above");
  await shoot(m, UNI, "03-university-form.png");
  await m.getByRole("button", { name: "Save university" }).click();
  await expect(m.getByText("Northbridge University added.")).toBeVisible();
  await m.getByRole("button", { name: "Add university" }).click();
  await m.getByLabel("Name (required)").fill("Harbour Point College");
  await m.getByLabel("Country (required)").fill("Canada");
  await m.getByLabel("City").fill("Halifax");
  await m.getByRole("button", { name: "Save university" }).click();
  await expect(m.getByText("Harbour Point College added.")).toBeVisible();
  await shoot(m, UNI, "04-universities-list.png");

  // --- DOC-STU-002 add a student (validation, success, duplicate) ---
  await m.goto("/overseas/agent/students");
  await m.getByRole("button", { name: "Add student" }).first().click();
  await m.getByLabel(/^Full name/).fill("Ravi");
  await m.getByLabel(/^Email/).first().fill("ravi@example");
  await m.getByLabel(/^Phone/).first().fill("12");
  await m.getByLabel("Graduation year").fill("1900");
  await m.getByRole("button", { name: "Save student" }).click();
  await expect(m.getByText("Enter a valid email address")).toBeVisible();
  await toTop(m.getByRole("heading", { name: "Add student" }));
  await shoot(m, STU, "04-add-student-validation.png");
  await m.getByRole("button", { name: "Cancel" }).first().click();

  await m.getByRole("button", { name: "Add student" }).first().click();
  await m.getByLabel(/^Full name/).fill("Neha Sharma");
  await m.getByLabel("Date of birth").fill("2003-04-18");
  await m.getByLabel(/^Email/).first().fill("neha.sharma@example.test");
  await m.getByLabel(/^Phone/).first().fill("+91 98765 43210");
  await m.getByLabel("Highest qualification").fill("B.Tech Computer Science");
  await m.getByLabel("Institution").fill("Anna University");
  await m.getByLabel("Graduation year").fill("2025");
  await m.getByLabel("Preferred country").fill("United Kingdom");
  await m.getByLabel("Preferred course").fill("MSc Data Science");
  await m.getByLabel(/Preferred intake/).fill("Sep 2027");
  await m.getByLabel("Notes").fill("Met at the Chennai education fair. Prefers universities in the north of England.");
  await toTop(m.getByRole("heading", { name: "Add student" }));
  await shoot(m, STU, "03-add-student-form.png");
  await m.getByRole("button", { name: "Save student" }).click();
  await expect(m.getByText("Neha Sharma added.")).toBeVisible();
  await shoot(m, STU, "06-add-student-success.png");

  await m.getByRole("button", { name: "Add student" }).first().click();
  await m.getByLabel(/^Full name/).fill("Neha S.");
  await m.getByLabel(/^Email/).first().fill("neha.sharma@example.test");
  await m.getByRole("button", { name: "Save student" }).click();
  await expect(m.getByText("A student with this email or phone already exists in your agency")).toBeVisible();
  await toTop(m.getByRole("heading", { name: "Add student" }));
  await shoot(m, STU, "05-add-student-duplicate.png");
  await m.getByRole("button", { name: "Go back" }).click();
  await m.getByRole("button", { name: "Cancel" }).first().click();

  // Paging filler (same API as the page, Master session).
  for (const name of FILLER) {
    const r = await m.request.post("/api/v1/workflows/overseas/agent/crm/students", { data: { full_name: name } });
    expect(r.ok()).toBeTruthy();
  }

  // --- DOC-STU-001 find students ---
  await m.goto("/overseas/agent/students");
  await expect(m.getByText(/Showing 1–20 of \d+/)).toBeVisible();
  await shoot(m, STU, "01-students-list-master.png");
  await toTop(m.getByText(/Showing 1–20 of \d+/), 500);
  await shoot(m, STU, "08-students-pagination.png");
  await m.getByLabel("Search students").fill("zzzz");
  await expect(m.getByText("No students match.")).toBeVisible();
  await shoot(m, STU, "07-students-no-match.png");
  await m.getByRole("button", { name: "Clear filters" }).click();
  await m.getByLabel("Search students").fill("Neha");
  await expect(cardHeading(m, "Neha Sharma")).toBeVisible();

  // --- DOC-STU-003 view / edit ---
  await btn(m, "View", "Neha Sharma").click();
  await expect(m.getByRole("heading", { name: "Counseling" })).toBeVisible();
  await toTop(m.getByRole("heading", { name: "Neha Sharma" }).first());
  await shoot(m, STU, "09-student-detail.png");
  await m.getByRole("button", { name: "Edit", exact: true }).first().click();
  await m.getByLabel(/^Phone/).first().fill("+91 98765 40000");
  await toTop(m.getByRole("heading", { name: /Edit Neha Sharma/ }));
  await shoot(m, STU, "10-student-edit.png");
  await m.getByRole("button", { name: "Save changes" }).click();
  await expect(m.getByText("Neha Sharma saved.")).toBeVisible();

  // --- DOC-STU-006 counseling ---
  await m.getByRole("button", { name: "Record counseling" }).click();
  await m.getByLabel("Counseling completed").check();
  await m.getByLabel("Career interest").fill("Data analytics in healthcare");
  await m.getByLabel("Course preference").fill("MSc Data Science");
  await m.getByLabel("Country preference").fill("United Kingdom");
  await m.getByLabel("Amount").fill("25,00,000.555");
  await m.getByRole("button", { name: "Save counseling" }).click();
  const cform = m.locator("form").filter({ has: m.getByLabel("Amount") });
  console.log(`VERIFY STU-006 budget error form text: ${(await cform.innerText()).replace(/\s+/g, " ")}`);
  await toTop(m.getByRole("heading", { name: "Counseling" }));
  await shoot(m, STU, "17-counseling-budget-error.png");
  await m.getByLabel("Amount").fill("2500000");
  await m.getByLabel("Remarks").fill("Strong maths background. Wants a one-year programme with a placement option.");
  await toTop(m.getByRole("heading", { name: "Counseling" }));
  await shoot(m, STU, "16-counseling-form.png");
  await m.getByRole("button", { name: "Save counseling" }).click();
  await expect(m.getByText("Counseling saved for Neha Sharma.")).toBeVisible();
  await toTop(m.getByRole("heading", { name: "Counseling" }));
  await shoot(m, STU, "18-counseling-saved.png");

  // --- DOC-STU-007 shortlist ---
  await m.getByRole("button", { name: "Add university to shortlist" }).click();
  await selectByText(m.getByLabel("University (required)"), "University of Manchester");
  await expect(m.getByLabel("Course")).toBeVisible();
  const course = m.getByLabel("Course");
  const firstCourse = await course.locator("option").nth(1).getAttribute("value");
  if (firstCourse) await course.selectOption(firstCourse);
  await m.getByLabel("Intake").fill("September 2027");
  await toTop(m.getByRole("heading", { name: "University shortlist" }));
  await shoot(m, STU, "19-shortlist-form.png");
  await m.getByRole("button", { name: "Save to shortlist" }).click();
  await expect(m.getByText("Saved to shortlist.")).toBeVisible();
  await m.getByRole("button", { name: "Add university to shortlist" }).click();
  await selectByText(m.getByLabel("University (required)"), "Northbridge University");
  await m.getByLabel("Course").fill("MSc Applied Data Science").catch(() => {});
  await m.getByLabel("Intake").fill("January 2028");
  await m.getByLabel("Tuition fee").fill("GBP 21,500 per year");
  await m.getByRole("button", { name: "Save to shortlist" }).click();
  await expect(m.getByText("Saved to shortlist.")).toBeVisible();
  // Same university again (U7)
  await m.getByRole("button", { name: "Add university to shortlist" }).click();
  await selectByText(m.getByLabel("University (required)"), "Northbridge University");
  await m.getByRole("button", { name: "Save to shortlist" }).click();
  await m.waitForTimeout(1500);
  console.log(`VERIFY U7 same university twice accepted: ${await m.getByRole("button", { name: "Remove Northbridge University" }).count()} Northbridge entries`);
  await toTop(m.getByRole("heading", { name: "University shortlist" }));
  await shoot(m, STU, "20-shortlist-cards.png");
  await m.getByRole("button", { name: "Remove Northbridge University" }).last().click();
  await shoot(m, STU, "21-shortlist-remove-confirm.png");
  await m.getByRole("group", { name: "Confirm remove Northbridge University" }).getByRole("button", { name: "Confirm remove" }).click();
  await m.waitForTimeout(800);

  // --- DOC-STU-008 journey and history ---
  await toTop(m.getByRole("heading", { name: "Journey" }));
  await shoot(m, STU, "22-journey.png");
  await m.getByRole("button", { name: "Show history" }).click();
  await expect(m.getByText("Counseling saved").first()).toBeVisible();
  await toTop(m.getByRole("button", { name: "Hide history" }), 200);
  await shoot(m, STU, "23-history.png");
  await m.getByRole("button", { name: "Close" }).first().click();

  // --- DOC-STU-005 assign ---
  await btn(m, "Assign", "Neha Sharma").click();
  await selectByText(m.getByLabel("Assign to"), "Asha Staff");
  await toTop(cardHeading(m, "Neha Sharma"));
  await shoot(m, STU, "14-assign-control.png");
  await m.getByRole("button", { name: "Save assignment" }).click();
  await expect(m.getByText("Neha Sharma assigned to")).toBeVisible();
  await say(m, "STU-005 assigned");
  await shoot(m, STU, "15-assign-success.png");

  // --- DOC-STU-004 archive / unarchive ---
  await m.getByLabel("Search students").fill("Kabir");
  await btn(m, "Archive", "Kabir Malhotra").click();
  await toTop(cardHeading(m, "Kabir Malhotra"), 200);
  await shoot(m, STU, "12-archive-confirm.png");
  await m.getByRole("button", { name: "Confirm archive" }).click();
  await expect(m.getByText("Kabir Malhotra archived.")).toBeVisible();
  await m.getByLabel("Show archived").check();
  await expect(btn(m, "Unarchive", "Kabir Malhotra")).toBeVisible();
  await shoot(m, STU, "13-archived-shown.png");

  // --- DOC-STU-003 student with a login (read-only) ---
  await m.getByLabel("Show archived").uncheck();
  await m.getByLabel("Search students").fill("Ananya");
  await btn(m, "View", "Ananya Sharma").click();
  await expect(m.getByRole("heading", { name: "Counseling" })).toBeVisible();
  await toTop(m.getByRole("heading", { name: "Ananya Sharma" }).first());
  await shoot(m, STU, "11-student-with-login.png");
  console.log(`VERIFY STU-003 login student has Edit: ${await m.getByRole("button", { name: "Edit", exact: true }).count()}`);
  await m.getByRole("button", { name: "Close" }).first().click();

  // --- DOC-STU-009 link student (legacy) ---
  // A student who registered on EduSphere themselves (Account type "Student") can be linked to the agency.
  const reg = await browser.newContext();
  const rp = await reg.newPage();
  await rp.goto("/overseas/register");
  await rp.fill('input[name="full_name"]', "Farah Ali");
  await rp.fill('input[name="email"]', `docs.farah.${Date.now().toString().slice(-6)}@example.test`);
  await rp.selectOption('select[name="account_type"]', "student");
  await rp.fill('input[name="password"]', password("test"));
  await rp.click('button:has-text("Create account")');
  await rp.waitForURL(/overseas\/student/);
  await reg.close();
  await m.reload();
  const linkForm = m.locator("form").filter({ has: m.getByRole("button", { name: "Link student" }) }).last();
  const picker = linkForm.getByRole("combobox", { name: "Overseas student reference" });
  await picker.fill("Ananya");
  await m.waitForTimeout(1200);
  await toTop(m.getByRole("heading", { name: "Link student" }), 200);
  await linkForm.getByRole("button", { name: "Link student" }).click();
  await shoot(m, STU, "26-link-student-already-linked.png");
  await picker.fill("Farah");
  await m.waitForTimeout(1200);
  const options = linkForm.getByRole("option");
  console.log(`VERIFY STU-009 picker options: ${JSON.stringify(await options.allInnerTexts())}`);
  await toTop(m.getByRole("heading", { name: "Link student" }), 200);
  await shoot(m, STU, "24-link-student-picker.png");
  if (await options.count()) await options.first().click();
  await linkForm.getByRole("button", { name: "Link student" }).click();
  await m.waitForTimeout(1200);
  await say(m, "STU-009 link existing");
  await toTop(m.getByRole("heading", { name: "Link student" }), 200);
  await shoot(m, STU, "25-link-student-result.png");

  // --- DOC-UNI-001 delete in use ---
  await m.goto("/overseas/agent/universities");
  await m.getByRole("button", { name: "Delete Northbridge University" }).click();
  await shoot(m, UNI, "06-university-delete-confirm.png");
  await m.getByRole("group", { name: "Confirm delete Northbridge University" }).getByRole("button", { name: /^Confirm delete/ }).click();
  await m.waitForTimeout(1200);
  await say(m, "UNI-001 delete in use");
  await shoot(m, UNI, "07-university-in-use.png");
  await ctx.close();

  // --- Staff views ---
  const sctx = await browser.newContext();
  const s = await sctx.newPage();
  await signIn(s, staffEmail("a"), "test");
  await s.goto("/overseas/agent/students");
  await expect(cardHeading(s, "Neha Sharma")).toBeVisible();
  await shoot(s, STU, "02-students-list-staff.png");
  await s.goto("/overseas/agent/universities");
  await expect(s.getByText("Northbridge University")).toBeVisible();
  await shoot(s, UNI, "05-universities-staff.png");
  console.log(`VERIFY staff sees Add university: ${await s.getByRole("button", { name: "Add university" }).count()}`);
  await sctx.close();
});
