import { deflateSync } from "node:zlib";
import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

// nehn-032 (DEC-SCOPE-301): the super admin replaces the Founder signature on the IT admin's Certificates page and previews the layout;
// the IT admin (no `certificates.manage`) does not see the card, and nobody without the grant can fetch a signature image (AC3).

const DEMO = "Demo@123";
const SIGNATORIES = "/api/v1/admin/certificate-signatories";

// A transparent RGBA PNG with a dark diagonal stroke, built here so the spec needs no fixture file.
function signaturePng(width = 240, height = 80): Buffer {
  const table = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const crc = (bytes: Buffer) => {
    let c = 0xffffffff;
    for (const b of bytes) c = table[(c ^ b) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };
  const chunk = (type: string, data: Buffer) => {
    const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
    const out = Buffer.alloc(body.length + 8);
    out.writeUInt32BE(data.length, 0);
    body.copy(out, 4);
    out.writeUInt32BE(crc(body), body.length + 4);
    return out;
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header.set([8, 6, 0, 0, 0], 8); // 8-bit RGBA
  const rows = Buffer.alloc((width * 4 + 1) * height);
  for (let y = 0; y < height; y++) {
    const x = Math.round((y / height) * width);
    for (let dx = -3; dx <= 3; dx++) {
      if (x + dx < 0 || x + dx >= width) continue;
      rows.set([14, 27, 43, 255], y * (width * 4 + 1) + 1 + (x + dx) * 4);
    }
  }
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", header), chunk("IDAT", deflateSync(rows)), chunk("IEND", Buffer.alloc(0))]);
}

async function api(browser: Browser, email: string, division: string): Promise<APIRequestContext> {
  const context = await browser.newContext();
  const response = await context.request.post("/api/v1/auth/login", { data: { email, password: DEMO, division } });
  expect(response.ok(), await response.text()).toBeTruthy();
  return context.request;
}

async function signIn(page: Page, portal: "it" | "admin", email: string) {
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", DEMO);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL((url) => !url.pathname.endsWith("/login"));
}

test("AC1/AC2: the super admin uploads a new Founder signature and previews the certificate", async ({ page }) => {
  await signIn(page, "admin", "superadmin@edusphere.local");
  await page.goto("/it/admin/certificates");
  const slot = page.getByRole("group", { name: "Founder signature" });
  await expect(slot).toBeVisible();
  const name = `Founder ${Date.now()}`;
  await slot.getByLabel("Name").fill(name);
  await slot.getByLabel("Designation").fill("Founder & Director");
  await slot.getByLabel(/Signature image/).setInputFiles({ name: "founder.png", mimeType: "image/png", buffer: signaturePng() });
  await slot.getByRole("button", { name: "Save founder signature" }).click();
  await expect(slot.getByRole("status")).toContainText("Founder signature saved");
  const image = slot.getByRole("img", { name: `${name} signature` });
  await expect(image).toBeVisible();
  await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth)).toBeGreaterThan(0); // decoded, not broken

  const preview = await page.request.get("/api/v1/admin/certificates/preview");
  expect(preview.status()).toBe(200);
  expect(preview.headers()["content-type"]).toBe("application/pdf");
  await expect(page.getByRole("link", { name: /Preview certificate/ })).toHaveAttribute("target", "_blank");
});

test("a JPEG is refused with a readable message", async ({ page }) => {
  await signIn(page, "admin", "superadmin@edusphere.local");
  await page.goto("/it/admin/certificates");
  const slot = page.getByRole("group", { name: "Coordinator signature" });
  await slot.getByLabel(/Signature image/).setInputFiles({ name: "x.jpg", mimeType: "image/jpeg", buffer: Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0, 0x10]) });
  await slot.getByRole("button", { name: "Save coordinator signature" }).click();
  await expect(slot.locator(".form-error")).toContainText("This file type is not allowed");
});

test("AC3: the IT admin does not see the card and neither they nor a coordinator can read a signature", async ({ page, browser }) => {
  const superAdmin = await api(browser, "superadmin@edusphere.local", "global");
  const founder = ((await (await superAdmin.get(SIGNATORIES)).json()) as { items: { id: string; role: string; active: boolean }[] }).items.find((i) => i.role === "founder" && i.active);
  expect(founder).toBeTruthy();

  await signIn(page, "it", "itadmin@edusphere.local");
  await page.goto("/it/admin/certificates");
  await expect(page.getByRole("heading", { name: "Certificate rules" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Certificate signatures" })).toHaveCount(0);
  expect((await page.request.get(`${SIGNATORIES}/${founder!.id}/image`)).status()).toBe(403);

  const coordinator = await api(browser, "coordinator@edusphere.local", "it");
  expect((await coordinator.get(`${SIGNATORIES}/${founder!.id}/image`)).status()).toBe(403);
  expect((await coordinator.get("/api/v1/admin/certificates/preview")).status()).toBe(403);
});
