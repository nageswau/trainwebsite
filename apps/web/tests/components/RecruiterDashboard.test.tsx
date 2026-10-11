import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterDashboardTiles from "@/components/RecruiterDashboardTiles";
import RecruiterQuickActions from "@/components/RecruiterQuickActions";
import RecruiterRecruiterFilter from "@/components/RecruiterRecruiterFilter";
import RecruiterSkillSearch from "@/components/RecruiterSkillSearch";
import { RECRUITER_MANAGER_NAV } from "@/lib/navigation";
import { TILES, dashboardUrl, skillSearchHref, tileHref, type RecruiterDashboard } from "@/lib/recruiterDashboard";

const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: nav.push, replace: vi.fn(), refresh: vi.fn() }) }));

afterEach(() => {
  cleanup();
  nav.push.mockReset();
});

const tiles = Object.fromEntries(TILES.map((t, i) => [t.key, i])) as unknown as RecruiterDashboard["tiles"];
const dashboard = (over: Partial<RecruiterDashboard> = {}): RecruiterDashboard => ({
  day: "2026-10-11", period: { from: "2026-10-01", to: "2026-10-11" }, recruiter: null, tiles: { ...tiles, requirements_expired: 2 }, ...over,
});

describe("RecruiterDashboardTiles (rec-032 §1, AC1/AC3)", () => {
  it("shows the fourteen tiles in the source's order, each a link to its list", () => {
    render(<RecruiterDashboardTiles dashboard={dashboard()} />);
    const items = within(screen.getByRole("list", { name: "Your figures" })).getAllByRole("listitem");
    expect(items.map((t) => t.querySelector("span")!.textContent)).toEqual([
      "New Recruiter Leads", "Calls/Contacts Pending", "Hot Recruiters", "Meetings Scheduled", "Active Companies", "New Job Requirements",
      "Candidates Sourced", "Profiles Shared", "Interviews Scheduled", "Candidates Selected", "Candidates Joined", "Rejected Candidates",
      "Follow-ups Due", "Requirements About to Expire"]);
    expect(within(items[0]).getByText("0")).toBeInTheDocument(); // zeros, never "no data"
    expect(screen.getByRole("link", { name: /Interviews Scheduled/ })).toHaveAttribute("href", "/recruiter/interviews?view=upcoming");
    expect(screen.getByRole("link", { name: /Follow-ups Due/ })).toHaveAttribute("href", "/recruiter/follow-ups?due=today");
    expect(screen.getByRole("link", { name: /Hot Recruiters/ })).toHaveAttribute("href", "/recruiter/companies?priority=hot");
    expect(within(items[13]).getByText("2 past the deadline")).toBeInTheDocument();
  });

  it("carries a filtered recruiter into the Companies and Requirements lists only", () => {
    render(<RecruiterDashboardTiles dashboard={dashboard({ recruiter: { id: "r-1", full_name: "Asha" } })} />);
    expect(screen.getByRole("link", { name: /Hot Recruiters/ })).toHaveAttribute("href", "/recruiter/companies?priority=hot&assigned=r-1");
    expect(screen.getByRole("link", { name: /About to Expire/ })).toHaveAttribute("href", "/recruiter/requirements?deadline=expiring&assigned=r-1");
    expect(screen.getByRole("link", { name: /Meetings Scheduled/ })).toHaveAttribute("href", "/recruiter/meetings?view=upcoming");
  });

  it("says so when the figures could not be loaded", () => {
    render(<RecruiterDashboardTiles dashboard={null} error="That recruiter is not in your team." />);
    expect(screen.getByRole("status")).toHaveTextContent("That recruiter is not in your team.");
    expect(screen.queryByRole("list")).not.toBeInTheDocument();
  });
});

