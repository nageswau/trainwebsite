import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// ccrm-005 (DEC-SCOPE-260): the spec §3 lead fields -- a telecaller creates an overseas lead with a contact preference, enquiry date,
// marketing consent and referral (LF1, LF4, LF5), changes the consent, and records the study, academic and English test answers with an
// expired IELTS (LF3); after the handover the counselor edits the referral and the qualification (LF7); another counselor is 404.
// Throwaway accounts; phone width has no sideways scroll.
test.describe.configure({ timeout: 240_000 });

async function signIn(page: Page, portal: "overseas" | "admin", email: string, password: string, landing: string) {
  await page.context().clearCookies();
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const noSideScroll = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);

test("lead contact, consent, referral and overseas qualification fields round-trip for the telecaller and the counselor", async ({ page }) => {
  const stamp = Date.now();
  await signIn(page, "admin", "superadmin@edusphere.local", "Demo@123", "/admin");
  const post = async (data: object) => {
    const response = await page.request.post("/api/v1/admin/users", { data });
    expect(response.status(), await response.text()).toBe(201);
    return response.json();
  };
  const manager = await post({ role: "telecaller_manager", division: "global", full_name: `E2E LF Manager ${stamp}`, email: `ccrm005-m-${stamp}@example.local` });
  const caller = await post({
    role: "telecaller", full_name: `E2E LF Telecaller ${stamp}`, email: `ccrm005-t-${stamp}@example.local`,
    telecaller_profile: { team: "overseas", employee_id: `LF-${stamp}`, reporting_manager_user_id: manager.id },
  });
  const counselor = await post({ role: "counselor", division: "overseas", full_name: `E2E LF Counselor ${stamp}`, email: `ccrm005-c-${stamp}@example.local` });
  const other = await post({ role: "counselor", division: "overseas", full_name: `E2E LF Other ${stamp}`, email: `ccrm005-o-${stamp}@example.local` });
  await page.request.post("/api/v1/auth/logout");
  for (const user of [caller, counselor, other]) await activateWithToken(page.request, user.development_welcome_token);

  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));
  page.on("pageerror", (e) => consoleErrors.push(e.message));

  // the telecaller creates the lead with the new fields
  await signIn(page, "overseas", caller.email, E2E_PASSWORD, "/telecaller/dashboard");
  const product = (await (await page.request.get("/api/v1/telecaller/products?group=overseas&active=true&limit=100")).json()).items[0];
  const name = `LF Lead ${stamp}`;
  await page.goto("/telecaller/leads/new");
  await page.getByLabel("Student name *").fill(name);
  await page.getByLabel("Mobile number *").fill(`8${String(Math.floor(Math.random() * 1e9)).padStart(9, "0")}`);
  await page.getByLabel("Product interest *").selectOption(product.id);
  await page.getByLabel("Lead source *").selectOption("walk_in");
  await page.getByLabel("Preferred contact method").selectOption("whatsapp");
  await page.getByLabel("Enquiry date").fill("2026-09-14");
  await page.getByLabel("Marketing consent").selectOption("yes");
  await page.getByLabel("Referred by (name)").fill("Priya Raman");
  await page.getByRole("button", { name: "Create lead" }).click();
  await page.waitForURL(/\/telecaller\/leads\/[0-9a-f-]{36}$/);
  const id = page.url().split("/").at(-1) as string;
  const details = page.getByRole("region", { name: "Lead details" });
  await expect(details.getByText("WhatsApp", { exact: true })).toBeVisible();
  await expect(details.getByText(/^Yes · /)).toBeVisible();
  await expect(details.getByText("Priya Raman")).toBeVisible();

  // consent changed to No
  await page.getByRole("button", { name: "Edit details" }).click();
  await page.getByLabel("Marketing consent").selectOption("no");
  await page.getByRole("button", { name: "Save details" }).click();
  await expect(page.getByText("Details saved.")).toBeVisible();
  await expect(details.getByText(/^No · /)).toBeVisible();

  // the overseas qualification: study mode, CGPA, backlogs and an expired IELTS
  const qualification = page.getByRole("region", { name: "Qualification" });
  await qualification.getByRole("button", { name: "Edit qualification" }).click();
  await page.getByLabel("Study mode").selectOption("full_time");
  await page.getByLabel("Preferred campus").fill("City campus");
  await page.getByLabel("CGPA (out of 10)").fill("8.2");
  await page.getByLabel("Backlogs").fill("1");
  await page.getByRole("button", { name: "Add English test" }).click();
  await page.getByLabel("English test 1 status").selectOption("taken");
  await page.getByLabel("English test 1 overall score").fill("6.5");
  await page.getByLabel("English test 1 test date").fill("2023-01-10");
  await page.getByLabel("English test 1 valid until").fill("2025-01-10");
  await page.getByRole("button", { name: "Save qualification" }).click();
  await expect(qualification.getByText("Qualification saved.")).toBeVisible();
  await expect(qualification.getByText("Expired")).toBeVisible();
  await expect(qualification.getByText("Full-time")).toBeVisible();
  const handed = await page.request.post(`/api/v1/telecaller/leads/${id}/handover`, { data: { counselor_id: counselor.id } });
  expect(handed.status(), await handed.text()).toBe(200);

  // the counselor edits the referral and the qualification of their lead
  await signIn(page, "overseas", counselor.email, E2E_PASSWORD, "/overseas/counselor/dashboard");
  await page.goto(`/overseas/counselor/leads/${id}`);
  await expect(page.getByRole("region", { name: "Qualification" }).getByText("Expired")).toBeVisible();
  await page.getByRole("button", { name: "Edit details" }).click();
  await page.getByLabel("Referrer's phone or email").fill("priya@example.com");
  await page.getByRole("button", { name: "Save details" }).click();
  await expect(page.getByText("Details saved.")).toBeVisible();
  await expect(page.getByText("Priya Raman · priya@example.com")).toBeVisible();
  const counselorQual = page.getByRole("region", { name: "Qualification" });
  await counselorQual.getByRole("button", { name: "Edit qualification" }).click();
  await page.getByLabel("Study mode").selectOption("part_time");
  await page.getByRole("button", { name: "Save qualification" }).click();
  await expect(counselorQual.getByText("Qualification saved.")).toBeVisible();
  await expect(counselorQual.getByText("Part-time")).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  expect(await noSideScroll(page)).toBe(true);
  expect(consoleErrors).toEqual([]);

  // another counselor cannot read or change it
  await signIn(page, "overseas", other.email, E2E_PASSWORD, "/overseas/counselor/dashboard");
  expect((await page.request.get(`/api/v1/counselor/leads/${id}/qualification`)).status()).toBe(404);
  expect((await page.request.patch(`/api/v1/counselor/leads/${id}`, { data: { contact_preference: "sms" } })).status()).toBe(404);
});
