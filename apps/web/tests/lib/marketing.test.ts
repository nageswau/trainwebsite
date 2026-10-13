import { describe, expect, it } from "vitest";

import { budgetErrors, budgetText, budgetsBody, budgetsUrl, marketingUrl, percentText } from "@/lib/marketing";

describe("marketing lib (mgmt-012)", () => {
  it("builds the read and save URLs", () => {
    expect(marketingUrl("")).toBe("/api/v1/management/marketing");
    expect(marketingUrl("2026-09")).toBe("/api/v1/management/marketing?month=2026-09");
    expect(budgetsUrl("2026-09")).toBe("/api/v1/management/marketing/budgets?month=2026-09");
  });

  it("writes ROI and conversion as a percent, or a dash when there is none (MK9 zero spend)", () => {
    expect(percentText(488.2)).toBe("488.2%");
    expect(percentText(-12.5)).toBe("-12.5%");
    expect(percentText(1250)).toBe("1,250%");
    expect(percentText(0)).toBe("0%");
    expect(percentText(null)).toBe("—");
  });

  it("tells a budget never set from a budget of nothing (MK3)", () => {
    expect(budgetText(null)).toBe("Not set");
    expect(budgetText("0.00")).toBe("₹0.00");
    expect(budgetText("100000.00")).toBe("₹1,00,000.00");
  });

  it("sends only the channels with a figure, in channel order, as typed (MK4)", () => {
    expect(budgetsBody({ instagram: " 100000 ", google: "", school: "0" }, ["instagram", "google", "school"])).toEqual({
      budgets: [{ channel: "instagram", amount: "100000" }, { channel: "school", amount: "0" }],
    });
    expect(budgetsBody({}, ["instagram"])).toEqual({ budgets: [] });
  });

  it("places a 422 on the channel that was sent at that index", () => {
    const sent = budgetsBody({ instagram: "1", google: "-5", school: "2" }, ["instagram", "google", "school"]).budgets.map((b) => b.channel);
    expect(budgetErrors({ detail: [{ loc: ["body", "budgets", 1, "amount"], msg: "An amount can't be negative" }] }.detail, sent)).toEqual({ google: "An amount can't be negative" });
    expect(budgetErrors("Finance access required", sent)).toEqual({});
  });
});
