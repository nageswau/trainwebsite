import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn() }), usePathname: () => "/x" }));
vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));

import { renderPanel } from "@/components/Student360Panels";
import Student360View from "@/components/Student360View";
import type { Student360, Tab360 } from "@/lib/student360";
import { TAB_KEYS, type TabKey } from "@/lib/student360Links";

afterEach(cleanup);

const EMPTY_DATA: Record<TabKey, Record<string, unknown>> = {
  overview: { achievements: [], portfolio_completion_percentage: 0 },
  personal_details: { id: "s1", full_name: "Asha Rao", school_name: "North School", student_code: null, grade_or_class: null, date_of_birth: null, assigned_teacher_name: null },
  academic_records: { grade_or_class: null, grade_history: [] },
  attendance: { activities: [], skill_sessions: [] },
  examination_results: { results: [] },
  career_guidance: { records: [] },
  psychometric_assessment: { assessments: [] },
  skills: { batches: null, portfolio_entries: [] },
  foreign_languages: { records: [] },
  english_testing: { records: [] },
  activities: { attended: null, upcoming: null, portfolio_entries: { project: [], internship: [], sport: [], leadership: [], volunteering: [], extracurricular: [] } },
  certificates: { entries: [] },
  documents: { psychometric_reports: [] },
  teacher_remarks: { remarks: [] },
  parent_communication: {},
  edusphere_programs: { programmes: [] },
};

const empty = (key: TabKey, not_tracked: string[] = []): Tab360 => ({ status: key === "personal_details" ? "has_data" : "empty", count: key === "personal_details" ? null : 0, not_tracked, data: EMPTY_DATA[key] });
const restricted: Tab360 = { status: "restricted", count: null, not_tracked: [], data: {} };

function view(overrides: Partial<Student360> = {}): Student360 {
  const tabs = Object.fromEntries(TAB_KEYS.map((k) => [k, empty(k)])) as Student360["tabs"];
  return { student: EMPTY_DATA.personal_details as Student360["student"], career_goal: null, can_edit_career_goal: false, tabs, ...overrides };
}

