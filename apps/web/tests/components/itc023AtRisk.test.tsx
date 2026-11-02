import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ItAtRiskList from "@/components/ItAtRiskList";
import ItRiskThresholdsPanel from "@/components/ItRiskThresholdsPanel";
import { riskReasonLabels, thresholdSummary, type RiskThreshold } from "@/lib/itAtRisk";
import { PORTAL_NAV } from "@/lib/navigation";

// itc-023 (DEC-SCOPE-352): at-risk thresholds per programme (the IT Admin) and the scoped at-risk list.
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));

const THRESHOLD: RiskThreshold = {
  program_id: "p1", program: "Full Stack Java", active: true, min_attendance_percent: null, min_assessment_percent: null,
  max_consecutive_absences: null, min_sessions: 3, monitored: false, updated_at: null,
};
const FLAG = {
  id: "f1", student: { id: "s1", full_name: "Asha Rao", student_code: "ITS-001" }, program: "Full Stack Java", batch: { id: "b1", name: "FSJ-Nov" },
  reasons: ["attendance", "absences"], attendance_percent: "68.00", assessment_percent: null, consecutive_absences: 3,
  raised_at: "2026-11-02T01:30:00Z", cleared_at: null, clear_reason: null, profile_url: "/it/counselor/students/s1/profile",
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("at-risk labels", () => {
  it("names each reason with its figure", () => {
    expect(riskReasonLabels({ reasons: ["attendance", "assessment", "absences"], attendance_percent: "68.00", assessment_percent: 45, consecutive_absences: 3 }))
      .toEqual(["Attendance 68%", "Assessment average 45%", "3 absences in a row"]);
  });

  it("summarises thresholds and says when a programme is not monitored", () => {
    expect(thresholdSummary(THRESHOLD)).toBe("Not monitored");
    expect(thresholdSummary({ ...THRESHOLD, min_attendance_percent: 75, max_consecutive_absences: 3 })).toBe("Attendance below 75% (after 3 sessions); 3 absences in a row");
  });

  it("adds At Risk to the IT Admin's nav and Notifications to the trainer's", () => {
    expect(PORTAL_NAV["it/admin"].some((item) => item.href === "/it/admin/at-risk" && item.label === "At Risk")).toBe(true);
    expect(PORTAL_NAV["it/trainer"].some((item) => item.href === "/it/trainer/notifications")).toBe(true);
  });
});

describe("ItAtRiskList", () => {
  it("lists flagged students with a link to their record and the reasons", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json([FLAG])));
    render(<ItAtRiskList />);
    const link = await screen.findByRole("link", { name: "Asha Rao" });
    expect(link.getAttribute("href")).toBe("/it/counselor/students/s1/profile");
    expect(screen.getByText("Attendance 68%")).toBeTruthy();
    expect(screen.getByText("3 absences in a row")).toBeTruthy();
  });

  it("shows the empty text and an error state", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json([])));
    render(<ItAtRiskList emptyText="None of your students is at risk right now." />);
    expect(await screen.findByText("None of your students is at risk right now.")).toBeTruthy();
    cleanup();
    vi.stubGlobal("fetch", vi.fn(() => json({ detail: "x" }, 500)));
    render(<ItAtRiskList />);
    expect((await screen.findByRole("alert")).textContent).toContain("Unable to load");
  });
});

describe("ItRiskThresholdsPanel", () => {
  it("edits one programme's thresholds with a PUT and shows the saved summary", async () => {
    const saved = { ...THRESHOLD, min_attendance_percent: 75, monitored: true };
    const fetchMock = vi.fn((url: string, init?: RequestInit) => (init?.method === "PUT" ? json(saved) : json([THRESHOLD])));
    vi.stubGlobal("fetch", fetchMock);
    render(<ItRiskThresholdsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit thresholds for Full Stack Java" }));
    fireEvent.change(screen.getByLabelText("Minimum attendance %"), { target: { value: "75" } });
    fireEvent.click(screen.getByRole("button", { name: "Save thresholds" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Thresholds for Full Stack Java saved"));
    const [url, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "PUT")!;
    expect(url).toBe("/api/v1/admin/it/risk-thresholds/p1");
    expect(JSON.parse(String(init!.body))).toEqual({ min_attendance_percent: 75, min_assessment_percent: null, max_consecutive_absences: null, min_sessions: 3 });
    const row = screen.getByRole("cell", { name: /Attendance below 75%/ });
    expect(within(row).getByText(/after 3 sessions/)).toBeTruthy();
  });

  it("keeps the form open and shows the API's message on a 422", async () => {
    vi.stubGlobal("fetch", vi.fn((_url: string, init?: RequestInit) => (init?.method === "PUT" ? json({ detail: "Input should be less than or equal to 100" }, 422) : json([THRESHOLD]))));
    render(<ItRiskThresholdsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit thresholds for Full Stack Java" }));
    fireEvent.click(screen.getByRole("button", { name: "Save thresholds" }));
    expect((await screen.findByRole("alert")).textContent).toContain("less than or equal to 100");
    expect(screen.getByRole("button", { name: "Save thresholds" })).toBeTruthy();
  });
});
