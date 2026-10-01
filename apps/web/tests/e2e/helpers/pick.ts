import { expect, type Locator } from "@playwright/test";

// ENH-031: choose from a SearchableSelect as a user would -- type to search, then click the option.
export async function pickFromList(input: Locator, search: string, option: string | RegExp = search) {
  await input.click();
  await input.fill(search);
  const listId = await input.getAttribute("aria-controls");
  await input.page().locator(`[id="${listId}"]`).getByRole("option", { name: option }).first().click();
  await expect(input).toHaveAttribute("aria-expanded", "false");
}

// When a spec only knows the record id (e.g. from an API call), pick the option carrying that id.
export async function pickByValue(input: Locator, value: string) {
  await input.click();
  const listId = await input.getAttribute("aria-controls");
  await input.page().locator(`[id="${listId}"] [data-value="${value}"]`).click();
  await expect(input).toHaveAttribute("aria-expanded", "false");
}
