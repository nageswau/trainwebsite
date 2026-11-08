import { expect, test, type Page } from "@playwright/test";

// pob-028 (DEC-SCOPE-436; AC: each widget ties out to its drill-down; a PO with no activity sees zeros, not errors): the seeded placement team
// member adds a company at Outreach Sent, opens the PO dashboard tab narrowed to it and opens the figure's records. Every figure is compared with
// its records through the API the page reads.

async function signIn(page: Page, email: string, landing: string) {
  await page.context().clearCookies();
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

const PATH = "/recruiter/recruitment-dashboards";
const API = "/api/v1/recruiter/recruitment-dashboards";
type Payload = { sections: { key: string; figures: { key: string; label: string; value: number }[] }[] };

test("a PO opens the PO dashboard, narrows it to a company and every figure ties out", async ({ page }) => {
  test.setTimeout(180_000);
  const stamp = Date.now();
  const failed: string[] = [];
  page.on("response", (r) => r.url().includes("/api/v1/") && r.status() >= 500 && failed.push(r.url()));
  const consoleErrors: string[] = [];
  page.on("console", (m) => m.type() === "error" && consoleErrors.push(m.text()));

  await signIn(page, "placement@edusphere.local", "/recruiter/dashboard");
  const name = `E2E Pob028 ${stamp} Ltd`;
  const company = await page.request.post("/api/v1/recruiter/companies", { data: { name } });
  expect(company.ok(), await company.text()).toBeTruthy();
  const id = (await company.json()).company.id;
  const due = new Date(Date.now() - 2 * 86_400_000).toISOString();
  const followUp = await page.request.post(`/api/v1/recruiter/companies/${id}/follow-ups`, { data: { reason: "new_requirement", due_at: due } });
  expect(followUp.ok(), await followUp.text()).toBeTruthy();

  await page.goto(`${PATH}/funnel`);
  await page.getByRole("navigation", { name: "Recruitment dashboards" }).getByRole("link", { name: "PO dashboard" }).click();
  await page.waitForURL(`**${PATH}/po`);
  await expect(page.getByRole("heading", { name: "BD pipeline (now)" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Invoicing and collections (now)" })).toBeVisible();
  await page.getByLabel("Employer").selectOption({ label: name });
  await page.getByRole("button", { name: "Apply" }).click();
  await page.waitForURL(/employer=/);

  await page.getByRole("link", { name: /^Overdue: 1\./ }).click();
  await page.waitForURL(/drill=follow_ups_overdue/);
  await expect(page.getByRole("heading", { name: "Overdue: 1 record" })).toBeVisible();
  await page.getByRole("link", { name }).click();
  await page.waitForURL(`**/recruiter/companies/${id}`);

  const board = (await (await page.request.get(`${API}/po?employer=${id}`)).json()) as Payload;
  expect(board.sections.map((s) => s.key)).toContain("follow_ups");
  for (const figure of board.sections.flatMap((s) => s.figures)) {
    const drill = await (await page.request.get(`${API}/po/drill/${figure.key}?employer=${id}&limit=100`)).json();
    expect(drill.total, figure.key).toBe(figure.value);
  }

  for (const width of [768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`${PATH}/po?employer=${id}`);
    await expect(page.getByRole("heading", { name: "Follow-ups (now)" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  }
  expect(failed).toEqual([]);
  expect(consoleErrors).toEqual([]);
});
