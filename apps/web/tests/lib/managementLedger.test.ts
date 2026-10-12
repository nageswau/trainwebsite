import { describe, expect, it } from "vitest";

import { describeActivity, managementNavFor, type ManagementActivityItem } from "@/lib/management";
import { formatInr, formatMoney, ledgerFilters, ledgerHref, ledgerUrl, LEDGER_HOME, SOURCE_LABEL, statusClass } from "@/lib/managementLedger";

const UUID = "0b7a1f8e-3c55-4b0e-9a51-2f3c4d5e6f70";
const none = { month: "", kind: "", category: "", vertical: "", status: "", include: "", offset: 0 };

describe("mgmt-004 ledger filters and links", () => {
  it("keeps only well-formed filters from the address", () => {
    expect(ledgerFilters({ month: "2026-10", kind: "expense", category: UUID, vertical: "shared", status: "submitted", offset: "25", other: "x" }))
      .toEqual({ month: "2026-10", kind: "expense", category: UUID, vertical: "shared", status: "submitted", include: "", offset: 25 });
    expect(ledgerFilters({ month: "2026-13", kind: "transfer", category: "nope", vertical: "branch", status: "paid", offset: "-3" })).toEqual(none);
    expect(ledgerFilters({ month: ["2026-10", "2026-11"] })).toEqual(none);
  });

  it("builds the page link and the API url with the page size", () => {
    expect(ledgerHref(none)).toBe(LEDGER_HOME);
    expect(ledgerHref({ ...none, status: "submitted", offset: 25 })).toBe("/management/ledger?status=submitted&offset=25");
    expect(ledgerUrl({ ...none, month: "2026-10", category: UUID })).toBe(`/api/v1/management/ledger?month=2026-10&category=${UUID}&limit=25`);
  });

  it("formats rupees the Indian way and maps statuses to pills", () => {
    expect(formatInr("120000.00")).toBe("₹1,20,000.00");
    expect(formatInr("-500")).toBe("-₹500.00");
    expect(statusClass("approved")).toBe("status");
    expect(statusClass("submitted")).toBe("status pending");
    expect(statusClass("rejected")).toBe("status error");
    expect(statusClass("draft")).toBe("badge");
  });
});

describe("mgmt-005 automatic lines", () => {
  it("keeps include=auto from the address and sends it to the page link and the API", () => {
    expect(ledgerFilters({ include: "auto", month: "2026-10" })).toEqual({ ...none, include: "auto", month: "2026-10" });
    expect(ledgerFilters({ include: "everything" })).toEqual(none);
    expect(ledgerHref({ ...none, include: "auto" })).toBe("/management/ledger?include=auto");
    expect(ledgerUrl({ ...none, include: "auto", kind: "income" })).toBe("/api/v1/management/ledger?kind=income&include=auto&limit=25");
  });

  it("labels every source and formats other currencies in their own money", () => {
    expect(SOURCE_LABEL).toEqual({
      payment: "Student payment", agent_commission: "Agent commission", trip_expense: "BDM trip expense", recruiter_payment: "Recruiter payment",
      university_commission: "University commission", salary: "Salaries",
    });
    expect(formatMoney("120000.00", "INR")).toBe("₹1,20,000.00");
    expect(formatMoney("300.00", "GBP")).toBe("£300.00");
  });
});

describe("mgmt-004 in the Command Center", () => {
  it("lists the ledger for the finance tier only", () => {
    const finance = managementNavFor({ operational: false, finance: true, partner_only: false });
    expect(finance).toContainEqual({ label: "Ledger", href: LEDGER_HOME });
    expect(managementNavFor({ operational: true, finance: false, partner_only: false }).some((i) => i.href === LEDGER_HOME)).toBe(false);
  });

  it("words the new ledger verbs in the activity feed", () => {
    const item = (verb: string): ManagementActivityItem => ({ id: "1", at: "", actor: null, kind: "mgmt.ledger", kind_label: "Ledger entry", verb, entity_id: null, fields: [], values: null, count: null });
    expect(["submit", "reject", "reverse", "download"].map((verb) => describeActivity(item(verb)).title))
      .toEqual(["Ledger entry submitted", "Ledger entry rejected", "Ledger entry reversed", "Ledger entry downloaded"]);
  });
});
