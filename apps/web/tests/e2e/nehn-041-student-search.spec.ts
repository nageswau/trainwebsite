import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

// nehn-041 (DEC-SCOPE-291): the unified Student search -- the header box, a phone in another format, one-click open, each admin's scope,
// the short-search message and the phone layout. The fixture is a fresh IT student with a unique phone, created by the Super Admin.

const PASSWORD = "Demo@123";

async function apiLogin(request: APIRequestContext, email: string, division: string) {
  const response = await request.post("/api/v1/auth/login", { data: { email, password: PASSWORD, division } });
  expect(response.ok()).toBeTruthy();
}

async function itStudent(request: APIRequestContext): Promise<{ name: string; email: string; code: string; digits: string }> {
  const tag = `${Date.now()}${Math.random().toString(36).slice(2, 6)}`;
  const digits = `7${String(Date.now()).slice(-9)}`;
  const email = `n041-${tag}@example.local`;
  const name = `Search QA ${tag}`;
  const created = await request.post("/api/v1/admin/users", { data: { email, full_name: name, role: "it_student", division: "it", phone: `+91 ${digits.slice(0, 5)} ${digits.slice(5)}` } });
  expect(created.status()).toBe(201);
  const rows = await (await request.get(`/api/v1/admin/users?q=${encodeURIComponent(email)}`)).json();
  return { name, email, code: rows[0].student_code, digits };
}

const group = (page: Page, name: RegExp) => page.getByRole("region", { name });

test("Super Admin finds a student by phone from the header box and opens them in one click (AC1, AC6)", async ({ page }) => {
  await apiLogin(page.request, "superadmin@edusphere.local", "global");
  const student = await itStudent(page.request);
  await page.goto("/admin/users");
  const box = page.getByRole("searchbox", { name: "Search students" });
  await box.fill(`0${student.digits.slice(0, 5)}-${student.digits.slice(5)}`);
  await box.press("Enter");
  await expect(page).toHaveURL(/\/admin\/student-search\?q=/);
  await expect(page.getByRole("heading", { name: "Student search" })).toBeVisible();
  const itGroup = group(page, /^IT students \(1\)$/);
  await expect(itGroup.getByText(`Student ID ${student.code}`)).toBeVisible();

  await page.reload();  // the search lives in the address
  await expect(itGroup.getByRole("link", { name: student.name })).toHaveCSS("text-decoration-line", "underline");  // QA-041-01
  await itGroup.getByRole("link", { name: student.name }).click();
  await expect(page).toHaveURL(new RegExp(`/admin/users\\?q=${student.code}$`));
  await expect(page.getByLabel("Search by name, email, role, or Student ID")).toHaveValue(student.code);
  await expect(page.getByLabel("Search by name, email, role, or Student ID")).toBeInViewport();  // QA-041-02
  await expect(page.getByText(student.email).first()).toBeVisible();
});

test("IT Admin sees IT students only; the Overseas Admin opens an overseas student's 360 (AC3, AC6)", async ({ browser }) => {
  const it = await browser.newPage();
  await apiLogin(it.request, "itadmin@edusphere.local", "it");
  await it.goto("/it/admin/student-search?q=student.overseas%40edusphere.local");
  await expect(it.getByRole("status")).toHaveText("No students you can see match “student.overseas@edusphere.local”.");
  await expect(it.getByLabel("Type")).toHaveCount(0);
  await it.close();

  const ov = await browser.newPage();
  await apiLogin(ov.request, "overseasadmin@edusphere.local", "overseas");
  await ov.goto("/overseas/admin/dashboard");
  await ov.getByRole("link", { name: "Student search", exact: true }).first().click();
  await expect(ov).toHaveURL(/\/overseas\/admin\/student-search$/);
  await ov.getByLabel("Student ID, name, phone, email or course").fill("student.overseas@edusphere.local");
  await ov.getByRole("button", { name: "Search" }).click();
  const card = group(ov, /^Overseas students \(1\)$/).getByRole("link");
  await expect(card).toHaveAttribute("href", /^\/overseas\/admin\/students\/[0-9a-f-]{36}$/);
  await card.click();
  await expect(ov).toHaveURL(/\/overseas\/admin\/students\/[0-9a-f-]{36}$/);
  await ov.close();
});

test("a too-short search is explained, not sent (AC5)", async ({ page }) => {
  await apiLogin(page.request, "superadmin@edusphere.local", "global");
  await page.goto("/admin/student-search?q=a");
  await expect(page.locator(".form-error")).toHaveText("Type at least 3 characters.");
  const api = await page.request.get("/api/v1/search/students?q=a");
  expect(api.status()).toBe(422);
});

test("phone layout: no sideways scroll, the header box gives way to the menu", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 800 });
  await apiLogin(page.request, "superadmin@edusphere.local", "global");
  await page.goto("/admin/student-search?q=edusphere.local");
  await expect(page.getByRole("heading", { name: "Student search" })).toBeVisible();
  await expect(page.getByRole("searchbox", { name: "Search students" })).toHaveCount(0);  // not on the search page itself
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  await page.goto("/admin/users");
  await expect(page.getByRole("searchbox", { name: "Search students" })).toBeHidden();
});
