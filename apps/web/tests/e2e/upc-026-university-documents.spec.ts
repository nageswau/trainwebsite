import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// upc-026 (AC1, AC2, P1, N1, E1): a partnership manager uploads a fee structure PDF (shared with counsellors by default) and a commission
// agreement (always internal) from the university page, is refused an executable, adds a second version and downloads it; the Documents
// menu lists them; an overseas_admin sees only the fee structure (never the commission agreement); a counselor is refused; the pages fit
// a phone. Throwaway accounts via the real admin API.

const PDF = Buffer.from("%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");

async function signIn(page: Page, loginPath: string, email: string, password = E2E_PASSWORD) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(loginPath);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

async function setUp(page: Page, stamp: number) {
  await signIn(page, "/admin/login", "superadmin@edusphere.local", "Demo@123");
  const post = async (url: string, data: unknown) => {
    const response = await page.request.post(url, { data });
    expect(response.ok(), await response.text()).toBe(true);
    return response.json();
  };
  const head = await post("/api/v1/admin/users", { role: "partnership_head", division: "global", full_name: `E2E Head ${stamp}`, email: `upc026-h-${stamp}@example.local` });
  const manager = await post("/api/v1/admin/users", {
    role: "partnership_manager", full_name: `E2E Manager ${stamp}`, email: `upc026-m-${stamp}@example.local`,
    partnership_profile: { employee_id: `U26-${stamp}`, reporting_head_user_id: head.id },
  });
  const admin = await post("/api/v1/admin/users", { role: "overseas_admin", division: "overseas", full_name: `E2E Overseas Admin ${stamp}`, email: `upc026-a-${stamp}@example.local` });
  const counselor = await post("/api/v1/admin/users", { role: "counselor", division: "overseas", full_name: `E2E Counselor ${stamp}`, email: `upc026-c-${stamp}@example.local` });
  const countries = await (await page.request.get("/api/v1/lookups/countries?q=United%20Kingdom&limit=5")).json();
  const { university } = await post("/api/v1/partnership/universities", { name: `E2E Documents University ${stamp}`, country_id: countries.items[0].id, city: "London" });
  await post(`/api/v1/partnership/universities/${university.id}/assign`, { primary_manager_user_id: manager.id });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [manager, admin, counselor]) await activateWithToken(page.request, user.development_welcome_token);
  return { manager, admin, counselor, university };
}

async function upload(page: Page, kind: string, title: string, buffer = PDF, name = "file.pdf") {
  await page.getByRole("button", { name: "Upload document" }).click();
  await page.getByLabel("Kind (required)").selectOption(kind);
  await page.getByLabel("Title (required)").fill(title);
  await page.getByLabel("File (required)").setInputFiles({ name, mimeType: "application/pdf", buffer });
  await page.getByRole("button", { name: "Upload document" }).click();
}

test("documents are kept per university, versioned, and sliced for non-partnership readers", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const { manager, admin, counselor, university } = await setUp(page, stamp);
  const universityPage = `/partnership/universities/${university.id}`;

  // P1 + AC1: the owning manager uploads a fee structure; it is shareable by default.
  await signIn(page, "/overseas/login", manager.email);
  await page.goto(universityPage);
  const section = page.locator("section", { has: page.getByRole("heading", { name: "Documents" }) });
  await expect(section.getByText("No documents uploaded yet.")).toBeVisible();
  await page.getByRole("button", { name: "Upload document" }).click();
  await page.getByLabel("Kind (required)").selectOption("fee_structure");
  await expect(page.getByLabel("Visible to counsellors (shareable)")).toBeChecked();
  await page.getByRole("button", { name: "Cancel" }).click();
  await upload(page, "fee_structure", "Fee structure 2026-27", PDF, "fees.pdf");
  await expect(section.getByRole("status")).toHaveText("Document uploaded.");
  await expect(section.getByRole("link", { name: "Download Fee structure 2026-27" })).toBeVisible();

  // AC2: the commission agreement cannot be shared.
  await page.getByRole("button", { name: "Upload document" }).click();
  await page.getByLabel("Kind (required)").selectOption("commission_agreement");
  await expect(page.getByLabel("Visible to counsellors (shareable)")).toBeDisabled();
  await page.getByRole("button", { name: "Cancel" }).click();
  await upload(page, "commission_agreement", "Commission terms 2026");
  await expect(section.getByRole("link", { name: "Download Commission terms 2026" })).toBeVisible();

  // N1: an executable is refused, and the form keeps what was typed.
  await upload(page, "brochure", "Brochure", Buffer.concat([Buffer.from("MZ"), Buffer.alloc(64)]), "brochure.pdf");
  await expect(section.locator(".form-error[role=alert]")).toHaveText("Upload a PDF, Word, Excel, PowerPoint, JPEG or PNG file");
  await expect(page.getByLabel("Title (required)")).toHaveValue("Brochure");
  await page.getByRole("button", { name: "Cancel" }).click();

  // E1: a second version becomes current; the first stays downloadable; the download is named by code, kind and version.
  await page.getByRole("button", { name: "New version of Fee structure 2026-27" }).click();
  await page.getByLabel("New file (saves version 2)").setInputFiles({ name: "fees-v2.pdf", mimeType: "application/pdf", buffer: PDF });
  await page.getByRole("button", { name: "Upload version" }).click();
  await expect(section.getByRole("status")).toHaveText("Version 2 uploaded.");
  await expect(section.getByText("Earlier versions (1)")).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: "Download Fee structure 2026-27" }).click()]);
  expect(download.suggestedFilename()).toBe(`${university.university_code}-fee_structure-v2.pdf`);

  // The Documents menu lists both for the manager, and fits a phone.
  await page.getByRole("link", { name: "Documents", exact: true }).first().click();
  await expect(page.getByRole("heading", { name: "University documents" })).toBeVisible();
  await page.goto(`/partnership/documents?q=${stamp}`);
  await expect(page.locator("tbody tr")).toHaveCount(2);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
  await page.goto(universityPage);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0);
  await page.setViewportSize({ width: 1280, height: 800 });

  // AC2 + P1: overseas_admin sees the fee structure only, never the commission agreement, and cannot upload.
  await signIn(page, "/overseas/login", admin.email);
  await page.goto(universityPage);
  await expect(section.getByRole("link", { name: "Download Fee structure 2026-27" })).toBeVisible();
  await expect(page.getByText("Commission terms 2026")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Upload document" })).toHaveCount(0);
  await page.goto(`/partnership/documents?q=${stamp}`);
  await expect(page.locator("tbody tr")).toHaveCount(1);

  // A counselor has no access to the document centre (counselors read via upc-030).
  await signIn(page, "/overseas/login", counselor.email);
  await page.goto("/partnership/documents");
  await expect(page.getByText("University master access required")).toBeVisible();
});
