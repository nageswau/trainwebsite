import { describe, expect, it } from "vitest";

import { MANAGEMENT_PILLARS, managementNavFor } from "@/lib/management";
import { RECRUITMENT_KPIS, placementRateText, recruitmentFilters, recruitmentHref, recruitmentUrl } from "@/lib/managementRecruitment";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";

describe("mgmt-025 recruitment helpers", () => {
  it("keeps only well-formed single dates from the address", () => {
    expect(recruitmentFilters({ date_from: "2026-10-01", date_to: "2026-10-13" })).toEqual({ date_from: "2026-10-01", date_to: "2026-10-13" });
    expect(recruitmentFilters({ date_from: "2026-02-30", date_to: ["2026-10-01", "2026-10-02"] })).toEqual({ date_from: "", date_to: "" });
  });

  it("builds the API and page addresses with only the set dates", () => {
    expect(recruitmentUrl({ date_from: "", date_to: "" })).toBe("/api/v1/management/recruitment");
    expect(recruitmentUrl({ date_from: "2026-10-01", date_to: "" })).toBe("/api/v1/management/recruitment?date_from=2026-10-01");
    expect(recruitmentHref({ date_from: "2026-10-01", date_to: "2026-10-13" })).toBe("/management/recruitment?date_from=2026-10-01&date_to=2026-10-13");
  });

  it("lists the §21 KPIs in source order and words", () => {
    expect(RECRUITMENT_KPIS.map((kpi) => kpi.label)).toEqual([
      "Recruiters", "Employer partners", "New companies", "Job openings", "Internship openings", "Candidates", "Interviews", "Selections",
      "Joining", "Placement rate", "Revenue",
    ]); // prettier-ignore
  });

  it("words the placement rate, with a dash when nobody was sourced", () => {
    expect(placementRateText(25)).toBe("25%");
    expect(placementRateText(null)).toBe("—");
  });

  it("makes the three mgmt-025 Command Center entries live for the operational tier only, and links the super admin's sidebar", () => {
    const entries = MANAGEMENT_PILLARS.flatMap((pillar) => pillar.entries).filter((entry) => entry.item === "mgmt-025");
    expect(entries.map((entry) => [entry.label, entry.href])).toEqual([
      ["Recruitment", "/management/recruitment"],
      ["Recruiters", "/management/recruitment#recruitment-kpis"],
      ["Companies", "/management/recruitment#company-pipeline"],
    ]);
    expect(managementNavFor({ operational: true, finance: false, partner_only: false })).toContainEqual({ label: "Recruitment", href: "/management/recruitment" });
    const finance = managementNavFor({ operational: false, finance: true, partner_only: false });
    expect(finance.some((item) => item.href.startsWith("/management/recruitment"))).toBe(false);
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Management recruitment figures", href: "/management/recruitment" });
  });
});
