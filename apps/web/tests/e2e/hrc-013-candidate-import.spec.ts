import { expect, test, type Page } from "@playwright/test";

// hrc-013 (DEC-SCOPE-391): a recruiter imports a CSV -- the preview shows a new person, a known person (matched, not duplicated), an
// in-file repeat and a row with an error; Import adds only the new person, and importing the same file again adds nobody. Seeded demo
// account; the people are made unique per run.
async function signIn(page: Page, email: string, division = "it") {
  expect((await page.request.post("/api/v1/auth/login", { data: { email, password: "Demo@123", division } })).ok()).toBeTruthy();
}

test("a candidate file is checked, imported once and safe to import again", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  await signIn(page, "placement@edusphere.local");
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const source = sources.items.find((s: { active: boolean }) => s.active);
  const known = await page.request.post("/api/v1/recruiter/candidates", { data: { source_id: source.id, name: `E2E Known ${stamp}`, email: `hrc013-k-${stamp}@example.com` } });
  expect(known.status(), await known.text()).toBe(201);
  const knownCode = (await known.json()).candidate_code as string;
  const csv = [
    "name,email,city",
    `E2E New ${stamp},hrc013-n-${stamp}@example.com,Pune`,
    `Someone Else,hrc013-k-${stamp}@example.com,`,
    `E2E New Again,HRC013-N-${stamp}@example.com,`,
    `No Contact ${stamp},,`,
  ].join("\n");
  const file = { name: `candidates-${stamp}.csv`, mimeType: "text/csv", buffer: Buffer.from(csv) };

  await page.goto("/recruiter/candidates");
  await page.getByRole("link", { name: "Import candidates" }).click();
  await expect(page.getByRole("heading", { name: "Import candidates", level: 2 })).toBeVisible();
  await page.getByLabel("Candidate source").selectOption(source.id);
  await page.getByLabel("Filled-in candidates file").setInputFiles(file);
  await page.getByRole("button", { name: "Check file" }).click();

  const rows = page.getByRole("table", { name: "Rows in this file" });
  await expect(rows).toBeVisible();
  await expect(page.getByText("1 new candidate, 2 already candidates, 1 row with an error")).toBeVisible();
  await expect(rows.getByRole("link", { name: knownCode })).toBeVisible();
  await expect(rows.getByText("Same person as row 2")).toBeVisible();
  await expect(rows.getByText("Enter a mobile number or an email")).toBeVisible();

  await page.getByRole("button", { name: "Import 1 new candidate" }).click();
  await expect(page.getByRole("heading", { name: "Import result" })).toBeFocused();
  await expect(page.locator("p.form-warning").filter({ hasText: "1 added, 2 already candidates, 1 error." })).toBeVisible();
  const report = page.getByRole("table", { name: "Import report" });
  await expect(report.getByRole("row").filter({ hasText: "Added" }).getByText(`E2E New ${stamp}`)).toBeVisible();
  await expect(report.getByText("Same person as row 2")).toBeVisible(); // browser QA-03: the stored report says why a row matched
  await expect(page.getByRole("table", { name: "Past imports" }).getByText(file.name)).toBeVisible();
  await expect(report.getByRole("link", { name: knownCode })).toHaveAttribute("href", /\/recruiter\/candidates\/[0-9a-f-]+$/);

  // AC3: the same file again (a new key after choosing it again) adds nobody
  await page.getByLabel("Filled-in candidates file").setInputFiles(file);
  await page.getByRole("button", { name: "Check file" }).click();
  await expect(page.getByText("Nothing new to add — every row is already a candidate or has an error.")).toBeVisible();

  // the new person is in the candidate master, once
  const list = await (await page.request.get(`/api/v1/recruiter/candidates?q=${encodeURIComponent(`E2E New ${stamp}`)}`)).json();
  expect(list.total).toBe(1);
});
