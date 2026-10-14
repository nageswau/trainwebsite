import { describe, expect, it } from "vitest";

import {
  CAPITAL_API,
  capitalHref,
  capitalQuery,
  capitalUrl,
  EMPTY_ENTRY_FORM,
  entryBody,
  entryProblem,
  overdraw,
  pctText,
  shareTotalWarning,
  sharesBody,
  sharesProblem,
  type CapitalAccount,
} from "@/lib/partnerCapital";

const ARJUN = { id: "a1", full_name: "Arjun Partner", active: true };
const account = (balance: string): CapitalAccount => ({
  partner: ARJUN, invested: "500000.00", additional: "0.00", withdrawals: "0.00", balance, returns: "0.00", share_pct: "50.00",
  commitment: null, outstanding: null, profit_share: null,
}); // prettier-ignore

describe("capitalQuery / capitalUrl (mgmt-015 CP10)", () => {
  it("keeps a valid month, period and offset and drops anything else", () => {
    expect(capitalQuery({ month: "2026-05", period: "quarter", offset: "25" })).toEqual({ month: "2026-05", period: "quarter", offset: 25 });
    expect(capitalQuery({ month: "2026-13", period: "week", offset: "-3" })).toEqual({ month: "", period: "year", offset: 0 });
    expect(capitalQuery({ month: ["2026-05", "2026-06"], offset: "99999" })).toEqual({ month: "", period: "year", offset: 10000 });
  });

  it("asks the API with the defaults left out and builds the page address", () => {
    expect(capitalUrl({ month: "", period: "year", offset: 0 })).toBe(CAPITAL_API);
    expect(capitalUrl({ month: "2026-05", period: "month", offset: 25 })).toBe(`${CAPITAL_API}?month=2026-05&period=month&offset=25`);
    expect(capitalHref({ month: "", period: "year", offset: 25 })).toBe("/management/capital?offset=25");
    expect(capitalHref({ month: "", period: "year", offset: 0 })).toBe("/management/capital");
  });
});

describe("shareTotalWarning (AC1, CP7)", () => {
  it("warns whenever the shares in force do not total exactly 100%", () => {
    expect(shareTotalWarning("100.00")).toBeNull();
    expect(shareTotalWarning("90.00")).toBe("Shares in force total 90.00%, not 100%.");
    expect(shareTotalWarning("0.00")).toBe("Shares in force total 0.00%, not 100%.");
  });

  it("shows a share or a dash", () => {
    expect(pctText("50.00")).toBe("50.00%");
    expect(pctText(null)).toBe("—");
  });
});

describe("the capital entry form (CP3, CP11)", () => {
  const form = { ...EMPTY_ENTRY_FORM, partner_id: "a1", entry_date: "2026-05-01", kind: "withdrawal", amount: " 600000 ", note: "  Paid out  " };

  it("names the first problem", () => {
    expect(entryProblem({ ...form, partner_id: "" }, "2026-10-14")).toEqual({ field: "partner_id", message: "Choose the partner." });
    expect(entryProblem({ ...form, entry_date: "" }, "2026-10-14")?.field).toBe("entry_date");
    expect(entryProblem({ ...form, entry_date: "2026-10-15" }, "2026-10-14")?.message).toBe("The entry date can't be in the future.");
    expect(entryProblem({ ...form, entry_date: "1999-12-31" }, "2026-10-14")?.message).toBe("The entry date can't be before 1 January 2000.");
    expect(entryProblem({ ...form, kind: "" }, "2026-10-14")?.field).toBe("kind");
    expect(entryProblem({ ...form, amount: "1.005" }, "2026-10-14")?.message).toBe("Enter the amount in rupees with up to 2 decimals.");
    expect(entryProblem({ ...form, amount: "0" }, "2026-10-14")?.message).toBe("The amount must be more than ₹0.");
    expect(entryProblem(form, "2026-10-14")).toBeNull();
  });

  it("sends trimmed values and a blank note as null", () => {
    expect(entryBody(form)).toEqual({ partner_id: "a1", entry_date: "2026-05-01", kind: "withdrawal", amount: "600000", note: "Paid out" });
    expect(entryBody({ ...form, note: "  " }).note).toBeNull();
  });

  it("flags a withdrawal over the partner's balance and nothing else", () => {
    expect(overdraw(form, [account("500000.00")])).toEqual({ name: "Arjun Partner", balance: "500000.00" });
    expect(overdraw({ ...form, amount: "500000" }, [account("500000.00")])).toBeNull();
    expect(overdraw({ ...form, kind: "additional" }, [account("500000.00")])).toBeNull();
  });
});

describe("the share % form (CP5, CP6)", () => {
  const rows = { a1: { share_pct: "50", commitment: "1000000" }, b2: { share_pct: "", commitment: "" } };

  it("needs a month and at least one share, each 0-100 with up to 2 decimals, and money commitments", () => {
    expect(sharesProblem({ effective_from: "", rows })?.field).toBe("effective_from");
    expect(sharesProblem({ effective_from: "2026-04", rows: { b2: { share_pct: "", commitment: "" } } })?.message).toBe("Enter at least one partner's share %.");
    expect(sharesProblem({ effective_from: "2026-04", rows: { a1: { share_pct: "100.5", commitment: "" } } })?.message).toBe("Enter each share as a percentage from 0 to 100 with up to 2 decimals.");
    expect(sharesProblem({ effective_from: "2026-04", rows: { a1: { share_pct: "50", commitment: "-1" } } })?.message).toBe("Enter each commitment in rupees with up to 2 decimals.");
    expect(sharesProblem({ effective_from: "2026-04", rows: { a1: { share_pct: "", commitment: "100" } } })?.message).toBe("Enter a share % for every partner with a commitment.");
    expect(sharesProblem({ effective_from: "2026-04", rows })).toBeNull();
  });

  it("sends only the partners with a share, a blank commitment as null", () => {
    expect(sharesBody({ effective_from: "2026-04", rows: { ...rows, c3: { share_pct: "0", commitment: " " } } })).toEqual({
      effective_from: "2026-04",
      shares: [{ partner_id: "a1", share_pct: "50", commitment: "1000000" }, { partner_id: "c3", share_pct: "0", commitment: null }],
    });
  });
});
