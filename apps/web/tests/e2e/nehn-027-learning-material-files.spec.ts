import { expect, test, type Page } from "@playwright/test";

// nehn-027 (DEC-SCOPE-294): the trainer uploads a PDF to their batch, the enrolled student downloads it from Downloads, then the trainer
// renames and deletes it and it disappears for the student. Requires the stack with `python -m app.seed` (demo trainer + IT student).

const PDF = Buffer.from("%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n", "binary");

async function signIn(page: Page, email: string, home: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${home}`);
}

test("trainer uploads, renames and deletes a PDF; the enrolled student downloads it until then", async ({ page }) => {
  const title = `nehn-027 notes ${Date.now()}`;
  await signIn(page, "trainer@edusphere.local", "/it/trainer/dashboard");
  await page.goto("/it/trainer/materials");
  const form = page.getByRole("form", { name: "Publish course material" });
  await form.getByLabel("Batch").selectOption({ index: 1 });
  await form.getByLabel("Title").fill(title);
  await form.getByLabel("Upload a file").check();
  await form.getByLabel(/^File/).setInputFiles({ name: "week-notes.pdf", mimeType: "application/pdf", buffer: PDF });
  await form.getByRole("button", { name: "Publish material" }).click();
  await expect(page.getByText("Material published.")).toBeVisible();
  const item = page.getByRole("listitem").filter({ has: page.getByRole("heading", { name: title }) });
  await expect(item.getByText(/week-notes\.pdf · \d+ KB/)).toBeVisible();

  await signIn(page, "student.it@edusphere.local", "/it/student/dashboard");
  await page.goto("/it/student/downloads");
  const open = page.getByRole("link", { name: `Open ${title}` });
  await expect(open).toBeVisible();
  const href = await open.getAttribute("href");
  expect(href).toMatch(/^\/api\/v1\/workflows\/it\/materials\/[0-9a-f-]+\/file$/);
  const download = await page.request.get(href!);
  expect(download.status()).toBe(200);
  expect(Buffer.from(await download.body()).equals(PDF)).toBe(true);

  await signIn(page, "trainer@edusphere.local", "/it/trainer/dashboard");
  await page.goto("/it/trainer/materials");
  const batchValue = await page.getByRole("form", { name: "Publish course material" }).getByLabel("Batch").locator("option").nth(1).getAttribute("value");
  await page.getByLabel("Show batch").selectOption(batchValue!);
  await page.getByRole("button", { name: `Edit ${title}` }).click();
  const renamed = `${title} (v2)`;
  const edit = page.getByRole("form", { name: `Edit ${title}` });
  await edit.getByLabel("Title").fill(renamed);
  await edit.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Material updated.")).toBeVisible();
  await page.getByRole("button", { name: `Delete ${renamed}` }).click();
  await page.getByRole("button", { name: "Confirm delete" }).click();
  await expect(page.getByText("Material deleted. Students no longer see it.")).toBeVisible();
  await expect(page.getByRole("heading", { name: renamed })).toHaveCount(0);

  await signIn(page, "student.it@edusphere.local", "/it/student/dashboard");
  await page.goto("/it/student/downloads");
  await expect(page.getByText(renamed)).toHaveCount(0);
  expect((await page.request.get(href!)).status()).toBe(404);
});

test("an oversize file is refused in the browser with link guidance", async ({ page }) => {
  await signIn(page, "trainer@edusphere.local", "/it/trainer/dashboard");
  await page.goto("/it/trainer/materials");
  const form = page.getByRole("form", { name: "Publish course material" });
  await form.getByLabel("Batch").selectOption({ index: 1 });
  await form.getByLabel("Title").fill("Too big");
  await form.getByLabel("Upload a file").check();
  await form.getByLabel(/^File/).setInputFiles({ name: "huge.pdf", mimeType: "application/pdf", buffer: Buffer.alloc(21 * 1024 * 1024) });
  await form.getByRole("button", { name: "Publish material" }).click();
  await expect(page.locator(".form-error")).toContainText("larger than 20 MB");
  await expect(page.locator(".form-error")).toContainText("YouTube or Google Drive");
});
