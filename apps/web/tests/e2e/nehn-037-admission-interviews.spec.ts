import { test, expect } from "@playwright/test";

import { signIn } from "./helpers/agency";
import { E2E_PASSWORD, createAndActivate } from "./helpers/welcome";

// nehn-037 part 4 (DEC-SCOPE-296) -- AC3: the counselor records an admission interview, is stopped from giving a result before the
// date (I3), records the result of a past one; the student sees both, with the result after the date, on desktop and on a phone.
// Requires the stack running with `python -m app.seed` applied; the spec makes its own counselor, student and application.

const local = (offsetDays: number) => {
  const d = new Date(Date.now() + offsetDays * 86_400_000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T10:30`;
};

test("a counselor's admission interview and its result reach the student (nehn-037)", async ({ page, request }) => {
  test.setTimeout(120_000);
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  const unique = Date.now();
  const counselorEmail = `nehn037-cns-${unique}@example.local`;
  const studentEmail = `nehn037-s-${unique}@example.local`;
  const studentName = `Interview Student ${unique}`;

  expect((await request.post("/api/v1/auth/login", { data: { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" } })).ok()).toBeTruthy();
  const counselor = await createAndActivate(request, "/api/v1/admin/users", { email: counselorEmail, full_name: "Interview Counselor", role: "counselor", division: "overseas" });
  const student = await createAndActivate(request, "/api/v1/admin/users", { email: studentEmail, full_name: studentName, role: "overseas_student", division: "overseas" });
  expect((await request.put(`/api/v1/admin/users/${student.id}/counselor`, { data: { counselor_id: counselor.id } })).ok()).toBeTruthy();

  await signIn(page, counselorEmail, E2E_PASSWORD, "/overseas/counselor/dashboard");
  const universities = (await (await page.request.get("/api/v1/public/universities")).json()) as { id: string; name: string }[];
  const app = await page.request.post("/api/v1/workflows/overseas/applications", { data: { student_id: student.id, university_id: universities[0].id, intake: "Fall 2027" } });
  expect(app.status()).toBe(201);

  await page.goto("/overseas/counselor/applications");
  const card = page.locator(".action-card", { has: page.getByRole("heading", { name: "Evaluate Applications" }) }).locator(".card", { hasText: studentName }).first();
  await card.getByRole("button", { name: "Interviews", exact: true }).click();
  const panel = card.getByRole("region", { name: "Admission interviews" });
  await expect(panel.getByText("No admission interviews recorded yet.")).toBeVisible();

  // A future online interview: a result is refused before the date.
  await panel.getByRole("button", { name: "Add interview" }).click();
  await panel.getByLabel("Date and time").fill(local(7));
  await panel.getByLabel("Link or place").fill("https://meet.example.edu/nehn037");
  await panel.getByLabel("Note for the student").fill("Have your passport ready.");
  await panel.getByLabel("Result").selectOption("passed");
  await panel.getByRole("button", { name: "Save interview" }).click();
  await expect(panel.locator(".form-error")).toContainText("only after the interview date");
  await panel.getByLabel("Result").selectOption("");
  await panel.getByRole("button", { name: "Save interview" }).click();
  await expect(card.getByText("Interview saved.")).toBeVisible();
  await expect(panel.getByRole("link", { name: "https://meet.example.edu/nehn037" })).toBeVisible();

  // A past in-person interview, then its result.
  await panel.getByRole("button", { name: "Add interview" }).click();
  await panel.getByLabel("Date and time").fill(local(-2));
  await panel.getByLabel("Mode").selectOption("in_person");
  await panel.getByLabel("Link or place").fill("Main campus, Room 4");
  await panel.getByRole("button", { name: "Save interview" }).click();
  await expect(panel.locator("li")).toHaveCount(2);
  const past = panel.locator("li", { hasText: "Main campus, Room 4" });
  await past.getByRole("button", { name: "Edit interview" }).click();
  const editor = panel.getByRole("form", { name: "Edit the interview" }); // the row shows the form while it is edited
  await expect(editor.getByLabel("Link or place")).toHaveValue("Main campus, Room 4");
  await editor.getByLabel("Result").selectOption("passed");
  await editor.getByRole("button", { name: "Save interview" }).click();
  await expect(past.getByText("Passed", { exact: true })).toBeVisible();

  // Student: both interviews, the result on the past one, read-only.
  await page.request.post("/api/v1/auth/logout");
  await signIn(page, studentEmail, E2E_PASSWORD, "/overseas/student/dashboard");
  await page.goto("/overseas/student/applications");
  const mine = page.locator(".action-card", { has: page.getByRole("heading", { name: "My interviews" }) });
  await expect(mine.locator("li")).toHaveCount(2);
  await expect(mine.locator("li", { hasText: "Main campus, Room 4" }).getByText("Passed", { exact: true })).toBeVisible();
  const upcoming = mine.locator("li", { hasText: "Have your passport ready." });
  await expect(upcoming.getByText("Awaiting result")).toBeVisible();
  await expect(upcoming.getByText(universities[0].name)).toBeVisible();
  await expect(mine.getByRole("button")).toHaveCount(0);

  await page.setViewportSize({ width: 375, height: 800 });
  await page.reload();
  await expect(mine.locator("li")).toHaveCount(2);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  expect(consoleErrors).toEqual([]);
});