describe("Student360Panels", () => {
  it("renders a restricted tab as 'not available', never as 'no records'", () => {
    render(<>{renderPanel("attendance", restricted, view())}</>);
    expect(screen.getByRole("heading", { level: 2, name: "Attendance" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/not available for your role/i);
    expect(screen.queryByText(/no attendance/i)).not.toBeInTheDocument();
  });

  it("renders an empty state naming who records the data, plus the not-tracked note", () => {
    render(<>{renderPanel("attendance", empty("attendance", ["Daily and period attendance is not tracked yet (ENH-030)."]), view())}</>);
    expect(screen.getByRole("status")).toHaveTextContent(/no attendance recorded yet/i);
    expect(screen.getByText(/not tracked yet \(ENH-030\)/)).toBeInTheDocument();
  });

  it("links only safe document URLs and shows unsafe ones as text", () => {
    const tab: Tab360 = { status: "has_data", count: 2, not_tracked: [], data: { psychometric_reports: [
      { assessment_type: "Aptitude", report_url: "/local-files/uploads/r.pdf", created_at: "2026-09-01T00:00:00Z" },
      { assessment_type: "Interest", report_url: "javascript:alert(1)", created_at: "2026-09-01T00:00:00Z" },
    ] } };
    render(<>{renderPanel("documents", tab, view())}</>);
    expect(screen.getByRole("link", { name: /aptitude report/i })).toHaveAttribute("href", "/local-files/uploads/r.pdf");
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(screen.getByText("javascript:alert(1)")).toBeInTheDocument();
  });

  it("shows the goal read-only for viewers and the editor for the counsellor", () => {
    render(<>{renderPanel("overview", empty("overview"), view({ career_goal: "Technology" }))}</>);
    expect(screen.getByText("Technology")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /career goal/i })).not.toBeInTheDocument();
    cleanup();
    render(<>{renderPanel("overview", empty("overview"), view({ can_edit_career_goal: true }))}</>);
    expect(screen.getByRole("button", { name: /set career goal/i })).toBeInTheDocument();
  });

  it("personal details hides fields the viewer's role does not receive", () => {
    render(<>{renderPanel("personal_details", empty("personal_details"), view())}</>);
    expect(screen.getByText("Asha Rao")).toBeInTheDocument();
    expect(screen.queryByText(/date of birth/i)).not.toBeInTheDocument();
  });

  it("labels career record types and programme statuses in words", () => {
    const career: Tab360 = { status: "has_data", count: 1, not_tracked: [], data: { records: [{ id: "c1", record_type: "counselling_note", notes: "Met parents.", created_at: "2026-09-01T00:00:00Z" }] } };
    render(<>{renderPanel("career_guidance", career, view())}</>);
    expect(screen.getByText("Counselling note")).toBeInTheDocument();
    cleanup();
    const programmes: Tab360 = { status: "has_data", count: 1, not_tracked: [], data: { programmes: [{ key: "global_education", status: "linked", applications: [] }] } };
    render(<>{renderPanel("edusphere_programs", programmes, view())}</>);
    expect(screen.getByText("Global education")).toBeInTheDocument();
    expect(screen.getByText("Application linked")).toBeInTheDocument();
  });

  it("shows upcoming school activities, and names the attended table once (browser QA-06)", () => {
    const tab: Tab360 = { status: "has_data", count: 1, not_tracked: [], data: {
      attended: [{ activity_id: "a1", title: "Career Awareness Session", scheduled_at: "2026-09-08T10:00:00Z", present: true }],
      upcoming: [{ id: "u1", title: "Annual Sports Day", scheduled_at: "2026-10-03T10:00:00Z" }],
      portfolio_entries: { project: [], internship: [], sport: [], leadership: [], volunteering: [], extracurricular: [] },
    } };
    render(<>{renderPanel("activities", tab, view())}</>);
    expect(screen.getByRole("heading", { level: 3, name: "Upcoming school activities" })).toBeInTheDocument();
    expect(screen.getByText("Annual Sports Day")).toBeInTheDocument();
    expect(screen.getAllByText("School activities attended")).toHaveLength(1);  // heading only -- no duplicate hidden caption
    expect(screen.getByRole("table", { name: "School activities attended" })).toBeInTheDocument();  // still named, via the heading
  });

  it("shows upcoming activities even when nothing has been attended yet", () => {
    const tab: Tab360 = { status: "empty", count: 0, not_tracked: [], data: {
      attended: [], upcoming: [{ id: "u1", title: "Annual Sports Day", scheduled_at: "2026-10-03T10:00:00Z" }],
      portfolio_entries: { project: [], internship: [], sport: [], leadership: [], volunteering: [], extracurricular: [] },
    } };
    render(<>{renderPanel("activities", tab, view())}</>);
    expect(screen.getByText("Annual Sports Day")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/no activities recorded yet/i);
  });

  it.each(TAB_KEYS.map((k) => [k]))("renders %s for a brand-new student without throwing", (key) => {
    render(<>{renderPanel(key, empty(key), view())}</>);
    expect(screen.getByRole("heading", { level: 2 })).toBeInTheDocument();
  });
});

describe("Student360View", () => {
  it("renders the header, one h1, the 16 tabs and falls back to Overview for an unknown ?tab", () => {
    render(<Student360View data={view({ career_goal: "Medicine" })} initialTab="<script>" backHref="/back" backLabel="Back to student" />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Asha Rao");
    expect(screen.getAllByRole("tab")).toHaveLength(16);
    expect(screen.getByRole("tab", { name: /^overview/i })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("link", { name: /back to student/i })).toHaveAttribute("href", "/back");
    expect(within(screen.getByRole("tabpanel")).getByText("Medicine")).toBeInTheDocument();
  });

  it("opens the requested tab", () => {
    render(<Student360View data={view()} initialTab="certificates" backHref="/b" backLabel="Back" />);
    expect(screen.getByRole("tab", { name: /^certificates/i })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent(/no certificates recorded yet/i);
  });
});
