import { expect, test, type Page } from "@playwright/test";

// hrc-011 (DEC-SCOPE-375): the placement manager sets a rate under Catalogues → Exchange rates; a recruiter records pay as the candidate
// states it (USD per month, INR per month) and sees the yearly rupee figure; HR (no compensation grant) sees none of it. Seeded demo
// accounts; the candidate is created per run.
async function signIn(page: Page, email: string, division = "it") {
  expect((await page.request.post("/api/v1/auth/login", { data: { email, password: "Demo@123", division } })).ok()).toBeTruthy();
}

test("manager sets a rate; recruiter records a package and sees the yearly rupee figure; HR sees no compensation", async ({ page }) => {
  await signIn(page, "placement.manager@edusphere.local", "global");
  await page.goto("/recruiter/manager/catalogue/exchange-rates");
  await expect(page.getByRole("heading", { name: "Exchange rates", level: 2 })).toBeVisible();
  await page.getByLabel(/Currency code/).fill("usd");
  await page.getByLabel(/Rupees for 1 unit/).fill("83.25");
  await page.getByRole("button", { name: "Save rate" }).click();
  await expect(page.getByText("Saved: 1 USD = ₹83.25.", { exact: false })).toBeVisible();
  await expect(page.locator("td strong", { hasText: "USD" })).toBeVisible();

  await signIn(page, "placement@edusphere.local");
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const stamp = Date.now();
  const created = await page.request.post("/api/v1/recruiter/candidates", {
    data: { name: `HRC Package ${stamp}`, email: `hrc011-${stamp}@example.com`, source_id: sources.items.find((s: { active: boolean }) => s.active).id },
  });
  expect(created.status()).toBe(201);
  const id = (await created.json()).id as string;
  await page.goto(`/recruiter/candidates/${id}`);
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  const group = page.getByRole("group", { name: "Compensation" });
  await group.getByLabel("Current salary", { exact: true }).fill("50000");
  await group.getByLabel("Current salary pay period").selectOption("month");
  await group.getByLabel("Expected salary", { exact: true }).fill("4000");
  await group.getByLabel("Expected salary currency").selectOption("USD");
  await group.getByLabel("Expected salary pay period").selectOption("month");
  await group.getByLabel("Negotiable").selectOption("yes");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Changes saved.")).toBeVisible();
  await expect(page.getByText("₹50,000 per month (≈ ₹6,00,000 a year)")).toBeVisible();
  await expect(page.getByText("USD 4,000 per month (≈ ₹39,96,000 a year)")).toBeVisible();

  await signIn(page, "hr@edusphere.local");
  await page.goto(`/recruiter/candidates/${id}`);
  await expect(page.getByRole("heading", { name: /HRC Package/ })).toBeVisible();
  await expect(page.getByText(/per month/)).toHaveCount(0);
  await expect(page.getByText("Negotiable")).toHaveCount(0);
  const detail = await (await page.request.get(`/api/v1/recruiter/candidates/${id}`)).json();
  expect(Object.keys(detail).filter((k) => k.includes("salary") || k.includes("annual_inr"))).toEqual([]);
});
