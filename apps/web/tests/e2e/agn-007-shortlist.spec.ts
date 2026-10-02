import { expect, test, type Page } from "@playwright/test";

import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";
import { E2E_PASSWORD } from "./helpers/welcome";

// AGN-007 -- a Master adds an agency university; Staff shortlist a catalogue entry and an agency entry; /public never shows the
// agency university; Staff get no write controls on Universities; 375 px. A fresh agency (the AGN-004 AC09 flow) keeps it independent
// of earlier runs; unique names per run (the E2E database is shared and keeps rows).
const MASTER_PASSWORD = "Sup3r-Secret-Pass!";
const stamp = () => Date.now() + Math.floor(Math.random() * 1e4);

async function addStudent(page: Page, name: string) {
  await page.getByRole("button", { name: "Add student", exact: true }).click();
  const form = page.getByRole("form", { name: "Add student" });
  await form.getByLabel("Full name (required)").fill(name);
  await form.getByRole("button", { name: "Save student" }).click();
  await expect(page.getByText(`${name} added.`)).toBeVisible();
}

test("Master adds a university; Staff shortlist catalogue and agency entries (AGN-007-AC01/02/05/06/13)", async ({ page, browser }) => {
  test.setTimeout(150_000);
  const id = stamp();
  const uniName = `E2E Agency Uni ${id}`;
  const student = `Shortlist Me ${id}`;
  const staffEmail = `agn007-s-${id}@example.local`;
  const masterEmail = await registerApprovedAgency(page, id, "agn007");

  // Master: a staff member, an agency university, and a student assigned to the staff member.
  await signIn(page, masterEmail, MASTER_PASSWORD);
  await page.goto("/overseas/agent/team");
  const staffForm = page.getByRole("form", { name: "Add a staff member" });
  await staffForm.getByLabel("Full name").fill("Upsilon Staff");
  await staffForm.getByLabel("Email").fill(staffEmail);
  await staffForm.getByRole("button", { name: "Add staff" }).click();
  const code = (await page.getByText(/-S001 created/).textContent())!.match(/(\S+-S001)/)![1];

  await page.goto("/overseas/agent/universities");
  await page.getByRole("button", { name: "Add university" }).click();
  const form = page.getByRole("form", { name: "Add university" });
  await form.getByLabel("Name (required)").fill(uniName);
  await form.getByLabel("Country (required)").fill("Atlantis");
  await form.getByRole("button", { name: "Save university" }).click();
  await expect(page.getByText(`${uniName} added.`)).toBeVisible();

  await page.goto("/overseas/agent/students");
  await addStudent(page, student);
  await page.getByRole("button", { name: `Assign ${student}`, exact: true }).click();
  const choice = page.getByRole("group", { name: `Assign ${student}` });
  await choice.getByLabel("Assign to").selectOption({ label: `${code} · Upsilon Staff` });
  await choice.getByRole("button", { name: "Save assignment" }).click();
  await expect(page.getByText(`${student} assigned to ${code} · Upsilon Staff.`)).toBeVisible();

  // A catalogue university that has a course: the seed adds courses only to an empty table, so look one up instead of assuming.
  const courses: { title: string; university: string }[] = await (await page.request.get("/api/v1/public/overseas-courses")).json();
  const unis: { name: string; city: string }[] = await (await page.request.get("/api/v1/public/universities")).json();
  const first = courses.find((c) => unis.some((u) => u.name === c.university))!;
  const catalogue = { label: `${first.university} — ${unis.find((u) => u.name === first.university)!.city}`, course: first.title };

  // Staff: view-only Universities; shortlist a catalogue entry and the agency entry from the student detail view.
  const staffPage = await (await browser.newContext()).newPage();
  await adminActivate(staffPage.request, staffEmail);
  await signIn(staffPage, staffEmail, E2E_PASSWORD);
  await staffPage.goto("/overseas/agent/universities");
  await expect(staffPage.getByRole("list", { name: "Agency universities" }).getByText(uniName)).toBeVisible();
  await expect(staffPage.getByRole("button", { name: "Add university" })).toHaveCount(0);
  await staffPage.goto("/overseas/agent/students");
  await staffPage.getByRole("button", { name: `View ${student}`, exact: true }).click();
  await staffPage.getByRole("button", { name: "Add university to shortlist" }).click();
  await staffPage.getByLabel("University (required)").selectOption({ label: catalogue.label });
  await staffPage.getByLabel("Course").selectOption({ label: catalogue.course });
  await staffPage.getByRole("button", { name: "Save to shortlist" }).click();
  await expect(staffPage.getByText("Saved to shortlist.")).toBeVisible();
  await staffPage.getByRole("button", { name: "Add university to shortlist" }).click();
  await staffPage.getByLabel("University (required)").selectOption({ label: `${uniName} — Atlantis` });
  await staffPage.getByLabel("Course").fill("BA Typed E2E");
  await staffPage.keyboard.press("Enter");
  await expect(staffPage.getByRole("list", { name: "Shortlist" }).getByText(uniName)).toBeVisible();

  // /public never shows it.
  const anon = await (await browser.newContext()).newPage();
  await anon.goto("/overseas/universities");
  await expect(anon.getByText(uniName)).toHaveCount(0);

  // 375 px: no horizontal scroll on the detail view.
  await staffPage.setViewportSize({ width: 375, height: 800 });
  const overflow = await staffPage.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
