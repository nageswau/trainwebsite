import { expect, test, type Page } from "@playwright/test";

// rec-014 (AC1, AC2; FT1-FT10): the seeded recruiter adds two candidates and extracts their resumes (rec-012). A resume search finds the one
// whose resume mentions Microservices with no such skill on the profile (AC1), marks the hits in the card's snippet, narrows with a skill
// chip (AC2), survives a refresh, explains a stop-word-only search, and HR reads the same results.

async function signIn(page: Page, email: string, landing: string) {
  await page.goto("/it/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

/** A one-page PDF whose text layer holds `lines` (the rec-012 e2e helper). */
function textPdf(lines: string[]): Buffer {
  const escape = (s: string) => s.replace(/[\\()]/g, (c) => `\\${c}`);
  const stream = `BT /F1 11 Tf 50 780 Td 14 TL ${lines.map((l) => `(${escape(l)}) '`).join(" ")} ET`;
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`,
  ];
  let pdf = "%PDF-1.4\n";
  const offsets = objects.map((body, i) => {
    const at = pdf.length;
    pdf += `${i + 1} 0 obj\n${body}\nendobj\n`;
    return at;
  });
  const xref = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n${offsets.map((o) => `${String(o).padStart(10, "0")} 00000 n \n`).join("")}`;
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(pdf, "latin1");
}

test("resume search: words not extracted as skills, highlighted snippet, narrowed by a skill, refresh, stop words; HR reads", async ({ page }) => {
  test.setTimeout(120_000);
  const stamp = Date.now();
  const tag = `zq${[...String(stamp).slice(-6)].map((d) => String.fromCharCode(97 + Number(d))).join("")}`; // a word only this run's resumes hold
  const consoleErrors: string[] = [];
  page.on("console", (message) => message.type() === "error" && consoleErrors.push(message.text()));
  const failedCalls: string[] = [];
  page.on("response", (response) => response.url().includes("/api/v1/") && response.status() >= 500 && failedCalls.push(response.url()));

  await signIn(page, "placement@edusphere.local", "/recruiter/dashboard");
  const sources = await (await page.request.get("/api/v1/recruiter/catalogue/candidate-sources?limit=100")).json();
  const source = sources.items.find((s: { name: string }) => s.name === "Referral");
  async function candidate(name: string, lines: string[], skill?: string) {
    const created = await page.request.post("/api/v1/recruiter/candidates", { data: { name, email: `${tag}${name.length}${stamp}@example.com`, source_id: source.id } });
    expect(created.status()).toBe(201);
    const c = await created.json();
    const upload = await page.request.put(`/api/v1/recruiter/candidates/${c.id}/resume`, {
      multipart: { file: { name: "cv.pdf", mimeType: "application/pdf", buffer: textPdf(lines) } },
    });
    expect(upload.status()).toBe(201);
    expect((await page.request.post(`/api/v1/recruiter/candidates/${c.id}/resume/${(await upload.json()).version}/extract`)).status()).toBe(200);
    if (skill) expect((await page.request.post(`/api/v1/recruiter/candidates/${c.id}/skills`, { data: { skill, level: "advanced" } })).status()).toBe(201);
    return c;
  }
  await candidate(`Micro ${tag}`, [`${tag} Senior Engineer`, "Java, Spring Boot and Microservices on Kubernetes", "AWS Certified Solutions Architect"], "Java");
  await candidate(`Mono ${tag} Developer`, [`${tag} Engineer`, "Java and Spring Boot monoliths with Oracle"]);

  await page.goto("/recruiter/find-candidates");
  await expect(page.getByText("or by words in their resume")).toBeVisible();
  await expect(page.getByText("Add a skill or a resume search to search every candidate in the pool.")).toBeVisible();

  // AC1: the four words, Microservices only in the resume text.
  await page.getByRole("textbox", { name: "Resume search" }).fill(`${tag} Java Spring Boot Microservices`);
  await page.getByRole("textbox", { name: "Resume search" }).press("Enter");
  const results = page.getByRole("region", { name: "Search results" });
  await expect(results.getByRole("heading", { name: "1 candidate found" })).toBeVisible();
  const card = results.getByRole("listitem", { name: new RegExp(`Micro ${tag}`) });
  await expect(card.getByText("From the resume")).toBeVisible();
  await expect(card.locator("mark", { hasText: "Microservices" })).toBeVisible();

  // AC2: both resumes say Spring; the Java skill chip keeps only the candidate who holds it.
  await page.getByRole("textbox", { name: "Resume search" }).fill(`${tag} spring`);
  await page.getByRole("button", { name: "Search candidates" }).click();
  await expect(results.getByRole("heading", { name: "2 candidates found" })).toBeVisible();
  const chips = page.getByRole("textbox", { name: "Must have all of these skills" });
  await chips.fill("Java");
  await chips.press("Enter");
  await page.getByRole("button", { name: "Search candidates" }).click();
  await expect(results.getByRole("heading", { name: "1 candidate found" })).toBeVisible();
  await expect(page).toHaveURL(new RegExp(`q=${tag}\\+spring&all=Java`));
  await page.reload();
  await expect(page.getByRole("textbox", { name: "Resume search" })).toHaveValue(`${tag} spring`);
  await expect(results.getByRole("heading", { name: "1 candidate found" })).toBeVisible();

  // FT3: only common words.
  await page.goto("/recruiter/find-candidates?q=the+and+of");
  await expect(results.getByText(/only has common words/)).toBeVisible();

  expect(consoleErrors).toEqual([]);
  expect(failedCalls).toEqual([]);

  // FT9: HR reads the same results (no Shortlist).
  await page.context().clearCookies();
  await signIn(page, "hr@edusphere.local", "/it/hr/dashboard");
  await page.goto(`/recruiter/find-candidates?q=${tag}+microservices`);
  await expect(results.getByRole("heading", { name: "1 candidate found" })).toBeVisible();
  await expect(results.getByRole("button", { name: /Shortlist/ })).toHaveCount(0);
});
