import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CandidateJobsBoard from "@/components/CandidateJobsBoard";
import { apiPath, dayText, experienceText, type JobCard, type JobsPage, pageHref, parseOffset, parseView } from "@/lib/candidateJobs";
import { CANDIDATE_NAV } from "@/lib/candidatePortal";
import { PORTAL_NAV } from "@/lib/navigation";

// hrc-027 (DEC-SCOPE-398): the three views, the card's explanation and the disclaimer (AC1-AC4), the no-skills prompt, and applying.
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: async () => body, headers: new Headers() });
let fetchMock: ReturnType<typeof vi.fn>;

const CARD: JobCard = {
  id: "j1", title: "Java Developer", company: "Acme", location: "Hyderabad", work_mode: "hybrid", employment_type: "full_time",
  required_skills: ["Java", "SQL"], preferred_skills: ["AWS"], experience_min_months: 24, experience_max_months: 60, closes_on: "2026-12-01",
  match: { score: 82, explanation: [{ key: "skills", label: "Skills", text: "Matches 2 of 2 required skills", matched: true }] },
  skills_text: "Matches 2 of 2 required skills", matches_skills: true, recommended: true, application: null, can_apply: true, blocked: [],
};
const PAGE: JobsPage = {
  view: "recommended", q: null, items: [CARD], total: 1, limit: 20, offset: 0, counts: { recommended: 1, matching: 2, all: 5 }, reason: null,
  disclaimer: "A match score is a guide … It is not a guarantee of suitability, an interview or an offer.", threshold: 50,
};
const BASE = "/it/careers/portal/jobs";

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  refresh.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("CandidateJobsBoard", () => {
  it("shows the three views with counts, the current one marked, and keeps the search in their links", () => {
    render(<CandidateJobsBoard data={{ ...PAGE, q: "java" }} base={BASE} profileHref="/p" />);
    const views = within(screen.getByRole("navigation", { name: "Job views" }));
    expect(views.getByRole("link", { name: "Recommended for you (1)" })).toHaveAttribute("aria-current", "page");
    expect(views.getByRole("link", { name: "Matching your skills (2)" })).toHaveAttribute("href", `${BASE}?view=matching&q=java`);
    expect(views.getByRole("link", { name: "All open jobs (5)" })).not.toHaveAttribute("aria-current");
  });

  it("shows a card's facts, its explanation and the not-a-guarantee disclaimer (AC3, AC4)", () => {
    render(<CandidateJobsBoard data={PAGE} base={BASE} profileHref="/p" />);
    expect(screen.getByRole("heading", { name: "Java Developer" })).toBeInTheDocument();
    expect(screen.getByText("82% match")).toBeInTheDocument();
    expect(screen.getByText("Hyderabad · Hybrid · Full time · 2 yrs – 5 yrs")).toBeInTheDocument();
    expect(screen.getByText("Skills: Matches 2 of 2 required skills")).toBeInTheDocument();
    expect(screen.getByText(/not a guarantee/)).toBeInTheDocument();
    expect(screen.getByText("1 Dec 2026")).toBeInTheDocument();
  });

  it("explains a non-matching job with its skills sentence", () => {
    const other = { ...CARD, id: "j2", match: null, recommended: false, matches_skills: false, skills_text: "Matches 0 of 1 required skills (missing Rust)" };
    render(<CandidateJobsBoard data={{ ...PAGE, view: "all", items: [other] }} base={BASE} profileHref="/p" />);
    expect(screen.getByText("Matches 0 of 1 required skills (missing Rust)")).toBeInTheDocument();
    expect(screen.queryByText(/% match/)).toBeNull();
  });

  it("prompts a profile without skills to add them, pointing at All open jobs", () => {
    render(<CandidateJobsBoard data={{ ...PAGE, items: [], total: 0, reason: "no_skills", counts: { recommended: 0, matching: 0, all: 3 } }} base={BASE} profileHref="/me" />);
    const prompt = screen.getByRole("status");
    expect(prompt).toHaveTextContent("Recommendations appear once your skills are on your profile.");
    expect(within(prompt).getByRole("link", { name: "Go to your profile" })).toHaveAttribute("href", "/me");
    expect(within(prompt).getByRole("link", { name: "All open jobs" })).toHaveAttribute("href", `${BASE}?view=all`);
  });

  it("shows an empty view's message and offers to clear a search", () => {
    render(<CandidateJobsBoard data={{ ...PAGE, view: "matching", q: "zzz", items: [], total: 0 }} base={BASE} profileHref="/p" />);
    expect(screen.getByText("No jobs match “zzz” in this view.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Clear" })).toHaveAttribute("href", `${BASE}?view=matching`);
  });

  it("says a page past the end is past the end, with a way back (QA27-01)", () => {
    render(<CandidateJobsBoard data={{ ...PAGE, view: "all", items: [], total: 5, offset: 9999 }} base={BASE} profileHref="/p" />);
    expect(screen.queryByText("There are no open jobs right now.")).toBeNull();
    expect(screen.getByText(/This page is past the end of the list/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the first page" })).toHaveAttribute("href", `${BASE}?view=all`);
  });

  it("does not repeat the location as the work mode (QA27-02)", () => {
    render(<CandidateJobsBoard data={{ ...PAGE, items: [{ ...CARD, location: "Remote", work_mode: "remote", employment_type: null, experience_min_months: null, experience_max_months: null }] }} base={BASE} profileHref="/p" />);
    expect(screen.getByText("Remote", { selector: "p" })).toBeInTheDocument();
  });

  it("pages forward and back", () => {
    render(<CandidateJobsBoard data={{ ...PAGE, view: "all", total: 45, offset: 20, items: Array.from({ length: 20 }, (_, i) => ({ ...CARD, id: `j${i}` })) }} base={BASE} profileHref="/p" />);
    expect(screen.getByText("Showing 21–40 of 45")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute("href", `${BASE}?view=all`);
    expect(screen.getByRole("link", { name: "Next" })).toHaveAttribute("href", `${BASE}?view=all&offset=40`);
  });
});

describe("Applying from a card", () => {
  it("sends one request, ignores a second click while sending, then shows the application", async () => {
    let resolve: (v: unknown) => void = () => {};
    fetchMock.mockReturnValue(new Promise((r) => { resolve = r; }));
    render(<CandidateJobsBoard data={PAGE} base={BASE} profileHref="/p" />);
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(screen.getByRole("button", { name: "Applying…" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Applying…" }));
    resolve(await json(201, { id: "a1", code: "JA-000123", status_label: "Received" }));
    expect(await screen.findByText("JA-000123")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/candidate/jobs/j1/apply");
    expect(refresh).toHaveBeenCalled();
  });

  it("shows the server's refusal", async () => {
    fetchMock.mockReturnValue(json(422, { detail: "Your profile does not meet this job's requirements: at least 2 yrs of experience." }));
    render(<CandidateJobsBoard data={PAGE} base={BASE} profileHref="/p" />);
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("at least 2 yrs of experience");
  });

  it("disables Apply with the reason when a requirement is not met, and shows an existing application", () => {
    const blocked = { ...CARD, can_apply: false, blocked: ["at least 2 yrs of experience"] };
    const applied = { ...CARD, id: "j9", title: "Applied job", can_apply: false, application: { code: "JA-000007", status_label: "Screening" } };
    render(<CandidateJobsBoard data={{ ...PAGE, items: [blocked, applied] }} base={BASE} profileHref="/p" />);
    const apply = screen.getByRole("button", { name: "Apply" });
    expect(apply).toBeDisabled();
    expect(apply).toHaveAccessibleDescription("This job needs at least 2 yrs of experience. Update your profile or ask your recruiter.");
    expect(screen.getByText("JA-000007")).toBeInTheDocument();
  });
});

describe("candidateJobs helpers and navigation", () => {
  it("parses the address and builds the API path", () => {
    expect(parseView("matching")).toBe("matching");
    expect(parseView("best")).toBe("recommended");
    expect(parseOffset("40")).toBe(40);
    expect(parseOffset("-1")).toBe(0);
    expect(parseOffset("x")).toBe(0);
    expect(apiPath("all", " java ", 20)).toBe("/api/v1/candidate/jobs?view=all&limit=20&offset=20&q=java");
    expect(pageHref(BASE, "all", "", 0)).toBe(`${BASE}?view=all`);
    expect(experienceText(6, null)).toBe("6 mos+");
    expect(experienceText(null, 12)).toBe("Up to 1 yr");
    expect(dayText("2027-01-09")).toBe("9 Jan 2027");
  });

  it("puts Jobs in both portals' menus", () => {
    expect(CANDIDATE_NAV.map((n) => n.href)).toContain("/it/careers/portal/jobs");
    expect(PORTAL_NAV["it/student"].find((n) => n.href === "/it/student/jobs")?.label).toBe("Jobs");
  });
});
