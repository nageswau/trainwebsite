import { describe, expect, it } from "vitest";

import { DEFAULT_LOCALE, SUPPORTED_LOCALES } from "@/lib/i18n";

describe("i18n locale configuration", () => {
  it("has a default locale that is itself supported", () => {
    expect(SUPPORTED_LOCALES).toContain(DEFAULT_LOCALE);
  });

  it("only lists en-GB until a second language is approved", () => {
    expect(SUPPORTED_LOCALES).toEqual(["en-GB"]);
  });
});
