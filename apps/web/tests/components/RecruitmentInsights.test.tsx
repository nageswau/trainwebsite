import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DataQualityView, PortalAnalyticsView, SkillDemandView } from "@/components/RecruitmentInsights";
import { drillHref, drillUrl, parseDrill, parsePeriod, parseSkill, portalAnalyticsUrl, skillDemandUrl, skillHref, vacanciesUrl } from "@/lib/recruitmentInsights";

vi.mock("@/lib/api", () => ({ serverApi: vi.fn(), ApiError: class extends Error {} }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));

afterEach(cleanup);

const params = parseSkill({});
const skills = {
  figures: [{ key: "zero_supply", label: "Skills with zero supply", value: 1, definition: "Skills open jobs ask for and nobody holds." }],
  items: [
    { skill_id: "1", name: "Rust", category: "Programming", required_jobs: 2, preferred_jobs: 1, open_jobs: 3, supply: 0, zero_supply: true },
    { skill_id: "2", name: "Java", category: "Programming", required_jobs: 1, preferred_jobs: 0, open_jobs: 1, supply: 7, zero_supply: false },
    { skill_id: "3", name: "Go", category: "Programming", required_jobs: 0, preferred_jobs: 0, open_jobs: 0, supply: 0, zero_supply: false },
  ],
  total: 3, limit: 50, offset: 0, sort: "demand" as const,
};
const vacancies = { n: 5, items: [{ id: "j", code: "REQ-1", title: "Developer", company: "Acme", matches: 0, reason: "no_skills" }], total: 1, limit: 50, offset: 0, checked: 1, open_jobs: 1 };

describe("hrc-034 skill demand (I2)", () => {
  it("highlights a skill with zero supply in text, and only that skill", () => {
    render(<SkillDemandView data={skills} vacancies={vacancies} params={params} />);
    const rust = screen.getByRole("row", { name: /Rust/ });
    expect(within(rust).getByText("No supply")).toBeTruthy();
    expect(screen.getAllByText("No supply")).toHaveLength(1);
  });

  it("explains a vacancy with no matchable skill, and says when jobs went unchecked", () => {
    const { rerender } = render(<SkillDemandView data={skills} vacancies={vacancies} params={params} />);
    expect(screen.getByText(/no Skills Master skill listed/)).toBeTruthy();
    expect(screen.queryByText(/Only the newest/)).toBeNull();
    rerender(<SkillDemandView data={skills} vacancies={{ ...vacancies, checked: 200, open_jobs: 350 }} params={params} />);
    expect(screen.getByRole("status").textContent).toBe("Only the newest 200 of 350 open jobs were checked.");
  });

  it("says candidate in the singular at N = 1 (QA-04)", () => {
    render(<SkillDemandView data={skills} vacancies={{ ...vacancies, n: 1 }} params={params} />);
    expect(screen.getByText(/^Open jobs with fewer than 1 candidate through/)).toBeTruthy();
  });

  it("shows empty states", () => {
    render(<SkillDemandView data={{ ...skills, items: [], total: 0 }} vacancies={{ ...vacancies, items: [], total: 0 }} params={params} />);
    expect(screen.getByText("No open job lists a Skills Master skill and no candidate holds one yet.")).toBeTruthy();
    expect(screen.getByText("Every open job checked has enough candidates.")).toBeTruthy();
  });

  it("marks the sort in use and pages by address", () => {
    render(<SkillDemandView data={{ ...skills, total: 60 }} vacancies={vacancies} params={params} />);
    expect(screen.getByRole("link", { name: "Most requested" }).getAttribute("aria-current")).toBe("page"); // QA-03: the styled state
    expect(screen.getByRole("link", { name: "Largest supply" }).getAttribute("aria-current")).toBeNull();
    expect(screen.getByRole("link", { name: "Next" }).getAttribute("href")).toBe("/recruiter/insights/skill-demand?offset=3");
  });
});

