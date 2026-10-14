import { expect, test } from "@playwright/test";

// PUB-024 (DEC-SCOPE-223): the three offices, with a Google Maps "Get directions" link each, on every contact page.
const OFFICES = ["Bengaluru", "Hyderabad", "Tadepalligudem"];

for (const path of ["/contact", "/it/contact", "/overseas/contact"]) {
  test(`${path} shows the three offices with directions links (PUB-024)`, async ({ page }) => {
    await page.goto(path);
    const block = page.getByRole("region", { name: "Our offices" });
    await expect(block).toBeVisible();
    for (const city of OFFICES) {
      await expect(block.getByRole("heading", { name: city, exact: true })).toBeVisible();
      const link = block.getByRole("link", { name: `Get directions to the ${city} office (opens in a new tab)` });
      await expect(link).toHaveAttribute("href", /^https:\/\/www\.google\.com\/maps\/search\/\?api=1&query=/);
      await expect(link).toHaveAttribute("target", "_blank");
    }
  });
}
