import { readFile } from "node:fs/promises";
import { expect, request as playwrightRequest, test, type APIRequestContext, type Page } from "@playwright/test";
import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// ENH-028 -- bulk data entry (docs/superpowers/specs/2026-10-01-enh-028-bulk-data-entry-design.md, AC1/AC3/AC11/AC12).
// API-only setup on a throwaway Platinum school (like enh-027): two students, one Academic Team and one Psychometric Team member.
// The feature itself is driven through the real UI: download the pre-filled template, fill it, upload, read the row report.
const unique = Date.now();
const email = (who: string) => `enh028-e2e-${who}-${unique}@example.local`;
const baseURL = process.env.E2E_BASE_URL || "http://localhost:3000";
const names = [`Asha 028 ${unique}`, `Ravi 028 ${unique}`];

async function apiAs(address: string, password: string): Promise<APIRequestContext> {
  const api = await playwrightRequest.newContext({ baseURL });
  const res = await api.post("/api/v1/auth/login", { data: { email: address, password, division: "overseas" } });
  if (!res.ok()) throw new Error(`login ${address}: ${res.status()} ${await res.text()}`);
  return api;
}

async function signIn(page: Page, address: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/overseas/login");
  await page.fill("#login-email", address);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

async function downloadTemplate(page: Page): Promise<string[][]> {
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: /Download the pre-filled template/ }).click()]);
  const text = await readFile((await download.path()) as string, "utf-8");
  return text.trim().split(/\r?\n/).map((line) => line.split(","));
}

function csv(rows: string[][]): Buffer {
  return Buffer.from(rows.map((r) => r.join(",")).join("\n") + "\n");
}

test.describe.serial("ENH-028 bulk data entry", () => {
  test.beforeAll(async () => {
    test.setTimeout(120_000);
    const admin = await apiAs("overseasadmin@edusphere.local", "Demo@123");
    const school = await createAndActivate(admin, "/api/v1/overseas-admin/schools", { name: `E2E 028 School ${unique}`, coordinator_full_name: "E2E 028 Coordinator", coordinator_email: email("coord") });
    expect((await admin.patch(`/api/v1/overseas-admin/schools/${school.id}`, { data: { tier: "platinum" } })).ok()).toBeTruthy();
    for (const role of ["academic_team", "psychometric_team"]) {
      await createAndActivate(admin, "/api/v1/overseas-admin/school-staff", { role, full_name: `E2E 028 ${role}`, email: email(role), school_ids: [school.id] });
    }
    await admin.dispose();
    const coord = await apiAs(email("coord"), E2E_PASSWORD);
    for (const full_name of names) expect((await coord.post("/api/v1/school/students", { data: { full_name, grade_or_class: "Grade 9" } })).status()).toBe(201);
    await coord.dispose();
  });

  test("an Academic Team member uploads a class's marks and sees each row's outcome", async ({ page }) => {
    await signIn(page, email("academic_team"), "/school/academic-team/dashboard");
    await page.getByText("Bulk entry — results (CSV)").click();
    const template = await downloadTemplate(page);
    expect(template[0].slice(0, 6)).toEqual(["student_code", "student_name", "school_name", "academic_year", "term", "subject"]);
    expect(template.slice(1).map((r) => r[1]).sort()).toEqual([...names].sort());

    const subject = `Bulk Maths ${unique}`;
    const [, first, second] = template;
    const rows = [template[0], [...first.slice(0, 3), "2026", "Term 1", subject, "100", "88", "A", ""], [...second.slice(0, 3), "2026", "Term 1", subject, "100", "150", "", ""]];
    await page.setInputFiles("#bulk-results-file", { name: "marks.csv", mimeType: "text/csv", buffer: csv(rows) });
    await page.getByRole("button", { name: "Upload results" }).click();

    await expect(page.getByRole("heading", { name: "Upload result" })).toBeFocused();
    await expect(page.getByText("1 of 2 rows added, 1 rejected. Rows that succeeded are kept.")).toBeVisible();
    await expect(page.getByRole("cell", { name: "marks_obtained must not exceed max_marks" })).toBeVisible();
    // The Results list above refreshes: the accepted row is a Draft, the rejected one is not there.
    await expect(page.getByRole("cell", { name: new RegExp(subject) })).toHaveCount(1);
  });

  test("a wrong file is refused with a clear message and nothing is added", async ({ page }) => {
    await signIn(page, email("academic_team"), "/school/academic-team/dashboard");
    await page.getByText("Bulk entry — language classes (CSV)").click();
    await page.setInputFiles("#bulk-language-file", { name: "wrong.csv", mimeType: "text/csv", buffer: Buffer.from("name,age\nX,9\n") });
    await page.getByRole("button", { name: "Upload language classes" }).click();
    // Next.js's route announcer is also role="alert"; the panel's own alert is the .form-error box.
    await expect(page.locator(".form-error[role=alert]")).toHaveText("Missing required column: student_code");
  });

  test("a Psychometric Team member assigns a batch's assessments", async ({ page }) => {
    await signIn(page, email("psychometric_team"), "/school/psychometric-team/dashboard");
    await page.getByText("Bulk entry — assessments (CSV)").click();
    const template = await downloadTemplate(page);
    const type = `Aptitude ${unique}`;
    const rows = [template[0], ...template.slice(1).map((r) => [...r.slice(0, 3), type, ...Array(template[0].length - 4).fill("")])];
    await page.setInputFiles("#bulk-psychometric-file", { name: "assess.csv", mimeType: "text/csv", buffer: csv(rows) });
    await page.getByRole("button", { name: "Upload assessments" }).click();
    await expect(page.getByText("2 of 2 rows added. Rows that succeeded are kept.")).toBeVisible();
    // exact: each row's Actions cell is also named "… — <type>" by its "Record results" button.
    await expect(page.getByRole("cell", { name: type, exact: true })).toHaveCount(2);
  });

  test("the panel fits a 320 px screen", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 720 });
    await signIn(page, email("academic_team"), "/school/academic-team/dashboard");
    await page.getByText("Bulk entry — results (CSV)").click();
    await page.getByText("Column reference").first().click();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow).toBeLessThanOrEqual(1);
  });
});
