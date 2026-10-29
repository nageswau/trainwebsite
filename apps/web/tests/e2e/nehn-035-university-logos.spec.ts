import { test, expect, type Locator, type Page } from "@playwright/test";

// nehn-035 (DEC-SCOPE-331) -- university logo upload and richer catalogue cards. Requires the seeded stack (University of Manchester is
// published with courses; RWTH Aachen is in Germany). The public pages are ISR (revalidate 60), so a new logo is polled for.

const LOGO = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAIAAADYYG7QAAAAOklEQVR42u3OQQ0AAAgEoEtiMBMbyxbOBxsBSPW8EiEhISEhISEhISEhISEhISEhISEhISEhISGhOwsXT0CmAPiVQQAAAABJRU5ErkJggg==",
  "base64",
);

async function login(page: Page, email: string, landing: string) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(landing);
}

async function manchester(page: Page) {
  const found = await page.request.get("/api/v1/partnership/universities?q=University%20of%20Manchester");
  expect(found.ok()).toBe(true);
  return (await found.json()).items.find((u: { name: string }) => u.name === "University of Manchester") as { id: string };
}

// Each poll attempt must give up quickly while the ISR page still shows the monogram (no <img>), or one attempt eats the whole poll.
const src = (image: Locator) => image.getAttribute("src", { timeout: 2_000 }).catch(() => null);

function card(page: Page, name: string) {
  return page.locator("article.card").filter({ has: page.getByRole("heading", { name, exact: true }) });
}

test("an Overseas Admin uploads a PNG logo; it shows on the catalogue card and the detail page (AC1)", async ({ page }) => {
  test.setTimeout(150_000);
  await login(page, "overseasadmin@edusphere.local", "**/overseas/admin/dashboard");
  const { id } = await manchester(page);
  const before = (await (await page.request.get(`/api/v1/partnership/universities/${id}`)).json()).university.logo_url;
  try {
    await page.goto(`/partnership/universities/${id}/edit`);
    await page.getByLabel("Upload a logo").setInputFiles({ name: "manchester.png", mimeType: "image/png", buffer: LOGO });
    await expect(page.getByText("Logo uploaded.")).toBeVisible();
    const uploaded = await page.getByLabel("Logo URL").inputValue();
    expect(uploaded).toMatch(/^\/api\/v1\/public\/university-logos\/[0-9a-f]{32}\.png$/);
    await expect(page.getByRole("img", { name: "University of Manchester logo" })).toHaveAttribute("src", uploaded);
    await page.getByRole("button", { name: "Save changes" }).click();
    await page.waitForURL(`**/partnership/universities/${id}`);

    await expect.poll(async () => {
      await page.goto("/overseas/universities");
      await page.getByPlaceholder(/Search university/).fill("University of Manchester");
      return src(card(page, "University of Manchester").getByRole("img", { name: "University of Manchester logo" }));
    }, { timeout: 100_000, intervals: [5_000] }).toBe(uploaded);
    await expect.poll(async () => {
      await page.goto("/overseas/universities/university-of-manchester");
      return src(page.locator(".page-hero img").first());
    }, { timeout: 100_000, intervals: [5_000] }).toBe(uploaded);
  } finally {
    await page.request.patch(`/api/v1/partnership/universities/${id}`, { data: { logo_url: before } });
  }
});

test("an SVG with a script is refused (AC5)", async ({ page }) => {
  await login(page, "overseasadmin@edusphere.local", "**/overseas/admin/dashboard");
  const { id } = await manchester(page);
  const svg = Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>');
  const refused = await page.request.put(`/api/v1/partnership/universities/${id}/logo`, { multipart: { file: { name: "x.svg", mimeType: "image/svg+xml", buffer: svg } } });
  expect(refused.status()).toBe(415);
  await page.goto(`/partnership/universities/${id}/edit`);
  await page.getByLabel("Upload a logo").setInputFiles({ name: "x.svg", mimeType: "image/svg+xml", buffer: svg });
  await expect(page.getByText("Choose a PNG, JPEG or WebP image of at most 1 MB.")).toBeVisible();
});

test("a card shows country, city, programs, View details and Apply; Apply logged out goes to login, then back preselected (AC2, AC3)", async ({ page }) => {
  await page.goto("/overseas/universities");
  await page.getByPlaceholder(/Search university/).fill("University of Manchester");
  const uni = card(page, "University of Manchester");
  await expect(uni.getByText("Manchester, United Kingdom")).toBeVisible();
  await expect(uni.locator("img.country-flag")).toHaveAttribute("src", "/flags/gb.svg");
  await expect(uni.getByText(/^\d+ programs?$/)).toBeVisible();
  await expect(uni.getByRole("link", { name: "View details for University of Manchester" })).toHaveAttribute("href", "/overseas/universities/university-of-manchester");
  await uni.getByRole("link", { name: "Apply to University of Manchester" }).click();
  await expect(page).toHaveURL(/\/overseas\/login\?next=/);
  await page.fill("#login-email", "student.overseas@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/overseas/student/applications?university=university-of-manchester");
  const form = page.locator(".action-card", { has: page.getByRole("heading", { name: "Apply to a University" }) });
  await expect(form.locator("#apply-university option:checked")).toHaveText(/^University of Manchester -- /);
  await expect(form.locator("#apply-country option:checked")).toHaveText("United Kingdom");
});

test("the catalogue filters by country (AC4)", async ({ page }) => {
  await page.goto("/overseas/universities");
  await page.getByLabel("Country").selectOption("United Kingdom");
  await page.getByPlaceholder(/Search university/).fill("University of Manchester");
  await expect(page.getByRole("heading", { name: "University of Manchester" })).toBeVisible();
  await page.getByPlaceholder(/Search university/).fill("RWTH Aachen");
  await expect(page.getByRole("heading", { name: "RWTH Aachen University" })).toHaveCount(0);
  await page.getByLabel("Country").selectOption("Germany");
  await expect(page.getByRole("heading", { name: "RWTH Aachen University" })).toBeVisible();
});