describe("tile links and URLs", () => {
  it("adds `assigned` beside an existing query, or as the only one", () => {
    const active = TILES.find((t) => t.key === "active_companies")!;
    expect(tileHref(active, "r-2")).toBe("/recruiter/companies?assigned=r-2");
    expect(tileHref(active, null)).toBe("/recruiter/companies");
    expect(dashboardUrl("r 2")).toBe("/api/v1/recruiter/dashboard?recruiter=r%202");
  });
});

describe("RecruiterQuickActions (rec-032 §1)", () => {
  it("gives a recruiter all six actions", () => {
    render(<RecruiterQuickActions role="placement_team" />);
    const links = within(screen.getByRole("navigation", { name: "Quick actions" })).getAllByRole("link");
    expect(links.map((l) => [l.textContent, l.getAttribute("href")])).toEqual([
      ["+ Add Recruiter", "/recruiter/companies/new?with=contact"], ["+ Add Company", "/recruiter/companies/new"],
      ["+ Add Job Requirement", "/recruiter/requirements/new"], ["+ Add Candidate", "/recruiter/candidates/new"],
      ["+ Schedule Meeting", "/recruiter/companies"], ["+ Schedule Interview", "/recruiter/requirements"],
    ]);
  });

  it("is one navigation landmark named by its heading (QA32-01)", () => {
    render(<RecruiterQuickActions role="placement_team" />);
    expect(screen.getByRole("navigation")).toHaveAccessibleName("Quick actions");
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("leaves scheduling out for a manager, who only reads meetings and interviews", () => {
    render(<RecruiterQuickActions role="placement_manager" />);
    expect(screen.getAllByRole("link").map((l) => l.textContent)).toEqual(["+ Add Recruiter", "+ Add Company", "+ Add Job Requirement", "+ Add Candidate"]);
  });
});

describe("RecruiterSkillSearch (S2-§9)", () => {
  it("builds the Find Candidates URL from comma-separated skills", () => {
    expect(skillSearchHref(" Java ,  spring boot, java ,")).toBe("/recruiter/find-candidates?all=Java&all=spring+boot");
    expect(skillSearchHref(" , ")).toBeNull();
  });

  it("is one search landmark named by its heading (QA32-01)", () => {
    render(<RecruiterSkillSearch />);
    expect(screen.getAllByRole("search")).toHaveLength(1);
    expect(screen.getByRole("search")).toHaveAccessibleName("Find Candidates by Skill");
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("opens Find Candidates with the skills, and asks for one when the box is empty", () => {
    render(<RecruiterSkillSearch />);
    fireEvent.click(screen.getByRole("button", { name: "Find candidates" }));
    expect(nav.push).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Type at least one skill.");
    expect(screen.getByLabelText("Skill")).toHaveAttribute("aria-invalid", "true");
    fireEvent.change(screen.getByLabelText("Skill"), { target: { value: "Java, SQL" } });
    fireEvent.click(screen.getByRole("button", { name: "Find candidates" }));
    expect(nav.push).toHaveBeenCalledWith("/recruiter/find-candidates?all=Java&all=SQL");
  });
});

describe("RecruiterRecruiterFilter (DB3)", () => {
  it("is a GET form on the dashboard listing the team, with the current choice selected", () => {
    const { container } = render(<RecruiterRecruiterFilter team={[{ id: "a", full_name: "Asha" }, { id: "b", full_name: "Ravi" }]} selected="b" />);
    const form = container.querySelector("form")!;
    expect(form).toHaveAttribute("action", "/recruiter/dashboard");
    expect(form).toHaveAttribute("method", "get");
    const select = screen.getByRole("combobox", { name: "Recruiter" });
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Whole team", "Asha", "Ravi"]);
    expect(select).toHaveValue("b");
  });
});

describe("manager navigation (rec-032)", () => {
  it("gives the manager a Dashboard entry", () => {
    expect(RECRUITER_MANAGER_NAV).toContainEqual({ label: "Dashboard", href: "/recruiter/dashboard" });
  });
});
