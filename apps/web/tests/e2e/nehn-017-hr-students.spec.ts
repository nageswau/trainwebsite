import { expect, test, type Page } from "@playwright/test";

// nehn-017 (DEC-SCOPE-310): HR's read-only student access. HR finds the seeded learner, opens their training (progress, completion,
// attendance) and their allowed documents only -- an ID proof uploaded beside the resume never shows -- downloads the HR attendance
// report (no money columns), and the pages hold at phone width.

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
const tag = `n017-${Date.now()}`;

async function signIn(page: Page, loginPath: string, email: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

/** The seeded learner uploads a resume and an ID proof (their own STU-011 route), so HR has one open and one closed document. */
async function uploadDocuments(page: Page) {
  await signIn(page, "/it/login", "student.it@edusphere.local");
  for (const [type, name] of [["Resume", `${tag}-cv.pdf`], ["ID proof", `${tag}-id.pdf`]]) {
    const stored = await page.request.post("/api/v1/files/local-upload", { multipart: { file: { name, mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n%%EOF\n") } } });
    expect(stored.ok()).toBeTruthy();
    const { url, size } = await stored.json();
    const created = await page.request.post("/api/v1/workflows/it/student/profile/documents", {
      data: { document_type: type, file_url: url, original_filename: name, content_type: "application/pdf", file_size: size },
    });
    expect(created.status()).toBe(201);
  }
}

test.describe("nehn-017 HR student access", () => {
  test("HR opens a learner's training and only the allowed documents", async ({ page }) => {
    await uploadDocuments(page);
    await signIn(page, "/it/login", "hr@edusphere.local");
    await page.locator("nav.portal-nav").getByRole("link", { name: "Students", exact: true }).click();
    await page.waitForURL("**/it/hr/students");
    await page.fill("#hr-student-q", "Arjun Rao");
    await page.getByRole("button", { name: "Search" }).click();
    await page.waitForURL("**q=Arjun**");
    await expect(page.getByRole("link", { name: "Arjun Rao" })).toHaveCSS("text-decoration-line", "underline"); // QA17-03: reads as a link
    await page.getByRole("link", { name: "Arjun Rao" }).click();
    await page.waitForURL(/\/it\/hr\/students\/[0-9a-f-]{36}$/);

    await expect(page.getByRole("heading", { name: "Arjun Rao" })).toBeVisible();
    const courses = page.getByRole("table", { name: "Courses" });
    await expect(courses.locator("thead th")).toHaveText(["Course", "Batch", "Trainer", "Status", "Progress", "Completed", "Certificate", "Attendance"]);
    await expect(courses.locator("tbody td[data-label='Batch']").first()).toBeVisible();
    await expect(courses.locator("tbody th[scope=row]").first()).toHaveCSS("text-transform", "none"); // QA17-01: a row header, not a column header
    await expect(courses.locator("tbody td[data-label='Attendance'] .nowrap").first()).toHaveCSS("white-space", "nowrap"); // QA17-05
    // QA17-06: the cell still wraps between the parts -- the whole table fits its card, nothing clipped
    expect(await page.locator(".table-wrap").first().evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
    await expect(courses.locator("tbody td[data-label='Attendance']").first()).toContainText(/Present \d+ · Late \d+ · Excused \d+ · Absent \d+|No classes marked yet/);
    await expect(page.locator("main")).not.toContainText(/fee|payment|discount|₹|INR/i);

    await expect(page.getByText(`${tag}-cv.pdf`)).toBeVisible();
    await expect(page.getByText(`${tag}-id.pdf`)).toHaveCount(0);
    // Headless Chromium downloads a PDF popup instead of showing it (its URL stays empty), so check the popup opened and the URL it got.
    const [popup, answer] = await Promise.all([
      page.waitForEvent("popup"),
      page.waitForResponse((r) => /\/hr\/students\/[^/]+\/documents\/[^/]+\/download$/.test(r.url())),
      page.getByRole("button", { name: `Download ${tag}-cv.pdf` }).click(),
    ]);
    expect(popup).toBeTruthy();
    const { url } = await answer.json();
    expect(url).toContain("/files/signed/");
    expect((await page.request.get(url)).headers()["content-type"]).toBe("application/pdf");
  });

  test("HR downloads the HR attendance report with no money columns", async ({ page }) => {
    await signIn(page, "/it/login", "hr@edusphere.local");
    await page.goto("/it/hr/report-library");
    for (const title of ["HR student progress", "HR completions", "HR attendance"]) await expect(page.locator("main").getByRole("link", { name: title, exact: true })).toBeVisible();
    await expect(page.locator("main").getByRole("link", { name: "Course-wise report", exact: true })).toHaveCount(0);
    await page.locator("main").getByRole("link", { name: "HR attendance", exact: true }).click();
    await page.waitForURL("**report=hr-attendance");
    await expect(page.locator("thead th")).toHaveText([
      "Student code", "Student", "Course", "Batch", "Trainer", "Classes marked", "Present", "Absent", "Late", "Excused", "Attendance %",
    ]);
    const [csv] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: "Download CSV" }).click()]);
    expect(csv.suggestedFilename()).toMatch(/^hr-attendance-\d{4}-\d{2}-\d{2}\.csv$/);
  });

  test("HR's Reports section and a student page hold at phone width", async ({ page }) => {
    await signIn(page, "/it/login", "hr@edusphere.local");
    await page.goto("/it/hr/reports");
    await expect(page.getByRole("heading", { name: "Placement Reports" })).toBeVisible();
    await page.setViewportSize({ width: 375, height: 800 });
    await page.goto("/it/hr/students?q=Arjun%20Rao");
    await page.getByRole("link", { name: "Arjun Rao" }).click();
    await expect(page.getByRole("table", { name: "Courses" })).toBeVisible();
    expect(await noSideScroll(page)).toBe(true);
    // QA17-07: on a tablet the eight columns stack (stack-wide) instead of clipping inside the card
    await page.setViewportSize({ width: 768, height: 1024 });
    await expect(page.locator("tbody td[data-label='Attendance']").first()).toBeInViewport();
    expect(await page.locator(".table-wrap").first().evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
  });

  test("a trainer is refused the HR students page", async ({ page }) => {
    await signIn(page, "/it/login", "trainer@edusphere.local");
    await page.goto("/it/hr/students");
    await expect(page.getByRole("heading", { name: "Access unavailable" })).toBeVisible();
    await expect(page.getByText("HR role required")).toBeVisible();
  });
});
