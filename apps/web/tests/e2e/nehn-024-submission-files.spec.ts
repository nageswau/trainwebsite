import { test, expect, type Page, type APIRequestContext } from "@playwright/test";

// nehn-024 (DEC-SCOPE-291) -- a student attaches files to a submission (picker, camera input on mobile), the batch trainer downloads
// them through the authorised route. Needs the stack running with `python -m app.seed` applied. Each test creates its own uniquely
// titled `file` assignment, so it never races other specs over the shared demo student.

const PDF_HEAD = "%PDF-1.4\n%âãÏÓ\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n";

async function loginAs(page: Page, email: string, dashboardPath: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${dashboardPath}`);
}

async function cookieHeader(page: Page) {
  const access = (await page.context().cookies()).find((c) => c.name === "edusphere_access")?.value;
  return { cookie: `edusphere_access=${access}` };
}

async function createFileAssignment(page: Page, request: APIRequestContext, title: string) {
  await loginAs(page, "trainer@edusphere.local", "/it/trainer/dashboard");
  const headers = await cookieHeader(page);
  const batchId = (await (await request.get("/api/v1/workflows/it/trainer/context", { headers })).json()).batches[0]?.id;
  const created = await request.post("/api/v1/workflows/it/trainer/assignments", {
    headers,
    data: { batch_id: batchId, title, description: "nehn-024 upload test.", due_date: new Date(Date.now() + 5 * 86_400_000).toISOString(), max_score: 100, assignment_type: "assignment", submission_type: "file", published: true },
  });
  expect(created.ok()).toBeTruthy();
  await page.context().clearCookies();
}

async function openSubmission(page: Page, title: string) {
  await loginAs(page, "student.it@edusphere.local", "/it/student/dashboard");
  await page.goto("/it/student/assignments");
  const card = page.locator(".card", { has: page.getByRole("heading", { name: title }) });
  await card.getByRole("button", { name: "Submit this work" }).click();
  await expect(card.getByText("Attach at least one file.")).toBeVisible();
  return card;
}

test("a student uploads a 3 MB PDF and the trainer downloads it (AC1)", async ({ page, request }) => {
  const title = `nehn-024 PDF ${Date.now()}`;
  await createFileAssignment(page, request, title);
  const card = await openSubmission(page, title);
  const pdf = Buffer.concat([Buffer.from(PDF_HEAD, "latin1"), Buffer.alloc(3 * 1024 * 1024, 48)]);
  await card.getByLabel("Choose files").setInputFiles({ name: "Week 1 answers.pdf", mimeType: "application/pdf", buffer: pdf });
  await expect(card.getByText("Week 1 answers.pdf")).toBeVisible();
  await card.getByRole("button", { name: "Submit", exact: true }).click();
  await expect(card.getByText("Submitted on time.")).toBeVisible({ timeout: 10_000 });
  await page.context().clearCookies();

  await loginAs(page, "trainer@edusphere.local", "/it/trainer/dashboard");
  await page.goto("/it/trainer/assignments");
  const select = page.getByLabel("Submitted work");
  const option = select.locator("option", { hasText: title });
  await select.selectOption(await option.getAttribute("value"));
  const link = page.getByRole("link", { name: "Download Week 1 answers.pdf (3.0 MB)" });
  await expect(link).toBeVisible();
  const href = await link.getAttribute("href");
  const download = await request.get(href!, { headers: await cookieHeader(page) });
  expect(download.status()).toBe(200);
  expect((await download.body()).length).toBe(pdf.length);
  expect((await request.get(href!, { headers: { cookie: "" } })).status()).toBe(401);
});

test("a 6 MB file is refused with a clear message before upload (AC2)", async ({ page, request }) => {
  const title = `nehn-024 big ${Date.now()}`;
  await createFileAssignment(page, request, title);
  const card = await openSubmission(page, title);
  await card.getByLabel("Choose files").setInputFiles({ name: "huge.pdf", mimeType: "application/pdf", buffer: Buffer.alloc(6 * 1024 * 1024, 48) });
  await expect(card.locator(".form-error[role=alert]")).toHaveText("huge.pdf is larger than 5 MB.");
  await expect(card.getByText("huge.pdf", { exact: true })).toHaveCount(0);
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("a photo from the camera input submits as an image (AC5)", async ({ page, request }) => {
    const title = `nehn-024 photo ${Date.now()}`;
    await createFileAssignment(page, request, title);
    const card = await openSubmission(page, title);
    const camera = card.getByLabel("Take a photo");
    await expect(camera).toHaveAttribute("capture", "environment");
    await camera.setInputFiles({ name: "page-1.jpg", mimeType: "image/jpeg", buffer: Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), Buffer.alloc(2048)]) });
    await card.getByRole("button", { name: "Submit", exact: true }).click();
    await expect(card.getByText("Submitted on time.")).toBeVisible({ timeout: 10_000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});
