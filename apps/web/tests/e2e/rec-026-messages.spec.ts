import { expect, test, type Page } from "@playwright/test";

// rec-026 (AC1-AC3; MS2, MS5, MS6): the seeded placement manager sees the seeded templates; the seeded recruiter sends a WhatsApp to a
// company contact (logged only on "Yes, record as sent") and an "Interview confirmation" email to a candidate (queued, then its status);
// a candidate without an email cannot be emailed. Needs the worker and SMTP (Mailpit) for the "Email sent" step.

async function signIn(page: Page, portal: "it" | "admin", email: string) {
  await page.context().clearCookies();
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((u) => !u.pathname.endsWith("/login"));
}

const messages = (page: Page) => page.locator("section").filter({ has: page.getByRole("heading", { name: "Messages", exact: true }) });

test("message templates, a WhatsApp to a contact and an email to a candidate", async ({ page }) => {
  test.setTimeout(120_000);
  // AC1: the 12 seeded kinds are in the manager's library.
  await signIn(page, "admin", "placement.manager@edusphere.local");
  await page.goto("/recruiter/manager/templates?channel=email");
  await expect(page.getByRole("cell", { name: "Joining confirmation" }).first()).toBeVisible();
  await page.getByRole("button", { name: "Preview Interview confirmation" }).first().click();
  await expect(page.getByRole("region", { name: "Preview of Interview confirmation" })).toContainText("Your interview with Acme Technologies is confirmed.");

  await signIn(page, "it", "placement@edusphere.local");
  const stamp = Date.now();
  const company = (await (await page.request.post("/api/v1/recruiter/companies", { data: { name: `E2E Rec026 ${stamp} Pvt` } })).json()).company;
  await page.request.post(`/api/v1/recruiter/companies/${company.id}/contacts`, { data: { name: "Meera Iyer", mobile: "98450 12345", email: `meera${stamp}@example.com` } });
  const source_id = (await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=1")).json()).items[0].id;
  const candidate = await (await page.request.post("/api/v1/recruiter/candidates", { data: { name: "Anita Rao", mobile: `8${String(stamp).slice(-9)}`, email: `anita${stamp}@example.com`, source_id } })).json();
  const noEmail = await (await page.request.post("/api/v1/recruiter/candidates", { data: { name: "Rahul Das", mobile: `9${String(stamp).slice(-9)}`, source_id } })).json();

  // AC3: WhatsApp to the contact -- nothing is logged until the recruiter confirms.
  await page.goto(`/recruiter/companies/${company.id}`);
  const box = messages(page);
  await box.getByRole("button", { name: "Send WhatsApp" }).click();
  await box.getByLabel("Template").selectOption({ label: "JD confirmation" });
  await expect(box.getByLabel("Message", { exact: true })).toHaveValue(/^Hi Meera Iyer, this is Kiran Placement from EduSphere\./);
  const link = box.getByRole("link", { name: /Open WhatsApp/ });
  expect(await link.getAttribute("href")).toMatch(/^https:\/\/wa\.me\/919845012345\?text=Hi%20Meera%20Iyer/);
  await link.evaluate((a) => a.addEventListener("click", (e) => e.preventDefault())); // stay on the page
  await link.click();
  await box.getByRole("button", { name: "Not sent" }).click();
  await expect(box.getByText("No messages sent yet.")).toBeVisible();
  await link.click();
  await box.getByRole("button", { name: "Yes, record as sent" }).click();
  await expect(box.getByText("WhatsApp to Meera Iyer recorded.")).toBeVisible();
  await expect(box.getByRole("list", { name: "Messages" }).getByRole("listitem")).toContainText(["WhatsApp sent"]);

  // AC2 / positive scenario: an "Interview confirmation" email to a candidate is queued, then delivered.
  await page.goto(`/recruiter/candidates/${candidate.id}`);
  const ebox = messages(page);
  await ebox.getByRole("button", { name: "Send email" }).click();
  await ebox.getByLabel("Template").selectOption({ label: "Interview confirmation" });
  await expect(ebox.getByText("Check the text: {company} has no value for this recipient.")).toBeVisible(); // MS2 / QA-02
  await ebox.getByLabel("Subject").fill("Interview confirmation – Acme");
  await ebox.getByRole("button", { name: "Send email" }).click();
  await expect(ebox.getByText("Email to Anita Rao queued for sending.")).toBeVisible();
  await expect(ebox.getByRole("list", { name: "Messages" }).getByRole("listitem").first()).toContainText("Email sent", { timeout: 30_000 });

  // Edge case: a candidate with no email.
  await page.goto(`/recruiter/candidates/${noEmail.id}`);
  await expect(messages(page).getByRole("button", { name: "Send email" })).toBeDisabled();
  await expect(messages(page).getByText("No email address for Rahul Das.")).toBeVisible();
});
