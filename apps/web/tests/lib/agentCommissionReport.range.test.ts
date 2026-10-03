import { describe, expect, it } from "vitest";

import { readRange } from "@/lib/agentCommissionReport";

// AGN-019 browser QA19-01: a date input cannot display an impossible date, so one read from the address would sit hidden in the form
// and be re-sent by every Apply. Only real calendar dates are read back; anything else means "no bound".
describe("readRange", () => {
  it("keeps real calendar dates", () => {
    expect(readRange("?from=2026-01-31&to=2028-02-29")).toEqual({ from: "2026-01-31", to: "2028-02-29" });
  });

  it.each(["2026-13-01", "2026-02-30", "2027-02-29", "2026-00-10", "2026-04-31", "0000-01-01"])("drops the impossible date %s", (value) => {
    expect(readRange(`?from=${value}&to=${value}`)).toEqual({ from: "", to: "" });
  });

  it("still drops malformed values", () => {
    expect(readRange("?from=abc&to=20260101")).toEqual({ from: "", to: "" });
  });
});