describe("hrc-034 portal analytics (I3)", () => {
  const data = {
    from: "2026-11-01", to: "2026-11-06", registrations: { total: 4, verified: 3 }, first_recorded: "2026-11-02",
    completion: [{ label: "0-24%", count: 2 }, { label: "100%", count: 1 }],
    funnel: [{ key: "job_view", label: "Viewed a job", events: 9, people: 5, dropped: null }, { key: "apply_start", label: "Started an application", events: 3, people: 2, dropped: 3 }],
  };

  it("shows registrations, drop-off and the completion bands", () => {
    render(<PortalAnalyticsView data={data} />);
    expect(screen.getByText("Registered").parentElement?.textContent).toContain("4");
    const started = screen.getByRole("row", { name: /Started an application/ });
    expect(within(started).getAllByRole("cell").map((c) => c.textContent)).toEqual(["2", "3", "3"]);
    expect(within(screen.getByRole("row", { name: /Viewed a job/ })).getAllByRole("cell")[1].textContent).toBe("—");
    expect(screen.getByRole("row", { name: /0-24%/ }).textContent).toContain("2");
  });

  it("says when a period is quiet", () => {
    render(<PortalAnalyticsView data={{ ...data, first_recorded: null, funnel: data.funnel.map((s) => ({ ...s, events: 0, people: 0 })) }} />);
    expect(screen.getByText("No job activity in this period.")).toBeTruthy();
    expect(screen.queryByRole("row", { name: /Viewed a job/ })).toBeNull();
  });
});

describe("hrc-034 data quality (I5)", () => {
  const data = { figures: [
    { key: "duplicates", label: "Duplicate queue", value: 2, definition: "Open pairs.", href: "/recruiter/candidates/duplicates" },
    { key: "incomplete_profiles", label: "Incomplete profiles", value: 0, definition: "Under 60%.", href: null },
  ] };

  it("offers a fix link only where the API gives one", () => {
    render(<DataQualityView data={data} drill={null} />);
    expect(screen.getByRole("link", { name: "Fix Duplicate queue" }).getAttribute("href")).toBe("/recruiter/candidates/duplicates");
    expect(screen.queryByRole("link", { name: "Fix Incomplete profiles" })).toBeNull();
    expect(screen.getByRole("link", { name: "Show what Incomplete profiles counts" }).getAttribute("href")).toBe("/recruiter/insights/data-quality?figure=incomplete_profiles");
  });

  it("lists a figure's records, joining a list and showing a blank as a dash", () => {
    const drill = {
      figure: { key: "jobs_missing_fields", label: "Jobs missing fields", definition: "Open jobs without…" },
      columns: [{ key: "code", label: "Requirement" }, { key: "title", label: "Title" }, { key: "missing", label: "Missing" }],
      items: [{ code: "REQ-1", title: null, missing: ["qualification", "vacancies"] }], total: 1, limit: 50, offset: 0,
    };
    render(<DataQualityView data={data} drill={drill} />);
    expect(screen.getByRole("heading", { name: "Jobs missing fields (1)" })).toBeTruthy();
    expect(screen.getAllByRole("cell").map((c) => c.textContent)).toEqual(["REQ-1", "—", "qualification, vacancies"]);
  });

  it("shows an empty drill-down", () => {
    render(<DataQualityView data={data} drill={{ figure: { key: "duplicates", label: "Duplicate queue", definition: "x" }, columns: [], items: [], total: 0, limit: 50, offset: 0 }} />);
    expect(screen.getByText("Nothing to correct here.")).toBeTruthy();
  });
});

describe("hrc-034 addresses", () => {
  it("ignores bad parameters instead of sending them", () => {
    expect(parseSkill({ sort: "name; drop", offset: "-1", n: "0", vacancy_offset: "x" })).toEqual({ sort: "demand", offset: 0, n: 5, vacancyOffset: 0 });
    expect(parsePeriod({ from: "soon", to: "2026-11-06" })).toEqual({ from: "", to: "2026-11-06" });
    expect(parseDrill({ figure: ["a", "b"], offset: "3" })).toEqual({ figure: "", offset: 3 });
  });

  it("builds the API and page addresses", () => {
    const s = parseSkill({ sort: "supply", n: "7", offset: "50" });
    expect(skillDemandUrl(s)).toBe("/api/v1/recruiter/recruitment-insights/skill-demand?sort=supply&offset=50&limit=50");
    expect(vacanciesUrl(s)).toBe("/api/v1/recruiter/recruitment-insights/skill-demand/vacancies?n=7&limit=50");
    expect(skillHref(s, { offset: 0 })).toBe("/recruiter/insights/skill-demand?sort=supply&n=7");
    expect(portalAnalyticsUrl({ from: "2026-11-01", to: "" })).toBe("/api/v1/recruiter/recruitment-insights/portal-analytics?from=2026-11-01");
    expect(drillUrl("a b", 0)).toBe("/api/v1/recruiter/recruitment-insights/data-quality/a%20b?limit=50");
    expect(drillHref("duplicates", 50)).toBe("/recruiter/insights/data-quality?figure=duplicates&offset=50");
  });
});
