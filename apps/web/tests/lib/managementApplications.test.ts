import { describe, expect, it } from "vitest";

import { applicationsHref, applicationsUrl, EMPTY_FUNNEL_FILTERS, funnelFilters, hasFilters, shareText, stageShare } from "@/lib/managementApplications";

const ID = "0b9c3f1e-6a52-4e43-9d7a-2b8f8f2f3c11";

describe("mgmt-024 funnelFilters", () => {
  it("keeps every well-formed filter from the address", () => {
    const filters = funnelFilters({
      date_from: "2026-04-01", date_to: "2026-09-30", agency: ID, counselor: "none", country: ID, university: ID, course: ID,
      intake: "Fall 2027", staff: ID, status: "offer",
    }); // prettier-ignore
    expect(filters).toEqual({
      date_from: "2026-04-01", date_to: "2026-09-30", agency: ID, counselor: "none", country: ID, university: ID, course: ID,
      intake: "Fall 2027", staff: ID, status: "offer",
    }); // prettier-ignore
  });

  it("drops repeated, malformed and unknown values so the API only sees what the form can send", () => {
    const filters = funnelFilters({ agency: [ID, ID], counselor: "12", country: "none", date_from: "2026-02-30", intake: "  ", status: "x".repeat(51), other: "1" });
    expect(filters).toEqual(EMPTY_FUNNEL_FILTERS);
  });
});

describe("mgmt-024 applicationsUrl", () => {
  it("is the bare API path with no filters", () => {
    expect(applicationsUrl(EMPTY_FUNNEL_FILTERS)).toBe("/api/v1/management/applications");
  });

  it("carries only the filters that are set", () => {
    expect(applicationsUrl({ ...EMPTY_FUNNEL_FILTERS, intake: "Fall 2027", agency: "none" })).toBe("/api/v1/management/applications?agency=none&intake=Fall+2027");
  });
});

describe("mgmt-024 hasFilters / stageShare", () => {
  it("knows when any filter is applied", () => {
    expect(hasFilters(EMPTY_FUNNEL_FILTERS)).toBe(false);
    expect(hasFilters({ ...EMPTY_FUNNEL_FILTERS, status: "offer" })).toBe(true);
  });

  it("is a stage's whole-number share of the applications created, 0 when none were", () => {
    expect(stageShare(1, 3)).toBe(33);
    expect(stageShare(2, 3)).toBe(67);
    expect(stageShare(5, 0)).toBe(0);
    expect(stageShare(4, 4)).toBe(100);
  });

  it("QA24-03: words the share, never 0% for a non-zero stage", () => {
    expect(shareText(2, 616)).toBe("Less than 1% of applications created");
    expect(shareText(0, 616)).toBe("0% of applications created");
    expect(shareText(71, 616)).toBe("12% of applications created");
  });
});

describe("mgmt-024 applicationsHref (QA24-01)", () => {
  it("is the page path with only the set filters", () => {
    expect(applicationsHref(EMPTY_FUNNEL_FILTERS)).toBe("/management/applications");
    expect(applicationsHref({ ...EMPTY_FUNNEL_FILTERS, status: "offer" })).toBe("/management/applications?status=offer");
  });
});
